"""个人模型外发防护；假网络流覆盖真实 HTTP 编码，不调用外部服务。"""
import asyncio
import socket
import ssl
from types import SimpleNamespace

import httpcore
import httpx
import pytest

from integrations.deeptutor import model_http


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    monkeypatch.setattr(model_http, "getproxies", lambda: {})


@pytest.fixture
def public_dns(monkeypatch):
    calls = []
    def resolve(host, port, **kwargs):
        calls.append(host)
        return [(2, 1, 6, "", ("8.8.8.8", port))]
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    return calls


@pytest.mark.asyncio
async def test_request_pins_ip_and_preserves_host_and_sni(public_dns):
    transport = model_http.StudentModelTransport("https://model.example:8443/v1")
    seen = []
    async def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})
    await transport.transport.aclose()
    transport.transport = httpx.MockTransport(respond)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post("https://model.example:8443/v1/chat/completions", headers={"Authorization": "Bearer test-key"}, json={"model": "test"})
    assert response.status_code == 200
    assert seen[0].url.host == "8.8.8.8"
    assert seen[0].headers["host"] == "model.example:8443"
    assert seen[0].extensions["sni_hostname"] == "model.example"
    assert public_dns == ["model.example"]


@pytest.mark.asyncio
async def test_rebinding_to_private_ip_blocks_before_network(monkeypatch):
    transport = model_http.StudentModelTransport("https://model.example/v1")
    answers = iter(["8.8.8.8", "127.0.0.1"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", (next(answers), port))])
    model_http.resolve_public_endpoint("https://model.example/v1")
    sent = []
    await transport.transport.aclose()
    transport.transport = httpx.MockTransport(lambda request: sent.append(request))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.TransportError, match="内网"):
            await client.post("https://model.example/v1/chat/completions")
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["http://model.example/v1", "https://other.example/v1", "https://model.example:444/v1"])
async def test_origin_change_rejected_before_dns_or_network(target):
    async with model_http.build_student_http_client("https://model.example/v1") as client:
        with pytest.raises(httpx.TransportError, match="端点"):
            await client.post(target)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_redirect_never_forwards_key_even_if_client_follows(public_dns, status):
    transport = model_http.StudentModelTransport("https://model.example/v1")
    seen = []
    async def redirect(request):
        seen.append(request)
        return httpx.Response(status, headers={"Location": "https://127.0.0.1/steal"})
    await transport.transport.aclose()
    transport.transport = httpx.MockTransport(redirect)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        with pytest.raises(httpx.TransportError, match="重定向"):
            await client.post("https://model.example/v1/chat/completions", headers={"Authorization": "Bearer test-key"})
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_proxy_connect_uses_ip_but_tls_and_host_use_original_name(monkeypatch, public_dns):
    monkeypatch.setattr(model_http, "getproxies", lambda: {"https": "http://127.0.0.1:7890"})
    writes, tls, connections = [], [], []
    class Stream(httpcore.AsyncMockStream):
        async def write(self, buffer, timeout=None):
            writes.append(buffer)
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            tls.append((server_hostname, ssl_context.verify_mode, ssl_context.check_hostname))
            return self
    async def connect(self, host, port, **kwargs):
        connections.append((host, port))
        return Stream([b"HTTP/1.1 200 Connection established\r\n\r\n", b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"])
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    async with model_http.build_student_http_client("https://model.example/v1") as client:
        assert (await client.post("https://model.example/v1/chat/completions", content=b"{}")).status_code == 200
    wire = b"".join(writes)
    assert connections == [("127.0.0.1", 7890)]
    assert b"CONNECT 8.8.8.8:443 HTTP/1.1" in wire
    assert b"Host: model.example" in wire
    assert tls == [("model.example", ssl.CERT_REQUIRED, True)]


def test_unsupported_proxy_fails_instead_of_bypassing_proxy(monkeypatch):
    monkeypatch.setattr(model_http, "getproxies", lambda: {"https": "socks5://127.0.0.1:7890"})
    with pytest.raises(ValueError, match="HTTP CONNECT"):
        model_http.build_student_http_client("https://model.example")


@pytest.mark.asyncio
async def test_sdk_uses_guard_even_with_ssl_bypass_setting(monkeypatch):
    from deeptutor.services.llm import openai_http_client as helper
    monkeypatch.setattr(helper, "_external_http_client", model_http.build_student_http_client)
    kwargs = helper.openai_sdk_client_kwargs(api_key="test-key", base_url="https://model.example/v1", disable_ssl_verify=True, sdk_max_retries=3)
    assert kwargs["max_retries"] == 0
    client = kwargs["http_client"]
    assert not client.follow_redirects
    assert isinstance(client._transport, model_http.StudentModelTransport)
    await client.aclose()
    def broken(base_url):
        raise ValueError("guard unavailable")
    monkeypatch.setattr(helper, "_external_http_client", broken)
    with pytest.raises(ValueError, match="guard unavailable"):
        helper.openai_sdk_client_kwargs(api_key="test-key", base_url="https://model.example/v1")


def test_student_provider_never_exports_key_to_environment(monkeypatch):
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.services.llm.provider_core.openai_compat_provider import OpenAICompatProvider
    from deeptutor.services.provider_registry import find_by_name
    from deeptutor.services.llm import openai_http_client as helper
    monkeypatch.setattr(helper, "_external_http_client", None)
    monkeypatch.setattr(helper, "build_openai_http_client", lambda: None)
    writes = []
    monkeypatch.setattr(OpenAICompatProvider, "_setup_env", lambda *args: writes.append(args))
    token = set_current_user(SimpleNamespace(id="student-a", is_admin=False))
    try:
        provider = OpenAICompatProvider(api_key="test-key", api_base="https://model.example/v1", spec=find_by_name("openai"))
        asyncio.run(provider.aclose())
    finally:
        reset_current_user(token)
    assert writes == []


def test_provider_cache_separates_students_and_administrator():
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.services.llm.provider_factory import _provider_cache_key
    from deeptutor.services.llm.config import LLMConfig
    loop = asyncio.new_event_loop()
    from deeptutor.runtime.agentic.client import LLMClientConfig, _client_cache_key
    keys, agentic_keys = [], []
    try:
        for uid, admin in [("a", False), ("b", False), ("admin", True)]:
            token = set_current_user(SimpleNamespace(id=uid, is_admin=admin))
            try:
                keys.append(_provider_cache_key(LLMConfig(model="test-model", api_key="same-test-key"), loop))
                agentic_keys.append(_client_cache_key(LLMClientConfig("openai", "test-model", "same-test-key", "https://model.example/v1"), loop, False))
            finally:
                reset_current_user(token)
    finally:
        loop.close()
    assert len(set(keys)) == len(set(agentic_keys)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("use_proxy", [False, True])
@pytest.mark.parametrize("wrong_hostname", [False, True])
async def test_real_tls_checks_original_hostname_before_sending_key(monkeypatch, tmp_path, use_proxy, wrong_hostname):
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "model.example")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("model.example")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.load_cert_chain(cert_file, key_file)
    sni, received, tunnels, proxy_tasks = [], [], [], []
    server_ssl.set_servername_callback(lambda socket, hostname, ctx: sni.append(hostname))

    async def serve(reader, writer):
        received.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0, ssl=server_ssl)
    port = server.sockets[0].getsockname()[1]
    async def proxy(reader, writer):
        proxy_tasks.append(asyncio.current_task())
        upstream = None
        try:
            tunnels.append(await reader.readuntil(b"\r\n\r\n"))
            upstream_reader, upstream = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            async def copy(source, target):
                while chunk := await source.read(65536):
                    target.write(chunk)
                    await target.drain()
            forward = [asyncio.create_task(copy(reader, upstream)), asyncio.create_task(copy(upstream_reader, writer))]
            await asyncio.wait(forward, return_when=asyncio.FIRST_COMPLETED)
            for task in forward:
                task.cancel()
            await asyncio.gather(*forward, return_exceptions=True)
        finally:
            writer.close()
            if upstream:
                upstream.close()
    proxy_server = await asyncio.start_server(proxy, "127.0.0.1", 0) if use_proxy else None
    if proxy_server:
        proxy_port = proxy_server.sockets[0].getsockname()[1]
        monkeypatch.setattr(model_http, "getproxies", lambda: {"https": f"http://127.0.0.1:{proxy_port}"})
    else:
        original_connect = httpcore.AnyIOBackend.connect_tcp
        async def route(self, host, port, **kwargs):
            assert host == "8.8.8.8"
            return await original_connect(self, "127.0.0.1", port, **kwargs)
        monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", route)
    monkeypatch.setattr(model_http, "resolve_public_endpoint", lambda base: (httpx.URL(base), ["8.8.8.8"]))
    hostname = "wrong.example" if wrong_hostname else "model.example"
    base = f"https://{hostname}:{port}/v1"
    transport = model_http.StudentModelTransport(base)
    transport.transport._pool._ssl_context = ssl.create_default_context(cafile=cert_file)
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            if wrong_hostname:
                with pytest.raises(httpx.ConnectError):
                    await client.get(base, headers={"Authorization": "Bearer local-test-secret"})
            else:
                assert (await client.get(base, headers={"Authorization": "Bearer local-test-secret"})).status_code == 200
        assert sni == [hostname]
        assert bool(received) is not wrong_hostname
        if received:
            assert b"local-test-secret" in received[0]
        if use_proxy:
            assert tunnels[0].startswith(f"CONNECT 8.8.8.8:{port} HTTP/1.1".encode())
    finally:
        server.close()
        await server.wait_closed()
        if proxy_server:
            proxy_server.close()
            await proxy_server.wait_closed()
            await asyncio.gather(*proxy_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_ipv6_only_proxy_endpoint_fails_explicitly(monkeypatch):
    monkeypatch.setattr(model_http, "getproxies", lambda: {"https": "http://127.0.0.1:7890"})
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(10, 1, 6, "", ("2606:4700:4700::1111", port, 0, 0))])
    async with model_http.build_student_http_client("https://model.example/v1") as client:
        with pytest.raises(httpx.TransportError, match="IPv4"):
            await client.get("https://model.example/v1")
