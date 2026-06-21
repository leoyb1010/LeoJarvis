from __future__ import annotations

import os
import secrets

# 由反向代理 / 隧道注入的转发头。一旦请求带有任意一个，就说明它不是本机直连，
# 而是经 Cloudflare Tunnel / Tailscale Funnel / nginx 等转发进来的公网流量，
# 即使对端 IP 显示为 127.0.0.1、Host 头伪造成 localhost，也必须强制鉴权。
_FORWARD_HEADERS = (
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "forwarded",
    "cf-connecting-ip",
    "cf-ipcountry",
    "cf-ray",
    "tailscale-user-login",
    "tailscale-user-name",
    "x-tailscale-user",
)

_LOOPBACK_HOSTS = {"127.0.0.1", "::1"}


def api_token() -> str:
    return os.environ.get("LEOJARVIS_API_TOKEN", "").strip()


def is_static_request(path: str) -> bool:
    if path == "/" or path.startswith("/assets/"):
        return True
    return path.endswith((".html", ".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webmanifest"))


def is_loopback_peer(client_host: str | None) -> bool:
    """对端（真实 TCP 来源 IP）是否为本机回环地址。

    与 Host 头不同，对端 IP 不可被客户端伪造，因此可作为信任判断的基础。
    """
    host = (client_host or "").strip().lower()
    if not host:
        return False
    if host.startswith("::ffff:"):  # IPv4-mapped IPv6, e.g. ::ffff:127.0.0.1
        host = host[len("::ffff:"):]
    return host in _LOOPBACK_HOSTS


def has_forwarding_headers(headers) -> bool:
    """请求是否带有反向代理/隧道注入的转发头。

    `headers` 为类 Mapping（如 Starlette 的 Headers，大小写不敏感）。
    """
    for name in _FORWARD_HEADERS:
        try:
            value = headers.get(name)
        except Exception:  # noqa: BLE001 - 容忍非标准 headers 容器
            value = None
        if value:
            return True
    return False


def is_trusted_local(client_host: str | None, headers) -> bool:
    """是否为可豁免 token 的本机直连请求。

    必须同时满足：对端是回环地址，且不带任何转发头。
    经隧道进来的公网请求虽然对端也是 127.0.0.1，但一定带转发头，因此会被拒绝豁免，
    从而堵死「伪造 Host: localhost 绕过鉴权」的漏洞。
    """
    return is_loopback_peer(client_host) and not has_forwarding_headers(headers)


def bearer_token(auth_header: str | None) -> str:
    auth = (auth_header or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def is_authorized(supplied: str | None) -> bool:
    token = api_token()
    if not token:
        return True
    candidate = (supplied or "").strip()
    return bool(candidate) and secrets.compare_digest(candidate, token)
