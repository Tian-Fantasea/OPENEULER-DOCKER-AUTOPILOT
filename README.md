# openeuler-docker-autopilot

面向 [openeuler-docker-images](https://gitcode.com/openeuler/openeuler-docker-images) 容器镜像仓库的 **全生命周期自动化流水线**：从 Issue 触发新镜像创建，到 PR CI 失败自动修复，全部由 GitHub Actions 编排、AI 大模型执行，无需人工介入。

## 两条流水线

本项目由两条相互独立、共享底层能力的流水线组成：

| 流水线 | 触发源 | 做什么 | 产物 |
|--------|--------|--------|------|
| **🆕 新镜像创建**（create-image） | GitCode Issue（标题含 `【new-image】`） | AI 拉取上游版本/License/Go 版本，生成 Dockerfile、meta.yml、README、image-info.yml | 上游软件包的镜像 PR |
| **🔧 CI 失败修复**（ci-fix） | PR 获得 `ci_failed` label | AI 抓取构建日志、定位根因、实施最小化修复，参考历史知识库 | 修复用的 Fix PR |

两条流水线共享同一套 AI 后端（OpenCode / Claude Code）、Secrets 体系与平台 API 抽象层，但各自拥有独立的监控配置和工作流文件，互不干扰。

---

## 目录

- [概述](#概述)
- [快速开始](#快速开始)
  - [配置 Secrets](#1-配置-secrets)
  - [配置 Variables](#2-配置-variables)
  - [配置监控仓库](#3-配置监控仓库)
- [流水线一：新镜像创建](#流水线一新镜像创建)
- [流水线二：CI 失败修复](#流水线二ci-失败修复)
- [AI 后端配置](#ai-后端配置)
- [CI Label 约定](#ci-label-约定)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [常见问题](#常见问题)
- [License](#license)

---

## 概述

### 背景

开源社区的容器镜像仓库以 PR 为单位持续演进，存在两类高频、模式固定的人工劳动：

1. **新增上游软件包**——需要按目录规范手写 Dockerfile、meta.yml、README 和 image-info.yml，查上游最新版本、License、构建依赖。
2. **版本升级 PR 的 CI 失败修复**——构建环境、依赖、编译参数变化导致 CI 红，需要维护者读日志、定位根因、改 Dockerfile 再提交，单条 PR 平均 15–30 分钟。

这两类工作的根因都高度可模式化，适合交给 AI 自动处理。本项目将二者合并为一套自动驾驶式流水线。

### 完整生命周期

```
                        openeuler-docker-images 仓库
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         │                                                     │
   Issue【new-image】                                    PR 获得 ci_failed
         │                                                     │
         ▼ 每小时轮询                                          ▼ 定时轮询
   watch-issues.yml                                    stream-pr-events.yml
         │ 解析 issue → dispatch                              │ 跳过规则过滤 → dispatch
         ▼                                                     ▼
   create-image-trigger.yml                          pr-ci-fix-trigger.yml（两阶段）
         │ image-creator agent                              │ ci-failure-analyst → code-fixer
         ▼                                                     ▼
   生成镜像文件 → 新镜像 PR                            诊断报告 → 修复 → Fix PR
                                                              │
                                                  CI 结果驱动闭环（最多重试 6 次）
```

---

## 快速开始

### 1. 配置 Secrets

在 **Settings → Secrets and variables → Actions → Secrets** 添加：

| Secret | 用途 | 必需 |
|--------|------|------|
| `GITCODE_TOKEN` | GitCode 读写：clone、读 PR/Issue/CI 日志、推送 fork、创建 PR、评论、打 label | 必填 |
| `DISPATCH_TOKEN` | GitHub 操作：repository_dispatch、ci-data 分支读写、checkout、推送 | 必填（GitHub PAT，需 `repo` + `workflow` scope） |
| `AI_API_KEY` | AI 模型 API Key（OpenCode 后端，如 DeepSeek） | `AI_RUNNER=opencode` 时必填 |
| `CLAUDE_CREDENTIALS_JSON` | Claude.ai OAuth 凭证 | `AI_RUNNER=claude-code-account` 时必填，见 [AI 后端配置](#ai-后端配置) |

### 2. 配置 Variables

在 **Settings → Secrets and variables → Actions → Variables** 添加（均有默认值，可按需覆盖）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AI_RUNNER` | AI 后端：`opencode` / `claude-code` / `claude-code-account` | `opencode` |
| `AI_MODEL` | 模型名称（opencode 格式如 `deepseek/deepseek-v4-pro`） | `deepseek/deepseek-v4-pro` |
| `AI_TIMEOUT_MS` | AI 执行超时（毫秒） | `1800000` |
| `OPENAI_BASE_URL` | 自定义 API 代理地址（可选） | _(空)_ |
| `GITCODE_FORK_REPO` | CI 修复用的 GitCode fork 路径（如 `yourname/repo`），为空时直接推原仓库 | _(空)_ |
| `OS_VERSION` | openEuler 版本（新镜像用） | `24.03-lts-sp3` |
| `OS_TAG` | 镜像 Tag 后缀（新镜像用） | `oe2403sp3` |
| `GIT_COMMIT_NAME` | Git 提交用户名（CLA 合规时必填） | `github-actions[bot]` |
| `GIT_COMMIT_EMAIL` | Git 提交邮箱 | `github-actions[bot]@users.noreply.github.com` |

### 3. 配置监控仓库

两条流水线各有一份监控配置，互不影响：

| 流水线 | 配置文件 |
|--------|---------|
| 新镜像创建 | `config/issue-watchlist.json` |
| CI 失败修复 | `config/watchlist.json` |

> CI 修复配置的 `poll_interval_minutes` 变更会自动触发 `sync-poll-interval.yml`，将 cron 表达式同步到 `stream-pr-events.yml`，无需手动改 workflow。平台识别：URL 含 `gitcode.com` 走 GitCode API，否则走 GitHub API。

---

## 流水线一：新镜像创建

### 触发方式

在 [openeuler-docker-images Issues](https://gitcode.com/openeuler/openeuler-docker-images/issues) 提交 issue，**标题包含 `【new-image】`** 即可触发。正文支持结构化或自由文本：

**结构化格式（推荐）：**
```
**软件包名称（Package Name）：** fluid
**源码仓库（Source Repository）：** https://github.com/fluid-cloudnative/fluid
**所属领域（Domain）：** 虚拟化
```

**自由文本格式：**
```
新增openeuler上游软件包fluid，源码仓库链接是https://github.com/fluid-cloudnative/fluid，场景属于虚拟化
```

### 领域 → 目录映射

| 领域关键词 | 目标目录 |
|-----------|---------|
| 虚拟化、云原生、云计算、网络 | `Cloud/` |
| AI、人工智能、机器学习 | `AI/` |
| 大数据 | `Bigdata/` |
| 数据库 | `Database/` |
| 高性能计算、HPC | `HPC/` |
| 安全 | `Security/` |
| 存储 | `Storage/` |
| 其他 | `Cloud/`（默认） |

### 执行流程

```
watch-issues.yml (cron: 0 * * * *)
   │ fetch open issues → 标题过滤 → state 去重 → 解析正文
   ▼ dispatch create-image
create-image-trigger.yml (repository_dispatch: create-image)
   ├─ Clone openeuler-docker-images fork
   ├─ image-creator agent：
   │    ├─ gh API 获取最新版本、Go 版本、License
   │    ├─ 生成 Dockerfile / meta.yml / README.md
   │    ├─ 生成 doc/image-info.yml + logo
   │    └─ 更新 image-list.yml
   ├─ git commit & push → add-{package} 分支
   ├─ GitCode API 创建 PR
   └─ GitCode API 回复 issue，打 image-created label
```

已 dispatch 的 issue 记录在 `state/dispatched_issues.json`，按 issue 号去重，避免重复触发。

---

## 流水线二：CI 失败修复

### 核心能力

| 能力 | 说明 |
|------|------|
| **精准日志抓取** | 从 PR 评论表格逐行解析 FAILED/SUCCESS 状态，只取实际失败架构（x86-64、aarch64 等）的构建 job 日志，排除 trigger/编排层；日志与 ci_failed 状态矛盾时主动标记"证据不足" |
| **历史知识库** | `docs/ci-failure-patterns.md` 按失败模式分类，每次修复后自动追加新案例，下次分析自动参考 |
| **Fix PR 自管理** | Fix PR CI 再次失败时追加 commit 重试，不创建新 PR；超过最大重试次数（默认 6 次）自动关闭并通知人工介入 |
| **多平台支持** | 同时兼容 GitCode 和 GitHub，按 URL 自动识别平台，API 层完全隔离 |
| **智能跳过** | 预发布版本（-alpha/-beta/-rc 等）和工作流自身创建的 Fix PR 自动跳过 |

### 执行流程

```
stream-pr-events.yml (cron 由 watchlist 控制)
   │ 扫描 ci_failed PR → 跳过规则过滤 → 决策
   ▼ dispatch run-ci-fix-phase
pr-ci-fix-trigger.yml (repository_dispatch: run-ci-fix-phase，两阶段串行)
   ├─ 阶段1 ci-log-analysis：
   │    ci-failure-analyst agent 抓日志 + PR diff + 知识库 → 诊断报告（写入 ci-fix-log 分支）
   └─ 阶段2 code-fix：
        code-fixer agent 按报告最小化修复 → commit → push → 创建/更新 Fix PR
```

### Monitor 决策表

`stream-pr-events.yml` 按 `poll_interval_minutes` 定时运行，对每条 `ci_failed` PR：

| Fix PR 状态 | 动作 |
|------------|------|
| 不存在 | dispatch ci-log-analysis（首次修复） |
| open + `ci_successful` | 评论原始 PR，通知 reviewer 合并（一次性） |
| open + `ci_processing` | CI 运行中，跳过等待 |
| open + `ci_failed`，次数 < 6 | 重新 dispatch ci-log-analysis |
| open + `ci_failed`，次数 ≥ 6 | 关闭 Fix PR，通知人工介入 |
| open + 无状态 label | CI 尚未开始，跳过 |
| closed | 重新 dispatch |
| merged | 已合并，跳过 |

### 跳过规则

| 规则 | 匹配条件 | 原因 |
|------|----------|------|
| **预发布版本** | 标题含 `-alpha`/`-beta`/`-rc`/`-preview`/`-dev`/`-snapshot`/`-nightly`（需 `-` 或 `.` 前缀，非软件名一部分） | 预发布版本不稳定，不值得自动修复 |
| **Fix PR 自身** | 标题以 `fix:` 开头 | 本工作流的 Fix PR 通过追加 commit 自行重试，不应递归触发 |
| **已有通过 CI 的修复** | 存在标题含 `(fix #<原PR号>)`、open、带 `ci_successful` 的 PR | 已通过 CI，等待 reviewer 合并 |

### 数据分支

| 分支 | 内容 | 维护方式 |
|------|------|----------|
| `main` | 工作流代码 + `docs/ci-failure-patterns.md`（知识库） | 每次修复后自动追加新案例 |
| `ci-fix-log` | `{pr-number}/ci-analysis.md`（诊断报告）+ `fix-summary.md`（修复摘要） | 每次修复后由工作流写入 |

---

## AI 后端配置

两条流水线共用同一套后端抽象（`scripts/lib/ai_runner.py` 按 `AI_RUNNER` 分发）。

### OpenCode（默认）

OpenCode 兼容 OpenAI 接口，支持 DeepSeek、通义等。将 `AI_RUNNER` 设为 `opencode`，`AI_MODEL` 填对应模型：

| 提供商 | `AI_MODEL` 示例 |
|--------|----------------|
| DeepSeek | `deepseek/deepseek-v4-pro` |
| 阿里通义 | `alibaba-cn/qwen-plus` |
| OpenAI | `openai/gpt-4o` |

### Claude Code（账号模式，无需 API Key）

适合已有 Claude Pro / Max 订阅的用户。将 `AI_RUNNER` 设为 `claude-code-account`，`AI_MODEL` 设为对应 Claude 模型名。

**一次性获取凭证：**
```bash
claude                            # 本地登录（浏览器 OAuth）
cat ~/.claude/.credentials.json   # 完整 JSON 存入 Secret CLAUDE_CREDENTIALS_JSON
```
> ⚠️ OAuth Token 会过期（通常数周至数月），过期后需重新登录并更新 Secret。

| `AI_MODEL` 示例 | 说明 |
|----------------|------|
| `claude-sonnet-4-6` | 推荐，速度与质量均衡 |
| `claude-opus-4-8` | 最强推理，适合复杂修复场景 |
| `claude-haiku-4-5-20251001` | 最快，适合简单 lint / 格式修复 |

---

## CI Label 约定

CI 失败修复流水线依赖目标仓库的 CI 在对应时机为 PR 打 label：

| label | 打上时机 |
|-------|---------|
| `ci_failed` | CI 失败时 |
| `ci_processing` | CI 运行中时 |
| `ci_successful` | CI 通过时 |

**GitCode（GitLab CI）示例：**
```yaml
label-ci-failed:
  stage: .post
  script:
    - |
      curl -X POST "https://gitcode.com/api/v5/repos/${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME}/issues/${CI_MERGE_REQUEST_IID}/labels" \
        -H "Content-Type: application/json" \
        -d '{"labels": ["ci_failed"]}' \
        -H "Authorization: token ${GITCODE_TOKEN}"
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      when: on_failure
```

**GitHub 示例：**
```yaml
- name: Add ci_failed label on failure
  if: failure()
  uses: actions-ecosystem/action-add-labels@v1
  with:
    labels: ci_failed
    github_token: ${{ secrets.GITHUB_TOKEN }}
```

---

## 项目结构

```
openeuler-docker-autopilot/
├── .github/
│   ├── agents/                              # AI Agent 提示词
│   │   ├── image-creator.md                 #   🆕 新镜像创建师
│   │   ├── ci-failure-analyst.md            #   🔧 CI 失败诊断师
│   │   └── code-fixer.md                    #   🔧 代码修复工程师
│   └── workflows/
│       ├── watch-issues.yml                 # 🆕 Issue 轮询（cron: 0 * * * *）
│       ├── create-image-trigger.yml         # 🆕 新镜像创建执行链路
│       ├── stream-pr-events.yml             # 🔧 PR 监控（cron 由 watchlist 控制）
│       ├── pr-ci-fix-trigger.yml            # 🔧 CI 修复执行链路（两阶段）
│       └── sync-poll-interval.yml           # 🔧 watchlist 变更时同步 cron
├── config/
│   ├── issue-watchlist.json                 # 🆕 新镜像监控配置
│   └── watchlist.json                       # 🔧 CI 修复监控配置
├── scripts/
│   ├── lib/                                 # 共享库
│   │   ├── ai_runner.py                     #   AI 后端统一入口（按 AI_RUNNER 分发）
│   │   ├── opencode_run.py                  #   AI 调用封装 — OpenCode
│   │   ├── claude_code_run.py               #   AI 调用封装 — Claude Code
│   │   ├── gitcode_issues_api.py            # 🆕 GitCode Issues API
│   │   ├── ci_api.py                        # 🔧 平台工厂（detect / normalize / get_api）
│   │   ├── ci_github_api.py                 # 🔧 GitHub API 封装
│   │   ├── ci_gitcode_api.py                # 🔧 GitCode API（v5 PR + v4 Pipeline + Jenkins 日志）
│   │   ├── ci_data.py                       # 🔧 ci-fix-log + main 分支读写
│   │   ├── fix_pr_body.py                   # 🔧 Fix PR 标题/正文生成
│   │   ├── stage_common.py                  # 🔧 阶段脚本公共工具
│   │   └── discover_conventions.py          # 🔧 自动读取源仓库项目规范
│   ├── stages/
│   │   ├── create-image.py                  # 🆕 新镜像文件创建
│   │   ├── ci-log-analysis.py               # 🔧 阶段1：CI 日志分析
│   │   └── code-fix.py                      # 🔧 阶段2：代码修复
│   └── watch/
│       ├── process_issue_events.py          # 🆕 Issue 轮询 + dispatch
│       ├── process_pr_events.py             # 🔧 PR 轮询 + dispatch 决策 + 跳过规则
│       └── sync_poll_interval.py            # 🔧 watchlist → cron 同步
├── docs/
│   ├── ci-failure-patterns.md               # 🔧 失败模式知识库（自动维护）
│   └── design/                              # 设计文档（PRD / 数据模型 / 系统设计）
├── tests/                                   # 107 个用例
│   ├── test_ci_gitcode_api.py               #   URL 评分与日志抓取
│   ├── test_fix_pr_body.py                  #   Fix PR 标题/正文生成
│   └── test_process_pr_events.py            #   跳过规则
└── requirements.txt
```

> 🆕 = 新镜像创建流水线   🔧 = CI 失败修复流水线   其余为两者共享

---

## 开发指南

### 运行测试

```bash
python3 -m pytest tests/ -v
```

| 文件 | 覆盖范围 |
|------|----------|
| `test_ci_gitcode_api.py` | `_url_score`、`_find_jenkins_url_in_comments`（混合 SUCCESS/FAILED 表格）、日志尾部优先截取、`get_latest_failed_run` 完整逻辑 |
| `test_fix_pr_body.py` | Fix PR 标题提取（软件名+版本）、正文结构、ci-data fallback |
| `test_process_pr_events.py` | 预发布版本检测（大小写/点分隔/软件名边界）、`fix:` 前缀跳过 |

### 新增监控平台（CI 修复）

1. 在 `scripts/lib/` 新建 `ci_{platform}_api.py`，实现与 `ci_github_api.py` 相同的接口
2. 在 `scripts/lib/ci_api.py` 的 `detect_platform` 和 `get_api` 中注册
3. 无需修改任何阶段脚本，平台切换完全由工厂层处理

### 调整跳过规则（CI 修复）

跳过规则集中在 `scripts/watch/process_pr_events.py` 主循环，新增规则在此追加并同步 `tests/test_process_pr_events.py`。

### 技术栈

| 组件 | 用途 |
|------|------|
| GitHub Actions | 工作流编排 + cron 调度 + repository_dispatch |
| Python 3.11 | 阶段脚本 + 工具库 |
| OpenCode / Claude Code | AI 模型调用（可切换） |
| GitHub Contents API | ci-fix-log 分支 + main 分支知识库读写 |
| GitCode API v5 | PR/Issue 读写、评论、标签（Gitee-compatible） |
| GitCode API v4 | Pipeline / Job 日志获取（GitLab-compatible） |

---

## 常见问题

### Q: 两条流水线会互相干扰吗？

不会。它们使用不同的监控配置文件（`issue-watchlist.json` vs `watchlist.json`）、不同的 dispatch 类型（`create-image` vs `run-ci-fix-phase`）、不同的 workflow 文件，仅共享 AI 后端与 Secrets。

### Q: 新镜像流水线运行了但没触发，怎么排查？

1. issue 标题是否包含 `【new-image】`
2. `config/issue-watchlist.json` 中该仓库 `enabled` 是否为 `true`
3. 该 issue 是否已在 `state/dispatched_issues.json` 中（已处理过会去重）
4. 查看 `watch-issues` 的运行日志

### Q: CI 修复运行了但没触发，怎么排查？

1. PR 是否确实有 `ci_failed` label（非拼写变体）
2. `config/watchlist.json` 中该仓库 `enabled` 是否为 `true`
3. PR 标题是否命中[跳过规则](#跳过规则)（预发布或 `fix:` 前缀）
4. `DISPATCH_TOKEN` / `GITCODE_TOKEN` 权限是否充足
5. 查看 `stream-pr-events` 日志，搜索 `→ Skipping` 或 `❌`

### Q: 诊断报告出现"证据不足"怎么办？

说明拉到的日志末尾是 `Finished: SUCCESS`，与 PR 的 `ci_failed` 矛盾——实际失败在未暴露的下游 job（多架构并行中只有部分架构失败）。报告会说明需要哪个架构的 job URL，手动拿到后参考报告提示定位即可。

### Q: Fix PR 再次 CI 失败怎么办？

无需手动操作。下次 Monitor 轮询会对其**原始 PR** 重新发起 ci-log-analysis，AI 根据新日志追加 commit；超过 6 次自动关闭并通知人工介入。

### Q: 想手动跳过某条 PR？

移除其 `ci_failed` label 即可，下次轮询不再处理。

---

## License

MIT
