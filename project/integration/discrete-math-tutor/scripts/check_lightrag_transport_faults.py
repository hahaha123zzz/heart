"""仅回环网络故障注入：真实SDK、假凭据，不连接模型网关。"""
import argparse
import asyncio
import json
from pathlib import Path
import socket
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from openai import OpenAI
from knowledge.lightrag.config import _run_adapter_with_retry


def check(mode):
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen()
    server.settimeout(.1)
    stopped = threading.Event()
    accepted = []

    def peer(connection):
        with connection:
            if mode == 'timeout':
                stopped.wait(2)
            else:
                connection.settimeout(1)
                connection.recv(1024)  # 收到ClientHello后关闭，产生真实TLS握手失败。

    def serve():
        while not stopped.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            accepted.append(time.monotonic())
            threading.Thread(target=peer, args=(connection,), daemon=True).start()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    # TLS仅对本机故障夹具关闭证书核验；不读取真实凭据或更改宿主模型配置。
    client = OpenAI(api_key='isolated-fault-placeholder',
        base_url=f'https://127.0.0.1:{server.getsockname()[1]}/v1',
        timeout=.2, max_retries=0,
        http_client=httpx.Client(verify=False, trust_env=False, timeout=.2))
    attempts = []

    async def request():
        attempts.append(time.monotonic())
        return await asyncio.to_thread(client.chat.completions.create,
            model='isolated-test', messages=[{'role':'user', 'content':'test'}], max_tokens=1)

    start = time.monotonic()
    try:
        asyncio.run(_run_adapter_with_retry(request, io_bridge=None))
        raise AssertionError('故障不应返回模型答案')
    except Exception as exc:
        names = []
        cause = exc
        while cause is not None and len(names) < 8:
            names.append(type(cause).__name__)
            cause = cause.__cause__
        assert len(attempts) == 3, (mode, len(attempts), names)
        assert type(exc).__name__ == ('APITimeoutError' if mode == 'timeout' else 'APIConnectionError'), names
        return {'mode':mode, 'attempts':len(attempts), 'accepted_connections':len(accepted),
                'seconds':time.monotonic()-start, 'error_chain':names,
                'fallback':False, 'real_gateway_called':False, 'sdk_transport_retries':0}
    finally:
        stopped.set()
        server.close()
        worker.join(timeout=1)
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = [check(mode) for mode in ('tls_eof', 'timeout')]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False))
