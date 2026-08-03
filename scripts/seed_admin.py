import argparse
import asyncio
import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an initial admin user")
    parser.add_argument("--email", default=os.environ.get("ADMIN_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD"))
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
    return parser.parse_args()


async def seed_admin() -> None:
    args = parse_args()

    if not args.email or not args.password:
        raise SystemExit(
            "ADMIN_EMAIL and ADMIN_PASSWORD are required (or pass --email/--password)"
        )

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == args.email))
        if existing:
            print(f"Admin user already exists: {existing.email} (role={existing.role})")
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

        print(f"Created admin user: {user.email} (role={user.role})")


if __name__ == "__main__":
    asyncio.run(seed_admin())
