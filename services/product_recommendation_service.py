"""Product recommendation service using Claude AI.

This service provides complementary product recommendations based on cart items.
"""

import asyncio
import json
from typing import List, Optional

import anthropic

from core.config import settings
from repositories import products_repo
from services.ai_models import (
    ProductRecommendation,
    ProductRecommendationsResponse,
)

# Safety cap: how many candidate names we send to the model. The names+indices
# list is cheap, but if a branch has hundreds of products we bound the prompt.
MAX_CANDIDATES = 120


class ProductRecommendationService:
    """Service for generating product recommendations using Claude AI."""

    def __init__(self):
        """Initialize product recommendation service."""
        if not settings.anthropic_api_key:
            print(
                "⚠ Anthropic API key not configured. Product recommendations will be disabled."
            )
            self.client = None
            self.model_name = None
        else:
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            self.model_name = settings.anthropic_model

    async def get_recommendations(
        self, product_ids: List[str], limit: int = 5
    ) -> Optional[ProductRecommendationsResponse]:
        """Complementary recommendations for the cart.

        Serves from the precomputed per-product complements (no live LLM,
        index built nightly with Sonnet). Only falls back to a live Claude call
        for products not indexed yet — the cold window right after they're added,
        before the nightly cron runs.
        """
        if not product_ids:
            return None
        precomputed = await self._from_precomputed(product_ids, limit)
        if precomputed is not None:
            return precomputed
        return await self._live_recommendations(product_ids, limit)

    async def _from_precomputed(
        self, product_ids: List[str], limit: int
    ) -> Optional[ProductRecommendationsResponse]:
        """Merge precomputed complements across all cart items (ponderation).

        A complement recommended for several cart items adds up its score, so the
        most broadly-complementary items rise to the top. Returns None only when
        NO cart product has precomputed data (so the caller falls back to live).
        """
        from clients import get_database

        cart_ids = [str(p).strip() for p in product_ids if str(p).strip()]
        if not cart_ids:
            return None

        db = get_database()
        docs = (
            await db["product_complements"]
            .find({"_id": {"$in": cart_ids}})
            .to_list(length=None)
        )
        if not docs:
            return None  # nothing indexed for this cart -> fall back to live LLM

        cart_set = set(cart_ids)
        agg: dict = {}  # complementId -> {"score", "best", "reason"}
        for doc in docs:
            for comp in doc.get("complements", []):
                cid = comp.get("productId")
                if not cid or cid in cart_set:
                    continue
                score = float(comp.get("score", 0.5))
                reason = str(comp.get("reason", "")).strip()
                cur = agg.get(cid)
                if cur:
                    cur["score"] += score  # ponderación entre ítems del carrito
                    if score > cur["best"]:
                        cur["best"] = score
                        cur["reason"] = reason
                else:
                    agg[cid] = {"score": score, "best": score, "reason": reason}

        if not agg:
            return ProductRecommendationsResponse(
                recommendations=[],
                reasoning="No hay complementos para este carrito en este momento.",
            )

        ranked = sorted(agg.items(), key=lambda kv: kv[1]["score"], reverse=True)

        # Hydrate to drop unavailable/deleted items and to get names.
        candidate_ids = [cid for cid, _ in ranked][: max(limit * 4, limit)]
        products = await products_repo.get_by_ids(candidate_ids)
        by_id = {str(p.id): p for p in products}

        recommendations: List[ProductRecommendation] = []
        for cid, info in ranked:
            product = by_id.get(cid)
            if not product or not getattr(product, "availability", True):
                continue
            recommendations.append(
                ProductRecommendation(
                    product_id=cid,
                    product_name=product.name,
                    reasoning=info["reason"] or "Complementa tu carrito.",
                )
            )
            if len(recommendations) >= limit:
                break

        print(
            f"🛒 [recommendations] precomputado: {len(recommendations)} de "
            f"{len(docs)} productos del carrito indexados"
        )
        return ProductRecommendationsResponse(
            recommendations=recommendations,
            reasoning="Productos que complementan tu carrito.",
        )

    async def _live_recommendations(
        self, product_ids: List[str], limit: int = 5
    ) -> Optional[ProductRecommendationsResponse]:
        """Live Claude (Haiku) recommender — cold-start fallback only."""
        if not self.client:
            print("⚠ Anthropic not configured, skipping recommendations")
            return None

        if not product_ids:
            print("⚠ No product IDs provided for recommendations")
            return None

        try:
            print(f"\n{'='*80}")
            print(f"🛒 [RECOMMENDATIONS] Starting recommendation request")
            print(f"   Product IDs: {product_ids}")
            print(f"   Limit: {limit}")

            # Step 1: Get cart products (with name and description)
            cart_products = await products_repo.get_by_ids(product_ids)
            print(f"   Cart products fetched: {len(cart_products)}")

            if not cart_products:
                print(f"⚠️  No products found for IDs: {product_ids}")
                print(f"{'='*80}\n")
                return None

            # Step 2: Get the branch ID from the first product
            # IMPORTANT: Only use the first branch if products are from multiple branches
            first_branch_id = cart_products[0].branchId
            print(
                f"🏪 Using branch ID: {first_branch_id} (from product: {cart_products[0].name})"
            )

            # Step 3: Get ALL products from the same branch (DIRECT MongoDB query, NO cache)
            print(f"📦 Fetching all products from branch {first_branch_id}...")
            print(f"   Using DIRECT MongoDB query (bypassing cache)")

            # Query MongoDB directly without cache
            from bson import ObjectId
            from clients import get_database
            from domain.models import Product

            db = get_database()
            # Convert branchId to ObjectId for proper MongoDB query
            branch_id_obj = ObjectId(str(first_branch_id))
            cursor = db["products"].find({"branchId": branch_id_obj})
            documents = await cursor.to_list(length=None)
            all_branch_products = [Product(**doc) for doc in documents]

            print(f"   Total products in branch: {len(all_branch_products)}")

            if all_branch_products:
                print(f"   First 3 products: {[p.name for p in all_branch_products[:3]]}")
            else:
                print(
                    f"   ⚠️ WARNING: No products found in MongoDB for branch {first_branch_id}"
                )

            # If no products in branch, return empty recommendations
            if not all_branch_products or len(all_branch_products) == 0:
                print(
                    f"⚠️ No products found in branch {first_branch_id}, returning empty recommendations"
                )
                return ProductRecommendationsResponse(
                    recommendations=[],
                    reasoning="No hay productos disponibles en esta tienda para hacer recomendaciones.",
                )

            # Filter out products already in cart
            cart_product_ids = {p.id for p in cart_products}
            available_for_recommendation = [
                p for p in all_branch_products if p.id not in cart_product_ids
            ]

            print(
                f"📦 Available for recommendation: {len(available_for_recommendation)} products (excluding {len(cart_product_ids)} in cart)"
            )

            # If no products available after filtering cart, return empty
            if not available_for_recommendation:
                print("⚠️ All branch products are already in cart, no recommendations")
                return ProductRecommendationsResponse(
                    recommendations=[],
                    reasoning="Todos los productos disponibles en esta tienda ya están en tu carrito.",
                )

            # Step 4: Bound candidates and build an index-based prompt.
            candidates = available_for_recommendation[:MAX_CANDIDATES]
            if len(available_for_recommendation) > MAX_CANDIDATES:
                print(
                    f"   Capping candidates {len(available_for_recommendation)} -> {MAX_CANDIDATES}"
                )

            prompt = self._build_recommendation_prompt(
                cart_products=cart_products,
                candidates=candidates,
                limit=limit,
            )

            # Step 5: Call Claude. The model only returns indices + short reasons,
            # so the output stays tiny.
            print(
                f"🤖 Calling Claude (candidates={len(candidates)}, limit={limit})..."
            )
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model_name,
                max_tokens=400,
                temperature=0.5,
                system=self._SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            if not response.content:
                print("⚠ Empty response from Claude")
                return None

            content = response.content[0].text.strip()

            # Step 6: Parse the index-based output, map indices back to products.
            recommendations = self._parse_picks(content, candidates, limit)
            print(
                f"✅ Returning {len(recommendations.recommendations)} recommendations"
            )
            print(f"{'='*80}\n")
            return recommendations

        except Exception as e:
            print(f"❌ Error generating recommendations: {e}")
            print(f"{'='*80}\n")
            import traceback

            traceback.print_exc()
            return None

    # System prompt: concise, complementarity-focused (cross-sell, not substitutes).
    _SYSTEM_PROMPT = (
        "Eres el asistente de ventas de Llego. Tu trabajo es subir el ticket "
        "recomendando productos COMPLEMENTARIOS: lo que pega con lo que el cliente "
        "ya lleva (bebida, acompañante, postre, salsa, extra). NUNCA recomiendes "
        "sustitutos ni más de lo mismo: si lleva una hamburguesa de res, sugiere una "
        "bebida o unas papas, NO otra hamburguesa ni otro plato de res. Eliges de una "
        "lista numerada y respondes SOLO con el JSON pedido."
    )

    def _build_recommendation_prompt(self, cart_products, candidates, limit: int) -> str:
        """Build an index-based prompt: cart names + a numbered candidate list.

        We send names only and ask the model to return list numbers (not Mongo
        ObjectIds, which tokenize very expensively). Indices are mapped back to
        real product IDs server-side.
        """
        cart_text = "\n".join(f"- {p.name}" for p in cart_products)
        options_text = "\n".join(
            f"{i}. {p.name}" for i, p in enumerate(candidates, start=1)
        )

        return (
            f"CARRITO:\n{cart_text}\n\n"
            f"OPCIONES (elige por número):\n{options_text}\n\n"
            f"Elige hasta {limit} opciones que COMPLEMENTEN el carrito "
            "(bebidas, acompañantes, postres o extras que combinen). Evita "
            "sustitutos y duplicados del mismo tipo. Si nada complementa bien, "
            'devuelve "picks": [].\n\n'
            "Responde SOLO con este JSON, sin markdown:\n"
            '{"strategy": "una frase corta", '
            '"picks": [{"n": <numero de la opcion>, "why": "por qué pega, breve"}]}'
        )

    def _parse_picks(
        self, content: str, candidates, limit: int
    ) -> ProductRecommendationsResponse:
        """Parse the model's index-based JSON and map numbers back to products."""
        try:
            data = json.loads(self._strip_code_fence(content))
        except Exception as exc:
            print(f"⚠ Could not parse recommendation JSON: {exc}")
            return ProductRecommendationsResponse(
                recommendations=[],
                reasoning="No se encontraron productos complementarios en este momento.",
            )

        strategy = str(data.get("strategy", "")).strip()
        picks = data.get("picks") or []

        recommendations: List[ProductRecommendation] = []
        seen = set()
        for pick in picks:
            try:
                n = int(pick.get("n"))
            except (TypeError, ValueError, AttributeError):
                continue
            idx = n - 1  # list is 1-indexed
            if idx < 0 or idx >= len(candidates) or idx in seen:
                continue
            seen.add(idx)
            product = candidates[idx]
            recommendations.append(
                ProductRecommendation(
                    product_id=str(product.id),
                    product_name=product.name,
                    reasoning=str(pick.get("why", "")).strip(),
                )
            )
            if len(recommendations) >= limit:
                break

        if not recommendations:
            return ProductRecommendationsResponse(
                recommendations=[],
                reasoning=strategy
                or "No se encontraron productos complementarios adecuados.",
            )

        return ProductRecommendationsResponse(
            recommendations=recommendations,
            reasoning=strategy or "Productos que complementan tu carrito.",
        )

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned


# Singleton instance
product_recommendation_service = ProductRecommendationService()
