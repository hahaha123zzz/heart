"""把实验心理学 AI 助教部署到 ECS（Ubuntu 22.04 + Caddy 反代 80 端口）。

用法（在仓库根目录，需要 paramiko）：
    set HEART_DEPLOY_PW=...      # 或 --password
    python project/integration/discrete-math-tutor/deploy/deploy_heart.py

重复执行是安全的：代码重新上传解包，依赖与 systemd 配置幂等刷新，.env 保留服务器上已有值。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import paramiko

APP_SRC = Path(__file__).resolve().parents[1]
REMOTE_ROOT = "/opt/heart"
REMOTE_APP = f"{REMOTE_ROOT}/app"
REMOTE_VENV = f"{REMOTE_ROOT}/venv"
ARCHIVE = "app.tar.gz"

EXCLUDES = [
    ".venv", ".venv-gpu", ".venv-deeptutor", ".venv-runtime", "node_modules", ".runtime",
    ".cache", ".pytest_cache", "__pycache__", ".ua", "artifacts", ".git", ".playwright-mcp",
    ".superpowers", "*.log", "*.zip",
]

# 2 核 2G：CPU 检索、关闭 GPU 重排与本地 DeepTutor worker；其余教学开关沿用本机已验证配置。
ENV_TEMPLATE = """\
DEEPSEEK_API_KEY={key}
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-flash
OPENAI_VISION_MODEL=deepseek-flash
LLM_MOCK=0
DATABASE_URL={database_url}
COURSE_DATABASE_URL={course_database_url}
TUTOR_COURSE=experimental-psychology-3
RAG_EMBED_DEVICE=cpu
RAG_RERANK_DEVICE=cpu
RAG_RERANK_MODEL=
Q3_RETRIEVAL_MODE=local_llamaindex
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
HF_ENDPOINT=https://hf-mirror.com
FASTEMBED_CACHE_PATH={root}/model-cache/fastembed
DEEPTUTOR_BACKEND_URL=http://127.0.0.1:18001
DEEPTUTOR_HOST_URL=http://127.0.0.1:8000
DEEPTUTOR_NATIVE_ENABLED=0
DEEPTUTOR_AUTOSTART=0
DEEPTUTOR_LLM_ENABLED=0
DEEPTUTOR_KNOWLEDGE_ENABLED=0
DEEPTUTOR_SESSION_SYNC=0
DEEPTUTOR_TURN_SYNC=0
FIXED_BOOK_RETRIEVAL_ENABLED=0
MEMORY_WORKER_ENABLED=0
CLEANUP_EXPIRED_ON_STARTUP=0
INTENT_ROLLOUT=all
INTENT_CONTEXT_ENABLED=1
INTENT_TASK_ENABLED=1
INTENT_CLARIFICATION_ENABLED=1
INTENT_REWRITE_ENABLED=0
VISUALIZATION_ON_DEMAND=0
Q5_LEARNING_ENABLED=1
LOCAL_AGENT_LOOP_ENABLED=1
ADAPTIVE_TUTORING_ENABLED=1
SELECTED_TEXT_AGENT_LOOP_ENABLED=1
INPUT_UNDERSTANDING_MODE=active
INPUT_UNDERSTANDING_SEMANTIC_ENABLED=1
SEMANTIC_LABELS_ENABLED=1
LABELS_POLICY=1
LABELS_STRUCTURE=1
LABELS_TURN=1
RESPONSE_COMPOSITION_ENABLED=1
RESPONSE_BLOCK_STREAMING_ENABLED=1
"""


def local_api_key() -> str:
    for line in (APP_SRC / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:DEEPSEEK_API_KEY|OPENAI_API_KEY)\s*=\s*['\"]?([^'\"\s]+)", line)
        if m:
            return m.group(1)
    sys.exit("本地 .env 里找不到 DEEPSEEK_API_KEY")


def build_archive(repack: bool = False) -> Path:
    out = Path(tempfile.gettempdir()) / "opencode" / ARCHIVE
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not repack:
        print(f"[pack] 复用已有包 {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
        return out
    cmd = ["tar", "-czf", str(out), "-C", str(APP_SRC.parent)]
    cmd += [f"--exclude={APP_SRC.name}/{p}" for p in EXCLUDES]
    # .env 单独生成，避免把本机路径和密钥混进代码包
    cmd += [f"--exclude={APP_SRC.name}/.env", APP_SRC.name]
    print(f"[pack] 排除 {len(EXCLUDES) + 1} 类文件后打包到 {out}")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        sys.exit(f"tar 打包失败 rc={rc}")
    size = out.stat().st_size / 1024 / 1024
    print(f"[pack] {out} ({size:.1f} MB)")
    return out


class Remote:
    def __init__(self, host: str, user: str, password: str):
        self.host, self.user, self.password = host, user, password
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(host, 22, user, password, timeout=20, banner_timeout=30,
                            auth_timeout=30)
        self.client.get_transport().set_keepalive(15)

    def run(self, cmd: str, timeout: int | None = None, quiet: bool = False,
            check: bool = False) -> str:
        if not quiet:
            print(f"\n$ {cmd}")
        _, out, err = self.client.exec_command(cmd, timeout=timeout)
        out.channel.set_combine_stderr(True)  # 避免大输出时管道互相阻塞
        text = out.read().decode("utf-8", "replace")
        status = out.channel.recv_exit_status()
        if not quiet:
            print(text.rstrip())
        if check and status != 0:
            raise RuntimeError(f"远程命令失败({status})：{cmd}\n{text[-2000:]}")
        return text

    def upload(self, local: Path, remote: str) -> None:
        """分块 SFTP 上传，断线后从已传字节续传；大包一次 cat 会被 sshd 重置。"""
        size = local.stat().st_size
        for attempt in range(1, 7):
            try:
                sftp = self.client.open_sftp()
                done = sftp.stat(remote).st_size if self._exists(sftp, remote) else 0
                if done >= size:
                    sftp.close()
                    print(f"[upload] 已在位 {remote} ({size / 1024 / 1024:.1f} MB)")
                    return
                print(f"[upload] {local.name} -> {remote} 从 {done / 1024 / 1024:.1f}"
                      f"/{size / 1024 / 1024:.1f} MB 继续（第 {attempt} 次）")
                t0, sent, last = time.time(), done, 0.0
                with local.open("rb") as src, sftp.open(remote, "r+b" if done else "wb") as dst:
                    src.seek(done)
                    dst.seek(done)
                    while chunk := src.read(262144):
                        dst.write(chunk)
                        sent += len(chunk)
                        now = time.time()
                        if now - last > 10:
                            last = now
                            print(f"    {sent / 1024 / 1024:6.1f} MB  "
                                  f"{(sent - done) / 1024 / 1024 / max(now - t0, 1e-6):4.1f} MB/s")
                sftp.close()
                if sent == size:
                    print(f"[upload] done {size / 1024 / 1024:.1f} MB in {time.time() - t0:.0f}s")
                    return
            except Exception as exc:  # 断连后重连继续
                print(f"[upload] 第 {attempt} 次中断：{exc}")
                self.reconnect()
                time.sleep(3)
        sys.exit("[upload] 多次重试仍失败")

    @staticmethod
    def _exists(sftp, path: str) -> bool:
        try:
            sftp.stat(path)
            return True
        except IOError:
            return False

    def reconnect(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        time.sleep(2)
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.host, 22, self.user, self.password, timeout=20,
                            banner_timeout=30, auth_timeout=30)
        self.client.get_transport().set_keepalive(15)

    def close(self) -> None:
        self.client.close()


def put_file(client: paramiko.SSHClient, local: Path, remote: str) -> None:
    sftp = client.open_sftp()
    sftp.put(str(local), remote)
    sftp.close()
    print(f"[put] {local.name} -> {remote}")


def deploy(args) -> None:
    password = args.password or os.environ.get("HEART_DEPLOY_PW")
    if not password:
        sys.exit("需要密码：--password 或环境变量 HEART_DEPLOY_PW")
    database_url = os.environ.get("HEART_DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        sys.exit(
            "需要 HEART_DATABASE_URL=postgresql://...；当前代码只支持 PostgreSQL。"
            "远端还须先安装 PG 18 + pgvector、建 heart/heart_psychology/heart_rag 三库，"
            "并部署 V/web（Next 构建）与 18001 worker；这些步骤目前未自动化。")

    r = Remote(args.host, args.user, password)
    try:
        r.run(f"mkdir -p {REMOTE_ROOT}/tmp {REMOTE_APP} {REMOTE_APP}/deploy", quiet=True)
        if args.skip_upload:
            put_file(r.client, APP_SRC / "deploy" / "provision_heart.sh",
                     f"{REMOTE_APP}/deploy/provision_heart.sh")
        if not args.skip_upload:
            archive = build_archive(args.repack)
            r.upload(archive, f"{REMOTE_ROOT}/tmp/{ARCHIVE}")
            r.run(f"rm -rf {REMOTE_ROOT}/app.prev && cp -a {REMOTE_APP} {REMOTE_ROOT}/app.prev",
                  quiet=True)
            r.run(f"rm -rf {REMOTE_APP}/* && "
                  f"tar -xzf {REMOTE_ROOT}/tmp/{ARCHIVE} -C {REMOTE_APP} --strip-components=1 && "
                  f"rm -f {REMOTE_ROOT}/tmp/{ARCHIVE} && "
                  f"ls {REMOTE_APP} | head -20 && du -sh {REMOTE_APP}", check=True)

        course_database_url = os.environ.get("HEART_COURSE_DATABASE_URL", "")
        if not course_database_url.startswith("postgresql"):
            sys.exit("需要 HEART_COURSE_DATABASE_URL=postgresql://...（心理学课程独立库）")
        env_body = ENV_TEMPLATE.format(key=local_api_key(), root=REMOTE_ROOT,
                                       database_url=database_url,
                                       course_database_url=course_database_url)
        if r.run(f"test -f {REMOTE_APP}/.env && echo KEEP || echo NEW", quiet=True).strip() == "KEEP":
            keep = r.run(f"grep -c '' {REMOTE_APP}/.env", quiet=True).strip()
            print(f"[env] 服务器已有 .env（{keep} 行），保留不动")
        else:
            sftp = r.client.open_sftp()
            with sftp.file(f"{REMOTE_APP}/.env", "w") as fh:
                fh.write(env_body)
            sftp.close()
            r.run(f"chmod 600 {REMOTE_APP}/.env && echo env written")

        if not args.skip_provision:
            r.run(f"HEART_PUBLIC_IP={args.host} bash {REMOTE_APP}/deploy/provision_heart.sh",
                  timeout=3600, check=True)

        r.run("systemctl restart heart-tutor && sleep 3 && systemctl is-active heart-tutor", timeout=120)
        wait_healthy(r, args.host)
        r.close()
    finally:
        try:
            r.close()
        except Exception:
            pass


def wait_healthy(r: Remote, host: str, attempts: int = 90) -> None:
    print("\n[health] 等待模型预热与 /health 就绪（首次约 1-3 分钟）")
    for i in range(attempts):
        body = r.run(f"curl -s -m 5 http://127.0.0.1:8000/health || true", quiet=True).strip()
        if '"status":"ok"' in body.replace(" ", ""):
            print(f"[health] OK after {i * 5}s\n{body}")
            print(r.run(f"curl -s -o /dev/null -w 'port80:%{{http_code}}\\n' -H 'Host: {host}' http://127.0.0.1/health", quiet=True).strip())
            print(r.run("systemctl show heart-tutor -p MemoryCurrent; free -m | head -2", quiet=True).strip())
            return
        time.sleep(5)
    print(r.run("journalctl -u heart-tutor -n 80 --no-pager", quiet=True))
    sys.exit("[health] 超时：服务未就绪，见上面日志")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="47.98.136.122")
    p.add_argument("--user", default="root")
    p.add_argument("--password")
    p.add_argument("--skip-upload", action="store_true", help="只改服务器配置，不重传代码")
    p.add_argument("--skip-provision", action="store_true", help="跳过 apt/pip/systemd/caddy 步骤")
    p.add_argument("--repack", action="store_true", help="重新打包，不使用缓存 tar.gz")
    deploy(p.parse_args())
