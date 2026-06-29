#!/usr/bin/env python3
"""
PR 监控 — CI 失败自动修复触发器

轮询 watchlist 中的仓库，检测带有 ci_failed label 的 PR，
根据 fix/<pr-number> PR 的存在状态决定动作：

  fix PR 不存在                    → dispatch ci-log-analysis（首次修复）
  fix PR open + ci_successful      → 通知原始 PR fix 已通过 CI（一次性，加 fix_notified 标记）
  fix PR open + ci_processing      → CI 运行中，跳过
  fix PR open + ci_failed          → 检查 commit 次数，未超限则 dispatch，超限则关闭 fix PR
  fix PR open + 无状态 label        → CI 尚未开始，跳过
  fix PR closed                    → 重新 dispatch
  fix PR merged                    → 已合并，跳过
"""

import os
import re
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from scripts.lib.ci_api import detect_platform, normalize_repo, get_api
from scripts.lib import ci_data

WATCHLIST_FILE = os.path.join(PROJECT_ROOT, 'config', 'watchlist.json')
MAX_RETRIES = 6


_PRERELEASE_RE = re.compile(
    r'[-.](?:alpha|beta|rc\d*|preview|dev|snapshot|nightly)(?![a-zA-Z])',
    re.IGNORECASE,
)


def _is_prerelease(title: str) -> bool:
    """判断 PR 标题是否包含预发布版本标记（alpha/beta/rc 等），是则跳过自动修复。"""
    return bool(_PRERELEASE_RE.search(title))


# create-image workflow 产出的新镜像 PR 标题形如：
#   'Feat: add <pkg> <version> docker image on openEuler <VER>'
# head 分支形如 'add-<pkg>'。这类 PR 的分支在我们自己的 fork 上，
# 应就地追加修复 commit（而非另开 fix PR）。
_CREATE_IMAGE_TITLE_RE = re.compile(
    r'^\s*feat:\s*add\b.*\bdocker image on openeuler\b', re.IGNORECASE,
)


def _is_create_image_pr(pr: Dict) -> bool:
    """识别 create-image workflow 产出的新镜像 PR（按标题或 head 分支前缀）。"""
    if _CREATE_IMAGE_TITLE_RE.search(pr.get('title', '')):
        return True
    head_ref = (pr.get('head') or {}).get('ref', '')
    return head_ref.startswith('add-')


def log(msg: str):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)


def dispatch_ci_fix(repo: str, platform: str, pr: Dict, pr_base_branch: str,
                    token: str, target_repo: str, fix_pr_number: int = 0,
                    fix_branch: Optional[str] = None) -> bool:
    # 默认在独立的 fix/<n> 分支上修复并另开 fix PR；就地修复（create-image PR）时
    # 由调用方传入原 PR 的 head 分支，使修复 commit 直接追加到原 PR。
    if fix_branch is None:
        fix_branch = f"fix/{pr['number']}"
    payload = {
        'event_type': 'run-ci-fix-phase',
        'client_payload': {
            'phase': 'ci-log-analysis',
            'source_repo': repo,
            'source_platform': platform,
            'pr_number': pr['number'],
            'pr_title': pr.get('title', ''),
            'head_sha': pr['head']['sha'],
            'fix_branch': fix_branch,
            'pr_base_branch': pr_base_branch,
            # 重试时传入 fix PR 编号，让 ci-log-analysis 从 fix PR 评论中查找最新 build URL
            'fix_pr_number': fix_pr_number,
        }
    }
    url = f"https://api.github.com/repos/{target_repo}/dispatches"
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 204:
            log(f"  ✅ Dispatched ci-log-analysis for PR #{pr['number']}")
            return True
        log(f"  ❌ Dispatch failed HTTP {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        log(f"  ❌ Dispatch error: {e}")
        return False


def _parse_time(ts: str) -> Optional[datetime]:
    """解析 ISO 8601 时间字符串为 UTC datetime，解析失败返回 None。"""
    if not ts:
        return None
    try:
        # 兼容 '2026-06-05T10:00:00+00:00' 和 '2026-06-05T10:00:00Z'
        ts = ts.replace('Z', '+00:00')
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _within_lookback(pr: Dict, cutoff: datetime) -> bool:
    """判断 PR 是否在 lookback 窗口内（以 updated_at 为准）。"""
    updated_at = _parse_time(pr.get('updated_at', ''))
    if updated_at is None:
        return True  # 解析失败时默认处理
    return updated_at >= cutoff


def process_create_image_pr(api, repo: str, platform: str, pr: Dict, pr_base: str,
                            write_token: str, dispatch_token: str, target_repo: str) -> bool:
    """就地修复 create-image PR：往该 PR 自己的 head 分支追加修复 commit，
    不另开 fix PR。超过最大重试次数时评论提醒人工介入（保留 PR，不关闭，
    因为它是关联 issue 的正主）。返回是否本轮发起了一次 dispatch。"""
    pr_number = pr['number']
    head = pr.get('head') or {}
    head_ref = head.get('ref', '')
    head_sha = head.get('sha', '')
    labels = [l.get('name') for l in (pr.get('labels') or [])]

    log(f"    → create-image PR, in-place fix on branch '{head_ref}'")

    if 'ci_processing' in labels:
        log("    → CI running (ci_processing), skipping")
        return False
    if 'ci_successful' in labels:
        log("    → CI passed, nothing to fix")
        return False

    state = ci_data.read_inplace_state(pr_number)
    attempts = state.get('attempts', 0)

    # 已对当前 head 发起过修复 → 等待 CI/修复结果，避免重复 dispatch
    if head_sha and state.get('last_sha') == head_sha:
        log(f"    → already dispatched fix for sha {head_sha[:8]}, awaiting result, skipping")
        return False

    if attempts >= MAX_RETRIES:
        if not ci_data.is_giveup_notified(pr_number):
            log(f"    → max in-place retries ({MAX_RETRIES}) reached, notifying human (PR kept open)")
            try:
                api.add_pr_comment(
                    repo, pr_number,
                    f"🤖 AI 已就地尝试修复 {MAX_RETRIES} 次仍未通过 CI，已停止自动修复，"
                    f"请人工介入处理本 PR。",
                    write_token,
                )
                ci_data.mark_giveup_notified(pr_number)
            except Exception as e:
                log(f"    ⚠️ notify failed: {e}")
        else:
            log("    → already notified human, skipping")
        return False

    log(f"    → dispatching in-place fix attempt #{attempts + 1}")
    inplace_pr = {'number': pr_number, 'title': pr.get('title', ''), 'head': head}
    ok = dispatch_ci_fix(repo, platform, inplace_pr, pr_base, dispatch_token, target_repo,
                         fix_branch=head_ref)
    if ok:
        try:
            ci_data.record_inplace_attempt(pr_number, head_sha)
        except Exception as e:
            log(f"    ⚠️ record attempt failed (non-fatal): {e}")
    return ok


def process_all():
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)

    settings = watchlist.get('settings', {})
    poll_interval = settings.get('poll_interval_minutes', 5)
    max_events = settings.get('max_events_per_run', 50)
    lookback_minutes = settings.get('lookback_minutes', 0)

    lookback_cutoff = None
    if lookback_minutes > 0:
        lookback_cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

    watch_token = os.getenv('DISPATCH_TOKEN', '')
    dispatch_token = watch_token
    target_repo = os.getenv('GITHUB_REPOSITORY', 'sunshuang1866/docker-images-workflow')

    if not watch_token:
        log("❌ DISPATCH_TOKEN not set")
        sys.exit(1)

    log("🔍 Starting PR monitoring cycle")
    log(f"   target_repo:  {target_repo}")
    log(f"   poll_interval: {poll_interval}m  max_events: {max_events}  lookback: {lookback_minutes}m")

    total_dispatched = 0

    for repo_config in watchlist.get('watched_repos', []):
        if not repo_config.get('enabled', True):
            continue

        raw_repo = repo_config['repo']
        platform = detect_platform(raw_repo)
        repo = normalize_repo(raw_repo, platform)
        api = get_api(platform)
        ci_failed_label = (repo_config.get('trigger_labels') or ['ci_failed'])[0]

        # GitCode: 读操作用 GITCODE_TOKEN，写操作（评论/标签）用 GITCODE_TOKEN
        token = watch_token
        write_token = watch_token
        if platform == 'gitcode':
            token = os.getenv('GITCODE_TOKEN') or watch_token
            write_token = os.getenv('GITCODE_TOKEN') or token

        log(f"\n{'='*60}")
        log(f"📦 {repo} [{platform}] label={ci_failed_label}")

        try:
            prs = api.fetch_prs_with_label(repo, ci_failed_label, token)
        except Exception as e:
            log(f"  ❌ Failed to fetch PRs: {e}")
            continue

        log(f"  Found {len(prs)} PR(s) with '{ci_failed_label}' label")

        for pr in prs:
            if total_dispatched >= max_events:
                log(f"\n  ⚠️ max_events_per_run ({max_events}) reached, stopping")
                break

            pr_number = pr['number']
            pr_base = pr['base']['ref']
            fix_branch = f'fix/{pr_number}'

            pr_title = pr.get('title', '')
            log(f"\n  🔎 PR #{pr_number}: {pr_title[:60]}")

            if _is_prerelease(pr_title):
                log(f"    → Skipping: pre-release version in title (alpha/beta/rc/etc.)")
                continue

            if pr_title.lstrip().lower().startswith('fix:'):
                log(f"    → Skipping: fix PR (title starts with 'fix:'), handles its own CI retries")
                continue

            # create-image PR：head 分支在我们自己的 fork 上，就地修复而非另开 fix PR
            if _is_create_image_pr(pr):
                if process_create_image_pr(api, repo, platform, pr, pr_base,
                                           write_token, dispatch_token, target_repo):
                    total_dispatched += 1
                continue

            fix_pr = api.find_any_pr_by_head_branch(repo, fix_branch, token)
            # fallback: branch search may miss fork-originated PRs on some platforms
            if fix_pr is None:
                fix_pr = api.find_open_ci_successful_fix_pr(repo, pr_number, token)

            if fix_pr is None or fix_pr['state'] == 'closed':
                # lookback 过滤：首次 dispatch 时检查 PR 是否在时间窗口内
                if lookback_cutoff and not _within_lookback(pr, lookback_cutoff):
                    log(f"    → Skipping: updated_at outside lookback window ({lookback_minutes}m)")
                    continue
                if fix_pr and fix_pr['state'] == 'closed':
                    log(f"    → Fix PR #{fix_pr['number']} was closed, re-dispatching")
                else:
                    log(f"    → No fix PR, dispatching first attempt")
                if dispatch_ci_fix(repo, platform, pr, pr_base, dispatch_token, target_repo):
                    total_dispatched += 1

            elif fix_pr['state'] == 'open':
                fix_labels = [l['name'] for l in fix_pr.get('labels', [])]
                fix_pr_url = fix_pr.get('html_url') or f"https://gitcode.com/{repo}/pull/{fix_pr['number']}"

                if 'ci_successful' in fix_labels:
                    if not ci_data.is_fix_notified(pr_number):
                        log(f"    → Fix PR #{fix_pr['number']} passed CI! Notifying original PR #{pr_number}")
                        try:
                            api.add_pr_comment(
                                repo, pr_number,
                                f"🎉 AI 修复 PR [#{fix_pr['number']}]({fix_pr_url}) 已通过 CI，请 review 并合并。",
                                write_token,
                            )
                            ci_data.mark_fix_notified(pr_number)
                        except Exception as e:
                            log(f"    ⚠️  Notification failed: {e}")
                        else:
                            # 通知成功后将经过 CI 验证的修复模式写入知识库
                            try:
                                analysis = ci_data.read_file(ci_data.analysis_path(pr_number))
                                fix_summary = ci_data.read_file(ci_data.fix_summary_path(pr_number))
                                if analysis and fix_summary:
                                    ci_data.append_pattern(pr_number, repo, analysis, fix_summary)
                                    log(f"    ✅ knowledge base updated with patterns from PR #{pr_number}")
                                else:
                                    log(f"    ⚠️  knowledge base skipped: ci-fix-log data not found for PR #{pr_number}")
                            except Exception as e:
                                log(f"    ⚠️  knowledge base update failed (non-fatal): {e}")
                    else:
                        log(f"    → Fix PR #{fix_pr['number']} CI passed, already notified, skipping")

                elif 'ci_processing' in fix_labels:
                    log(f"    → Fix PR #{fix_pr['number']} CI running (ci_processing), skipping")

                elif ci_failed_label in fix_labels:
                    count = api.get_branch_commit_count(repo, fix_branch, pr_base, token)
                    log(f"    → Fix PR #{fix_pr['number']} ci_failed, commits={count}")
                    if count >= MAX_RETRIES:
                        log(f"    → Max retries ({MAX_RETRIES}) reached, closing fix PR")
                        try:
                            api.close_pull_request(repo, fix_pr['number'], write_token)
                            api.add_pr_comment(
                                repo, fix_pr['number'],
                                f"🤖 AI 已尝试修复 {MAX_RETRIES} 次，仍未通过 CI，自动关闭。请人工处理。",
                                write_token,
                            )
                        except Exception as e:
                            log(f"    ⚠️  Close/comment failed: {e}")
                    else:
                        log(f"    → Dispatching retry (attempt #{count + 1})")
                        retry_pr = {
                            'number': pr_number,
                            'title': pr_title,
                            'head': fix_pr['head'],
                        }
                        if dispatch_ci_fix(repo, platform, retry_pr, pr_base, dispatch_token, target_repo,
                                           fix_pr_number=fix_pr['number']):
                            total_dispatched += 1

                else:
                    log(f"    → Fix PR #{fix_pr['number']} CI pending (no status label), skipping")

            else:
                log(f"    → Fix PR #{fix_pr['number']} state={fix_pr['state']}, skipping")

    log(f"\n✅ PR monitoring cycle complete. dispatched={total_dispatched}/{max_events}")


if __name__ == '__main__':
    process_all()
