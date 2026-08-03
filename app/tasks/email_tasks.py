import structlog

logger = structlog.get_logger()


async def send_order_confirmation(ctx: dict, order_id: str):
    """Send order confirmation email to customer."""
    logger.info("Sending order confirmation email", order_id=order_id)
    # TODO: Implement with SendGrid
    # 1. Fetch order from DB
    # 2. Build email template with order details
    # 3. Send via SendGrid API
    logger.info("Order confirmation email sent", order_id=order_id)


async def send_order_status_update(ctx: dict, order_id: str, new_status: str):
    """Send order status update notification to customer."""
    logger.info(
        "Sending order status update",
        order_id=order_id,
        new_status=new_status,
    )
    # TODO: Implement with SendGrid
    logger.info("Order status update email sent", order_id=order_id)


async def send_password_reset(ctx: dict, email: str, token: str):
    """Send password reset email."""
    logger.info("Sending password reset email", email=email)
    # TODO: Implement with SendGrid
    # Build reset URL: {FRONTEND_URL}/reset-password?token={token}
    logger.info("Password reset email sent", email=email)
