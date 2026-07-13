# docker-images-workflow — 产品需求分析

**状态:** 已发布
**日期:** 2026-06-15
**版本:** 1.0

---

## 目录

1. [背景与问题](#一背景与问题)
2. [目标用户](#二目标用户)
3. [需求陈述](#三需求陈述)
4. [解决方案概述](#四解决方案概述)
5. [功能需求](#五功能需求)
6. [非功能需求](#六非功能需求)
7. [成功指标](#七成功指标)
8. [约束与边界](#八约束与边界)

---

## 一、背景与问题

### 1.1 容器镜像仓库的维护现状

开源社区的容器镜像仓库（如 `openeuler/openeuler-docker-images`）通过 Pull Request 持续更新软件版本。典型的更新路径如下：

```
上游软件发布新版本
      ↓
自动化 PR（如 bot 创建）提交新版本的 Dockerfile / 构建脚本变更
      ↓
CI 运行构建与测试（多架构：x86-64、aarch64 等）
      ↓
CI 失败 → 维护者人工介入
```

版本升级 PR 经常因以下原因导致 CI 失败：

| 失败类型 | 典型场景 |
|---------|---------|
| 下载 URL 变更 | 依赖包的 CDN 下载地址在新版本中改变（如 Apache Maven 不再保留旧版本） |
| 硬编码路径错误 | URL 路径中硬编码了主版本号，次版本升级后路径失效 |
| 缺少编译依赖 | 新版本引入了新的编译时依赖，Dockerfile 未同步更新 |
| 链接参数变更 | 新版本改变了 CMake/Makefile 链接选项 |
| 校验和/签名变更 | 新版本文件的 SHA256 与 Dockerfile 中硬编码值不符 |

### 1.2 当前工作流程（As-Is）

```
CI 系统为 PR 打上 ci_failed 标签
          ↓
维护者人工检查 PR 列表
          ↓
打开 CI 日志（通常是 Jenkins 多架构并行构建，链接在评论表格中）
          ↓
阅读日志，定位失败原因
          ↓
克隆仓库，修改 Dockerfile / 脚本
          ↓
提交修复，等待 CI 重新运行
```

这一过程的痛点：

| 问题 | 说明 |
|------|------|
| **高度重复** | 同类失败（如 Maven CDN 404、URL 路径错误）反复出现，每次都需重新分析 |
| **模式固定** | 根因往往是已知构建失败模式，不需要创造性解决，只需对应套用 |
| **时间成本高** | 人工处理每条 PR 平均需要 15–30 分钟，拖慢合并节奏 |
| **专注度消耗** | 维护者需要频繁切换上下文，影响对高价值工作的投入 |
| **知识不积累** | 修复经验停留在个人记忆中，无法系统性复用 |

### 1.3 问题陈述

开源社区容器镜像仓库的维护者面临一个高频且高度重复的问题：

1. **无自动化** — CI 失败后只能靠维护者人工逐条处理，缺乏自动化修复能力
2. **知识不积累** — 历史修复经验无法自动沉淀为可搜索、可复用的知识库
3. **响应滞后** — PR 等待修复期间持续占用 CI 资源，合并队列积压
4. **重试繁琐** — 修复后如果 CI 再次失败，需要再次人工介入

---

## 二、目标用户

### 2.1 主要用户：仓库维护者

**角色描述：** 负责维护容器镜像仓库的工程师，需要处理持续涌入的版本升级 PR。

**需求：**
- 减少处理 CI 失败 PR 的重复性工作
- 当修复无法自动完成时，获得精准的诊断报告以指导人工介入
- 对已通过 CI 的修复 PR 收到及时通知，完成最终 review 和合并

**使用场景：**
- 接入工作流：Fork 仓库、配置 Secrets、添加监控目标
- 日常使用：监控工作流运行状态、review 自动创建的 Fix PR
- 故障处理：阅读 ci-fix-log 分支上的诊断报告，判断是否需要人工干预

### 2.2 次要用户：工作流开发者

**角色描述：** 负责维护和扩展 docker-images-workflow 本身的工程师。

**需求：**
- 清晰的模块边界，便于理解和修改
- 完善的单元测试，支持快速迭代
- 可扩展的平台抽象，支持接入新的代码托管平台

---

## 三、需求陈述

### 3.1 核心需求（Must Have）

**M1 — PR 自动监控**
- 系统定时轮询目标仓库，自动检测带有 `ci_failed` 标签的 PR
- 支持多仓库监控，配置驱动（`watchlist.json`），无需修改代码
- 支持轮询间隔配置，变更后自动同步到 cron 表达式，无需手动编辑 workflow 文件

**M2 — CI 日志智能分析**
- 自动从 PR 评论中定位失败的 CI 构建日志 URL
- 智能过滤编排层日志（trigger/gate/pre-check），只分析实际构建失败的日志
- 多架构并行构建场景下，准确定位哪个架构的哪个 job 失败
- AI 诊断报告必须包含：失败类型分类、根因定位、与 PR 变更的关联分析、修复方向

**M3 — 代码自动修复**
- AI 根据诊断报告，在源代码中实施最小化修复（仅修改原始 PR 涉及的文件）
- 修复内容以 git commit 形式提交到独立的 fix 分支
- 自动创建 Fix PR，标题格式清晰（`fix: <软件名> <版本> (fix #<原PR号>)`）

**M4 — Fix PR 生命周期管理**
- Fix PR CI 失败时，自动触发新一轮分析和修复（追加 commit，不创建新 PR）
- 超过最大重试次数（6次）后，自动关闭 Fix PR 并评论通知人工介入
- Fix PR 通过 CI 后，在原始 PR 上评论通知维护者 review 和合并

**M5 — 知识库积累**
- 每次 Fix PR 通过 CI 验证后，自动将本次修复的失败模式写入知识库
- 知识库按失败模式分类，每类包含：症状关键词、根因分析、修复方法、历史案例
- 下次分析同类失败时，AI 自动参考知识库，提高诊断置信度

### 3.2 应有需求（Should Have）

**S1 — 多平台支持**
- 支持 GitCode（Gitee-compatible API v5）和 GitHub 仓库
- 平台识别通过 URL 自动判断（`gitcode.com` → GitCode，否则 → GitHub）
- API 层完全隔离，阶段脚本无需感知平台差异

**S2 — 多 AI 后端支持**
- 支持 OpenCode 后端（兼容 OpenAI 接口，支持 DeepSeek、通义等模型）
- 支持 Claude Code 账号模式（无需 API Key，使用 OAuth 凭证）
- 后端切换通过环境变量配置，代码无需修改

**S3 — 智能跳过规则**
- 预发布版本（alpha/beta/rc 等）自动跳过，不触发修复
- 工作流自身创建的 Fix PR 自动跳过，避免递归触发
- 已有通过 CI 的修复 PR 时，跳过再次触发

**S4 — 安全文件管控**
- Fix PR 严禁包含 AI 工具产生的辅助文件（.claude、.opencode 等）
- 只允许修改原始 PR 涉及的文件，不扩展到其他文件

### 3.3 可有需求（Could Have）

**C1 — 项目规范感知**
- 自动读取源仓库的代码规范文件（CONTRIBUTING.md、.editorconfig 等），供 AI 参考
- 修复后的代码风格与仓库规范保持一致

**C2 — 知识库手动维护接口**
- 支持手动编辑知识库（`docs/ci-failure-patterns.md`），修正 AI 自动写入的条目

### 3.4 不纳入（Won't Have）

- **自动合并 Fix PR**：Fix PR 通过 CI 后，合并决策由维护者人工完成
- **修改 CI 配置文件**：不允许通过修改 CI 配置绕过检查，根本原因必须修复
- **UI / 仪表盘**：当前版本不提供可视化界面，通过 GitHub Actions 日志和 PR 评论追踪状态

---

## 四、解决方案概述

docker-images-workflow 是一套以 **GitHub Actions 为编排引擎、AI 大模型为执行者**的 CI 失败自动修复流水线。

### 4.1 核心设计思想

**两阶段流水线 + 知识库反馈：**

```
分析阶段 (ci-log-analysis)
  AI 诊断师阅读日志 → 参考历史知识库 → 输出结构化诊断报告
                                                  ↓
修复阶段 (code-fix)
  AI 修复工程师读取报告 → 在源码中最小化修改 → commit + push
                                                  ↓
Fix PR CI 通过 → 写入知识库 → 下次同类失败置信度更高
```

**分离关注点：**
- 诊断师只做分析，不做修改，输出报告即完成职责
- 修复工程师只看报告，不分析日志，只改代码
- 知识库在 main 分支持久化，跨 PR 共享

**自管理生命周期：**
- Fix PR 失败自动重试，无需人工干预
- 超过重试上限自动收敛，不无限循环
- 通过 CI 自动通知，维护者只需最终确认

### 4.2 完整生命周期

```
目标仓库 PR 获得 ci_failed label
         ↓
Monitor (stream-pr-events) 定时轮询
   ├─ 跳过规则过滤（预发布/fix PR/已有成功修复）
   └─ 决策：dispatch ci-log-analysis
         ↓
Stage 1: ci-log-analysis
   ├─ 拉取 PR diff
   ├─ 定位失败 CI 日志 URL（逐行解析评论表格，过滤编排层）
   ├─ 读取历史知识库
   ├─ AI 诊断师分析 → ci-analysis.md
   ├─ 写入 ci-fix-log 分支
   └─ dispatch code-fix
         ↓
Stage 2: code-fix
   ├─ 读取 ci-analysis.md
   ├─ AI 修复工程师实施最小化修复
   ├─ git commit → push fix 分支
   ├─ 创建 Fix PR（已存在则追加 commit）
   └─ 写入 code-fix-summary.md
         ↓
Fix PR CI 结果
   ├─ ci_successful → 评论原始 PR，通知 review + 更新知识库 ✅
   ├─ ci_processing → 等待下次轮询
   ├─ ci_failed（< 6次）→ 重新进入 ci-log-analysis（用 Fix PR 评论查日志）
   └─ ci_failed（≥ 6次）→ 关闭 Fix PR，评论通知人工介入 ⚠️
```

---

## 五、功能需求

### 5.1 PR 监控（Monitor）

| 需求 ID | 需求描述 | 优先级 |
|---------|---------|--------|
| MON-01 | 按 `poll_interval_minutes` 定时运行，扫描所有 `watched_repos` 中启用的仓库 | Must |
| MON-02 | 识别带有 `ci_failed` label 的 PR（label 名称可配置） | Must |
| MON-03 | 根据 Fix PR 状态决策动作，状态包括：不存在、open+各种状态标签、closed、merged | Must |
| MON-04 | 通过时间窗口（`lookback_minutes`）过滤，避免处理过旧的 PR | Must |
| MON-05 | 检测预发布版本（alpha/beta/rc/preview/dev/snapshot/nightly）并跳过 | Must |
| MON-06 | 跳过以 `fix:` 开头的 PR 标题，避免递归触发 | Must |
| MON-07 | 已有 open + ci_successful 的修复 PR 时，跳过原始 PR | Should |
| MON-08 | 每次运行最多处理 `max_events_per_run` 条 PR，防止 Action 超时 | Should |

### 5.2 CI 日志分析（ci-log-analysis）

| 需求 ID | 需求描述 | 优先级 |
|---------|---------|--------|
| ANA-01 | 获取 PR 的完整 diff | Must |
| ANA-02 | 从 PR 评论中提取 CI 构建 URL，过滤编排层（/trigger/、/gate/、/pre-check/） | Must |
| ANA-03 | 逐行解析评论 HTML 表格，只取同行标记为 FAILED 的 URL | Must |
| ANA-04 | 含架构标识的 URL（x86-64、aarch64 等）优先选取 | Must |
| ANA-05 | 获取日志末尾 500 行（尾部优先截取策略） | Must |
| ANA-06 | 日志末尾显示成功（Finished: SUCCESS）时，标记证据不足，不强行分析 | Must |
| ANA-07 | 重试时从 Fix PR 评论中查找最新构建 URL（而非原始 PR） | Must |
| ANA-08 | 参考 `docs/ci-failure-patterns.md` 知识库，识别已知模式或标注新模式 | Should |
| ANA-09 | 输出包含失败类型、置信度、根因定位、修复方向的结构化报告 | Must |
| ANA-10 | 报告写入 ci-fix-log 分支的 `ci-fix-log/{pr_number}/ci-analysis.md` | Must |

### 5.3 代码修复（code-fix）

| 需求 ID | 需求描述 | 优先级 |
|---------|---------|--------|
| FIX-01 | 从 ci-fix-log 分支读取诊断报告（不通过环境变量传递） | Must |
| FIX-02 | 严格限制只修改原始 PR 涉及的文件 | Must |
| FIX-03 | 修复前清理工作目录中的 AI 工具产物 | Must |
| FIX-04 | 修复后清理暂存区，确保只提交 PR 涉及文件 | Must |
| FIX-05 | AI 判断无需代码修改时（infra-error），不做强制提交，输出说明 | Must |
| FIX-06 | 写入修复摘要到 ci-fix-log 分支 | Must |
| FIX-07 | Fix PR 已存在时追加 commit，不创建新 PR | Must |

### 5.4 知识库管理

| 需求 ID | 需求描述 | 优先级 |
|---------|---------|--------|
| KB-01 | Fix PR 通过 CI（获得 ci_successful label）时触发知识库更新 | Must |
| KB-02 | 根据分析报告的"知识库匹配"字段，判断追加到已有模式或新建模式 | Must |
| KB-03 | 知识库写入 main 分支的 `docs/ci-failure-patterns.md` | Must |
| KB-04 | 已通知原始 PR 后，标记 fix-notified，避免重复通知 | Should |

### 5.5 镜像创建（create-image）

除 CI 失败修复外，系统还包含第二条独立流水线：为新增上游软件包**自动生成镜像文件并提交 PR**，覆盖"从 Issue 请求到镜像上线"的另一类重复性维护工作。

**Issue 监控：**

| 需求 ID | 需求描述 | 优先级 |
|---------|---------|--------|
| ISW-01 | 按小时级 cron 定时运行，扫描 `issue-watchlist.json` 中启用的仓库 | Must |
| ISW-02 | 识别标题包含触发关键词（默认「【new-image】」）的 open issue | Must |
| ISW-03 | 从 issue 标题和正文解析出软件包名、源码仓库 URL、所属领域 | Must |
| ISW-04 | 按所属领域自动映射到目标分类目录（如"云原生"→`Cloud`） | Must |
| ISW-05 | 用本地 state 文件（`dispatched_issues.json`）按 issue 号去重，避免重复触发 | Must |
| ISW-06 | 每次运行最多处理 `max_events_per_run` 条 issue，防止 Action 超时 | Should |
| ISW-07 | 解析信息不足（无法提取包名或源码仓库）时跳过，不强行 dispatch | Must |

**镜像文件生成：**

| 需求 ID | 需求描述 | 优先级 |
|---------|---------|--------|
| IMG-01 | 克隆目标仓库的 Fork，在本地生成 Dockerfile、meta.yml、README.md、doc/image-info.yml、logo | Must |
| IMG-02 | 自动研究上游软件包的最新版本、构建语言、License、依赖信息 | Must |
| IMG-03 | 参考仓库内同分类目录下的已有软件包，保持文件风格与规范一致 | Must |
| IMG-04 | Dockerfile 必须同时支持 amd64 和 arm64 架构 | Must |
| IMG-05 | 只创建新文件，不修改仓库内任何已有软件包的文件 | Must |
| IMG-06 | 更新对应分类目录下的 `image-list.yml` 索引 | Must |
| IMG-07 | 生成结果以 commit 形式提交到独立的 `add-{package_name}` 分支，并自动创建 PR | Must |
| IMG-08 | PR 正文关联原始 issue（`Closes #{issue_number}`） | Must |
| IMG-09 | 生成成功后在原始 issue 评论 PR 链接并打 `image-created` label；失败则评论说明并附 workflow 日志链接 | Must |
| IMG-10 | Logo 缺失官方图时需 fallback 生成占位图，不得使用 AI 生成图像 | Should |

---

## 六、非功能需求

### 6.1 可靠性

- Monitor 轮询失败时，不影响其他仓库的处理（按仓库隔离错误）
- 同一 PR 的修复链路串行执行（`concurrency` 配置），避免并发冲突
- ci-log-analysis 和 code-fix 任一阶段失败，均记录错误日志，不静默失败

### 6.2 安全性

- Fix PR 提交的代码变更严格限定在原始 PR 文件范围内
- AI 工具产物（.claude、.opencode 等）不进入 Fix PR
- 敏感凭证（Token、API Key）通过 GitHub Secrets 传入，不硬编码
- GitCode 操作使用专用 `GITCODE_TOKEN`，不复用 GitHub Token

### 6.3 可扩展性

- 新增监控仓库只需修改 `config/watchlist.json`，无需改代码
- 新增代码托管平台只需在 `scripts/lib/` 下新增 `ci_{platform}_api.py` 并注册工厂
- AI 后端可通过 `AI_RUNNER` 环境变量切换，无需修改业务逻辑

### 6.4 可观测性

- 每个处理步骤输出带时间戳的结构化日志
- GitHub Actions 日志完整记录决策路径（为什么跳过、为什么 dispatch）
- 诊断报告和修复摘要持久化在 ci-fix-log 分支，可事后追溯

### 6.5 测试覆盖

- 核心算法（URL 评分、跳过规则、标题提取）需有单元测试覆盖
- 测试用例覆盖边界条件（空输入、混合 SUCCESS/FAILED 表格、软件名边界等）

---

## 七、成功指标

| 指标 | 目标 | 说明 |
|------|------|------|
| **自动修复成功率** | ≥ 60% | 在 6 次重试内成功通过 CI 的 Fix PR 占所有触发修复的 PR 比例 |
| **平均修复时间** | ≤ 30 分钟 | 从 ci_failed 到 Fix PR 创建的时间（不含 CI 运行时间） |
| **知识库准确率** | ≥ 90% | 知识库中已知模式在后续同类失败中被正确匹配的比例 |
| **误触发率** | ≤ 5% | 预发布版本或 Fix PR 被误触发修复的比例 |
| **维护者工作量削减** | ≥ 50% | 维护者实际需要人工处理的 CI 失败 PR 比例（相比无工作流时） |

---

## 八、约束与边界

### 8.1 前置约束

- 目标仓库的 CI 系统必须在 PR 上使用标准化 label（`ci_failed`、`ci_processing`、`ci_successful`）
- Jenkins 多架构构建的 URL 必须出现在 PR 评论的 HTML 表格中（openEuler CI 的标准行为）
- Fix PR 的创建者必须对目标仓库有 fork 权限（GitCode）或 push 权限

### 8.2 已知限制

- 对于日志完全不可访问（需要 VPN 或私有认证）的 CI 系统，日志分析阶段会降级为"证据不足"
- 对于需要修改原始 PR 未涉及文件的修复（如新增 Dockerfile 依赖文件），当前版本不支持
- 修复逻辑依赖 AI 模型能力，对罕见的构建失败模式效果有限

### 8.3 范围边界

| 在范围内 | 在范围外 |
|---------|---------|
| 容器镜像仓库的 Dockerfile 类 CI 失败修复 | 一般软件项目的 CI 修复（不排除，但未专门优化） |
| GitCode 和 GitHub 仓库 | GitLab 自托管实例（架构支持扩展，未实现） |
| 版本升级类 PR | 功能开发类 PR 的 CI 失败（不会跳过，但修复效果未专门评估） |
| 修复 Dockerfile、构建脚本等构建相关文件 | 修复业务代码逻辑（不受限，但 AI 能力是瓶颈） |
