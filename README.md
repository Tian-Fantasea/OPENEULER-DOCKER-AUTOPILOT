# openeuler-docker-autopilot

面向 [openeuler-docker-images](https://gitcode.com/openeuler/openeuler-docker-images) 容器镜像仓库的 **全生命周期自动化流水线**：从 Issue 触发新镜像创建，到 PR CI 失败自动修复，全部由 GitHub Actions 编排、AI 大模型执行，无需人工介入。

## 受众导航

| 你是… | 直接跳到 |
|-------|---------|
| **仓库维护者**（接入仓库、配置 Secret、看工作流是否正常运行） | [快速开始](#快速开始) → [CI Label 约定](#ci-label-约定) → [常见问题](#常见问题) |
| **开发者**（修改代码、新增功能、写测试） | [目录结构](#目录结构) → [模块说明](#模块说明) → [开发指南](#开发指南) |

## 目录

- [概述](#概述)

**仓库维护者**
- [快速开始](#快速开始)
- [流水线一：新镜像创建](#流水线一新镜像创建)
- [流水线二：CI 失败修复](#流水线二ci-失败修复)
- [跳过与路由规则](#跳过与路由规则)
- [AI 后端配置](#ai-后端配置)
- [CI Label 约定](#ci-label-约定)
- [常见问题](#常见问题)

**开发者**
- [目录结构](#目录结构)
- [模块说明](#模块说明)
- [开发指南](#开发指南)

## 概述

### 背景

开源社区的容器镜像仓库以 PR 为单位持续演进，存在两类高频、模式固定的人工劳动：

1. **新增上游软件包**——需要按目录规范手写 Dockerfile、meta.yml、README 和 image-info.yml，查上游最新版本、License、构建依赖。
2. **版本升级 PR 的 CI 失败修复**——构建环境、依赖、编译参数变化导致 CI 红，需要维护者读日志、定位根因、改 Dockerfile 再提交，单条 PR 平均 15–30 分钟。

这两类工作的根因都高度可模式化，适合交给 AI 自动处理。本项目将二者合并为一套自动驾驶式流水线。

### 解决方案

openeuler-docker-autopilot 以 GitHub Actions 作为编排引擎、AI 大模型作为执行者，由两条相互独立、共享底层能力的流水线组成：

| 流水线 | 触发源 | 执行内容 | 输出 |
|--------|--------|----------|------|
| **🆕 新镜像创建**（create-image） | GitCode Issue（标题含 `【new-image】`） | AI 拉取上游版本/License/Go 版本，生成 Dockerfile、meta.yml、README、image-info.yml | 上游软件包的镜像 PR |
| **🔧 CI 失败修复**（ci-fix） | PR 获得 `ci_failed` label | AI 抓取构建日志、定位根因、参考历史知识库实施最小化修复 | 修复用的 Fix PR / 就地修复 commit |

两条流水线共享同一套 AI 后端（OpenCode / Claude Code）、Secrets 体系与平台 API 抽象层，但各自拥有独立的监控配置和工作流文件，互不干扰。

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
         │ 解析 issue → dispatch                              │ 跳过/路由 → dispatch
         ▼                                                     ▼
   create-image-trigger.yml                          pr-ci-fix-trigger.yml（两阶段）
         │ image-creator agent                              │ ci-failure-analyst → code-fixer
         ▼                                                     ▼
   生成镜像文件 → 新镜像 PR ──────┐                  ┌── 升级 PR：另开 Fix PR
                                    │                  │
                          若新镜像 PR CI 失败          └── create-image PR：就地追加修复 commit
                                    │                          │
                                    └──────────────────────────┘
                                            CI 结果驱动闭环（最多重试 6 次）
```

### 核心能力

| 能力 | 说明 |
|------|------|
| **新镜像零干预创建** | Issue 一句话描述软件包，AI 查版本/License 自动生成全套镜像文件并提 PR |
| **精准日志抓取** | 从 PR 评论表格逐行解析 FAILED/SUCCESS，只取实际失败架构（x86-64、aarch64 等）的构建 job 日志，排除 trigger/编排层；日志与 ci_failed 状态矛盾时主动标记"证据不足" |
| **历史知识库** | `docs/ci-failure-patterns.md` 按失败模式分类，每次修复后自动追加新案例，下次分析自动参考 |
| **双模式修复** | 升级 PR → 另开 Fix PR；本项目自己创建的 create-image PR → **就地往原 PR 分支追加修复 commit**，不产生重复 PR |
| **自管理重试** | 修复失败时自动追加 commit 重试，超过最大次数（默认 6 次）：Fix PR 自动关闭、create-image PR 保留并评论提醒人工 |
| **多平台支持** | 同时兼容 GitCode 和 GitHub，按 URL 自动识别平台，API 层完全隔离 |

---

## 快速开始

### 1. Fork 本仓库

Fork 本仓库到你的 GitHub 账号，后续在 fork 仓库的 Actions 中运行。

### 2. 配置 Secrets

在 **Settings → Secrets and variables → Actions → Secrets** 添加：

| Secret | 用途 | 必需 |
|--------|------|------|
| `GITCODE_TOKEN` | GitCode 读写：clone、读 PR/Issue/CI 日志、推送 fork、创建 PR、评论、打 label | 必填 |
| `DISPATCH_TOKEN` | GitHub 操作：repository_dispatch、ci-data 分支读写、checkout、推送 | 必填（GitHub PAT，需 `repo` + `workflow` scope） |
| `AI_API_KEY` | AI 模型 API Key（OpenCode 后端，如 DeepSeek） | `AI_RUNNER=opencode` 时必填 |
| `CLAUDE_CREDENTIALS_JSON` | Claude.ai OAuth 凭证 | `AI_RUNNER=claude-code-account` 时必填，见 [AI 后端配置](#ai-后端配置) |

### 3. 配置 Variables

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

### 4. 配置监控仓库

两条流水线各有一份监控配置，互不影响：

| 流水线 | 配置文件 | 触发依据 | 轮询间隔 |
|--------|---------|---------|---------|
| 新镜像创建 | `config/issue-watchlist.json` | issue 标题含 `【new-image】` | `poll_interval_hours`（默认 1 小时） |
| CI 失败修复 | `config/watchlist.json` | PR 带 `ci_failed` label | `poll_interval_minutes`（默认 10 分钟） |

> 修改 `config/watchlist.json` 的 `poll_interval_minutes` 会自动触发 `sync-poll-interval.yml`，将 cron 表达式同步到 `stream-pr-events.yml`，无需手动改 workflow。平台识别：URL 含 `gitcode.com` 走 GitCode API，否则走 GitHub API。

### 5. 确认 CI Label 约定

CI 失败修复流水线依赖目标仓库的 CI 在对应时机打 label，详见 [CI Label 约定](#ci-label-约定)。配置完成后，等待下一次 cron 触发（或手动运行对应 workflow）即可。

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

### 工作流程

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
   ├─ GitCode API 创建 PR（标题 'Feat: add {pkg} {version} docker image on openEuler ...'）
   └─ GitCode API 回复 issue，打 image-created label
```

已 dispatch 的 issue 记录在 `state/dispatched_issues.json`，按 issue 号去重，避免重复触发。生成的 PR 的 head 分支 `add-{package}` 位于配置的 fork 仓库上——这一点是它能被 CI 失败修复流水线**就地修复**的前提。

---

## 流水线二：CI 失败修复

### 工作流程

```
stream-pr-events.yml (cron 由 watchlist 控制)
   │ 扫描 ci_failed PR → 跳过/路由判定 → 决策
   ▼ dispatch run-ci-fix-phase
pr-ci-fix-trigger.yml (repository_dispatch: run-ci-fix-phase，两阶段串行)
   ├─ 阶段1 ci-log-analysis：
   │    ci-failure-analyst agent 抓日志 + PR diff + 知识库 → 诊断报告（写入 ci-fix-log 分支）
   └─ 阶段2 code-fix：
        code-fixer agent 按报告最小化修复 → commit → push → 创建/更新目标 PR
```

### Monitor 决策（升级 PR）

`stream-pr-events.yml` 按 `poll_interval_minutes` 定时运行。对**普通升级 PR**，依据其对应 `fix/<pr-number>` 分支的 Fix PR 状态决策：

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

### create-image PR 就地修复（本项目自建 PR）

流水线一创建的 PR（标题 `Feat: add ... docker image on openEuler`、分支 `add-{package}`）一旦 CI 失败，**不会**另开一个 Fix PR——因为它的 head 分支就在我们自己的 fork 上，可以直接往原分支追加修复 commit，PR 自动更新。这避免了"两个 PR 都在新增同一个镜像"的重复与割裂。

识别依据（`process_pr_events.py`）：标题匹配 `Feat: add ... docker image on openEuler`，或 head 分支以 `add-` 开头。命中后走就地修复决策：

| create-image PR 状态 | 动作 |
|---------------------|------|
| `ci_processing` | CI 运行中，跳过 |
| `ci_successful` | 已通过，无需处理 |
| `ci_failed`，且当前 head_sha 已 dispatch 过 | 等待本轮修复/CI 结果，跳过（去重） |
| `ci_failed`，尝试次数 < 6 | dispatch 就地修复（`fix_branch` = PR 自己的 `add-{package}` 分支） |
| `ci_failed`，尝试次数 ≥ 6 | **评论提醒人工、保留 PR 不关闭**（它是关联 issue 的正主） |

就地修复全程复用流水线二的两阶段链路与文件白名单（只允许改原 PR diff 涉及的镜像文件），唯一区别是把修复推回原 PR 的分支、并跳过"建新 PR"。重试计数与去重状态记录在 `ci-fix-log` 分支的 `{pr-number}/inplace-fix-state.json`（记 `attempts` 与 `last_sha`），与分支所在仓库无关。

### 知识积累

每次修复完成、且 Fix PR 通过 CI 后，自动更新 `docs/ci-failure-patterns.md`（main 分支）：新案例归入已有模式章节，全新失败类型则新建章节，下次分析自动参考。

---

## 跳过与路由规则

Monitor 轮询时，对每条 `ci_failed` PR 依次判定：

| 判定 | 匹配条件 | 处理 |
|------|----------|------|
| **预发布版本** | 标题含 `-alpha`/`-beta`/`-rc`/`-preview`/`-dev`/`-snapshot`/`-nightly`（需 `-` 或 `.` 前缀，非软件名一部分） | 跳过（不稳定，不值得自动修复） |
| **Fix PR 自身** | 标题以 `fix:` 开头 | 跳过（通过追加 commit 自重试，不应递归触发） |
| **create-image PR** | 标题 `Feat: add ... docker image on openEuler` 或分支前缀 `add-` | **路由到就地修复**（见上节） |
| **普通升级 PR** | 其余 | 走 `fix/<pr-number>` 另开 Fix PR 的标准链路 |

**示例：**

| PR 标题 | 结果 |
|---------|------|
| `【自动升级】etcd容器镜像升级至3.8.0-alpha.0版本.` | 跳过（预发布）|
| `fix: etcd 3.6.11 (fix #2534)` | 跳过（Fix PR 自身）|
| `Feat: add fluid 1.2.3 docker image on openEuler 24.03-LTS-SP3` | 就地修复（create-image PR）|
| `【自动升级】etcd容器镜像升级至3.6.11版本.` | 标准修复（另开 Fix PR）|
| `【自动升级】developer-tool升级至1.0.0版本.` | 标准修复（`developer-` 是软件名，非版本标记）|

---

## AI 后端配置

两条流水线共用同一套后端抽象（`scripts/lib/ai_runner.py` 按 `AI_RUNNER` 分发）。

### 使用 OpenCode（默认）

OpenCode 兼容 OpenAI 接口，支持 DeepSeek、通义等。将 `AI_RUNNER` 设为 `opencode`，`AI_MODEL` 填对应模型：

| 提供商 | `AI_MODEL` 示例 |
|--------|----------------|
| DeepSeek | `deepseek/deepseek-v4-pro` |
| 阿里通义 | `alibaba-cn/qwen-plus` |
| OpenAI | `openai/gpt-4o` |

### 使用 Claude Code（账号模式，无需 API Key）

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

CI 失败修复流水线依赖目标仓库的 CI 在以下时机为 PR 打对应 label：

| label | 打上时机 |
|-------|---------|
| `ci_failed` | CI 失败时 |
| `ci_processing` | CI 运行中时 |
| `ci_successful` | CI 通过时 |

**GitCode（GitLab CI）示例：**

```yaml
# .gitlab-ci.yml（目标仓库，片段）
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
# .github/workflows/ci.yml（目标仓库，片段）
- name: Add ci_failed label on failure
  if: failure()
  uses: actions-ecosystem/action-add-labels@v1
  with:
    labels: ci_failed
    github_token: ${{ secrets.GITHUB_TOKEN }}
```

---

## 常见问题

### Q: 两条流水线会互相干扰吗？

不会。它们使用不同的监控配置文件（`issue-watchlist.json` vs `watchlist.json`）、不同的 dispatch 类型（`create-image` vs `run-ci-fix-phase`）、不同的 workflow 文件，仅共享 AI 后端与 Secrets。

### Q: create-image PR 的 CI 失败了，会被怎么处理？

会被 CI 失败修复流水线识别为 create-image PR，**就地往它自己的 `add-{package}` 分支追加修复 commit**，不会另开新 PR——所以不会出现两个都在新增同一镜像的重复 PR。重试 6 次仍失败时保留该 PR 并评论提醒人工，不会关闭它。详见 [create-image PR 就地修复](#create-image-pr-就地修复本项目自建-pr)。

### Q: 新镜像流水线运行了但没触发，怎么排查？

1. issue 标题是否包含 `【new-image】`
2. `config/issue-watchlist.json` 中该仓库 `enabled` 是否为 `true`
3. 该 issue 是否已在 `state/dispatched_issues.json` 中（已处理过会去重）
4. 在 Actions tab 查看 `watch-issues` 的运行日志

### Q: CI 修复运行了但没触发，怎么排查？

1. PR 是否确实有 `ci_failed` label（非拼写变体）
2. `config/watchlist.json` 中该仓库 `enabled` 是否为 `true`
3. PR 标题是否命中[跳过与路由规则](#跳过与路由规则)（预发布或 `fix:` 前缀）
4. `DISPATCH_TOKEN` / `GITCODE_TOKEN` 权限是否充足
5. 查看 `stream-pr-events` 日志，搜索 `→ Skipping` 或 `❌`

### Q: 日志抓取逻辑是怎么工作的？

openEuler CI 的 PR 评论表格中同时包含 trigger 层 URL 和各架构构建 URL，且路径深度相同。系统采用：

1. **排除编排层**：含 `/trigger/`、`/gate/`、`/pre-check/` 的 URL 直接丢弃
2. **逐行解析**：按 HTML `<tr>` 行匹配 URL 与同行的 FAILED/SUCCESS 标记，避免把成功架构的 URL 误判为失败
3. **架构优先**：含 `x86-64`、`aarch64` 等架构标识的 URL 评分更高
4. **重试时用 Fix PR 评论**：首次从原始 PR 评论查 URL；重试时切换到 Fix PR 编号查询，确保取最新构建
5. **日志截取**：取日志末尾 500 行（尾部优先），构建失败几乎总在末尾

### Q: 诊断报告出现"证据不足"怎么办？

说明拉到的日志末尾是 `Finished: SUCCESS`，与 PR 的 `ci_failed` 矛盾——实际失败在未暴露的下游 job（多架构并行中只有部分架构失败）。报告会说明需要哪个架构的 job URL，手动拿到后参考报告提示定位即可。

### Q: 想手动跳过某条 PR？

移除其 `ci_failed` label 即可，下次轮询不再处理。

---

## 目录结构

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
│   │   ├── ci_data.py                       # 🔧 ci-fix-log + main 分支读写、就地修复状态
│   │   ├── fix_pr_body.py                   # 🔧 Fix PR 标题/正文生成
│   │   ├── stage_common.py                  # 🔧 阶段脚本公共工具
│   │   └── discover_conventions.py          # 🔧 自动读取源仓库项目规范
│   ├── stages/
│   │   ├── create-image.py                  # 🆕 新镜像文件创建
│   │   ├── ci-log-analysis.py               # 🔧 阶段1：CI 日志分析
│   │   └── code-fix.py                      # 🔧 阶段2：代码修复
│   └── watch/
│       ├── process_issue_events.py          # 🆕 Issue 轮询 + dispatch
│       ├── process_pr_events.py             # 🔧 PR 轮询 + 跳过/路由 + 就地修复决策
│       └── sync_poll_interval.py            # 🔧 watchlist → cron 同步
├── docs/
│   ├── ci-failure-patterns.md               # 🔧 失败模式知识库（自动维护）
│   └── design/                              # 设计文档（PRD / 数据模型 / 系统设计）
├── state/
│   └── dispatched_issues.json               # 🆕 已 dispatch 的 issue 去重记录
├── tests/                                   # 125 个用例
│   ├── test_ci_gitcode_api.py               #   URL 评分与日志抓取（44）
│   ├── test_fix_pr_body.py                  #   Fix PR 标题/正文生成（22）
│   └── test_process_pr_events.py            #   跳过规则 + create-image 识别 + 就地修复决策（59）
└── requirements.txt
```

> 🆕 = 新镜像创建流水线   🔧 = CI 失败修复流水线   其余为两者共享

### 关键数据分支

| 分支 | 内容 | 维护方式 |
|------|------|----------|
| `main` | 工作流代码 + `docs/ci-failure-patterns.md`（知识库） | 每次修复后自动追加新案例 |
| `ci-fix-log` | `{pr-number}/ci-analysis.md`（诊断报告）+ `code-fix-summary.md`（修复摘要）+ `inplace-fix-state.json`（就地修复计数）+ `fix-notified` / `giveup-notified`（通知标记） | 每次修复/通知后由工作流写入 |

---

## 模块说明

### 工作流编排

| 文件 | 职责 |
|------|------|
| `watch-issues.yml` | cron 触发，调用 `process_issue_events.py` 扫描 `【new-image】` issue，dispatch create-image |
| `create-image-trigger.yml` | 接收 dispatch，运行 image-creator agent 生成镜像文件、提 PR、回复 issue |
| `stream-pr-events.yml` | cron 触发，调用 `process_pr_events.py` 扫描 `ci_failed` PR，决策 dispatch |
| `pr-ci-fix-trigger.yml` | 接收 dispatch，串行执行 ci-log-analysis → code-fix 两阶段 |
| `sync-poll-interval.yml` | 监听 `watchlist.json` 变更，自动更新 `stream-pr-events.yml` 的 cron 表达式 |

### AI Agent Prompt

| 文件 | 职责 |
|------|------|
| `image-creator.md` | 新镜像创建师：按领域目录规范生成 Dockerfile / meta.yml / README / image-info.yml |
| `ci-failure-analyst.md` | 诊断师：错误类型分类、分析方法（含前置一致性检查）、核心约束（禁止在 SUCCESS 日志中找根因） |
| `code-fixer.md` | 修复工程师：读取诊断报告、最小化修改原则、提交规范 |

### Python 库（`scripts/lib/`）

| 模块 | 职责 |
|------|------|
| `ai_runner.py` | 根据 `AI_RUNNER` 分发到 opencode 或 claude-code 后端 |
| `gitcode_issues_api.py` | GitCode Issues 读取、过滤、评论、正文解析 |
| `ci_gitcode_api.py` | GitCode v5（PR 读写、评论）+ Jenkins 日志抓取（逐行 URL 解析、编排层过滤、架构评分） |
| `ci_github_api.py` | GitHub REST API（PR 读写） |
| `ci_api.py` | 平台工厂，根据 repo URL 自动分发到对应 API 模块 |
| `ci_data.py` | ci-fix-log + main 分支读写；就地修复状态（`read_inplace_state` / `record_inplace_attempt`）与通知标记（`fix_notified` / `giveup_notified`） |
| `fix_pr_body.py` | 从诊断报告和修复摘要构建 Fix PR 标题（提取软件名+版本）与正文 |

### 就地修复 vs 另开 Fix PR

```
ci_failed PR
   │
   ├─ 标题/分支命中 create-image PR？
   │      │
   │      是 → fix_branch = 原 PR 的 add-{package} 分支
   │           code-fix push 回原分支 → 原 PR 自动更新（不建新 PR）
   │           计数/去重：ci-fix-log/{n}/inplace-fix-state.json
   │
   └─ 否（普通升级 PR）→ fix_branch = fix/{n}
                         code-fix push 到 fork → 另开 'fix:' 标题的 Fix PR
                         计数：fix 分支相对 base 的 commit 数
```

---

## 开发指南

### 运行测试

```bash
python3 -m pytest tests/ -v
```

| 文件 | 覆盖范围 | 用例数 |
|------|----------|--------|
| `test_ci_gitcode_api.py` | `_url_score`、`_find_jenkins_url_in_comments`（混合 SUCCESS/FAILED 表格）、日志尾部优先截取、`get_latest_failed_run` 完整逻辑 | 44 |
| `test_fix_pr_body.py` | Fix PR 标题提取（软件名+版本）、正文结构、ci-data fallback | 22 |
| `test_process_pr_events.py` | 预发布检测、`fix:` 前缀跳过、create-image PR 识别、就地修复决策（计数/去重/超限通知） | 59 |

### 新增监控平台（CI 修复）

1. 在 `scripts/lib/` 新建 `ci_{platform}_api.py`，实现与 `ci_github_api.py` 相同的接口
2. 在 `scripts/lib/ci_api.py` 的 `detect_platform` 和 `get_api` 中注册
3. 无需修改任何阶段脚本，平台切换完全由工厂层处理

### 调整跳过/路由规则

集中在 `scripts/watch/process_pr_events.py` 主循环：

```python
if _is_prerelease(pr_title):                       # 预发布版本检测
    ...
if pr_title.lstrip().lower().startswith('fix:'):   # Fix PR 过滤
    ...
if _is_create_image_pr(pr):                         # create-image PR → 就地修复
    ...
```

新增规则在此追加，并同步在 `tests/test_process_pr_events.py` 中覆盖。

### 技术栈

| 组件 | 用途 |
|------|------|
| GitHub Actions | 工作流编排 + cron 调度 + repository_dispatch |
| Python 3.11 | 阶段脚本 + 工具库 |
| OpenCode / Claude Code | AI 模型调用（可切换） |
| GitHub Contents API | ci-fix-log 分支 + main 分支知识库读写 |
| GitCode API v5 | PR/Issue 读写、评论、标签（Gitee-compatible） |
| GitCode API v4 | Pipeline / Job 日志获取（GitLab-compatible） |

## License

MIT
