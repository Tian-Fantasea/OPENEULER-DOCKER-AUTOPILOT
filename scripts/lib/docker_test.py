#!/usr/bin/env python3
"""
Docker 镜像测试工具库

封装 docker build / run / exec / cleanup 操作，
供 image-test.py 调用。
"""

import subprocess
import time
import json
from typing import Optional, List


def run_cmd(cmd: str, timeout: int = 300) -> tuple:
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def build_image(dockerfile_path: str, context_dir: str, tag: str, timeout: int = 600) -> dict:
    ret = {
        'action': 'build',
        'command': f'docker build -t {tag} -f {dockerfile_path} {context_dir}',
        'success': False,
        'log': '',
    }
    code, out, err = run_cmd(ret['command'], timeout=timeout)
    ret['success'] = (code == 0)
    ret['log'] = out + ('\n--- stderr ---\n' + err if err else '')
    return ret


def run_container(image: str, name: str, ports: Optional[List[str]] = None, env: Optional[dict] = None) -> dict:
    ret = {
        'action': 'run',
        'success': False,
        'container_id': '',
    }
    port_args = ' '.join([f'-p {p}' for p in (ports or [])])
    env_args = ' '.join([f'-e {k}={v}' for k, v in (env or {}).items()])
    cmd = f'docker run -d --name {name} --entrypoint tail {port_args} {env_args} {image} -f /dev/null'
    code, out, err = run_cmd(cmd, timeout=30)
    ret['success'] = (code == 0)
    ret['container_id'] = out
    return ret


def container_is_running(name: str) -> bool:
    code, out, _ = run_cmd(
        f'docker ps --filter "name={name}" --filter "status=running" --format "{{{{.Names}}}}"',
        timeout=10,
    )
    return code == 0 and name in out


def wait_for_container(name: str, timeout: int = 30) -> bool:
    for _ in range(timeout):
        if container_is_running(name):
            return True
        time.sleep(1)
    return False


def exec_command(name: str, command: str, timeout: int = 60) -> dict:
    ret = {
        'action': 'exec',
        'command': f'docker exec {name} {command}',
        'success': False,
        'output': '',
    }
    code, out, err = run_cmd(ret['command'], timeout=timeout)
    ret['success'] = (code == 0)
    ret['output'] = out + (f'\n{err}' if err else '')
    return ret


def get_image_size(tag: str) -> Optional[int]:
    code, out, _ = run_cmd(
        f'docker image inspect {tag} --format "{{{{.Size}}}}"', timeout=10
    )
    if code == 0 and out:
        try:
            return int(out.strip().strip('"'))
        except ValueError:
            return None
    return None


def stop_and_remove_container(name: str):
    run_cmd(f'docker stop -t 5 {name} 2>/dev/null', timeout=30)
    run_cmd(f'docker rm -f {name} 2>/dev/null', timeout=30)


def remove_image(tag: str):
    run_cmd(f'docker rmi -f {tag} 2>/dev/null', timeout=10)
