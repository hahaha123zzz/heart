"""Windows/WSL传输适配；执行、挂载隔离和限额仍由原生bwrap服务负责。"""
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import sys


def wsl_path(value):
    text = str(value)
    if re.match(r'^[A-Za-z]:[\\/]', text):
        path = PureWindowsPath(text)
        # shortcut: 使用已验证的WSL标准/mnt挂载；支持自定义automount时改用wslpath查询。
        return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])
    if text.startswith('\\\\'):
        raise ValueError('WSL沙箱不支持UNC工作区')
    return text


def install():
    distro = os.getenv('HEART_WSL_SANDBOX_DISTRO', '').strip()
    if sys.platform != 'win32' or not distro:
        return
    from deeptutor.services.sandbox import service
    from deeptutor.services.sandbox.backends import SandboxBackend, _communicate
    from deeptutor.services.sandbox.spec import ExecResult, IsolationLevel
    from deeptutor.tools.exec_tool import ExecTool
    if getattr(service.build_backend, '_heart_wsl', False):
        return
    root = Path(__file__).resolve().parents[2]
    python = wsl_path(root / '.runtime/wsl-word-runtime/bin/python3')
    helper = wsl_path(Path(__file__).with_name('wsl_sandbox_runner.py'))
    vendor = wsl_path(root.parents[1] / 'vendor/DeepTutor')

    class WslBwrapBackend(SandboxBackend):
        level = IsolationLevel.SYSTEM

        async def _call(self, payload, timeout=30, max_chars=10000):
            try:
                process = await asyncio.create_subprocess_exec('wsl.exe', '-d', distro, '--exec',
                    python, helper, vendor, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                process.stdin.write(json.dumps(payload,ensure_ascii=False).encode('utf-8'))
                await process.stdin.drain();process.stdin.close()
                result = await _communicate(process, timeout+15, max_chars*6+8192)
                if result.timed_out or result.error or result.exit_code != 0:
                    return {'error':'WSL bwrap执行失败；未切换到宿主执行'}
                return json.loads(result.stdout)
            except (OSError, ValueError):
                return {'error':'WSL bwrap运行环境不可用'}

        async def health(self):
            result = await self._call({'health':True})
            return not bool(result.get('error')), result.get('error') or '原生WSL bwrap可用'

        async def exec(self, request):
            workspace = request.env.get('DEEPTUTOR_WORKSPACE_ROOT')
            if not workspace or not request.workdir:
                return ExecResult(error='执行缺少原生工作区绑定')
            root_path = Path(workspace).resolve()
            if not Path(request.workdir).resolve().is_relative_to(root_path) or any(
                    not Path(mount.host_path).resolve().is_relative_to(root_path) for mount in request.mounts):
                return ExecResult(error='执行挂载超出本轮工作区')
            payload = asdict(request)
            payload['workdir'] = wsl_path(request.workdir)
            payload['mounts'] = [{**asdict(mount),'host_path':wsl_path(mount.host_path),
                'sandbox_path':wsl_path(mount.sandbox_path)} for mount in request.mounts]
            payload['env'] = {key:wsl_path(value) for key,value in request.env.items() if key != 'PATH'}
            if request.argv:
                payload['argv'] = [wsl_path(value) for value in request.argv]
                payload['command'] = shlex.join(payload['argv'])
            result = await self._call(payload, request.limits.timeout_s, request.limits.max_output_chars)
            return ExecResult(**result)

    original_build = service.build_backend
    def build(settings):
        return original_build(settings) if settings.runner_url else WslBwrapBackend()
    build._heart_wsl = True
    service.build_backend = build
    service.reset_sandbox_service()

    def command(cls, language, *, has_stdin, call_dir=''):
        source = wsl_path(call_dir).rstrip('/') + '/' + cls._LANGUAGES[language][0]
        redirect = '< ' + shlex.quote(wsl_path(call_dir).rstrip('/') + '/stdin.txt') if has_stdin else ''
        return cls._LANGUAGES[language][1].format(src=shlex.quote(source), stdin=redirect).strip()
    ExecTool._command_for_platform = classmethod(command)
