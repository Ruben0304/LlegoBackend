"""Create MongoDB indexes required by cash KYC feature.

Usage:
  python3 create_kyc_indexes.py
"""

import asyncio

from clients.mongodb_client import close_mongo_connection, connect_to_mongo
from repositories.kyc_verification_repository import create_kyc_indexes
from repositories.payments_attempt_repository import create_payment_indexes


async def main():
    await connect_to_mongo()
    try:
        await create_payment_indexes()
        await create_kyc_indexes()
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
