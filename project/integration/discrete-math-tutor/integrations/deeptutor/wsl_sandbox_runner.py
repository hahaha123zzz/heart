"""可信WSL进程只负责解码请求；模型代码始终交给固定上游BwrapBackend。"""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0,sys.argv[1])
from deeptutor.services.sandbox.backends import BwrapBackend
from deeptutor.services.sandbox.spec import ExecRequest, Mount, ResourceLimits

class WorkspaceBwrap(BwrapBackend):
    def _build_argv(self, request):
        argv = super()._build_argv(request)
        # 辅助进程的环境和凭据不应传入模型代码。
        argv[1:1] = ['--clearenv']
        workspace = request.env.get('DEEPTUTOR_WORKSPACE_ROOT')
        if workspace and request.workdir:
            # 工作区内的原生数据库/租约不属于可供模型读取的文档。
            private = Path(workspace) / '.deeptutor'
            if private.is_dir():
                index = argv.index('--chdir')
                argv[index:index] = ['--tmpfs',str(private)]
        return argv

async def main():
    payload = json.load(sys.stdin)
    backend = WorkspaceBwrap()
    if payload.pop('health',False):
        import docx
        healthy, detail = await backend.health()
        result = {} if healthy else {'error':detail}
    else:
        payload['mounts'] = tuple(Mount(**item) for item in payload.get('mounts',[]))
        payload['limits'] = ResourceLimits(**payload['limits'])
        payload['argv'] = tuple(payload.get('argv',[]))
        from deeptutor.services.sandbox.runner.server import _build_preexec_fn
        apply_limits = _build_preexec_fn(payload['limits'].memory_mb, payload['limits'].cpu_seconds)
        if apply_limits:
            apply_limits()
        result = asdict(await backend.exec(ExecRequest(**payload)))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    asyncio.run(main())
