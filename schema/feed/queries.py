"""GraphQL query resolvers for Feed."""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Set

import strawberry
from strawberry.types import Info

from services.ads_service import ads_service
from services.feed_service import feed_service
from services.scoring_service import scoring_service
from utils.cache import mem_cache
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import get_public_url
from utils.serialization import to_strawberry_dict
from utils.rate_limit import rate_limit_graphql

from .types import (
    FeedCreativeSection,
    FeedCreativeType,
    FeedProductType,
    FeedResponse,
    FeedSection,
    FeedSectionDiagnostic,
)


def _meal_extra_title(meal_title: str) -> str:
    """Return a 'more of the same meal moment' variant title for page > 0."""
    mapping = {
        "Desayunos Populares": "Más cositas para el desayuno",
        "Desayunos del Finde": "Más para arrancar el finde",
        "Para el Almuerzo": "Más opciones para el almuerzo",
        "El Almuerzo del Finde": "Más para el almuerzo del finde",
        "Para Merendar": "Más cositas que puedes merendar",
        "Para la Cena": "Más opciones para la cena",
        "Antojos de Noche": "Más antojos de noche",
    }
    return mapping.get(meal_title, f"Más {meal_title.lower()}")


@strawberry.type
class FeedQuery:
    @strawberry.field(description="Get personalized feed with multiple sections")
    async def get_feed(
        self,
        info: Info,
        branch_tipo: str,
        first: int = 10,
        page: int = 0,
        explorar_page: int = 0,
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

        # For page > 0 the same section types reappear but with fresh titles
        # so the scroll feels like new content, not a repeat.
        if page == 0:
            available_sections = {
                "para_ti": ("Para Ti", "Productos personalizados según tus preferencias"),
                "pide_de_nuevo": ("Pide de Nuevo", "Tus pedidos anteriores, listos para repetir"),
                "populares_cerca": ("Populares Cerca de Ti", "Los más populares en tu zona"),
                "trending": ("Trending Ahora", "Productos con mayor actividad reciente"),
                "hora_del_dia": (meal_title, meal_description),
                "basado_busquedas": ("Basado en tus Búsquedas", "Según lo que has buscado"),
                "nuevos_lugares_favoritos": (
                    "Nuevos en tus Lugares Favoritos",
                    "Productos recientes de tus negocios favoritos",
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
                "recomendado_qdrant": (
                    "Especialmente para Ti",
                    "Productos similares a los que más te gustan",
                ),
            }
        else:
            _meal_extra = _meal_extra_title(meal_title)
            available_sections = {
                "para_ti": ("Más para Ti", "Más opciones que se ajustan a tus gustos"),
                "pide_de_nuevo": ("Más para Repetir", "Otros que ya pediste y seguro se te antojan"),
                "populares_cerca": ("Más cositas cerca de ti", "Más opciones populares en tu zona"),
                "trending": ("Más de lo que está en tendencia", "Más productos con mucha actividad"),
                "hora_del_dia": (_meal_extra, meal_description),
                "basado_busquedas": ("Más según lo que buscas", "Más opciones relacionadas con tus búsquedas"),
                "nuevos_lugares_favoritos": (
                    "Más de tus lugares favoritos",
                    "Más novedades de los negocios que te gustan",
                ),
                "mas_favoriteados": (
                    "Más de los más queridos",
                    "Más productos con muchos favoritos",
                ),
                "cerca_ti": ("Más cerquita de ti", "Más opciones a pocos pasos"),
                "te_podria_gustar": (
                    "Más que te podría gustar",
                    "Sigue explorando, hay más por descubrir",
                ),
                "recomendado_qdrant": (
                    "Más para Ti",
                    "Más productos similares a tus favoritos",
                ),
            }

        # Filter sections if specified
        section_diagnostics: List[FeedSectionDiagnostic] = []
        if sections:
            requested_sections = {
                k: v for k, v in available_sections.items() if k in sections
            }
            print(f"[DEBUG] Feed - sections requested: {sections}")
            unknown_sections = [s for s in sections if s not in available_sections and s != "explorar"]
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
            elif section_id == "recomendado_qdrant":
                if user_id:
                    tasks.append(
                        feed_service.get_qdrant_recomendado_section(
                            user_id,
                            branch_ids,
                            first,
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
                            reason="Requiere JWT válido (recomendación vectorial no disponible)",
                            total_before_dedup=0,
                            total_after_dedup=0,
                        )
                    )

        # Each section fetches candidate_limit = max(first*3, 30) products.
        # Page N serves a different slice of those candidates so scroll feels infinite.
        candidate_limit = feed_service._candidate_limit(first)
        has_more = (page + 1) * first < candidate_limit

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

        # For pages > 0, skip the first `page * first` candidates so each page
        # shows a fresh slice without repeating products from earlier pages.
        if page > 0:
            offset = page * first
            raw_sections = [section[offset:] for section in raw_sections]

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

        # --- Explorar section: all remaining products not shown in other sections ---
        EXPLORAR_LIMIT = 20
        seen_in_feed: Set[str] = set()
        for scored_list in deduplicated_sections:
            for sp in scored_list:
                seen_in_feed.add(str(sp.product.id))

        explorar_scored = await feed_service.get_explorar_section(
            all_products=all_products,
            seen_ids=seen_in_feed,
            page=explorar_page,
            limit=EXPLORAR_LIMIT,
            user_location=user_location,
            radius_km=radius_km,
        )
        explorar_has_more = len(explorar_scored) > EXPLORAR_LIMIT
        explorar_page_products = explorar_scored[:EXPLORAR_LIMIT]

        if explorar_page_products:
            products = []
            for sp in explorar_page_products:
                product_data = to_strawberry_dict(sp.product)
                products.append(FeedProductType(**product_data, score=sp.score, distance_m=None))

            final_sections.append(
                FeedSection(
                    title="Explora otras opciones",
                    section_id="explorar",
                    description="Todos los productos disponibles",
                    products=products,
                    total_count=len(products),
                )
            )

        # --- Paid creative sections (Destacados / Ofertas) ---
        # Additive and non-breaking: organic `sections` are untouched. Only
        # active campaigns whose branch is in this feed's (approved) branch set
        # are eligible.
        creative_sections: List[FeedCreativeSection] = []
        try:
            print(f"[ADS] Fetching creative sections for {len(branch_ids)} branches (tipo={branch_tipo})")
            for placement, title, sid in (
                ("destacado", "Negocios Destacados", "destacados"),
                ("oferta", "Ofertas", "ofertas"),
            ):
                campaigns = await ads_service.get_feed_campaigns(
                    placement, branch_ids, limit=8
                )
                print(f"[ADS] {placement}: {len(campaigns)} active campaigns found")
                if not campaigns:
                    continue
                items = [
                    FeedCreativeType(
                        campaignId=str(c.id),
                        branchId=str(c.branchId),
                        businessId=str(c.businessId),
                        placement=c.placement,
                        imageUrl=get_public_url(c.creativeImagePath),
                        ctaDeeplink=f"llego://branch/{c.branchId}",
                    )
                    for c in campaigns
                    if c.creativeImagePath
                ]
                if not items:
                    continue
                creative_sections.append(
                    FeedCreativeSection(title=title, section_id=sid, items=items)
                )
        except Exception as e:
            import traceback
            print(f"[ADS] Error building creative sections: {e}")
            traceback.print_exc()

        return FeedResponse(
            sections=final_sections,
            section_diagnostics=section_diagnostics,
            timestamp=datetime.now(timezone.utc),
            has_more=has_more,
            explorar_has_more=explorar_has_more,
            creative_sections=creative_sections,
        )
