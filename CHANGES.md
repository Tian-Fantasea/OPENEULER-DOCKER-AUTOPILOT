# OPENEULER-DOCKER-AUTOPILOT Tian Fork 修改记录

## 1. Git remote
- 原始: `git@github.com:opensourceways/openeuler-docker-autopilot.git`
- 改为: `git@github.com:Tian-Fantasea/OPENEULER-DOCKER-AUTOPILOT.git`

## 2. runs-on 改动
以下 5 个文件共 6 处，`runs-on: self-hosted` → `runs-on: ubuntu-latest`：

| 文件 | 行号 |
|------|------|
| `.github/workflows/watch-issues.yml` | 23 |
| `.github/workflows/create-image-trigger.yml` | 48 |
| `.github/workflows/sync-poll-interval.yml` | 17 |
| `.github/workflows/pr-ci-fix-trigger.yml` | 33, 116 |
| `.github/workflows/stream-pr-events.yml` | 21 |

> 如后续部署了自己的 self-hosted runner，改回 `runs-on: self-hosted` 即可。

## 3. config/issue-watchlist.json
- `fork_repo`: `sunshuang1866/openeuler-docker-images` → `Tian-Fantasea/openeuler-docker-images`
- `enabled`: 保持 `false`

## 4. 新增镜像构建与测试功能

### 新增文件
| 文件 | 说明 |
|------|------|
| `.github/agents/image-tester.md` | AI Agent 提示词，根据 Dockerfile 生成定制功能测试脚本 test.sh |
| `scripts/stages/image-test.py` | 测试执行阶段：AI 生成 test.sh → docker build → docker run → 通用测试 → 执行 test.sh → 清理 |
| `scripts/lib/docker_test.py` | Docker 操作工具库：build_image / run_container / exec_command / wait_for_container / get_image_size / cleanup |

### 修改文件
| 文件 | 改动 |
|------|------|
| `.github/workflows/create-image-trigger.yml` | 在 step 6 和 step 7 之间插入 step 6.5 "Build and test image"；step 7 和 step 8 的 if 条件加 `steps.image_test.outputs.passed == 'true'`；step 9 增加 TEST_ERROR 环境变量和测试失败的评论内容 |
| `.github/agents/image-creator.md` | 步骤 11 输出 JSON 新增 `dockerfile_path` 和 `binary_name` 字段 |
| `scripts/stages/create-image.py` | GITHUB_OUTPUT 新增 `dockerfile_path` 和 `binary_name` 输出 |

### 测试流程
```
AI 生成 Dockerfile + 镜像文件
    ↓
AI 生成 test.sh（定制功能测试）
    ↓
docker build 构建镜像（通用测试）
    ↓
docker run 启动容器（通用测试）
    ↓
通用测试：容器存活 + 镜像大小检查
    ↓
执行 test.sh：版本验证 + 端口监听 + 功能验证
    ↓
全部通过 → push + 创建 PR
部分失败 → 回复 issue 报错，不提 PR
```
