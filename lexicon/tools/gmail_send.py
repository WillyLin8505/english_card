"""Send the owner a mail through their own Gmail (card #922, owner's decision on 問題回報 #1175).

The address and app password live in lexicon/.env and come only through app.config; nothing here
prints, logs or stores them. Sender and recipient are the same address: this mails the owner only.
"""
from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
TIMEOUT = 20


def _config():
    from app import config
    return config


def ready() -> bool:
    """Both .env fields are filled in; an unloadable config counts as not set up."""
    try:
        cfg = _config()
    except Exception:
        return False
    return bool(cfg.GMAIL_ADDRESS and cfg.GMAIL_APP_PASSWORD)


def send(subject: str, body: str) -> str | None:
    """None when sent, else a reason that is safe to store: never the server's text or a credential."""
    cfg = _config()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg.GMAIL_ADDRESS, cfg.GMAIL_ADDRESS
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT) as smtp:
            smtp.login(cfg.GMAIL_ADDRESS, cfg.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return "Gmail 不接受這組地址和應用程式密碼"
    except (smtplib.SMTPException, OSError, ValueError) as e:
        return f"寄送失敗（{type(e).__name__}）"
    return None
