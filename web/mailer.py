"""Sending the verification code.

Configured entirely from the environment, and honest when it isn't:

  AIW_SMTP_HOST      smtp.gmail.com
  AIW_SMTP_PORT      587
  AIW_SMTP_USER      you@gmail.com
  AIW_SMTP_PASSWORD  a Gmail **App Password**, not your account password
  AIW_SMTP_FROM      optional display address, defaults to AIW_SMTP_USER

Gmail rejects your normal password over SMTP. Turn on 2-Step Verification,
then create an App Password at https://myaccount.google.com/apppasswords and
use that 16-character value.

With nothing configured, `send_code()` reports `delivered=False` and returns
the code so the sign-up screen can show it on the page. That keeps the flow
usable in development without pretending an email went out — the screen says
plainly that it was not sent.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from lucida.observability import get_logger

logger = get_logger("mailer")


@dataclass
class Delivery:
    delivered: bool
    detail: str = ""


def _cfg() -> dict[str, str]:
    return {
        "host": os.environ.get("AIW_SMTP_HOST", "").strip(),
        "port": os.environ.get("AIW_SMTP_PORT", "587").strip() or "587",
        "user": os.environ.get("AIW_SMTP_USER", "").strip(),
        "password": os.environ.get("AIW_SMTP_PASSWORD", "").strip(),
        "sender": (os.environ.get("AIW_SMTP_FROM", "").strip()
                   or os.environ.get("AIW_SMTP_USER", "").strip()),
    }


def configured() -> bool:
    c = _cfg()
    return bool(c["host"] and c["user"] and c["password"])


def status() -> str:
    if not configured():
        return "not configured — codes are shown on screen instead"
    c = _cfg()
    return f"sending as {c['sender']} via {c['host']}:{c['port']}"


BODY = """Hello{name},

Your Lucida verification code is:

    {code}

It expires in {ttl} minutes. If you didn't ask for this, you can ignore
this message — nobody can use the code without it.

— Lucida
"""


def send_code(to_email: str, code: str, owner_name: str = "",
              ttl_minutes: int = 15) -> Delivery:
    """Send the code. Never raises — delivery failure is reported, not thrown."""
    if not configured():
        logger.warning("SMTP not configured; verification code not sent")
        return Delivery(False, "Email is not set up on this server.")

    c = _cfg()
    name = f" {owner_name}" if owner_name else ""
    message = EmailMessage()
    message["Subject"] = f"{code} is your Lucida code"
    message["From"] = c["sender"]
    message["To"] = to_email
    message.set_content(BODY.format(name=name, code=code, ttl=ttl_minutes))

    try:
        context = ssl.create_default_context()
        if c["port"] == "465":
            with smtplib.SMTP_SSL(c["host"], int(c["port"]), context=context,
                                  timeout=20) as s:
                s.login(c["user"], c["password"])
                s.send_message(message)
        else:
            with smtplib.SMTP(c["host"], int(c["port"]), timeout=20) as s:
                s.starttls(context=context)
                s.login(c["user"], c["password"])
                s.send_message(message)
        logger.info("verification code sent")
        return Delivery(True)
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP rejected the credentials")
        return Delivery(
            False,
            "The mail server refused those credentials. Gmail needs an App "
            "Password, not your normal password.",
        )
    except Exception as exc:  # noqa: BLE001 — never break sign-up over email
        logger.error("SMTP send failed: %s", exc)
        return Delivery(False, f"Could not reach the mail server: {exc}")
