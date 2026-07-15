#!/usr/bin/env python3
"""
Stage: 镜像构建与测试

在 create-image 生成 Dockerfile 后、push 分支前执行：
1. AI 生成定制测试脚本 test.sh（由 image-tester agent）
2. docker build 构建镜像
3. docker run 启动容器
4. 通用测试（容器存活、二进制存在、镜像大小）
5. 执行 test.sh 定制功能测试
6. 清理容器和镜像
7. 输出 test-result.json

输入（环境变量）:
  PACKAGE_NAME      - 软件包名称
  VERSION           - 软件版本号
  CATEGORY          - 分类目录
  IMAGE_REPO_DIR    - 已克隆的 openeuler-docker-images 路径
  AI_RUNNER         - AI 后端
  AI_MODEL          - 模型名称
  AI_TIMEOUT_MS     - 超时毫秒

输出:
  GITHUB_OUTPUT: passed=true/false
  ${IMAGE_REPO_DIR}/test-result.json
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

from scripts.lib.ai_runner import run_agent
from scripts.lib import docker_test

AGENT_PROMPT_FILE = os.path.join(PROJECT_ROOT, '.github', 'agents', 'image-tester.md')

MAX_IMAGE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB


def log(msg: str):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] image-test {msg}", file=sys.stderr, flush=True)


def main():
    package_name   = os.getenv('PACKAGE_NAME', '').strip()
    version        = os.getenv('VERSION', '').strip()
    category       = os.getenv('CATEGORY', 'Cloud').strip()
    image_repo_dir = os.getenv('IMAGE_REPO_DIR', '').strip()

    if not package_name or not version:
        log("❌ PACKAGE_NAME and VERSION are required")
        sys.exit(1)
    if not image_repo_dir or not Path(image_repo_dir).is_dir():
        log(f"❌ IMAGE_REPO_DIR '{image_repo_dir}' does not exist")
        sys.exit(1)

    ai_result_file = os.path.join(image_repo_dir, 'ai-result.json')
    if not Path(ai_result_file).exists():
        log(f"❌ ai-result.json not found: {ai_result_file}")
        sys.exit(1)

    with open(ai_result_file, 'r', encoding='utf-8') as f:
        ai_result = json.load(f)

    if not ai_result.get('success'):
        log("❌ image creation was not successful, skipping tests")
        _write_output(False, "image creation failed")
        return

    dockerfile_path = ai_result.get('dockerfile_path', '')
    binary_name     = ai_result.get('binary_name', '')
    tag             = ai_result.get('tag', f"test-{package_name}:{version}")

    if not dockerfile_path:
        log("❌ dockerfile_path not found in ai-result.json")
        _write_output(False, "dockerfile_path missing")
        return

    abs_dockerfile = os.path.join(image_repo_dir, dockerfile_path)
    dockerfile_dir = os.path.dirname(abs_dockerfile)

    if not Path(abs_dockerfile).exists():
        log(f"❌ Dockerfile not found: {abs_dockerfile}")
        _write_output(False, f"Dockerfile not found: {dockerfile_path}")
        return

    log(f"package={package_name} version={version} dockerfile={dockerfile_path}")

    test_result = {
        'package_name': package_name,
        'version': version,
        'dockerfile_path': dockerfile_path,
        'tests': [],
        'passed': False,
        'error': None,
    }

    # ── Step 1: AI 生成测试脚本 ──────────────────────────────
    log("Step 1: Generating test script via AI...")
    test_ai_output = os.path.join(image_repo_dir, 'test-ai-result.json')
    test_log_dir   = os.path.join(PROJECT_ROOT, 'create-image-log', package_name, 'image-test')

    context = {
        'package_name':    package_name,
        'version':         version,
        'dockerfile_path': dockerfile_path,
        'binary_name':     binary_name,
        'category':        category,
        'image_repo_dir':  image_repo_dir,
    }

    instruction = (
        f"请读取 {abs_dockerfile} 的内容，"
        f"为 {package_name} v{version} 生成功能测试脚本 test.sh，"
        f"放在 {dockerfile_dir}/test.sh，"
        f"并将结果写入 {test_ai_output}。"
    )

    try:
        run_agent(
            prompt_file=AGENT_PROMPT_FILE,
            context=context,
            instruction=instruction,
            work_dir=image_repo_dir,
            output_file=test_ai_output,
            log_dir=test_log_dir,
            label=f'image-test-{package_name}',
        )
    except Exception as e:
        log(f"⚠️ AI test script generation failed: {e}")

    test_script_path = os.path.join(dockerfile_dir, 'test.sh')
    has_test_script = Path(test_script_path).exists()
    if has_test_script:
        os.chmod(test_script_path, 0o755)
        log(f"✅ test.sh generated at {test_script_path}")
    else:
        log("⚠️ test.sh not generated, will run generic tests only")

    # ── Step 2: docker build ─────────────────────────────────
    log("Step 2: Building Docker image...")
    image_tag = f"test-{package_name}:{version}"
    build_result = docker_test.build_image(abs_dockerfile, dockerfile_dir, image_tag, timeout=600)
    test_result['tests'].append({
        'name': 'docker_build',
        'success': build_result['success'],
        'log': build_result['log'][-2000:],
    })

    if not build_result['success']:
        log("❌ Docker build failed")
        test_result['error'] = 'docker build failed'
        _write_result(test_result, image_repo_dir)
        return

    # ── Step 3: docker run ────────────────────────────────────
    log("Step 3: Starting container...")
    container_name = f"test-{package_name}"
    docker_test.stop_and_remove_container(container_name)

    run_result = docker_test.run_container(image_tag, container_name)
    test_result['tests'].append({
        'name': 'container_start',
        'success': run_result['success'],
        'container_id': run_result.get('container_id', ''),
    })

    if not run_result['success']:
        log("❌ Container failed to start")
        test_result['error'] = 'container start failed'
        docker_test.remove_image(image_tag)
        _write_result(test_result, image_repo_dir)
        return

    # ── Step 4: 通用测试 ─────────────────────────────────────
    log("Step 4: Running generic tests...")

    # 4.1 容器存活检查
    if docker_test.wait_for_container(container_name, timeout=30):
        log("  ✅ Container is running")
        test_result['tests'].append({'name': 'container_alive', 'success': True})
    else:
        log("  ❌ Container exited unexpectedly")
        test_result['tests'].append({'name': 'container_alive', 'success': False})
        # 获取容器退出日志
        _, logs, _ = docker_test.run_cmd(f'docker logs {container_name} 2>&1 | tail -50', timeout=10)
        test_result['tests'][-1]['log'] = logs
        docker_test.stop_and_remove_container(container_name)
        docker_test.remove_image(image_tag)
        test_result['error'] = 'container exited unexpectedly'
        _write_result(test_result, image_repo_dir)
        return

    # 4.2 镜像大小检查
    image_size = docker_test.get_image_size(image_tag)
    if image_size is not None:
        size_mb = image_size / (1024 * 1024)
        size_ok = image_size <= MAX_IMAGE_SIZE
        log(f"  {'✅' if size_ok else '❌'} Image size: {size_mb:.1f} MB")
        test_result['tests'].append({
            'name': 'image_size',
            'success': size_ok,
            'size_mb': round(size_mb, 1),
        })

    # ── Step 5: 执行定制测试脚本 ────────────────────────────
    if has_test_script:
        log("Step 5: Running custom test.sh...")
        test_env = os.environ.copy()
        test_env['PACKAGE_NAME'] = package_name
        test_env['CONTAINER_NAME'] = container_name

        import subprocess
        proc = subprocess.run(
            ['bash', test_script_path],
            capture_output=True, text=True, timeout=120, env=test_env,
        )
        custom_success = (proc.returncode == 0)
        test_result['tests'].append({
            'name': 'custom_test',
            'success': custom_success,
            'log': (proc.stdout + proc.stderr)[-2000:],
        })
        log(f"  {'✅' if custom_success else '❌'} Custom test {'passed' if custom_success else 'failed'}")
    else:
        log("Step 5: Skipped (no custom test.sh)")

    # ── Step 6: 清理 ─────────────────────────────────────────
    log("Step 6: Cleaning up...")
    docker_test.stop_and_remove_container(container_name)
    docker_test.remove_image(image_tag)

    # ── 汇总结果 ─────────────────────────────────────────────
    all_passed = all(t.get('success', False) for t in test_result['tests'])
    test_result['passed'] = all_passed
    test_result['error'] = None if all_passed else 'some tests failed'

    _write_result(test_result, image_repo_dir)

    if all_passed:
        log("✅ All tests passed!")
    else:
        failed = [t['name'] for t in test_result['tests'] if not t.get('success', False)]
        log(f"❌ Tests failed: {', '.join(failed)}")


def _write_result(test_result: dict, image_repo_dir: str):
    result_file = os.path.join(image_repo_dir, 'test-result.json')
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(test_result, f, ensure_ascii=False, indent=2)
    log(f"Result written to {result_file}")
    _write_output(test_result['passed'], test_result.get('error', ''))


def _write_output(passed: bool, error: str = ''):
    github_output = os.getenv('GITHUB_OUTPUT', '')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"passed={'true' if passed else 'false'}\n")
            if error:
                f.write(f"test_error={error}\n")


if __name__ == '__main__':
    main()
