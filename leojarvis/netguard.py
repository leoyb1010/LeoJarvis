"""SSRF 防护：在抓取用户/LLM 提供的 URL 前，挡掉指向内网/本机/保留网段的请求。

威胁场景：用户（或被注入了恶意页面的 LLM）让 LeoJarvis「读」某个 URL，
攻击者借此让常驻在 Mac 上的 daemon 去访问 http://127.0.0.1:<port>、
169.254.169.254（云元数据）、或局域网里其它机器/服务，并把响应读回。

防护手段：解析主机名 → 把所有解析到的 IP 都做私网/保留判断 → 命中即拒绝。
同时对重定向逐跳复检（见 safe_get），避免「先返回公网地址再 302 到内网」。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class BlockedURLError(ValueError):
    """目标 URL 指向不允许访问的网段（内网/本机/保留地址）。"""


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def ensure_public_url(url: str) -> str:
    """校验 URL 协议与目标地址；通过则原样返回，否则抛 BlockedURLError。

    - 只允许 http/https。
    - 主机名解析出的**每一个** IP 都必须是公网地址（任意一个落在私网/保留段即拒绝）。
    """
    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise BlockedURLError(f"不支持的协议: {scheme or '(空)'}")
    host = parts.hostname
    if not host:
        raise BlockedURLError("URL 缺少主机名")

    # 主机本身就是 IP 字面量
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_is_blocked(literal):
            raise BlockedURLError(f"目标地址 {host} 属于内网/保留网段，已拒绝")
        return url

    # 主机名 → 解析所有 A/AAAA，逐个校验（含 DNS 重绑定式 evil.com→127.0.0.1）
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedURLError(f"无法解析主机 {host}: {exc}") from exc
    if not infos:
        raise BlockedURLError(f"无法解析主机 {host}")
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise BlockedURLError(f"主机 {host} 解析出无效地址 {ip_str}")
        if _ip_is_blocked(ip):
            raise BlockedURLError(f"主机 {host} 解析到内网/保留地址 {ip_str}，已拒绝")
    return url


def safe_get(client, url: str, *, max_redirects: int = 4, **kwargs):
    """用给定的 httpx.Client 安全 GET：禁用自动重定向，逐跳复检 SSRF。

    每一跳的目标都会经过 ensure_public_url，因此「先公网 200/302 再跳内网」也会被挡下。
    """
    current = ensure_public_url(url)
    for _ in range(max_redirects + 1):
        resp = client.get(current, follow_redirects=False, **kwargs)
        if resp.is_redirect and resp.has_redirect_location:
            nxt = str(resp.headers.get("location", ""))
            # 相对重定向交给 httpx 解析成绝对 URL 后再校验
            current = ensure_public_url(str(resp.next_request.url) if resp.next_request else nxt)
            continue
        return resp
    raise BlockedURLError("重定向次数过多")
