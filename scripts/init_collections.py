"""Initialize Qdrant collections with correct vector configuration."""
import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from clients import connect_to_qdrant, create_collection, get_qdrant_client
from qdrant_client.models import Distance
from core.config import settings


async def init_collection(collection_name: str, recreate: bool = False) -> bool:
    """Initialize or recreate a single collection."""
    client = get_qdrant_client()

    try:
        collections = await client.get_collections()
        existing_collections = [c.name for c in collections.collections]

        if collection_name in existing_collections:
            print(f"⚠️  Collection '{collection_name}' already exists")
            if recreate:
                print(f"🗑️  Deleting collection '{collection_name}'...")
                await client.delete_collection(collection_name=collection_name)
                print("✅ Collection deleted")
            else:
                print(f"✓ Skipping '{collection_name}' (already exists)")
                return True
    except Exception as e:
        print(f"❌ Error checking collection '{collection_name}': {e}")
        return False

    # Create collection with correct vector configuration
    print(f"\n📦 Creating collection '{collection_name}'...")
    print(f"   Vector size: {settings.embedding_dimension}")
    print(f"   Distance metric: COSINE")

    try:
        success = await create_collection(
            collection_name=collection_name,
            vector_size=settings.embedding_dimension,  # 768 from Gemini
            distance=Distance.COSINE
        )

        if success:
            print(f"✅ Collection '{collection_name}' created successfully!")
            return True
        else:
            print(f"❌ Failed to create collection '{collection_name}'")
            return False

    except Exception as e:
        print(f"❌ Error creating collection '{collection_name}': {e}")
        return False


async def init_all_collections(recreate: bool = False):
    """Initialize all required Qdrant collections."""
    print("=" * 70)
    print("🔧 Initializing Qdrant Collections")
    print("=" * 70)

    # Connect to Qdrant
    print("\n1️⃣ Connecting to Qdrant...")
    connected = await connect_to_qdrant()

    if not connected:
        print("❌ Failed to connect to Qdrant. Check your connection settings.")
        return False

    print("✅ Connected to Qdrant\n")

    # Collections to create
    collections = [
        "users",
        "businesses",
        "branches",
        "products"
    ]

    print(f"2️⃣ Initializing {len(collections)} collections...")
    print("=" * 70)

    results = {}
    for collection_name in collections:
        print(f"\n▶ Processing '{collection_name}'...")
        success = await init_collection(collection_name, recreate)
        results[collection_name] = success

    # Summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)

    for collection_name, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {collection_name}")

    all_success = all(results.values())

    if all_success:
        print("\n" + "=" * 70)
        print("✅ ALL COLLECTIONS READY")
        print("=" * 70)
        print("\nYou can now use the application normally.")
    else:
        print("\n⚠️  Some collections failed to initialize")

    return all_success


async def main():
    """Main entry point."""
    try:
        # You can pass recreate=True to force recreate all collections
        success = await init_all_collections(recreate=False)
        if not success:
            exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
