"""个人模型 HTTPS 外发：公网 IP 固定、原域名 TLS 校验、禁止重定向。"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.request import getproxies

import httpcore
import httpx


def resolve_public_endpoint(base_url: str) -> tuple[httpx.URL, list[str]]:
    try:
        url = httpx.URL(base_url)
        port = 443 if url.port is None else url.port
    except (httpx.InvalidURL, ValueError):
        raise ValueError("Base URL 格式或端口无效") from None
    if any(char.isspace() for char in base_url) or "\\" in base_url:
        raise ValueError("Base URL 包含无效字符")
    if url.scheme != "https" or not url.raw_host or not 1 <= port <= 65535:
        raise ValueError("Base URL 必须是 https 公网地址")
    if url.userinfo or url.query or url.fragment:
        raise ValueError("Base URL 不能包含凭据、查询参数或片段")
    host = url.raw_host.decode("ascii")
    if host in {"localhost", "metadata.google.internal"}:
        raise ValueError("Base URL 不能指向本机或云元数据地址")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(item[4][0])
                         for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        except (OSError, ValueError):
            raise ValueError("Base URL 域名无法解析") from None
    if not addresses or any(not address.is_global or address.is_multicast for address in addresses):
        raise ValueError("Base URL 不能指向内网或保留地址")
    return url, list(dict.fromkeys(str(address) for address in addresses))


class _HostnameStream(httpcore.AsyncNetworkStream):
    def __init__(self, stream, hostname: str):
        self.stream, self.hostname = stream, hostname

    async def read(self, max_bytes, timeout=None):
        return await self.stream.read(max_bytes, timeout)

    async def write(self, buffer, timeout=None):
        await self.stream.write(buffer, timeout)

    async def aclose(self):
        await self.stream.aclose()

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        # CONNECT 的目标是已校验 IP，证书和 SNI 仍必须使用原域名。
        return await self.stream.start_tls(ssl_context, self.hostname, timeout)


class _ProxyTLSBackend(httpcore.AnyIOBackend):
    def __init__(self, hostname: str):
        super().__init__()
        self.hostname = hostname

    async def connect_tcp(self, *args, **kwargs):
        return _HostnameStream(await super().connect_tcp(*args, **kwargs), self.hostname)


class StudentModelTransport(httpx.AsyncBaseTransport):
    def __init__(self, base_url: str):
        self.endpoint = httpx.URL(base_url)
        proxies = getproxies()
        proxy = proxies.get("https") or proxies.get("all")
        if proxy and httpx.URL(proxy).scheme != "http":
            raise ValueError("个人模型目前只支持 HTTP CONNECT 代理，请配置 HTTP 代理地址")
        self.uses_proxy = bool(proxy)
        self.transport = httpx.AsyncHTTPTransport(proxy=proxy, verify=True, trust_env=False, retries=0)
        if proxy:
            # shortcut: httpx 尚无公开 network_backend 参数；升级 httpx/httpcore 时运行代理 CONNECT 回归。
            self.transport._pool._network_backend = _ProxyTLSBackend(self.endpoint.raw_host.decode("ascii"))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        expected = (self.endpoint.scheme, self.endpoint.raw_host, self.endpoint.port)
        actual = (request.url.scheme, request.url.raw_host, request.url.port)
        if actual != expected or request.url.userinfo:
            raise httpx.TransportError("个人模型请求不能离开已配置端点")
        try:
            _, addresses = await asyncio.to_thread(resolve_public_endpoint, str(self.endpoint))
        except ValueError as exc:
            raise httpx.TransportError(str(exc)) from None
        address = next((item for item in addresses if ipaddress.ip_address(item).version == 4), addresses[0])
        if self.uses_proxy and ipaddress.ip_address(address).version != 4:
            # shortcut: httpcore 的 CONNECT 目标未给 IPv6 加括号；升级其实现后开放纯 IPv6 代理端点。
            raise httpx.TransportError("当前 HTTP CONNECT 代理仅支持带公网 IPv4 的模型端点")
        hostname = self.endpoint.raw_host.decode("ascii")
        authority = self.endpoint.netloc.decode("ascii")
        headers = request.headers.copy()
        headers["Host"] = authority
        pinned = httpx.Request(request.method, request.url.copy_with(host=address),
                               headers=headers, stream=request.stream,
                               extensions={**request.extensions, "sni_hostname": hostname})
        response = await self.transport.handle_async_request(pinned)
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise httpx.TransportError("个人模型端点不支持重定向，请填写最终 HTTPS 地址")
        return response

    async def aclose(self):
        await self.transport.aclose()


def build_student_http_client(base_url: str | None) -> httpx.AsyncClient:
    if not base_url:
        raise ValueError("请先配置个人模型 HTTPS 地址")
    return httpx.AsyncClient(transport=StudentModelTransport(base_url), follow_redirects=False,
                             trust_env=False, timeout=httpx.Timeout(60, connect=10))
