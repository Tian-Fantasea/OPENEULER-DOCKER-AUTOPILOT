#!/usr/bin/env python3
"""
Stage: 新增镜像创建

输入（环境变量）:
  PACKAGE_NAME      - 软件包名称，如 fluid
  SOURCE_REPO_URL   - 上游源码仓库地址，如 https://github.com/fluid-cloudnative/fluid
  DOMAIN            - 所属领域，如 虚拟化
  CATEGORY          - 目标目录，如 Cloud（由 process_issue_events.py 解析）
  OS_VERSION        - openEuler 版本，如 24.03-lts-sp3
  OS_TAG            - 镜像 Tag 后缀，如 oe2403sp3
  IMAGE_REPO_DIR    - 已克隆的 openeuler-docker-images 路径
  AI_RUNNER         - AI 后端：opencode（默认）/ claude-code / claude-code-account
  AI_MODEL          - 模型名称，如 deepseek/deepseek-v4-pro
  AI_TIMEOUT_MS     - 超时毫秒，默认 1800000

输出:
  ${IMAGE_REPO_DIR}/ai-result.json  写入创建结果，供 workflow 读取
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from scripts.lib.ai_runner import run_agent

AGENT_PROMPT_FILE = os.path.join(PROJECT_ROOT, '.github', 'agents', 'image-creator.md')
DEFAULT_OS_VERSION = '24.03-lts-sp3'
DEFAULT_OS_TAG = 'oe2403sp3'


def log(msg: str):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] create-image {msg}", file=sys.stderr, flush=True)


def main():
    package_name    = os.getenv('PACKAGE_NAME', '').strip()
    source_repo_url = os.getenv('SOURCE_REPO_URL', '').strip()
    domain          = os.getenv('DOMAIN', '').strip()
    category        = os.getenv('CATEGORY', 'Cloud').strip()
    os_version      = os.getenv('OS_VERSION', DEFAULT_OS_VERSION).strip()
    os_tag          = os.getenv('OS_TAG', DEFAULT_OS_TAG).strip()
    image_repo_dir  = os.getenv('IMAGE_REPO_DIR', '').strip()

    if not package_name or not source_repo_url:
        log("❌ PACKAGE_NAME and SOURCE_REPO_URL are required")
        sys.exit(1)
    if not image_repo_dir or not Path(image_repo_dir).is_dir():
        log(f"❌ IMAGE_REPO_DIR '{image_repo_dir}' does not exist")
        sys.exit(1)

    output_file = os.path.join(image_repo_dir, 'ai-result.json')
    log_dir     = os.path.join(PROJECT_ROOT, 'create-image-log', package_name)

    log(f"package={package_name} repo={source_repo_url} domain={domain} "
        f"category={category} os={os_version} "
        f"runner={os.getenv('AI_RUNNER', 'opencode')} model={os.getenv('AI_MODEL', '')}")

    context = {
        'package_name':    package_name,
        'source_repo_url': source_repo_url,
        'domain':          domain,
        'category':        category,
        'os_version':      os_version,
        'os_tag':          os_tag,
        'image_repo_dir':  image_repo_dir,
    }

    instruction = (
        f"请在 {image_repo_dir} 目录下，按照规范为 {package_name} 软件包创建所有所需文件，"
        f"包括 Dockerfile、meta.yml、README.md、doc/image-info.yml 和 logo，"
        f"并更新对应分类目录下的 image-list.yml。"
        f"完成后将结果写入 {output_file}。"
    )

    run_agent(
        prompt_file=AGENT_PROMPT_FILE,
        context=context,
        instruction=instruction,
        work_dir=image_repo_dir,
        output_file=output_file,
        log_dir=log_dir,
        label=f'create-image-{package_name}',
    )

    if not Path(output_file).exists():
        log(f"❌ output file not found: {output_file}")
        sys.exit(1)

    with open(output_file, 'r', encoding='utf-8') as f:
        result = json.load(f)

    log(f"✅ Result: {json.dumps(result, ensure_ascii=False)}")

    # 输出供 GitHub Actions 步骤读取的变量
    github_output = os.getenv('GITHUB_OUTPUT', '')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"package_name={result.get('package_name', package_name)}\n")
            f.write(f"version={result.get('version', 'unknown')}\n")
            f.write(f"category={result.get('category', category)}\n")
            f.write(f"tag={result.get('tag', '')}\n")
            f.write(f"dockerfile_path={result.get('dockerfile_path', '')}\n")
            f.write(f"binary_name={result.get('binary_name', '')}\n")
            f.write(f"success={str(result.get('success', False)).lower()}\n")


if __name__ == '__main__':
    main()
