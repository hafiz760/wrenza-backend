"""Create the first admin user.

Run by the container on every start. A fresh database has no accounts and the
dashboard has no sign-up, so without this there is no way into a new
deployment.

Idempotent, and deliberately conservative: it does nothing if *any* admin
already exists. Checking for the configured email alone would quietly add a
second admin after someone changed theirs.

Only the admin is seeded. Products, categories and orders are real business
data — inventing them on startup would put fictional items in a live shop.
"""

import argparse
import asyncio
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an initial admin user")
    # ADMIN_USER_EMAIL, not ADMIN_EMAIL — the latter is the address that
    # receives new-order alerts, and reusing it would create an admin login
    # for order@wrenza.com.
    parser.add_argument("--email", default=os.environ.get("ADMIN_USER_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("ADMIN_USER_PASSWORD"))
    parser.add_argument(
        "--first-name", default=os.environ.get("ADMIN_FIRST_NAME", "Admin")
    )
    parser.add_argument(
        "--last-name", default=os.environ.get("ADMIN_LAST_NAME", "User")
    )
    parser.add_argument("--phone", default=os.environ.get("ADMIN_PHONE"))
    parser.add_argument(
        "--role",
        choices=["admin", "manager"],
        default=os.environ.get("ADMIN_ROLE", "admin"),
    )
    # Startup should not fail because seeding is unconfigured; a human running
    # this by hand wants to be told they got it wrong.
    parser.add_argument(
        "--quiet-if-unconfigured",
        action="store_true",
        help="Exit 0 without complaining when no credentials are set.",
    )
    return parser.parse_args()


async def seed_admin() -> None:
    args = parse_args()

    if not args.email or not args.password:
        message = (
            "No admin seeded — set ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD "
            "(or pass --email/--password)"
        )
        if args.quiet_if_unconfigured:
            print(f"  {message}")
            return
        raise SystemExit(message)

    async with AsyncSessionLocal() as session:
        # Any admin at all, not just this email. Someone who renamed their
        # account should not end up with a second one on the next restart.
        existing_admin = await session.scalar(
            select(User).where(User.role == UserRole.ADMIN)
        )
        if existing_admin:
            print(f"  Admin already exists: {existing_admin.email}")
            return

        # Separately guard the email: it is unique, and a customer may have
        # registered with it before anyone got round to seeding.
        taken = await session.scalar(select(User).where(User.email == args.email))
        if taken:
            print(
                f"  Cannot seed admin — {args.email} is already registered "
                f"as {taken.role.value}",
                file=sys.stderr,
            )
            return

        user = User(
            first_name=args.first_name,
            last_name=args.last_name,
            email=args.email,
            password_hash=await hash_password(args.password),
            phone=args.phone,
            role=UserRole(args.role),
            is_active=True,
        )
        session.add(user)
        await session.commit()

        print(f"  Created admin: {user.email}")


if __name__ == "__main__":
    asyncio.run(seed_admin())
