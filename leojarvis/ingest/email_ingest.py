from __future__ import annotations

import email
import imaplib
import sqlite3
from email.header import decode_header
from pathlib import Path
from urllib.parse import unquote

from .. import db, user_settings
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


def _email_accounts() -> list[dict]:
    """Support both legacy sources.toml and settings-page multi accounts."""
    accounts: list[dict] = []
    ui_email = user_settings.load().get("email", {})
    if ui_email.get("enabled", False):
        for row in ui_email.get("accounts", []):
            if isinstance(row, dict) and row.get("enabled", True):
                accounts.append(row)

    legacy = sources().get("email", {})
    if legacy.get("enabled"):
        accounts.append({
            "name": legacy.get("name") or legacy.get("user") or legacy.get("username") or "email",
            "host": legacy.get("host") or legacy.get("imap_host"),
            "user": legacy.get("user") or legacy.get("username"),
            "password": legacy.get("password"),
            "mailbox": legacy.get("mailbox") or "INBOX",
            "limit": legacy.get("limit", 20),
            "enabled": True,
        })
    return accounts


def _apple_mail_db() -> Path | None:
    mail_root = Path.home() / "Library/Mail"
    for version in ("V10", "V9", "V8", "V7"):
        path = mail_root / version / "MailData" / "Envelope Index"
        if path.exists():
            return path
    candidates = sorted(mail_root.glob("V*/MailData/Envelope Index"), reverse=True)
    return candidates[0] if candidates else None


def _mailbox_label(url: str | None) -> str:
    if not url:
        return "Apple Mail"
    tail = unquote(str(url).rsplit("/", 1)[-1] or "Apple Mail")
    return tail or "Apple Mail"


def apple_mail_unread_count() -> int | None:
    """Real Apple Mail unread count straight from the local Envelope Index.

    Counts read=0 messages, excluding Trash/Junk/Sent so the number matches the
    unread badge a user actually sees in Mail. Returns None when the DB cannot be
    read (no Mail data / no Full Disk Access), so callers can show 未授权 rather
    than a misleading 0.
    """
    path = _apple_mail_db()
    if not path:
        return None
    try:
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=2) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM messages m
                LEFT JOIN mailboxes mb ON mb.ROWID = m.mailbox
                WHERE m.read = 0 AND m.deleted = 0
                  AND COALESCE(mb.url, '') NOT LIKE '%Trash%'
                  AND COALESCE(mb.url, '') NOT LIKE '%Junk%'
                  AND COALESCE(mb.url, '') NOT LIKE '%Spam%'
                  AND COALESCE(mb.url, '') NOT LIKE '%Sent%'
                  AND COALESCE(mb.url, '') NOT LIKE '%Deleted%'
                """
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return None


def gmail_config() -> dict:
    return user_settings.load().get("gmail", {}) or {}


def gmail_unread_count() -> int | None:
    """Unread count for a dedicated Gmail account via IMAP UNSEEN (count only,
    never fetches bodies). Returns None if not configured or on connection error."""
    cfg = gmail_config()
    if not cfg.get("enabled"):
        return None
    user = cfg.get("user")
    password = cfg.get("app_password") or cfg.get("password")
    if not user or not password:
        return None
    host = cfg.get("host") or "imap.gmail.com"
    mailbox_name = cfg.get("mailbox") or "INBOX"
    box = None
    try:
        box = imaplib.IMAP4_SSL(str(host), int(cfg.get("port") or 993))
        box.login(str(user), str(password))
        box.select(str(mailbox_name), readonly=True)
        typ, data = box.search(None, "UNSEEN")
        if typ != "OK":
            return None
        return len([x for x in data[0].split() if x])
    except Exception:
        return None
    finally:
        if box is not None:
            try:
                box.logout()
            except Exception:
                pass


def _apple_mail_items(limit: int = 20, unread_only: bool = False) -> list[RawItem]:
    path = _apple_mail_db()
    if not path:
        return []
    where = "m.deleted=0"
    if unread_only:
        where += " AND m.read=0"
    try:
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=2) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT m.ROWID, m.message_id, m.date_received, m.read,
                       s.subject, a.address, a.comment, mb.url
                FROM messages m
                LEFT JOIN subjects s ON s.ROWID=m.subject
                LEFT JOIN addresses a ON a.ROWID=m.sender
                LEFT JOIN mailboxes mb ON mb.ROWID=m.mailbox
                WHERE {where}
                ORDER BY m.date_received DESC
                LIMIT ?
                """,
                (max(1, min(limit, 80)),),
            ).fetchall()
    except Exception:
        return []

    items: list[RawItem] = []
    for row in rows:
        subject = row["subject"] or "（无主题邮件）"
        sender = row["address"] or row["comment"] or "未知发件人"
        mailbox = _mailbox_label(row["url"])
        items.append(RawItem(
            source=f"email:Apple Mail:{mailbox}",
            domain="life",
            kind="email",
            title=str(subject),
            content=f"From: {sender}\nMailbox: {mailbox}\n状态：{'未读' if int(row['read'] or 0) == 0 else '最近邮件'}",
            meta={
                "from": sender,
                "account": mailbox,
                "message_id": row["message_id"] or f"apple-mail:{row['ROWID']}",
                "apple_mail_rowid": row["ROWID"],
                "read": bool(row["read"]),
                "date_received": row["date_received"],
                "dedup_key": f"email:apple:{row['ROWID']}",
            },
        ))
    return items


class EmailCollector(Collector):
    name = "email"
    domain = "life"

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        for account in _email_accounts():
            if account.get("provider") == "apple_mail":
                items.extend(_apple_mail_items(limit=int(account.get("limit") or 20), unread_only=bool(account.get("unread_only", False))))
                continue
            host = account.get("host") or account.get("imap_host")
            user = account.get("user") or account.get("username")
            password = account.get("password")
            if not host or not user or not password:
                continue
            mailbox = imaplib.IMAP4_SSL(str(host), int(account.get("port") or 993))
            try:
                mailbox.login(str(user), str(password))
                mailbox.select(str(account.get("mailbox") or "INBOX"))
                _, ids = mailbox.search(None, str(account.get("search") or "UNSEEN"))
                limit = int(account.get("limit") or 20)
                for num in ids[0].split()[-limit:]:
                    _, msg_data = mailbox.fetch(num, "(BODY.PEEK[HEADER])")
                    msg = email.message_from_bytes(msg_data[0][1])
                    subject = _decode(msg.get("Subject")) or "（无主题邮件）"
                    sender = _decode(msg.get("From"))
                    msg_id = _decode(msg.get("Message-ID")) or f"{user}:{num.decode('utf-8', 'ignore')}"
                    account_name = str(account.get("name") or user)
                    items.append(RawItem(
                        source=f"email:{account_name}",
                        domain="life",
                        kind="email",
                        title=subject,
                        content=f"From: {sender}",
                        meta={"from": sender, "account": account_name, "message_id": msg_id},
                    ))
            finally:
                try:
                    mailbox.logout()
                except Exception:
                    pass
        if not items and _email_accounts():
            return items
        if not items:
            cfg = user_settings.load().get("email", {})
            if cfg.get("apple_mail_fallback", True):
                raw = _apple_mail_items(limit=int(cfg.get("apple_mail_limit") or 20), unread_only=bool(cfg.get("apple_mail_unread_only", False)))
                # 只导入数据库里没见过的 Apple Mail，避免没有新邮件时反复把旧邮件推入判断链。
                for item in raw:
                    key = f"email:apple:{item.meta.get('apple_mail_rowid')}"
                    with db.conn() as c:
                        exists = c.execute("SELECT 1 FROM events WHERE dedup_key=?", (key,)).fetchone()
                    if not exists:
                        item.meta["dedup_key"] = key
                        items.append(item)
        return items
