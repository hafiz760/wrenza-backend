"""SMTP sending, one function, two mailboxes.

Everything email-related goes through `send_email`. Keeping the transport in
one place means moving to a provider like Resend later is a change here rather
than in every task that sends something.
"""

from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from enum import Enum

import aiosmtplib
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


class Mailbox(str, Enum):
    """Which address a message is sent from.

    Named by role rather than address so callers do not hardcode
    `order@wrenza.com` in a dozen places.
    """

    ORDER = "order"
    INFO = "info"


def _credentials(mailbox: Mailbox) -> tuple[str, str]:
    settings = get_settings()
    if mailbox is Mailbox.ORDER:
        return settings.SMTP_ORDER_USER, settings.SMTP_ORDER_PASSWORD
    return settings.SMTP_INFO_USER, settings.SMTP_INFO_PASSWORD


async def send_email(
    mailbox: Mailbox,
    to: str,
    subject: str,
    html: str,
    text: str,
    reply_to: str | None = None,
) -> bool:
    """Send one message. Returns whether it was accepted by the server.

    Never raises. A failed email must not fail the order that triggered it —
    the customer has paid, and an SMTP hiccup is not their problem. Failures
    are logged with enough context to resend by hand.

    `text` is required, not optional: a multipart message scores better with
    spam filters and stays readable in clients that refuse HTML.
    """
    settings = get_settings()
    sender, password = _credentials(mailbox)

    if not settings.email_enabled or not sender or not password:
        logger.warning(
            "Email skipped — no credentials configured",
            mailbox=mailbox.value,
            to=to,
            subject=subject,
        )
        return False

    message = EmailMessage()
    message["From"] = f"{settings.SMTP_FROM_NAME} <{sender}>"
    message["To"] = to
    message["Subject"] = subject
    # Replies about an order should reach the order mailbox, not a black hole
    message["Reply-To"] = reply_to or sender
    message["Date"] = formatdate(localtime=True)
    # An explicit domain in the Message-ID matches the DKIM signing domain
    message["Message-ID"] = make_msgid(domain=sender.split("@")[-1])

    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=sender,
            password=password,
            # Port 465 is implicit TLS; 587 negotiates it with STARTTLS
            use_tls=settings.SMTP_PORT == 465,
            start_tls=settings.SMTP_PORT != 465,
            timeout=30,
        )
    except Exception as exc:
        logger.error(
            "Email failed to send",
            mailbox=mailbox.value,
            to=to,
            subject=subject,
            error=str(exc),
        )
        return False

    logger.info("Email sent", mailbox=mailbox.value, to=to, subject=subject)
    return True
