"""
Seed script: creates the App Store review demo account and store.

Run once with:
    python seed_demo_store.py

Safe to re-run — checks for existing docs before inserting.

Demo credentials to give Apple:
    Email:    demo@llego.app
    Password: LlegoDemo2025!
"""

import asyncio
from datetime import datetime

import bcrypt
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

# ── Connection ────────────────────────────────────────────────────────────────
MONGO_URI = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627"
DB_NAME = "llego"  # adjust if your DB name differs

# ── Demo constants ────────────────────────────────────────────────────────────
DEMO_EMAIL = "demo@llego.app"
DEMO_PASSWORD = "LlegoDemo2025!"
DEMO_STORE_NAME = "Llego Demo Store"
DEMO_BUSINESS_NAME = "Llego Demo"

# Havana, Cuba coordinates (central location for the feed)
DEMO_LAT = 23.1136
DEMO_LNG = -82.3666


# ── Helpers ───────────────────────────────────────────────────────────────────

def hash_pw(password: str) -> str:
    pw_bytes = password.encode("utf-8")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def all_day_schedule() -> dict:
    """24/7 open schedule."""
    return {
        "days": [
            {"day": i, "isOpen": True, "hours": [{"open": "00:00", "close": "23:59"}]}
            for i in range(7)
        ],
        "temporaryStatus": {"temporallyClosed": False, "temporallyOpen": True, "reason": "Demo store - always open"},
    }


# ── Main seed ─────────────────────────────────────────────────────────────────

async def seed():
    client = AsyncIOMotorClient(MONGO_URI)

    # Try common DB names
    db = client[DB_NAME]
    # Quick sanity check — list collections
    cols = await db.list_collection_names()
    if not cols:
        # Fallback: try first available DB
        dbs = await client.list_database_names()
        user_dbs = [d for d in dbs if d not in ("admin", "local", "config")]
        if user_dbs:
            db = client[user_dbs[0]]
            print(f"⚠️  Using DB: {user_dbs[0]}")
        else:
            print("❌ No databases found. Check connection string.")
            return

    print(f"✅ Connected to DB: {db.name}")
    print(f"   Collections: {await db.list_collection_names()}\n")

    # ── 1. Demo user ──────────────────────────────────────────────────────────
    existing_user = await db.users.find_one({"email": DEMO_EMAIL})
    if existing_user:
        user_id = existing_user["_id"]
        print(f"👤 Demo user already exists: {user_id}")
    else:
        user_data = {
            "_id": ObjectId(),
            "name": "Demo User",
            "email": DEMO_EMAIL,
            "username": "demo_llego",
            "phone": None,
            "password": hash_pw(DEMO_PASSWORD),
            "role": "customer",
            "isPro": False,
            "wallet": {"local": 0.0, "usd": 0.0},
            "walletStatus": "active",
            "authProvider": "local",
            "createdAt": datetime.utcnow(),
        }
        await db.users.insert_one(user_data)
        user_id = user_data["_id"]
        print(f"✅ Created demo user: {user_id}  ({DEMO_EMAIL} / {DEMO_PASSWORD})")

    # ── 2. Demo business ──────────────────────────────────────────────────────
    # NOTE: The production collection has a typo — it's "bussisnes", not "businesses"
    biz_col = db["bussisnes"]
    existing_biz = await biz_col.find_one({"name": DEMO_BUSINESS_NAME})
    if existing_biz:
        biz_id = existing_biz["_id"]
        print(f"🏢 Demo business already exists: {biz_id}")
    else:
        biz_data = {
            "_id": ObjectId(),
            "name": DEMO_BUSINESS_NAME,
            "ownerId": user_id,
            "globalRating": 5.0,
            "avatar": "https://via.placeholder.com/150/023133/FFFFFF?text=Demo",
            "description": "This is the App Store review demo store. Orders are auto-accepted and payments are simulated.",
            "tags": ["demo"],
            "isActive": True,
            "approvalStatus": "approved",
            "approvedAt": datetime.utcnow(),
            "createdAt": datetime.utcnow(),
        }
        await biz_col.insert_one(biz_data)
        biz_id = biz_data["_id"]
        print(f"✅ Created demo business: {biz_id}")

    # ── 3. Payment methods: cash USD + stripe USD ─────────────────────────────
    # Find or create cash USD method
    cash_pm = await db.payment_methods.find_one({"method": "cash", "currency": "USD"})
    if cash_pm:
        cash_pm_id = cash_pm["_id"]
        print(f"💵 Cash USD payment method: {cash_pm_id}")
    else:
        cash_pm_data = {
            "_id": ObjectId(),
            "name": "Efectivo (USD)",
            "method": "cash",
            "currency": "USD",
            "code": "cash_usd_demo",
            "isActive": True,
            "commissionPercent": 0,
            "deliveryFeePercent": 0,
            "pickupEnabled": True,
            "deliveryOnly": False,
            "createdAt": datetime.utcnow(),
        }
        await db.payment_methods.insert_one(cash_pm_data)
        cash_pm_id = cash_pm_data["_id"]
        print(f"✅ Created cash USD payment method: {cash_pm_id}")

    # Find or create stripe USD method
    stripe_pm = await db.payment_methods.find_one({"method": "stripe", "currency": "USD"})
    if stripe_pm:
        stripe_pm_id = stripe_pm["_id"]
        print(f"💳 Stripe USD payment method: {stripe_pm_id}")
    else:
        stripe_pm_data = {
            "_id": ObjectId(),
            "name": "Tarjeta de crédito/débito (USD)",
            "method": "stripe",
            "currency": "USD",
            "code": "stripe_usd_demo",
            "isActive": True,
            "commissionPercent": 0,
            "pickupEnabled": True,
            "deliveryOnly": False,
            "createdAt": datetime.utcnow(),
        }
        await db.payment_methods.insert_one(stripe_pm_data)
        stripe_pm_id = stripe_pm_data["_id"]
        print(f"✅ Created stripe USD payment method: {stripe_pm_id}")

    payment_method_ids = [cash_pm_id, stripe_pm_id]

    # ── 4. Demo branch ────────────────────────────────────────────────────────
    existing_branch = await db.branches.find_one({"isDemoStore": True})
    if existing_branch:
        branch_id = existing_branch["_id"]
        print(f"🏪 Demo branch already exists: {branch_id}")
        # Ensure payment methods are up to date
        await db.branches.update_one(
            {"_id": branch_id},
            {"$set": {
                "paymentMethodIds": payment_method_ids,
                "isDemoStore": True,
            }}
        )
        print("   ✔ Payment methods updated on existing demo branch")
    else:
        branch_data = {
            "_id": ObjectId(),
            "businessId": biz_id,
            "name": DEMO_STORE_NAME,
            "address": "Calle 23, Vedado, La Habana",
            "coordinates": {
                "type": "Point",
                "coordinates": [DEMO_LNG, DEMO_LAT],  # [lng, lat]
            },
            "phone": "+53 55 000 000",
            "schedule": all_day_schedule(),
            "managerIds": [user_id],
            "isActive": True,
            "status": "open",
            "avatar": "https://via.placeholder.com/150/023133/FFFFFF?text=Demo",
            "coverImage": "https://via.placeholder.com/600x200/023133/FFFFFF?text=Llego+Demo+Store",
            "tipos": ["restaurante", "tienda"],  # Shows in multiple feed categories
            "paymentMethodIds": payment_method_ids,
            "wallet": {"local": 0.0, "usd": 0.0},
            "walletStatus": "active",
            "useAppMessaging": True,
            "catalogOnly": False,
            "pickupEnabled": True,          # Supports pickup
            "vehicles": ["moto", "bicicleta", "caminando"],  # must match BranchVehicle enum
            "deliveryRadius": 10.0,
            "acceptedCurrency": "USD",
            "acceptsQvapay": False,
            "acceptsZelle": False,
            "cashKycEnabled": False,
            "isDemoStore": True,            # ← Key flag for auto-accept
            "createdAt": datetime.utcnow(),
        }
        await db.branches.insert_one(branch_data)
        branch_id = branch_data["_id"]
        print(f"✅ Created demo branch: {branch_id}")

    # ── 5. Demo products ──────────────────────────────────────────────────────
    existing_products = await db.products.count_documents({"branchId": branch_id})
    if existing_products > 0:
        print(f"📦 Demo products already exist ({existing_products} items)")
    else:
        products = [
            {
                "_id": ObjectId(),
                "branchId": branch_id,
                "businessId": biz_id,
                "name": "Demo Coffee",
                "description": "A delicious demo coffee. No real charge will be made.",
                "price": 3.50,
                "currency": "USD",
                "imageUrl": "https://via.placeholder.com/300/6B4226/FFFFFF?text=Coffee",
                "isAvailable": True,
                "categoryName": "Bebidas",
                "stock": None,
                "createdAt": datetime.utcnow(),
            },
            {
                "_id": ObjectId(),
                "branchId": branch_id,
                "businessId": biz_id,
                "name": "Demo Sandwich",
                "description": "A tasty demo sandwich. No real charge will be made.",
                "price": 6.00,
                "currency": "USD",
                "imageUrl": "https://via.placeholder.com/300/8B7355/FFFFFF?text=Sandwich",
                "isAvailable": True,
                "categoryName": "Comida",
                "stock": None,
                "createdAt": datetime.utcnow(),
            },
            {
                "_id": ObjectId(),
                "branchId": branch_id,
                "businessId": biz_id,
                "name": "Demo Juice",
                "description": "A refreshing demo juice. No real charge will be made.",
                "price": 2.50,
                "currency": "USD",
                "imageUrl": "https://via.placeholder.com/300/FFA500/FFFFFF?text=Juice",
                "isAvailable": True,
                "categoryName": "Bebidas",
                "stock": None,
                "createdAt": datetime.utcnow(),
            },
            {
                "_id": ObjectId(),
                "branchId": branch_id,
                "businessId": biz_id,
                "name": "Demo Combo",
                "description": "Coffee + Sandwich combo. Demo only — no real payment.",
                "price": 8.50,
                "currency": "USD",
                "imageUrl": "https://via.placeholder.com/300/023133/FFFFFF?text=Combo",
                "isAvailable": True,
                "categoryName": "Combos",
                "stock": None,
                "createdAt": datetime.utcnow(),
            },
        ]
        await db.products.insert_many(products)
        print(f"✅ Created {len(products)} demo products")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  APP STORE REVIEW — DEMO ACCOUNT READY")
    print("═" * 60)
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print(f"  Store:    {DEMO_STORE_NAME}")
    print(f"  Branch ID: {branch_id}")
    print()
    print("  To test the full flow:")
    print("  1. Log in with the credentials above")
    print(f"  2. Find '{DEMO_STORE_NAME}' in the feed")
    print("  3. Add any product to cart")
    print("  4. Select Cash (USD) or Card as payment")
    print("  5. Place the order")
    print("  6. The store accepts automatically in ~4 seconds")
    print("  7. Payment completes automatically (no real charge)")
    print("  8. Watch order progress through all statuses")
    print("═" * 60)

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
