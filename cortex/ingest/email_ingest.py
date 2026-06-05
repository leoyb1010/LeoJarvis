from __future__ import annotations

import email
import imaplib
from email.header import decode_header

from ..config import sources
from .base import Collector, RawItem


def _decode(value) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out: list[str] = []
    for blob, enc in parts:
        if isinstance(blob, bytes):
            out.append(blob.decode(enc or "utf-8", "ignore"))
        else:
            out.append(blob)
    return "".join(out)


class EmailCollector(Collector):
    name = "email"
    domain = "life"

    def collect(self) -> list[RawItem]:
        cfg = sources().get("email", {})
        if not cfg.get("enabled"):
            return []
        items: list[RawItem] = []
        mailbox = imaplib.IMAP4_SSL(cfg["host"])
        try:
            mailbox.login(cfg["user"], cfg["password"])
            mailbox.select("INBOX")
            _, ids = mailbox.search(None, "UNSEEN")
            for num in ids[0].split()[: int(cfg.get("limit", 20))]:
                _, msg_data = mailbox.fetch(num, "(BODY.PEEK[HEADER])")
                msg = email.message_from_bytes(msg_data[0][1])
                subject = _decode(msg.get("Subject")) or "（无主题邮件）"
                sender = _decode(msg.get("From"))
                items.append(RawItem(
                    source="email",
                    domain="life",
                    kind="email",
                    title=subject,
                    content=f"From: {sender}",
                    meta={"from": sender},
                ))
        finally:
            try:
                mailbox.logout()
            except Exception:
                return items
        return items
