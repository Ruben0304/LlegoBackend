"""Assign proper perfumeria categories to Fournier Parfums products.

This normalizes both uncategorized products and products incorrectly assigned
to tienda categories so mixed-branch feed filtering works correctly.
"""

from pathlib import Path
import argparse

from bson import ObjectId
from pymongo import MongoClient


BRANCH_NAME = "Fournier Parfums"

CATEGORY_IDS = {
    "amaderados": "69a26e955b4fd73f7a908c1a",
    "eau_de_parfum": "69a26e955b4fd73f7a908c16",
    "eau_de_toilette": "69a26e955b4fd73f7a908c17",
    "florales": "69a26e955b4fd73f7a908c19",
    "frescos_citricos": "69a26e955b4fd73f7a908c1c",
    "orientales": "69a26e955b4fd73f7a908c1b",
    "perfumes_mujer": "69a26e955b4fd73f7a908c13",
    "perfumes_hombre": "69a26e955b4fd73f7a908c14",
    "perfumes_unisex": "69a26e955b4fd73f7a908c15",
    "sets_regalo": "69a26e955b4fd73f7a908c1d",
}

PRODUCT_CATEGORY_MAP = {
    # Carolina Herrera
    "69a26a977cad0497ea6230cb": CATEGORY_IDS["eau_de_toilette"],  # CH Bad Boy EDT
    "69a26a987cad0497ea6230cd": CATEGORY_IDS["perfumes_hombre"],  # CH Bad Boy Elixir
    "69a26b287cad0497ea6230d3": CATEGORY_IDS["perfumes_mujer"],  # CH Good Girl Blush Elixir
    "69a26a9b7cad0497ea6230d1": CATEGORY_IDS["perfumes_mujer"],  # CH Good Girl Blush
    "69a26a9a7cad0497ea6230cf": CATEGORY_IDS["perfumes_mujer"],  # CH Good Girl
    "69a26b297cad0497ea6230d5": CATEGORY_IDS["perfumes_mujer"],  # CH La Bomba
    "69a26b2a7cad0497ea6230d7": CATEGORY_IDS["perfumes_mujer"],  # CH Very Good Girl Elixir
    # Caron
    "69a26a917cad0497ea6230c7": CATEGORY_IDS["frescos_citricos"],  # Caron L'eau Pure
    "69a26a967cad0497ea6230c9": CATEGORY_IDS["perfumes_hombre"],  # Caron Pour un Homme Sport
    # Dior
    "69a266877cad0497ea6230b5": CATEGORY_IDS["eau_de_parfum"],  # Dior Sauvage Eau Forte
    "69a26b2b7cad0497ea6230d9": CATEGORY_IDS["eau_de_parfum"],  # Dior Sauvage EDP
    # Issey Miyake
    "69a266897cad0497ea6230b7": CATEGORY_IDS["perfumes_hombre"],  # Fusion D'Issey
    "69a2668b7cad0497ea6230bb": CATEGORY_IDS["florales"],  # Eau&Magnolia
    "69a2668d7cad0497ea6230bd": CATEGORY_IDS["amaderados"],  # pour Homme Eau&Cedre
    "69a2668a7cad0497ea6230b9": CATEGORY_IDS["perfumes_mujer"],  # L'Eau D'Issey
    # Jean Paul Gaultier
    "69a266d57cad0497ea6230c3": CATEGORY_IDS["perfumes_hombre"],  # Le Male
    "69a2668e7cad0497ea6230bf": CATEGORY_IDS["perfumes_mujer"],  # La Belle
    "69a266cc7cad0497ea6230c1": CATEGORY_IDS["perfumes_hombre"],  # Le Beau Paradise Garden
    "69a266e07cad0497ea6230c5": CATEGORY_IDS["perfumes_hombre"],  # Le Male Elixir
    "69a263a009bea5041a351227": CATEGORY_IDS["perfumes_hombre"],  # Le Male Elixir Parfum Intense
    # Narciso Rodriguez
    "69a21631cf25865edf3e59dd": CATEGORY_IDS["eau_de_parfum"],  # Narciso
    "69a263a609bea5041a351229": CATEGORY_IDS["eau_de_toilette"],  # For Her EDT
    "69a262f409bea5041a351218": CATEGORY_IDS["eau_de_toilette"],  # For Her EDT
    "69a2631a09bea5041a35121a": CATEGORY_IDS["amaderados"],  # For Him Bleu Noir
    "69a262e109bea5041a351216": CATEGORY_IDS["eau_de_parfum"],  # all of me
    # UDV / sets
    "69a2634109bea5041a35121d": CATEGORY_IDS["sets_regalo"],  # UDV FLASH Gift Set
    "69a263bb09bea5041a35122b": CATEGORY_IDS["sets_regalo"],  # UDV FOR MEN Gift Set
    "69a2635409bea5041a351221": CATEGORY_IDS["sets_regalo"],  # UDV FOR MEN Gift Set
    "69a263bf09bea5041a35122d": CATEGORY_IDS["perfumes_mujer"],  # UDV Flash
    "69a2634709bea5041a35121f": CATEGORY_IDS["perfumes_hombre"],  # UDV For Men
    "69a2637a09bea5041a351223": CATEGORY_IDS["perfumes_mujer"],  # UDV INDRA
    "69a2638609bea5041a351225": CATEGORY_IDS["perfumes_mujer"],  # UDV ISA
    "69a260ac09bea5041a35120c": CATEGORY_IDS["sets_regalo"],  # UDV NIGHT Gift Set
    "69a260aa09bea5041a35120a": CATEGORY_IDS["perfumes_hombre"],  # UDV Night
    "69a260ae09bea5041a35120e": CATEGORY_IDS["perfumes_mujer"],  # UDV Oh ! Venise
    "69a260b009bea5041a351210": CATEGORY_IDS["perfumes_mujer"],  # UDV Pour Elle CHIC-ISSIME
    "69a260b109bea5041a351212": CATEGORY_IDS["perfumes_mujer"],  # UDV Pour Elle GOLD-ISSIME
    "69a260b309bea5041a351214": CATEGORY_IDS["perfumes_mujer"],  # UDV V.I.P
    # Versace
    "69a220c409bea5041a3511f6": CATEGORY_IDS["florales"],  # Bright Crystal Absolu
    "69a2213009bea5041a351200": CATEGORY_IDS["orientales"],  # Crystal Noir
}


def load_env() -> dict:
    env = {}
    for line in Path(".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the category assignments to MongoDB.",
    )
    args = parser.parse_args()

    env = load_env()
    client = MongoClient(env["MONGODB_URL"], serverSelectionTimeoutMS=30000)
    db = client[env.get("MONGODB_DATABASE", "llego")]

    branch = db["branches"].find_one(
        {"name": {"$regex": f"^{BRANCH_NAME}$", "$options": "i"}},
        {"name": 1},
    )
    if not branch:
        raise SystemExit(f"Branch not found: {BRANCH_NAME}")

    perfumeria_ids = {
        str(doc["_id"])
        for doc in db["product_categories"].find(
            {"branchType": "perfumeria"},
            {"_id": 1},
        )
    }
    unknown_categories = set(PRODUCT_CATEGORY_MAP.values()) - perfumeria_ids
    if unknown_categories:
        raise SystemExit(f"Unknown perfumeria category ids: {sorted(unknown_categories)}")

    products = list(
        db["products"].find({"branchId": branch["_id"]}, {"name": 1, "categoryId": 1})
    )
    product_ids = {str(doc["_id"]) for doc in products}
    unmapped = sorted(product_ids - set(PRODUCT_CATEGORY_MAP.keys()))
    if unmapped:
        raise SystemExit(f"Unmapped Fournier products: {unmapped}")

    print(f"Branch: {branch['name']}")
    print(f"Products to normalize: {len(PRODUCT_CATEGORY_MAP)}")

    updates = []
    for doc in sorted(products, key=lambda item: item["name"].lower()):
        product_id = str(doc["_id"])
        target_category_id = PRODUCT_CATEGORY_MAP[product_id]
        current_category_id = str(doc["categoryId"]) if doc.get("categoryId") else None
        if current_category_id != target_category_id:
            updates.append((product_id, doc["name"], current_category_id, target_category_id))

    print(f"Products needing update: {len(updates)}")
    for product_id, name, current_category_id, target_category_id in updates:
        print(
            {
                "product_id": product_id,
                "name": name,
                "from": current_category_id,
                "to": target_category_id,
            }
        )

    if not args.apply:
        print("Dry run only. Re-run with --apply to persist changes.")
        return 0

    for product_id, _, _, target_category_id in updates:
        db["products"].update_one(
            {"_id": ObjectId(product_id)},
            {"$set": {"categoryId": ObjectId(target_category_id)}},
        )

    print(f"Applied updates: {len(updates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
