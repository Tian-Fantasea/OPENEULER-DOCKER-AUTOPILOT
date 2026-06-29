"""
Tests for scripts/watch/process_pr_events.py

覆盖范围：
- _is_prerelease: PR 标题预发布版本检测
- fix PR skip logic: title starts with 'fix:'
"""

import pytest

from scripts.watch.process_pr_events import _is_prerelease, _is_create_image_pr


class TestIsPrerelease:

    # ── 应该跳过（预发布版本）─────────────────────────────────────────────────

    @pytest.mark.parametrize("title", [
        '【自动升级】etcd容器镜像升级至3.8.0-alpha.0版本.',
        '【自动升级】etcd容器镜像升级至3.8.0-alpha版本.',
        '【自动升级】kafka升级至3.5.0-beta.1版本.',
        '【自动升级】kafka升级至3.5.0-beta版本.',
        '【自动升级】someapp升级至1.0.0-rc1版本.',
        '【自动升级】someapp升级至2.0.0-rc版本.',
        '【自动升级】nginx升级至1.0.0-preview版本.',
        '【自动升级】tool升级至2.0.0-dev版本.',
        '【自动升级】app升级至1.0-snapshot版本.',
        '【自动升级】app升级至1.0.0-nightly版本.',
        # 大写
        '【自动升级】pkg升级至1.0.0-Alpha.1版本.',
        '【自动升级】pkg升级至1.0.0-BETA版本.',
        '【自动升级】pkg升级至1.0.0-RC2版本.',
        # 点分隔
        '【自动升级】pkg升级至1.0.0.alpha.1版本.',
        '【自动升级】pkg升级至1.0.0.beta版本.',
    ])
    def test_prerelease_titles_are_skipped(self, title):
        assert _is_prerelease(title) is True, f"Expected prerelease: {title}"

    # ── 应该处理（正式版本）──────────────────────────────────────────────────

    @pytest.mark.parametrize("title", [
        '【自动升级】etcd容器镜像升级至3.6.11版本.',
        '【自动升级】nginx容器镜像升级至1.25.3版本.',
        '【自动升级】openssl升级至3.1.0版本.',
        '【自动升级】golang升级至1.23.9版本.',
        '【自动升级】python升级至3.12.0版本.',
        # 较短版本号
        '【自动升级】busybox升级至1.36版本.',
        # 四段版本号
        '【自动升级】somelib升级至1.2.3.4版本.',
    ])
    def test_stable_titles_are_processed(self, title):
        assert _is_prerelease(title) is False, f"Expected stable: {title}"

    # ── 边界：软件名中含预发布关键词时不应误判 ────────────────────────────────

    @pytest.mark.parametrize("title", [
        # 软件名以 dev/preview 开头或包含这些词
        '【自动升级】developer-tool升级至1.0.0版本.',
        '【自动升级】preview-app升级至2.0.0版本.',
        '【自动升级】alphabetical升级至1.0.0版本.',
        '【自动升级】betamax升级至3.0.0版本.',
        # rc 作为普通词缀（非版本标记）
        '【自动升级】rclone升级至1.65.0版本.',
    ])
    def test_software_name_keywords_not_flagged(self, title):
        assert _is_prerelease(title) is False, f"Should not flag as prerelease: {title}"

    # ── 非自动升级 PR 标题 ───────────────────────────────────────────────────

    def test_plain_title_without_version(self):
        assert _is_prerelease('fix some unrelated issue') is False

    def test_empty_title(self):
        assert _is_prerelease('') is False

    def test_title_with_alpha_in_description_not_version(self):
        # alpha 出现在描述中但不是版本标记（没有 -. 前缀）
        assert _is_prerelease('升级 alpha 通道的软件包') is False


# ── fix PR skip（标题以 fix: 开头）────────────────────────────────────────────

def _is_fix_pr_title(title: str) -> bool:
    """复用 process_pr_events.py 中相同的判断逻辑。"""
    return title.lstrip().lower().startswith('fix:')


class TestIsFixPrTitle:
    @pytest.mark.parametrize("title", [
        'fix: etcd 3.6.11 (fix #2534)',
        'fix: libyuv 1948 (fix #2546)',
        'Fix: something capitalized',
        '  fix: leading spaces',
        'FIX: uppercase',
    ])
    def test_fix_titles_are_skipped(self, title):
        assert _is_fix_pr_title(title) is True, f"Expected fix PR: {title}"

    @pytest.mark.parametrize("title", [
        '【自动升级】etcd容器镜像升级至3.6.11版本.',
        'chore: update dependencies',
        'feat: add new feature',
        'fixup some thing',       # 以 fixup 开头，不是 fix:
        'prefix fix: something',  # fix: 不在开头
        '',
    ])
    def test_non_fix_titles_are_not_skipped(self, title):
        assert _is_fix_pr_title(title) is False, f"Should not skip: {title}"


# ── create-image PR 识别（就地修复路由）────────────────────────────────────────

class TestIsCreateImagePr:

    # ── 按标题识别（create-image workflow 生成的确定性标题）──────────────────────

    @pytest.mark.parametrize("title", [
        'Feat: add fluid 1.2.3 docker image on openEuler 24.03-LTS-SP3',
        'feat: add kafka 3.5.0 docker image on openeuler 24.03-lts-sp3',  # 全小写
        'Feat: add some-tool 0.1.0 docker image on openEuler 22.03-LTS',
    ])
    def test_create_image_titles_detected(self, title):
        assert _is_create_image_pr({'title': title}) is True, f"Expected create-image: {title}"

    # ── 按 head 分支前缀识别（标题格式漂移时的兜底）──────────────────────────────

    def test_detected_by_add_branch_prefix(self):
        pr = {'title': '随便一个标题', 'head': {'ref': 'add-fluid'}}
        assert _is_create_image_pr(pr) is True

    def test_title_match_without_head(self):
        pr = {'title': 'Feat: add fluid 1.2.3 docker image on openEuler 24.03'}
        assert _is_create_image_pr(pr) is True

    # ── 不应误判为 create-image PR ───────────────────────────────────────────────

    @pytest.mark.parametrize("pr", [
        {'title': '【自动升级】etcd容器镜像升级至3.6.11版本.', 'head': {'ref': 'etcd-3.6.11'}},
        {'title': 'fix: etcd 3.6.11 (fix #2534)', 'head': {'ref': 'fix/2534'}},
        {'title': 'feat: add new feature', 'head': {'ref': 'feature/x'}},  # 无 'docker image on openEuler'
        {'title': 'chore: update deps', 'head': {'ref': 'chore-1'}},
        {'title': '', 'head': {'ref': ''}},
        {'title': ''},  # 无 head 字段
    ])
    def test_non_create_image_prs_not_detected(self, pr):
        assert _is_create_image_pr(pr) is False, f"Should not detect: {pr}"


# ── 就地修复决策（process_create_image_pr）────────────────────────────────────

class _FakeApi:
    def __init__(self):
        self.comments = []

    def add_pr_comment(self, repo, pr_number, body, token):
        self.comments.append((pr_number, body))


@pytest.fixture
def inplace_env(monkeypatch):
    """打桩 ci_data 与 dispatch_ci_fix，返回可断言的内存状态。"""
    from scripts.watch import process_pr_events as mod

    state = {
        'inplace': {},          # pr_number -> {'attempts', 'last_sha'}
        'giveup_notified': set(),
        'dispatched': [],       # (pr_number, fix_branch)
        'recorded': [],         # (pr_number, head_sha)
    }

    monkeypatch.setattr(mod.ci_data, 'read_inplace_state',
                        lambda n: dict(state['inplace'].get(n, {'attempts': 0, 'last_sha': ''})))
    monkeypatch.setattr(mod.ci_data, 'is_giveup_notified',
                        lambda n: n in state['giveup_notified'])
    monkeypatch.setattr(mod.ci_data, 'mark_giveup_notified',
                        lambda n: state['giveup_notified'].add(n))

    def _record(n, sha):
        cur = state['inplace'].get(n, {'attempts': 0, 'last_sha': ''})
        cur = {'attempts': cur['attempts'] + 1, 'last_sha': sha}
        state['inplace'][n] = cur
        state['recorded'].append((n, sha))
        return cur
    monkeypatch.setattr(mod.ci_data, 'record_inplace_attempt', _record)

    def _dispatch(repo, platform, pr, pr_base, token, target_repo, fix_pr_number=0, fix_branch=None):
        state['dispatched'].append((pr['number'], fix_branch))
        return True
    monkeypatch.setattr(mod, 'dispatch_ci_fix', _dispatch)

    return mod, state


def _make_pr(number=1, ref='add-fluid', sha='abc123', labels=('ci_failed',)):
    return {
        'number': number,
        'title': 'Feat: add fluid 1.2.3 docker image on openEuler 24.03',
        'head': {'ref': ref, 'sha': sha},
        'labels': [{'name': l} for l in labels],
    }


class TestProcessCreateImagePr:

    def test_first_attempt_dispatches_on_head_branch(self, inplace_env):
        mod, state = inplace_env
        api = _FakeApi()
        pr = _make_pr(number=42, ref='add-fluid', sha='sha1')

        result = mod.process_create_image_pr(api, 'o/r', 'gitcode', pr, 'master',
                                             'wtok', 'dtok', 'me/repo')

        assert result is True
        # 就地修复：fix_branch 必须是 PR 自己的 head 分支
        assert state['dispatched'] == [(42, 'add-fluid')]
        assert state['recorded'] == [(42, 'sha1')]
        assert api.comments == []

    def test_same_sha_not_redispatched(self, inplace_env):
        mod, state = inplace_env
        state['inplace'][42] = {'attempts': 1, 'last_sha': 'sha1'}
        api = _FakeApi()
        pr = _make_pr(number=42, sha='sha1')

        result = mod.process_create_image_pr(api, 'o/r', 'gitcode', pr, 'master',
                                             'wtok', 'dtok', 'me/repo')

        assert result is False
        assert state['dispatched'] == []   # 同一 head 不重复 dispatch

    def test_new_sha_after_fix_redispatches(self, inplace_env):
        mod, state = inplace_env
        state['inplace'][42] = {'attempts': 1, 'last_sha': 'oldsha'}
        api = _FakeApi()
        pr = _make_pr(number=42, sha='newsha')

        result = mod.process_create_image_pr(api, 'o/r', 'gitcode', pr, 'master',
                                             'wtok', 'dtok', 'me/repo')

        assert result is True
        assert state['dispatched'] == [(42, 'add-fluid')]
        assert state['inplace'][42]['attempts'] == 2

    def test_max_retries_notifies_human_without_dispatch(self, inplace_env):
        mod, state = inplace_env
        state['inplace'][42] = {'attempts': 6, 'last_sha': 'oldsha'}  # MAX_RETRIES == 6
        api = _FakeApi()
        pr = _make_pr(number=42, sha='newsha')

        result = mod.process_create_image_pr(api, 'o/r', 'gitcode', pr, 'master',
                                             'wtok', 'dtok', 'me/repo')

        assert result is False
        assert state['dispatched'] == []          # 不再修复
        assert len(api.comments) == 1             # 评论提醒人工
        assert 42 in state['giveup_notified']     # 不关闭 PR，仅标记已通知

    def test_giveup_comment_is_idempotent(self, inplace_env):
        mod, state = inplace_env
        state['inplace'][42] = {'attempts': 6, 'last_sha': 'oldsha'}
        state['giveup_notified'].add(42)
        api = _FakeApi()
        pr = _make_pr(number=42, sha='newsha')

        result = mod.process_create_image_pr(api, 'o/r', 'gitcode', pr, 'master',
                                             'wtok', 'dtok', 'me/repo')

        assert result is False
        assert api.comments == []                 # 已通知过，不重复评论

    def test_ci_processing_skips(self, inplace_env):
        mod, state = inplace_env
        api = _FakeApi()
        pr = _make_pr(number=42, labels=('ci_failed', 'ci_processing'))

        result = mod.process_create_image_pr(api, 'o/r', 'gitcode', pr, 'master',
                                             'wtok', 'dtok', 'me/repo')

        assert result is False
        assert state['dispatched'] == []

    def test_ci_successful_skips(self, inplace_env):
        mod, state = inplace_env
        api = _FakeApi()
        pr = _make_pr(number=42, labels=('ci_failed', 'ci_successful'))

        result = mod.process_create_image_pr(api, 'o/r', 'gitcode', pr, 'master',
                                             'wtok', 'dtok', 'me/repo')

        assert result is False
        assert state['dispatched'] == []
