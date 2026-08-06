"""Background email jobs.

Each task takes ids and loads its own data. A queued job can run seconds or
minutes after it was enqueued, so passing a rendered payload risks sending a
snapshot that no longer matches the order.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models.order import Order
from app.db.session import AsyncSessionLocal
from app.services.email import Mailbox, send_email
from app.services.email.render import render

logger = structlog.get_logger()


def _order_context(order: Order) -> dict:
    """Shape one order for the templates.

    Reads the stored snapshot rather than the live product, so an email about a
    six-month-old order still shows what was actually bought, at the price it
    was bought for, even if the product has since changed or been deleted.
    """
    items = []
    for item in order.items:
        snapshot = item.product_snapshot or {}
        variation = snapshot.get("variation") or {}
        options = ", ".join(variation.get("attributes", {}).values())
        unit = float(item.unit_price or snapshot.get("price") or 0)

        items.append(
            {
                "name": snapshot.get("name", "Item"),
                "options": options or None,
                "quantity": item.quantity,
                "line_total": unit * item.quantity,
            }
        )

    name_parts = [order.guest_first_name, order.guest_last_name]
    customer_name = " ".join(p for p in name_parts if p) or None

    return {
        "order_number": order.order_number,
        "customer_name": customer_name,
        "email": order.email,
        "phone": order.phone,
        "notes": order.notes,
        "items": items,
        "subtotal": float(order.subtotal),
        "discount": float(order.discount),
        "shipping": float(order.shipping),
        "total": float(order.total),
        "address": order.shipping_address or {},
    }


async def _load_order(session, order_id: str) -> Order | None:
    result = await session.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


async def send_order_confirmation(ctx: dict, order_id: str) -> None:
    """Confirmation to the customer, and an alert to the shop.

    Both go out together: same trigger, and neither is useful without the
    order having been placed.
    """
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        order = await _load_order(session, order_id)
        if order is None:
            logger.error("Confirmation skipped — order not found", order_id=order_id)
            return
        context = _order_context(order)

    if context["email"]:
        subject = f"Order confirmed — {context['order_number']}"
        html, text = render(
            "order_confirmation",
            subject=subject,
            preheader=f"We have your order. Rs. {context['total']:,.0f} on delivery.",
            **context,
        )
        await send_email(
            Mailbox.ORDER, to=context["email"], subject=subject, html=html, text=text
        )
    else:
        logger.warning("Order has no email address", order_id=order_id)

    if settings.ADMIN_EMAIL:
        subject = f"New order — {context['order_number']}"
        html, text = render(
            "new_order_alert",
            subject=subject,
            preheader=(
                f"Rs. {context['total']:,.0f} to pack for "
                f"{context['customer_name'] or 'a guest'}."
            ),
            **context,
        )
        await send_email(
            Mailbox.ORDER, to=settings.ADMIN_EMAIL, subject=subject, html=html, text=text
        )


async def send_order_status_update(ctx: dict, order_id: str, new_status: str) -> None:
    """Shipped or delivered only.

    Emailing on every internal transition — confirmed, processing — trains
    people to stop opening these, so the ones that matter get ignored too.
    """
    if new_status not in {"shipped", "delivered"}:
        return

    async with AsyncSessionLocal() as session:
        order = await _load_order(session, order_id)
        if order is None:
            logger.error("Status email skipped — order not found", order_id=order_id)
            return
        context = _order_context(order)
        context["status"] = new_status
        context["tracking_number"] = order.tracking_number

    if not context["email"]:
        return

    if new_status == "shipped":
        subject = f"On its way — {context['order_number']}"
        preheader = "Your order has left our workshop."
    else:
        subject = f"Delivered — {context['order_number']}"
        preheader = "Your order has arrived."

    html, text = render("order_status", subject=subject, preheader=preheader, **context)
    await send_email(
        Mailbox.ORDER, to=context["email"], subject=subject, html=html, text=text
    )


async def send_order_cancelled(ctx: dict, order_id: str) -> None:
    """Confirms nothing will arrive and nothing is owed."""
    async with AsyncSessionLocal() as session:
        order = await _load_order(session, order_id)
        if order is None:
            logger.error("Cancellation skipped — order not found", order_id=order_id)
            return
        context = _order_context(order)

    if not context["email"]:
        return

    subject = f"Order cancelled — {context['order_number']}"
    html, text = render(
        "order_cancelled",
        subject=subject,
        preheader="Nothing will be delivered and there is nothing to pay.",
        **context,
    )
    await send_email(
        Mailbox.ORDER, to=context["email"], subject=subject, html=html, text=text
    )


async def send_password_reset(ctx: dict, email: str, token: str) -> None:
    """Reset link. Sent from info@, not order@ — an account matter, not an order."""
    settings = get_settings()
    reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"

    subject = "Reset your Wrenza password"
    html, text = render(
        "password_reset",
        subject=subject,
        preheader="Use this link within 30 minutes.",
        reset_url=reset_url,
        expires_minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES,
    )
    await send_email(Mailbox.INFO, to=email, subject=subject, html=html, text=text)


async def send_contact_enquiry(
    ctx: dict, name: str, email: str, subject_line: str, message: str
) -> None:
    """Contact form submissions.

    `Reply-To` is the enquirer, so answering from the inbox reaches them
    directly rather than bouncing off info@.
    """
    settings = get_settings()
    if not settings.ADMIN_EMAIL:
        logger.warning("Contact enquiry not emailed — no ADMIN_EMAIL set")
        return

    subject = f"Enquiry — {subject_line}"
    html, text = render(
        "contact_form",
        subject=subject,
        preheader=f"{name} asks about {subject_line.lower()}.",
        subject_line=subject_line,
        name=name,
        email=email,
        message=message,
    )
    await send_email(
        Mailbox.INFO,
        to=settings.ADMIN_EMAIL,
        subject=subject,
        html=html,
        text=text,
        reply_to=email,
    )
