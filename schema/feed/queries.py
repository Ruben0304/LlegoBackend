"""GraphQL query resolvers for Feed."""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import strawberry
from strawberry.types import Info

from services.feed_service import feed_service
from services.scoring_service import scoring_service
from utils.cache import mem_cache
from utils.graphql_auth import apply_optional_jwt
from utils.serialization import to_strawberry_dict
from utils.rate_limit import rate_limit_graphql

from .types import FeedProductType, FeedResponse, FeedSection, FeedSectionDiagnostic


@strawberry.type
class FeedQuery:
    @strawberry.field(description="Get personalized feed with multiple sections")
    async def get_feed(
        self,
        info: Info,
        branch_tipo: str,
        first: int = 10,
        radius_km: Optional[float] = None,
        sections: Optional[List[str]] = None,
        product_category_id: Optional[str] = None,
        jwt: Optional[str] = None,
    ) -> FeedResponse:
        """
        Get personalized product feed with multiple scored sections.

        Args:
            branch_tipo: Branch type to filter feed (e.g. "restaurante", "tienda", "dulceria")
            first: Number of products per section (default 10, max 50)
            radius_km: Radius in km for proximity calculations
            sections: Optional filter for specific sections
                Available: ["para_ti", "populares_cerca", "trending", "basado_busquedas",
                           "nuevos_lugares_favoritos", "mas_favoriteados", "cerca_ti", "te_podria_gustar"]
            jwt: JWT token for authentication (optional, but required for personalized sections)
                Available sections include: ["para_ti", "pide_de_nuevo", "populares_cerca",
                           "trending", "hora_del_dia", "basado_busquedas",
                           "nuevos_lugares_favoritos", "mas_favoriteados", "cerca_ti",
                           "te_podria_gustar"]

        Returns:
            FeedResponse with multiple sections of scored products
        """
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "feed")

        # Limit products per section
        first = min(first, 50)

        # Fetch branch IDs for the requested tipo once — all sections share this filter
        branch_ids = await feed_service.get_branch_ids_by_tipo(branch_tipo)

        # Narrow branch_ids by product category if specified
        if product_category_id:
            from repositories import products_repo

            category_branch_ids = (
                await products_repo.get_distinct_branch_ids_by_category(
                    product_category_id
                )
            )
            branch_ids = branch_ids & category_branch_ids

        # Get user context
        user_id = info.context.get("user_id")
        user_location = None

        if user_id:
            user_location = await scoring_service.get_user_location(user_id)

        # Fetch ALL products ONCE — shared across all feed sections (2-min in-process cache)
        from repositories import products_repo

        _products_cache_key = f"feed:products:{branch_tipo.lower()}:{','.join(sorted(branch_ids))}"
        all_products = mem_cache.get(_products_cache_key)
        if all_products is None:
            all_products = await products_repo.get_feed_products(
                branch_ids=list(branch_ids),
                apply_category_filter=True,
                requested_branch_tipo=branch_tipo.lower(),
            )
            mem_cache.set(_products_cache_key, all_products, ttl=120)

        if product_category_id:
            all_products = [
                product
                for product in all_products
                if str(product.categoryId) == product_category_id
            ]

        # Default sections if not specified
        meal_title, meal_description = feed_service.get_meal_context()
        available_sections = {
            "para_ti": ("Para Ti", "Productos personalizados según tus preferencias"),
            "pide_de_nuevo": (
                "Pide de Nuevo",
                "Tus pedidos anteriores, listos para repetir",
            ),
            "populares_cerca": (
                "Populares Cerca de Ti",
                "Los más populares en tu zona",
            ),
            "trending": ("Trending Ahora", "Productos con mayor actividad reciente"),
            "hora_del_dia": (meal_title, meal_description),
            "basado_busquedas": ("Basado en tus Búsquedas", "Según lo que has buscado"),
            "nuevos_lugares_favoritos": (
                "Nuevos en tus Lugares Favoritos",
                "Productos recientes de tus branches favoritos",
            ),
            "mas_favoriteados": (
                "Los Más Favoriteados",
                "Los productos más guardados en favoritos",
            ),
            "cerca_ti": ("Cerca de Ti", "Productos disponibles cerca de tu ubicación"),
            "te_podria_gustar": (
                "Te Podría Gustar",
                "Recomendaciones basadas en tus preferencias",
            ),
        }

        # Filter sections if specified
        section_diagnostics: List[FeedSectionDiagnostic] = []
        if sections:
            requested_sections = {
                k: v for k, v in available_sections.items() if k in sections
            }
            print(f"[DEBUG] Feed - sections requested: {sections}")
            unknown_sections = [s for s in sections if s not in available_sections]
            for unknown_section in unknown_sections:
                section_diagnostics.append(
                    FeedSectionDiagnostic(
                        section_id=unknown_section,
                        title=unknown_section,
                        status="omitted",
                        reason="Sección no reconocida",
                        total_before_dedup=0,
                        total_after_dedup=0,
                    )
                )
        else:
            requested_sections = available_sections
            print(
                f"[DEBUG] Feed - No sections filter, using all {len(requested_sections)} sections"
            )

        # Prepare tasks for parallel execution
        tasks = []
        section_keys = []

        for section_id in requested_sections.keys():
            if section_id == "para_ti":
                if user_id:
                    tasks.append(
                        feed_service.get_para_ti_section(
                            user_id,
                            user_location,
                            branch_ids,
                            first,
                            radius_km=radius_km,
                            all_products=all_products,
                        )
                    )
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(
                        FeedSectionDiagnostic(
                            section_id=section_id,
                            title=title,
                            status="omitted",
                            reason="Requiere JWT válido (usuario no autenticado)",
                            total_before_dedup=0,
                            total_after_dedup=0,
                        )
                    )
            elif section_id == "pide_de_nuevo":
                if user_id:
                    tasks.append(
                        feed_service.get_pide_de_nuevo_section(
                            user_id,
                            user_location,
                            branch_ids,
                            first,
                            radius_km=radius_km,
                            all_products=all_products,
                        )
                    )
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(
                        FeedSectionDiagnostic(
                            section_id=section_id,
                            title=title,
                            status="omitted",
                            reason="Requiere JWT válido (sin historial de pedidos del usuario)",
                            total_before_dedup=0,
                            total_after_dedup=0,
                        )
                    )
            elif section_id == "populares_cerca":
                tasks.append(
                    feed_service.get_populares_cerca_section(
                        user_location,
                        branch_ids,
                        first,
                        radius_km=radius_km,
                        all_products=all_products,
                    )
                )
                section_keys.append(section_id)
            elif section_id == "trending":
                tasks.append(
                    feed_service.get_trending_section(
                        user_location,
                        branch_ids,
                        first,
                        radius_km=radius_km,
                        all_products=all_products,
                    )
                )
                section_keys.append(section_id)
            elif section_id == "hora_del_dia":
                tasks.append(
                    feed_service.get_hora_del_dia_section(
                        user_location,
                        branch_ids,
                        first,
                        radius_km=radius_km,
                        all_products=all_products,
                    )
                )
                section_keys.append(section_id)
            elif section_id == "basado_busquedas":
                if user_id:
                    tasks.append(
                        feed_service.get_basado_busquedas_section(
                            user_id, branch_ids, first, all_products=all_products
                        )
                    )
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(
                        FeedSectionDiagnostic(
                            section_id=section_id,
                            title=title,
                            status="omitted",
                            reason="Requiere JWT válido (sin historial de búsquedas de usuario)",
                            total_before_dedup=0,
                            total_after_dedup=0,
                        )
                    )
            elif section_id == "nuevos_lugares_favoritos":
                if user_id:
                    tasks.append(
                        feed_service.get_nuevos_lugares_favoritos_section(
                            user_id, branch_ids, first, all_products=all_products
                        )
                    )
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(
                        FeedSectionDiagnostic(
                            section_id=section_id,
                            title=title,
                            status="omitted",
                            reason="Requiere JWT válido (sin favoritos del usuario)",
                            total_before_dedup=0,
                            total_after_dedup=0,
                        )
                    )
            elif section_id == "mas_favoriteados":
                tasks.append(
                    feed_service.get_mas_favoriteados_section(
                        user_location,
                        branch_ids,
                        first,
                        radius_km=radius_km,
                        all_products=all_products,
                    )
                )
                section_keys.append(section_id)
            elif section_id == "cerca_ti":
                if user_location:
                    tasks.append(
                        feed_service.get_cerca_de_ti_section(
                            user_location,
                            branch_ids,
                            first,
                            radius_km=radius_km,
                            all_products=all_products,
                        )
                    )
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(
                        FeedSectionDiagnostic(
                            section_id=section_id,
                            title=title,
                            status="omitted",
                            reason="No hay ubicación del usuario disponible",
                            total_before_dedup=0,
                            total_after_dedup=0,
                        )
                    )
            elif section_id == "te_podria_gustar":
                if user_id:
                    tasks.append(
                        feed_service.get_te_podria_gustar_section(
                            user_id,
                            user_location,
                            branch_ids,
                            first,
                            radius_km=radius_km,
                            all_products=all_products,
                        )
                    )
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(
                        FeedSectionDiagnostic(
                            section_id=section_id,
                            title=title,
                            status="omitted",
                            reason="Requiere JWT válido (personalización no disponible)",
                            total_before_dedup=0,
                            total_after_dedup=0,
                        )
                    )

        # Execute all sections in parallel
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = []

        # Collect raw ScoredFeedProduct results and track valid section indices
        raw_sections = []
        valid_keys = []
        for i, result in enumerate(results):
            section_id = section_keys[i]
            title, _ = requested_sections[section_id]
            if isinstance(result, Exception):
                print(f"Error in section {section_keys[i]}: {result}")
                section_diagnostics.append(
                    FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="error",
                        reason=f"Error interno generando sección: {result}",
                        total_before_dedup=0,
                        total_after_dedup=0,
                    )
                )
                continue
            raw_sections.append(result)
            valid_keys.append(section_id)

        # Deduplicate products across sections using backfill from extra candidates.
        deduplicated_sections = feed_service._deduplicate_sections(
            raw_sections, target_limit=first
        )

        # Convert ScoredFeedProduct lists to FeedSection GraphQL types
        final_sections = []
        for i, scored_products in enumerate(deduplicated_sections):
            section_id = valid_keys[i]
            title, description = requested_sections[section_id]
            total_before_dedup = len(raw_sections[i])
            effective_scored_products = scored_products
            total_after_dedup = len(effective_scored_products)

            if total_before_dedup == 0:
                section_diagnostics.append(
                    FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="omitted",
                        reason="No se encontraron productos para esta sección",
                        total_before_dedup=0,
                        total_after_dedup=0,
                    )
                )
                continue

            if total_after_dedup == 0:
                section_diagnostics.append(
                    FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="omitted",
                        reason="Todos los productos quedaron duplicados frente a secciones anteriores",
                        total_before_dedup=total_before_dedup,
                        total_after_dedup=0,
                    )
                )
                continue

            products = []
            for sp in effective_scored_products:
                product_data = to_strawberry_dict(sp.product)
                products.append(
                    FeedProductType(**product_data, score=sp.score, distance_m=None)
                )

            final_sections.append(
                FeedSection(
                    title=title,
                    section_id=section_id,
                    description=description,
                    products=products,
                    total_count=len(products),
                )
            )

            if total_after_dedup < total_before_dedup:
                section_diagnostics.append(
                    FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="partial",
                        reason="Se removieron duplicados y se rellenó la sección con candidatos alternativos cuando fue posible",
                        total_before_dedup=total_before_dedup,
                        total_after_dedup=total_after_dedup,
                    )
                )
            else:
                section_diagnostics.append(
                    FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="included",
                        reason=None,
                        total_before_dedup=total_before_dedup,
                        total_after_dedup=total_after_dedup,
                    )
                )

        return FeedResponse(
            sections=final_sections,
            section_diagnostics=section_diagnostics,
            timestamp=datetime.now(timezone.utc),
        )
