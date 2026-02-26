"""Product recommendation service using DeepSeek AI.

This service provides complementary product recommendations based on cart items.
"""

import asyncio
from typing import List, Optional

from openai import OpenAI

from core.config import settings
from repositories import products_repo
from services.ai_models import ProductRecommendationsResponse


class ProductRecommendationService:
    """Service for generating product recommendations using DeepSeek AI."""

    def __init__(self):
        """Initialize product recommendation service."""
        if not settings.deepseek_api_key:
            print(
                "⚠ DeepSeek API key not configured. Product recommendations will be disabled."
            )
            self.client = None
            self.model_name = None
        else:
            self.client = OpenAI(
                api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url
            )
            self.model_name = settings.deepseek_model

    async def get_recommendations(
        self, product_ids: List[str], limit: int = 5
    ) -> Optional[ProductRecommendationsResponse]:
        """
        Get complementary product recommendations based on cart items.

        Args:
            product_ids: List of product IDs currently in the cart
            limit: Maximum number of recommendations to return

        Returns:
            ProductRecommendationsResponse with recommendations, or None if service unavailable
        """
        # Skip if DeepSeek is not configured
        if not self.client:
            print("⚠ DeepSeek not configured, skipping recommendations")
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

            # Step 3: Get ALL products from the same branch (only names, no descriptions)
            print(f"📦 Fetching all products from branch {first_branch_id}...")
            all_branch_products = await products_repo.get_by_branch(first_branch_id)
            print(f"   Total products in branch: {len(all_branch_products)}")

            if all_branch_products:
                print(f"   First 3 products: {[p.name for p in all_branch_products[:3]]}")

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

            # Step 4: Build the prompt for DeepSeek
            prompt = self._build_recommendation_prompt(
                cart_products=cart_products,
                available_products=available_for_recommendation,
                limit=limit,
            )

            # Step 5: Call DeepSeek AI with Structured Outputs
            print(f"🤖 Calling DeepSeek for recommendations (limit={limit})...")
            print(f"   Using Structured Outputs with strict JSON schema validation")

            # Build JSON schema from Pydantic model for strict validation
            schema = ProductRecommendationsResponse.model_json_schema()
            print(f"   Schema keys: {list(schema.get('properties', {}).keys())}")

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres un asistente experto en recomendaciones de productos complementarios. "
                            "Tu objetivo es sugerir productos que complementen bien los items en el carrito del usuario. "
                            "Responde ÚNICAMENTE con un JSON válido que cumpla EXACTAMENTE con el siguiente schema JSON:\n\n"
                            f"{schema}\n\n"
                            "CRÍTICO: La respuesta DEBE ser un objeto JSON válido con exactamente estas propiedades:\n"
                            "- recommendations: array de objetos con product_id, product_name, reasoning\n"
                            "- reasoning: string con explicación general\n"
                            "NO incluyas campos adicionales ni omitas campos requeridos."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "product_recommendations",
                        "strict": True,
                        "schema": schema,
                    },
                },
                temperature=0.7,
                max_tokens=2000,
            )

            if not response.choices or not response.choices[0].message.content:
                print("⚠ Empty response from DeepSeek")
                return None

            # Step 6: Parse and validate the response
            content = response.choices[0].message.content.strip()
            print(f"✅ Received response from DeepSeek")
            print(f"   Raw response length: {len(content)} chars")

            # Validate with Pydantic
            recommendations = ProductRecommendationsResponse.model_validate_json(
                content
            )
            print(f"   Parsed recommendations: {len(recommendations.recommendations)} items")
            print(f"   AI Reasoning: {recommendations.reasoning[:100]}...")

            # Step 7: Validate that all recommended product IDs exist in available products
            valid_product_ids = {p.id for p in available_for_recommendation}
            validated_recommendations = [
                rec
                for rec in recommendations.recommendations
                if rec.product_id in valid_product_ids
            ]

            if len(validated_recommendations) < len(recommendations.recommendations):
                print(
                    f"⚠ Filtered out {len(recommendations.recommendations) - len(validated_recommendations)} invalid product IDs"
                )

            # If no valid recommendations after validation, return empty
            if not validated_recommendations:
                print("⚠️ No valid recommendations after validation")
                return ProductRecommendationsResponse(
                    recommendations=[],
                    reasoning="No se encontraron productos complementarios recomendados en este momento.",
                )

            # Return validated recommendations
            print(f"✅ Returning {len(validated_recommendations)} validated recommendations")
            print(f"{'='*80}\n")

            return ProductRecommendationsResponse(
                recommendations=validated_recommendations,
                reasoning=recommendations.reasoning,
            )

        except Exception as e:
            print(f"❌ Error generating recommendations: {e}")
            print(f"{'='*80}\n")
            import traceback

            traceback.print_exc()
            return None

    def _build_recommendation_prompt(
        self, cart_products, available_products, limit: int
    ) -> str:
        """Build the AI prompt for product recommendations."""
        # Format cart products (with descriptions)
        cart_items_text = "\n".join(
            [
                f"- ID: {p.id}, Nombre: {p.name}, Descripción: {p.description}, Precio: ${p.price} {p.currency}"
                for p in cart_products
            ]
        )

        # Format available products (only names and IDs)
        available_items_text = "\n".join(
            [f"- ID: {p.id}, Nombre: {p.name}" for p in available_products]
        )

        prompt = f"""Eres un asistente de recomendaciones de productos. Analiza los productos en el carrito y recomienda productos complementarios.

PRODUCTOS EN EL CARRITO ({len(cart_products)} items):
{cart_items_text}

PRODUCTOS DISPONIBLES EN LA TIENDA ({len(available_products)} items):
{available_items_text}

TAREA:
Recomienda hasta {limit} productos de la lista de "PRODUCTOS DISPONIBLES EN LA TIENDA" que complementen los items en el carrito.

CRITERIOS:
1. Los productos deben ser complementarios (no duplicados)
2. Deben tener sentido con los del carrito (ej: pizza → bebidas/postres, dulces → más dulces diferentes)
3. Considera el tipo de negocio (dulcería, restaurante, supermercado, perfumería, etc)
4. SOLO usa IDs exactos de la lista de "PRODUCTOS DISPONIBLES EN LA TIENDA"
5. Si no hay buenos complementos, devuelve un array vacío en "recommendations"

FORMATO DE RESPUESTA (JSON válido):
{{
  "recommendations": [
    {{
      "product_id": "ID_EXACTO_DE_LA_LISTA",
      "product_name": "NOMBRE_EXACTO_DEL_PRODUCTO",
      "reasoning": "Por qué complementa el carrito"
    }}
  ],
  "reasoning": "Estrategia general de recomendación"
}}

IMPORTANTE:
- SOLO product_ids de la lista "PRODUCTOS DISPONIBLES EN LA TIENDA"
- Si no hay buenos complementos, devuelve: {{"recommendations": [], "reasoning": "No se encontraron productos complementarios adecuados."}}
- Responde SOLO con JSON válido, sin markdown ni texto adicional"""

        return prompt


# Singleton instance
product_recommendation_service = ProductRecommendationService()
