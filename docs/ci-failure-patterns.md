# CI 失败模式知识库

> **按失败模式分类**，每个模式包含：典型报错、根因分析、修复方法、历史案例。  
> 处理新失败 PR 时，**用报错关键词搜索对应章节**，直接找到修复方法。

---

## 模式01：Apache CDN Maven 版本 404

**症状关键词**: `dlcdn.apache.org` `404 Not Found` `maven`

**根因**: `dlcdn.apache.org` 只托管当前最新版 Maven，旧版本下架后返回 404。

**典型报错**:
```
> [3/7] RUN wget https://dlcdn.apache.org/maven/maven-3/3.9.14/binaries/apache-maven-3.9.14-bin.tar.gz
0.110 --2026-05-11 02:46:31--  https://dlcdn.apache.org/maven/maven-3/3.9.14/binaries/...
404 Not Found
0.297 2026-05-11 02:46:31 ERROR 404: Not Found.
------
Dockerfile:12
```

**修复方法**（两种，按情况选择）:
1. **换镜像站**：将下载源改为 `repo.huaweicloud.com/apache/maven/maven-3/` 或 `archive.apache.org/dist/maven/`，保留历史版本
2. **升级版本**：将 `MAVEN_VERSION` 升为 Apache CDN 当前可用版本（如 3.9.14、3.9.12）

**历史案例**:
- PR #2265: `Others/netty/4.2.13` — Maven 3.9.14 在 CDN 404 → 换华为云镜像站
- PR #2100: `Others/netty/4.2.12` — Maven 3.9.12 在 CDN 404 → 升级到 3.9.14
- PR #1884: `Others/netty/4.2.10` — Maven 3.9.11 在 CDN 404 → 升级到 3.9.12，文件名改用变量
- PR #2926: `Others/spring-framework/7.0.3/24.03-lts-sp4/Dockerfile` — Maven 3.9.12 从 `dlcdn.apache.org` CDN 下架导致下载 404，将下载源替换为 Apa

---

## 模式02：下载 URL 硬编码版本路径错误 / 软件包版本不存在

**症状关键词**: `404 Not Found` `wget` `does not exist`

**根因**: URL 中版本目录路径硬编码（如目录写 `3.2` 但下载 `3.3.0`），或上游已停止对该平台版本提供制品。

**典型报错**:
```
> [4/6] RUN wget https://www.haproxy.org/download/3.2/src/haproxy-3.3.0.tar.gz
0.069 --2026-05-11 01:59:16--  https://www.haproxy.org/download/3.2/src/haproxy-3.3.0.tar.gz
404 Not Found
1.240 2026-05-11 01:59:17 ERROR 404: Not Found.
```

**修复方法**:
1. **动态生成 URL**：从 `VERSION` 变量中提取主次版本号（如 `${VERSION%.*}`）构造正确路径，替代硬编码
2. **换归档源 + 修正组合**：Phoenix 类问题需同时换用 `archive.apache.org/dist` 并修正平台标识（如 hbase-2.4 → hbase-2.5）

**历史案例**:
- PR #2267: `Others/haproxy/3.3.0` — URL 目录写 `3.2`，应为动态生成
- PR #1932: `Database/phoenix/5.3.0` — `phoenix-hbase-2.4-5.3.0-bin.tar.gz` 不存在（Phoenix 5.3.0 已弃 HBase 2.4） → 换 `archive.apache.org` + `hbase-2.5`
- PR #2659: `Database/redis/5.4.1/24.03-lts-sp3/Dockerfile` — CI 构建失败：Dockerfile 中 `ARG VERSION=5.4.1` 指定的 Redis 版本不存在（Git
- PR #2731: `Others/mongoose/7.22/24.03-lts-sp3/Dockerfile` — Dockerfile 中 `ARG VERSION=7.22` 引用的上游 Git tag `7.22` 在 `cesa

---

## 模式03：JDK / 二进制包版本在镜像站不存在（404）

**症状关键词**: `Adoptium` `OpenJDK` `404 Not Found` `mirrors.tuna`

**根因**: Dockerfile 中硬编码了 JDK 的具体 build 号（如 `11.0.28_6`），但镜像站只保留当前 build，旧 build 被覆盖后 404。

**典型报错**:
```
#10 0.087 --2026-04-06 01:14:48--  https://mirrors.tuna.tsinghua.edu.cn/Adoptium/11/jre/x64/linux/OpenJDK11U-jre_x64_linux_hotspot_11.0.28_6.tar.gz
#10 0.317 Connecting to mirrors.tuna.tsinghua.edu.cn|101.6.15.130|:443... connected.
#10 0.503 HTTP request sent, awaiting response... 404 Not Found
```

**修复方法**: 将 JDK 版本升级为 Adoptium/镜像站当前实际可用的 build（查询镜像站目录确认版本号后再提交）。

**历史案例**:
- PR #2105: `Bigdata/kyuubi/1.11.1` — JDK 11.0.28_6 404 → 升级到 11.0.30_7

---

## 模式04：镜像站 403（访问被拒）

**症状关键词**: `403 Forbidden` `mirrors.ustc.edu.cn`

**根因**: 部分镜像站（如 USTC）对 CI 构建环境的请求触发防爬限制，返回 403。

**典型报错**:
```
wget https://mirrors.ustc.edu.cn/gnu/gcc/gcc-15.2.0/gcc-15.2.0.tar.gz
--2026-04-24 14:21:05--  https://mirrors.ustc.edu.cn/gnu/gcc/gcc-15.2.0/gcc-15.2.0.tar.gz
Connecting to mirrors.ustc.edu.cn|202.141.160.110|:443... connected.
HTTP request sent, awaiting response... 403 Forbidden
2026-04-24 14:21:06 ERROR 403: Forbidden.
```

**修复方法**: 将下载源从 `mirrors.ustc.edu.cn` 替换为 `mirrors.tuna.tsinghua.edu.cn`（清华镜像站对 CI 环境兼容性更好）。

**历史案例**:
- PR #2212: `Others/gcc/16.1.0` — USTC 403 → 清华镜像站

---

## 模式05：groupadd / useradd: command not found（缺 shadow-utils）

**症状关键词**: `groupadd: command not found` `useradd: command not found`

**根因**: `openeuler:24.03-lts-sp3` 基础镜像默认**不包含** `shadow-utils`，导致 `groupadd`/`useradd` 命令不存在。

**典型报错**:
```
49.71 /bin/sh: line 1: groupadd: command not found
```

**修复方法**: 在 Dockerfile 的第一个 `dnf install` 步骤中添加 `shadow` 包（openEuler 中 shadow-utils 的包名为 `shadow`）。

```dockerfile
RUN dnf install -y shadow python3-pip ...
```

**历史案例**:
- PR #2266: `AI/mlflow/3.12.0`
- PR #2164: `AI/mlflow/3.11.1`
- PR #1858: `AI/mlflow/3.9.0` — 同类问题，两架构均失败

---

## 模式06：COPY 目标文件不存在（env2yaml 二进制未提交到仓库）

**症状关键词**: `failed to calculate checksum` `not found` `env2yaml`

**根因**: Dockerfile 中 `COPY env2yaml/env2yaml-amd64 /usr/local/bin/env2yaml` 引用的二进制文件**未随 Dockerfile 一起提交**到仓库。

**典型报错**:
```
#15 [11/13] COPY env2yaml/env2yaml-amd64 /usr/local/bin/env2yaml
#15 ERROR: failed to calculate checksum of ref kzw8fcgm9psa1a0kbi7cp9fx0::...: "/env2yaml/env2yaml-amd64": not found
```

**修复方法**: 在同一目录下补充提交 `env2yaml/env2yaml-amd64` 和 `env2yaml/env2yaml-arm64` 两个架构的二进制文件。

**历史案例**:
- PR #2264: `Bigdata/logstash/9.4.0`
- PR #2206: `Bigdata/logstash/9.3.4`
- PR #2163: `Bigdata/logstash/9.3.3`
- PR #2743: `HPC/seissol/202103.Sumatra/24.03-lts-sp3/Dockerfile` — SeisSol 202103.Sumatra 的 CMakeLists.txt 无 `install()` 目标，`cm

---

## 模式07：Maven 版本不满足项目 enforcer 约束

**症状关键词**: `RequireMavenVersion` `is not in the allowed range` `maven-enforcer`

**根因**: 项目的 `maven-enforcer-plugin` 指定了最低 Maven 版本要求（如 `[3.9.11,)`），而 Dockerfile 中安装的 Maven 版本（如 3.9.1）低于该要求。

**典型报错**:
```
#8 69.10 [ERROR] Rule 5: org.apache.maven.enforcer.rules.version.RequireMavenVersion failed with message:
#8 69.10 [ERROR] Detected Maven Version: 3.9.1 is not in the allowed range [3.9.11,).
#8 69.10 [ERROR] -> [Help 1]
#8 ERROR: process "/bin/sh -c git clone -b ${VERSION} ... && mvn clean install ..." did not complete successfully: exit code: 1
```

**修复方法**: 将 Dockerfile 中的 Maven 版本从旧版（如 3.9.1）升级到满足约束的版本（如 3.9.14）。注意同时确认新版 Maven 在 `dlcdn.apache.org` 可用（否则参考模式01换源）。

**历史案例**:
- PR #2207: `Database/neo4j/2026.04.0` — 要求 >= 3.9.11，安装了 3.9.1 → 升级到 3.9.14
- PR #2102: `Database/neo4j/2026.03.1` — 同类问题 → 升级到 3.9.14

---

## 模式08：cmake patch hunk 应用失败（上游代码变更导致偏移量不匹配）

**症状关键词**: `Hunk #N FAILED` `patch unexpectedly ends` `.rej` `cmake_curl.patch`

**根因**: 补丁文件（如 `cmake_curl.patch`）是针对特定版本上游代码生成的，上游代码更新后行号偏移，导致 `patch` 命令 hunk 应用失败。

**典型报错**:
```
#13 0.064 patching file cmake/external.cmake
#13 0.064 Hunk #1 succeeded at 937 (offset 43 lines).
#13 0.064 patch unexpectedly ends in middle of line
#13 0.064 Hunk #2 FAILED at 1099.
#13 0.064 1 out of 2 hunks FAILED -- saving rejects to file cmake/external.cmake.rej
#13 ERROR: process "/bin/sh -c patch -Np1 < cmake_curl.patch && ./build.sh" did not complete successfully: exit code: 1
```

**修复方法**: 针对目标版本的实际上游源码**重新生成** patch 文件（`git diff` 生成），一并更新 Dockerfile 和 build.sh。

**历史案例**:
- PR #2209: `Database/tdengine/3.4.1.7` — cmake/external.cmake 行号偏移 43 行
- PR #2104: `Database/tdengine/3.4.1.1` — 同类问题

---

## 模式09：BuildKit 预定义变量 BUILDARCH 冲突

**症状关键词**: `BUILDARCH` `amd64` `404` `if [ "amd64" = "amd64" ]`

**根因**: `BUILDARCH` 是 BuildKit 的**预定义全局 ARG**（值为 `amd64`/`arm64`），在 `RUN` 中对其重新赋值（如 `BUILDARCH="x64"`）不会生效——BuildKit 会恢复为内置值，导致用错误架构字符串构造下载 URL，产生 404。

**典型报错**:
```
> [4/5] RUN if [ "amd64" = "amd64" ]; then BUILDARCH="x64"; ...
0.285 HTTP request sent, awaiting response... 404 Not Found
0.353 2026-05-04 00:12:49 ERROR 404: Not Found.
```

**修复方法**: 将变量名从 `BUILDARCH` 改为其他自定义名称（如 `MY_ARCH`、`JAVA_ARCH`），避免与 BuildKit 预定义变量冲突。

**历史案例**:
- PR #2211: `Others/spring-cloud/5.0.1`
- PR #2105: `Bigdata/kyuubi/1.11.1`（与 JDK 版本 404 叠加）

---

## 模式10：缺少构建依赖（CMake / configure 找不到系统库）

**症状关键词**: `Could NOT find` `cmake` `configure: error` `missing:` `-devel`

**根因**: Dockerfile 的 `dnf install` 步骤遗漏了编译所需的 `-devel` 库包，cmake/autoconf 配置阶段报错。

**典型报错（示例）**:
```
# libxml2 缺失
CMake Error: Could NOT find LibXml2 (missing: LIBXML2_LIBRARY LIBXML2_INCLUDE_DIR)

# PCRE 缺失
./configure: error: the HTTP rewrite module requires the PCRE library.

# protobuf-c 缺失
./configure: error: protoc-c not found. Please install protobuf-c-compiler package.

# MySQL Boost 缺失（表现为 CURL 报错，实为 Boost 未配置）
-- Could NOT find CURL (missing: CURL_LIBRARY CURL_INCLUDE_DIR)
```

**修复方法**: 根据报错的库名，在 `dnf install` 中补充对应的 `-devel` 包：

| 报错 | 需安装的包 |
|------|-----------|
| `LibXml2` not found | `libxml2-devel` |
| PCRE library required | `pcre pcre-devel` |
| `protoc-c` not found | `protobuf-c-compiler protobuf-c-devel` |
| MySQL Boost 未配置 | cmake 参数加 `-DDOWNLOAD_BOOST=1 -DWITH_BOOST=/tmp/boost` |

**历史案例**:
- PR #2210: `Others/wireshark/4.6.5` — 缺 `libxml2-devel`
- PR #2162: `Cloud/nginx/1.30.0` — 缺 `pcre pcre-devel`
- PR #1933: `Others/rsyslog/8.2602.0` — 缺 `protobuf-c-compiler protobuf-c-devel`
- PR #2205: `Database/mysql/9.7.0` — Boost 未配置，cmake 加 `-DDOWNLOAD_BOOST=1`
- PR #2512: `Storage/3fs/22fca04/24.03-lts-sp3/Dockerfile` — 修复 3FS Dockerfile 中的三个构建错误：运行时包名不存在（boost-foundation）、缺少构建依赖

---

## 模式11：YAML / 元数据文件错误

**症状关键词**: `yaml.parser.ParserError` `expected '<document start>'` `version_suffix` `image-list.yml`

**根因**: 元数据文件（`meta.yml`、`image-info.yml`、`image-list.yml`）存在格式错误或字段名错误，导致 CI 预检阶段解析失败或一致性校验不通过。

**典型报错**:
```
yaml.parser.ParserError: expected '<document start>', but found '<block mapping start>'
  in "Others/fastjson/meta.yml", line 6, column 1
Build step 'Execute shell' marked build as failure
Finished: FAILURE
```

**修复方法**:

| 问题类型 | 修复操作 |
|---------|---------|
| YAML block mapping 格式错误 | 修正缩进或文档分隔符（`---`） |
| 字段名拼写错误 | 检查 CI schema，如 `version_suffix` → `version_prefix` |
| image-list.yml 条目遗漏 | 向对应的 `image-list.yml` 补充缺失的镜像条目 |
| 元数据包含不可用版本 | 从 `image-info.yml` 移除 beta/不稳定版本条目 |

**历史案例**:
- PR #2268: `Others/fastjson/meta.yml` — YAML 格式错误（block mapping start）
- PR #2270: `AI/diskann/doc/image-info.yml` — 字段名 `version_suffix` → `version_prefix`
- PR #2262: `Bigdata/image-list.yml` — 7 条镜像条目缺失
- PR #2269: `Database/milvus/doc/image-info.yml` — 包含不稳定 `3.0-beta` 版本条目
- PR #2512: `.claude/agents/README.md` — CI appstore 路径校验失败：`.claude/agents/README.md` 不在期望路径 `.claud
- PR #2512: `.claude/agents/README.md` — CI appstore 发布规范预检失败：`.claude/agents/README.md` 路径不符合预期，要求 R
- PR #2512: `.claude/README.md` — CI appstore 发布规范预检失败：`.claude/agents/README.md` 路径不符合规范，CI 期
- PR #2512: `.claude/README.md` — CI appstore 发布规范检查要求 `.claude/` 工具目录的 README 文件位于根层级 `.claud
- PR #2512: `.claude/agents/README.md` — CI appstore 发布规范预检要求 `.claude/README.md` 位于 `.claude/` 根目录，而
- PR #2512: `.claude/README.md` — CI appstore 预检失败：`.claude/agents/README.md` 路径不符合规范，期望位置为 `.
- PR #2512: `.claude/agents/README.md` — CI appstore 发布规范预检失败：`.claude/agents/README.md` 路径不符合规范，期望路径

---

## 模式12：上游代码目录结构变更（requirements / 配置路径迁移）

**症状关键词**: `No such file or directory` `requirements` `Could not open requirements file`

**根因**: 上游项目重组了目录结构，Dockerfile 中 `COPY` 或 `pip install -r` 引用的路径已失效。

**典型报错**:
```
#12 [build 1/2] RUN pip install -r requirements/cpu-build.txt
#12 0.668 ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements/cpu-build.txt'
#12 ERROR: process "/bin/sh -c pip install -r requirements/cpu-build.txt" did not complete successfully: exit code: 1
```

**修复方法**: 查看上游仓库对应版本的实际目录结构，更新 Dockerfile 中的路径引用。

**历史案例**:
- PR #2204: `AI/vllm-cpu/0.20.1` — requirements 从 `requirements/cpu-build.txt` 迁移到 `requirements/build/cpu.txt`

---

## 模式13：Shell 命令替换语法错误（$cmd 误写为命令）

**症状关键词**: `$nproc` `UndefinedVar` `make: *** Error 2`

**根因**: `nproc` 是 Shell 命令而非变量，`$nproc` 展开为空字符串，导致 make 使用默认并行数或产生语法错误。

**典型报错**:
```
make: *** [Makefile:156: all] Error 2
- UndefinedVar: Usage of undefined variable '$LD_LIBRARY_PATH' (line 16)
```

**修复方法**: 将 `$nproc` 改为 `$(nproc)`（命令替换），或使用 `${NPROC:-$(nproc)}` 以支持外部覆盖。

**历史案例**:
- PR #2208: `Others/snort3/3.12.2.0` — `make -j $nproc` → `make -j $(nproc)`

---

## 模式14：pip 版本不兼容（pip 26.0 移除 API）

**症状关键词**: `AttributeError` `allow_all_prereleases` `PackageFinder` `pip`

**根因**: SPDK 等项目的 `pkgdep.sh` 在创建 Python venv 时使用 `--upgrade-deps` 将 pip 升级到 26.0，而 `pip-tools 7.5.2` 调用了 pip 26.0 中已删除的 `PackageFinder.allow_all_prereleases` 属性。

**典型报错**:
```
AttributeError: 'PackageFinder' object has no attribute 'allow_all_prereleases'
(x86_64 和 aarch64 的 check_build 均失败)
```

**修复方法**: 在 Dockerfile 中，运行 `pkgdep.sh` 前用 `sed` 删除脚本中的 `--upgrade-deps` 参数，使 venv 保留系统 pip 版本（与 pip-tools 兼容）：

```dockerfile
RUN sed -i 's/--upgrade-deps//g' scripts/pkgdep/rhel.sh && ./pkgdep.sh
```

**历史案例**:
- PR #1856: `Others/spdk/26.01` — pip-tools 7.5.2 与 pip 26.0 不兼容

---

## 模式15：编译错误——AVX512BF16 缺少 fallback 分支

**症状关键词**: `incomplete type` `qk_vec_type` `void` `AVX512BF16` `BFloat16`

**根因**: `KernelVecType<c10::BFloat16>` 只特化了 `__AVX512BF16__`/`__s390x__`/`__aarch64__` 三个分支，无 `#else`，导致在普通 x86_64（无 AVX512BF16 指令集支持）上 `qk_vec_type` 解析为 `void`，编译器报错。

**典型报错**:
```
error: incomplete type 'qk_vec_type' {aka 'void'} used in nested name specifier
```

**修复方法**: 在 Dockerfile 的 `git clone` 后，用 Python/sed patch 步骤应用 vllm-project/vllm PR #34052 的修复：将两个相同的 `#elif` 分支合并为单一 `#else`，使所有非 AVX512BF16 平台共用 `FP32Vec16` 计算路径。

**历史案例**:
- PR #1934: `AI/vllm-cpu/0.16.0`

---

## 模式16：RPM 包停止发布（换多阶段构建绕过）

**症状关键词**: `does not publish RPM` `RPM releases stopped` `404` RPM 下载

**根因**: 上游项目在某版本后停止了 RPM 包发布，CI 尝试下载时失败。

**修复方法**: 改用多阶段 Docker 构建，直接从官方 Docker 镜像中 `COPY` 二进制文件，替代从 RPM 安装：

```dockerfile
FROM grafana/agent:v0.44.7 AS agent-source
FROM openeuler/openeuler:24.03-lts-sp3
COPY --from=agent-source /bin/grafana-agent /usr/local/bin/grafana-agent
```

**历史案例**:
- PR #1857: `Cloud/grafana-agent/0.44.7` — v0.44.2 后无 RPM 发布

---

## 模式17：Copyright / SPDX 声明缺失

**症状关键词**: `check_package_license` `Copyright` `SPDX` `license check`

**根因**: 新增文件（Dockerfile、README.md、meta.yml、image-info.yml）未包含 Copyright 和 SPDX-License-Identifier 头，CI `check_package_license` 检查未通过。

**修复方法**: 为每类文件添加对应格式的版权头：

```dockerfile
# Copyright (c) Huawei Technologies Co., Ltd. 2024-2024. All rights reserved.
# SPDX-License-Identifier: MulanPSL-2.0
```

```markdown
<!-- Copyright (c) Huawei Technologies Co., Ltd. 2024-2024. All rights reserved. -->
<!-- SPDX-License-Identifier: MulanPSL-2.0 -->
```

**历史案例**:
- PR #2516: `AI/vllm-cpu/0.22.1` — 4 个新增文件均缺少 Copyright + SPDX 头

---

## 模式18：git 浅克隆与 commit hash checkout 不兼容

**症状关键词**: `--depth 1` `git checkout` `commit hash` `2>/dev/null || true`

**根因**: `git clone --depth 1` 只拉取最新提交，历史 commit hash 不在浅克隆的可访问范围内；同时 `|| true` 静默掩盖了错误，导致 checkout 实际失败但构建继续，产生错误的构建结果。

**修复方法**: 将 checkout 逻辑从 `git checkout ${VERSION} 2>/dev/null || true` 改为先 `git fetch origin ${VERSION}` 再 `git checkout ${VERSION}`，或去掉 `--depth 1` 改为完整克隆。

**历史案例**:
- PR #2512: `Storage/3fs/22fca04` — `--depth 1` + commit hash checkout 不兼容
- PR #2512: `Storage/3fs/22fca04/24.03-lts-sp3/Dockerfile` — `git clone --depth 1` 浅克隆后无法 checkout 指定 commit hash，导致 3FS 
- PR #2512: `Storage/3fs/22fca04/24.03-lts-sp3/Dockerfile:22-24` — `git clone --depth 1` 浅克隆后无法 checkout 指定 commit hash `22fca0

---

## 模式19：证据不足 / 无法定位根因

适用于 CI 日志无法获取、PR 描述过于简略的情况，优先通过 diff 推断修复意图。

**历史案例**:
- PR #2489: `AI/diskann/0.52.0` — VERSION 变量引用方式有误（diff 推断）
- PR #2308: `AI/diskann/README.md` — 纯文档修正
- PR #1768: `Others/spring-cloud/5.0.0` — Dockerfile 重写，具体错误信息缺失

---

## 模式20：ENV自引用未定义变量

**症状关键词**: UndefinedVar, LD_LIBRARY_PATH, ENV

**根因**: Dockerfile `ENV LD_LIBRARY_PATH=...:$LD_LIBRARY_PATH` 在首次定义该变量的阶段自引用了尚未存在的 `$LD_LIBRARY_PATH`，BuildKit 检测到对未定义变量的引用，产生 `UndefinedVar` 警告。

**修复方法**: 将 `$LD_LIBRARY_PATH` 改为 `${LD_LIBRARY_PATH:-}`（shell 默认值语法），变量未定义时展开为空字符串，消除 BuildKit 警告：

```dockerfile
ENV LD_LIBRARY_PATH=/usr/local/lib:/libyuv/build:${LD_LIBRARY_PATH:-}
```

**历史案例**:
- PR #2546: `Others/libyuv/1948/24.03-lts-sp3/Dockerfile` — `ENV LD_LIBRARY_PATH=...:$LD_LIBRARY_PATH` 自引用未定义变量，改为 `${LD_LIBRARY_PATH:-}` 消除 BuildKit UndefinedVar 警告

---

## 模式21：NEON符号缺失链失败

**症状关键词**: undefined reference, RGBToUVMatrixRow_NEON, collect2: error, ld returned 1 exit status, aarch64

**根因**: libyuv 某版本的 `row.h` 在 aarch64 条件块内定义了 `HAS_RGBTOUVMATRIXROW_NEON` 宏，但 `row_neon64.cc` 和 `row_neon.cc` 中均只有 `ARGBToUVMatrixRow_NEON`，缺少不带 A 前缀的 `RGBToUVMatrixRow_NEON` 实现，导致 aarch64 链接 `yuvconvert` 时产生未定义符号错误。

**修复方法**: 在 Dockerfile 的 `git clone` 后、`cmake` 前，用 `sed` 注释掉 `row.h` 中 `HAS_RGBTOUVMATRIXROW_NEON` 宏定义，使编译器回退到 C 语言通用实现（牺牲少量 NEON 性能换取 aarch64 构建成功）：

```dockerfile
RUN sed -i 's/#define HAS_RGBTOUVMATRIXROW_NEON/\/\/#define HAS_RGBTOUVMATRIXROW_NEON/' include/libyuv/row.h
```

**历史案例**:
- PR #2546: `Others/libyuv/1948/24.03-lts-sp3/Dockerfile` — `row.h` 定义了 `HAS_RGBTOUVMATRIXROW_NEON` 但实现缺失，通过 sed 注释掉该宏定义修复 aarch64 链接失败

---

## 模式22：Git分支名构造错误

**症状关键词**: `fatal: Remote branch`, `not found in upstream origin`, `git clone`, `exit code: 128`, `CMAQv`

**根因**: - 失败位置: `HPC/cmaq/5.5.2Oct2024/24.03-lts-sp3/Dockerfile:60`
- 失败原因: Dockerfile 中 git clone 的分支名模板 `CMAQv${VERSION}_2Oct2024` 展开为 `CMAQv5.5.2Oct2024_2Oct2024`，其中 "2Oct2024" 出现两次——VERSION 变量值 `5.5.2Oct2024` 已包含 "2Oct2024"，模板又追加了 `_2Oct2024` 后缀，导致构造出的分支名在上游仓库 `USEPA/CMAQ` 中不存在。

**修复方法**: Dockerfile 中 git clone 构造的分支名 `CMAQv5.5.2Oct2024_2Oct2024` 在 USEPA/CMAQ 上游仓库中不存在，导致构建失败。

**历史案例**:
- PR #2653: `HPC/cmaq/5.5.2Oct2024/24.03-lts-sp3/Dockerfile:60` — Dockerfile 中 git clone 构造的分支名 `CMAQv5.5.2Oct2024_2Oct2024` 在

---

## 模式23：PyTorch版本锁定冲突

**症状关键词**: ResolutionImpossible, conflicting dependencies, torchvision depends on torch

**根因**: - 失败位置: `AI/torchvision/0.27.1/24.03-lts-sp3/Dockerfile`:10（pip install 步骤）
- 失败原因: Dockerfile 中 `TORCH_VERSION=2.12.0` 与 torchvision 0.27.1 的上游依赖 `torch==2.12.1` 不兼容，pip 依赖解析器无法满足约束。

**修复方法**: Dockerfile 中 `TORCH_VERSION=2.12.0` 与 torchvision 0.27.1 的上游依赖 `torch==2.12.1` 不兼容，导致 pip 依赖解析失败。

**历史案例**:
- PR #2650: `AI/torchvision/0.27.1/24.03-lts-sp3/Dockerfile` — Dockerfile 中 `TORCH_VERSION=2.12.0` 与 torchvision 0.27.1 的上游

---

## 模式24：注释测试后引入checkstyle违规

**症状关键词**: Checkstyle, UnusedImports, Unused import, maven-checkstyle-plugin, checkstyle.xml

**根因**: - 失败位置: `Dockerfile:33`（`RUN git clone ... && printf ... python3 ... && make clean install-dev` 步骤）
- 失败原因: Dockerfile 中的 Python 脚本注释了 `LocalizedMessageHelperTest.java` 内三个测试方法（`testForEnglish`、`testForNonTranslatedLanguage`、`testForNotDefaultLanguage`），但保留了这些方法所用 import 语句。测试方法被注释后，import 变为未使用，触发 

**修复方法**: Dockerfile 中 Python 脚本注释测试方法后未移除对应的未使用 import，导致 Maven checkstyle 检测到 4 个 UnusedImports 违规。

**历史案例**:
- PR #2651: `Cloud/ovirt-engine/4.5.7/24.03-lts-sp3/Dockerfile` — Dockerfile 中 Python 脚本注释测试方法后未移除对应的未使用 import，导致 Maven check

---

## 模式25：容器启动后立即退出

**症状关键词**: No such object, failed to start container, Spark did not start within the allocated time, container_status: false

**根因**: - 失败位置: `Bigdata/spark/4.1.2/24.03-lts-sp3/Dockerfile` + `entrypoint.sh`（运行时阶段）
- 失败原因: Docker 镜像构建成功（10/10 步骤均通过），但在 CI [Check] 阶段的 `test_spark_container_startup` 测试中，容器被创建后几乎立即退出/消失，导致 check 脚本无法获取容器状态（"No such object"持续出现），最终在 60 秒超时后判定失败。

**修复方法**: 容器在无参数启动时立即退出，导致 `test_spark_container_startup` 测试失败（容器 PID 1 退出、`docker ps` 不可见）。

**历史案例**:
- PR #2674: `Bigdata/spark/4.1.2/24.03-lts-sp3/Dockerfile` — 容器在无参数启动时立即退出，导致 `test_spark_container_startup` 测试失败（容器 PID 

---

## 模式26：Maven仓库证书过期

**症状关键词**: PKIX path validation failed, CertPathValidatorException, validity check failed, NotAfter, releases.java.net, maven.java.net, txw2, jax-maven-plugin

**根因**: - 失败位置: `Bigdata/oozie/5.2.1/24.03-lts-sp3/Dockerfile:16-18`（`./mkdistro.sh -DskipTests` 步骤）
- 失败原因: Oozie 5.2.1 的 Maven 构建依赖 `org.glassfish.jaxb:txw2:jar:2.4.0-b180608.0325`，该制品的版本号含预发布后缀 `-b180608.0325`，仅托管在 `releases.java.net`（即 `maven.java.net`）仓库。该仓库的 SSL 证书已于 **2026-04-01 23:59:59 UTC** 过期，构建日

**修复方法**: Oozie 5.2.1 Maven 构建因 `releases.java.net` 仓库 SSL 证书过期导致 `org.glassfish.jaxb:txw2:2.4.0-b180608.0325` 依赖解析失败。

**历史案例**:
- PR #2684: `Bigdata/oozie/5.2.1/24.03-lts-sp3/Dockerfile` — Oozie 5.2.1 Maven 构建因 `releases.java.net` 仓库 SSL 证书过期导致 `org

---

## 模式27：GitHub Release URL 404

**症状关键词**: curl: (22), 404, github.com, releases/download, apache kylin

**根因**: - 失败位置: `Bigdata/kylin/5.0.3/24.03-lts-sp3/Dockerfile:60-63`
- 失败原因: Dockerfile 中构造的 GitHub Release 下载 URL `https://github.com/apache/kylin/releases/download/kylin-5.0.3/apache-kylin-5.0.3-bin.tar.gz` 不存在（HTTP 404），可能的原因包括：① Apache Kylin 5.0.3 尚未在该 URL 发布 release 制品；② GitHub Release 的 tag 命名格式不是 `ky

**修复方法**: Docker 构建时从 GitHub Releases 下载 Apache Kylin 5.0.3 二进制包返回 HTTP 404，将下载源切换至 Apache Archive。

**历史案例**:
- PR #2704: `Bigdata/kylin/5.0.3/24.03-lts-sp3/Dockerfile` — Docker 构建时从 GitHub Releases 下载 Apache Kylin 5.0.3 二进制包返回 HTT

---

## 模式28：Git短哈希无法作为远程ref

**症状关键词**: `fatal: couldn't find remote ref`, `git fetch`, `--depth 1`, abbreviated SHA, `${VERSION}`

**根因**: - 失败位置: `AI/xla/3b0ff80/24.03-lts-sp3/Dockerfile:21-24`
- 失败原因: Dockerfile 中 `git fetch --depth 1 origin ${VERSION}` 使用 7 字符的缩写 Git SHA（`3b0ff80`）作为远程 ref，Git 在 fetch 阶段无法解析缩写 SHA，报 `fatal: couldn't find remote ref`。

**修复方法**: Dockerfile 中 `git fetch --depth 1 origin ${VERSION}` 使用了 7 字符缩写 Git SHA（`3b0ff80`），Git 无法将缩写 SHA 解析为远程 ref，导致 `fatal: couldn't find remote ref` 构建失败。

**历史案例**:
- PR #2712: `AI/xla/3b0ff80/24.03-lts-sp3/Dockerfile` — Dockerfile 中 `git fetch --depth 1 origin ${VERSION}` 使用了 7 字

---

## 模式29：版本路径超层级

**症状关键词**: Failed to check file path, image-version, os-version, format.py, _parse_image_info

**根因**: - 失败位置: `eulerpublisher/update/container/app/format.py:101`（`_parse_image_info` 函数）
- 失败原因: 新增 Dockerfile 路径为 `Cloud/openvelinux/velinux/1.0 velinux2/24.03-lts-sp3/Dockerfile`，相对于镜像根目录（`Cloud/openvelinux/`）包含三个目录层级（`velinux/`, `1.0 velinux2/`, `24.03-lts-sp3/`），但 CI 校验工具 `format.py` 期望严格的两级结构 `{imag

**修复方法**: 将 `velinux/1.0+velinux2` 版本目录从三级扁平化为二级，使其符合 CI 校验要求的 `{image-version}/{os-version}/Dockerfile` 路径规范。

**历史案例**:
- PR #2751: `Cloud/openvelinux/velinux/1.0 velinux2/24.03-lts-sp3/Dockerfile` — 将 `velinux/1.0+velinux2` 版本目录从三级扁平化为二级，使其符合 CI 校验要求的 `{image

---

## 模式30：架构不匹配（meta缺失arch约束）

**症状关键词**: does not have a compatible architecture, x86_64, aarch64, intel-basekit

**根因**: - 失败位置: `AI/oneapi-basekit/2024.2.0/24.03-lts-sp4/Dockerfile:30`（`yum install` 步骤）
- 失败原因: CI 在 aarch64 runner（`ecs-build-docker-aarch64-01-sp`）上构建该 Dockerfile，但 Intel oneAPI / GPU 仓库（配置为 RHEL x86_64 源）仅提供 x86_64 架构的 RPM 包（如 `intel-basekit-2025.3.2-19.x86_64`、`intel-opencl-...x86_64`），yum 在 aarch64 

**修复方法**: `meta.yml` 中新增的 `2024.2.0-oe2403sp4` 条目缺少 `arch: x86_64` 约束，导致 CI 将该镜像调度到 aarch64 runner 上构建失败。

**历史案例**:
- PR #3135: `AI/oneapi-basekit/meta.yml` — `meta.yml` 中新增的 `2024.2.0-oe2403sp4` 条目缺少 `arch: x86_64` 约束，

---

## 模式31：架构不匹配

**症状关键词**: does not have a compatible architecture, x86_64 on aarch64, oneAPI, yum install

**根因**: - 失败位置: `AI/oneapi-runtime/2024.2.0/24.03-lts-sp4/Dockerfile:30`
- 失败原因: 新增 Dockerfile 对应的 `meta.yml` 条目未设置 `arch: x86_64`，导致 CI 在 aarch64 节点上也尝试构建该镜像。而 Intel oneAPI 仓库和 Intel GPU 驱动仓库均只提供 x86_64 架构的 RPM 包，在 aarch64 上 yum 无法安装，报 "does not have a compatible architecture"。

**修复方法**: 新增的 `2024.2.0-oe2403sp4` 镜像条目缺少 `arch: x86_64` 架构限制，导致 CI 在 aarch64 节点上也尝试构建该镜像，Intel oneAPI 包仅支持 x86_64 而安装失败。

**历史案例**:
- PR #3136: `AI/oneapi-runtime/meta.yml` — 新增的 `2024.2.0-oe2403sp4` 镜像条目缺少 `arch: x86_64` 架构限制，导致 CI 在 

---

## 模式32：Git快照返回HTML

**症状关键词**: `gzip: stdin: not in gzip format`, `text/html`, `saved [2090]`, `git.kernel.org`, `snapshot`

**根因**: - 失败位置: `Others/bcache/1.1/24.03-lts-sp4/Dockerfile:20`（wget + tar 步骤）
- 失败原因: `wget` 请求 `git.kernel.org` 的 snapshot URL（`bcache-tools-1.1.tar.gz`），服务器返回 `text/html` 内容（仅 2090 字节的 HTML 页面）而非 gzip 压缩包，`tar -zxvf` 解压时报 `not in gzip format`。

**修复方法**: `git.kernel.org` 的 Anubis 反爬保护导致 `wget` 下载 snapshot tar.gz 时返回 HTML 页面而非 gzip 压缩包，构建失败。

**历史案例**:
- PR #2929: `Others/bcache/1.1/24.03-lts-sp4/Dockerfile` — `git.kernel.org` 的 Anubis 反爬保护导致 `wget` 下载 snapshot tar.gz 时