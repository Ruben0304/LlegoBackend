"""Quick test script for re-ranking service."""
import asyncio
from services.reranking_service import reranking_service


async def test_reranking():
    """Test re-ranking with sample data."""
    print("Testing re-ranking service...\n")

    # Mock products
    class MockProduct:
        def __init__(self, id, name, branchId):
            self.id = id
            self.name = name
            self.branchId = branchId

        def model_dump(self):
            return {"id": self.id, "name": self.name, "branchId": self.branchId}

    products = [
        MockProduct("prod1", "Pizza Margherita", "branch1"),
        MockProduct("prod2", "Pizza Pepperoni", "branch2"),
        MockProduct("prod3", "Hamburguesa", "branch3"),
    ]

    # Mock vector scores
    vector_scores = {
        "prod1": 0.85,
        "prod2": 0.90,
        "prod3": 0.75,
    }

    # Test re-ranking
    ranked = await reranking_service.rerank_products(
        products=products,
        query="pizza",
        user_id=None,  # No user for this test
        user_location=None,  # No location for this test
        vector_scores=vector_scores
    )

    print("Re-ranked results:")
    print("-" * 80)
    for i, rp in enumerate(ranked, 1):
        print(f"{i}. {rp.product.name}")
        print(f"   Vector: {rp.vector_score:.3f} | "
              f"Popular: {rp.popularity_score:.3f} | "
              f"Proximity: {rp.proximity_score:.3f} | "
              f"Personal: {rp.personalization_score:.3f}")
        print(f"   → FINAL: {rp.final_score:.3f}\n")

    print("✓ Re-ranking service working!")


if __name__ == "__main__":
    asyncio.run(test_reranking())
