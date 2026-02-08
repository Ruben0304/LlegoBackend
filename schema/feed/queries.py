"""GraphQL query resolvers for Feed."""
import strawberry
from typing import Optional, List
from strawberry.types import Info
from datetime import datetime
import asyncio

from .types import FeedResponse, FeedSection, FeedProductType, FeedSectionDiagnostic
from services.feed_service import feed_service
from services.scoring_service import scoring_service
from utils.graphql_auth import apply_optional_jwt
from utils.rate_limit import rate_limit_graphql


@strawberry.type
class FeedQuery:
    @strawberry.field(description="Get personalized feed with multiple sections")
    async def get_feed(
        self,
        info: Info,
        first: int = 10,
        radius_km: Optional[float] = None,
        sections: Optional[List[str]] = None,
        jwt: Optional[str] = None
    ) -> FeedResponse:
        """
        Get personalized product feed with multiple scored sections.

        Args:
            first: Number of products per section (default 10, max 50)
            radius_km: Radius in km for proximity calculations
            sections: Optional filter for specific sections
                Available: ["para_ti", "populares_cerca", "trending", "basado_busquedas",
                           "nuevos_lugares_favoritos", "mas_favoriteados", "cerca_ti", "te_podria_gustar"]
            jwt: JWT token for authentication (optional, but required for personalized sections)

        Returns:
            FeedResponse with multiple sections of scored products
        """
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "feed")

        # Limit products per section
        first = min(first, 50)

        # Get user context
        user_id = info.context.get("user_id")
        user_location = None

        if user_id:
            user_location = await scoring_service.get_user_location(user_id)

        # Default sections if not specified
        available_sections = {
            "para_ti": ("Para Ti", "Productos personalizados según tus preferencias"),
            "populares_cerca": ("Populares Cerca de Ti", "Los más populares en tu zona"),
            "trending": ("Trending Ahora", "Productos con mayor actividad reciente"),
            "basado_busquedas": ("Basado en tus Búsquedas", "Según lo que has buscado"),
            "nuevos_lugares_favoritos": ("Nuevos en tus Lugares Favoritos", "Productos recientes de tus branches favoritos"),
            "mas_favoriteados": ("Los Más Favoriteados", "Los productos más guardados en favoritos"),
            "cerca_ti": ("Cerca de Ti", "Productos disponibles cerca de tu ubicación"),
            "te_podria_gustar": ("Te Podría Gustar", "Recomendaciones basadas en tus preferencias")
        }

        # Filter sections if specified
        section_diagnostics: List[FeedSectionDiagnostic] = []
        if sections:
            requested_sections = {k: v for k, v in available_sections.items() if k in sections}
            unknown_sections = [s for s in sections if s not in available_sections]
            for unknown_section in unknown_sections:
                section_diagnostics.append(FeedSectionDiagnostic(
                    section_id=unknown_section,
                    title=unknown_section,
                    status="omitted",
                    reason="Sección no reconocida",
                    total_before_dedup=0,
                    total_after_dedup=0
                ))
        else:
            requested_sections = available_sections

        # Prepare tasks for parallel execution
        tasks = []
        section_keys = []

        for section_id in requested_sections.keys():
            if section_id == "para_ti":
                if user_id:
                    tasks.append(feed_service.get_para_ti_section(user_id, user_location, first))
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="omitted",
                        reason="Requiere JWT válido (usuario no autenticado)",
                        total_before_dedup=0,
                        total_after_dedup=0
                    ))
            elif section_id == "populares_cerca":
                tasks.append(feed_service.get_populares_cerca_section(user_location, first))
                section_keys.append(section_id)
            elif section_id == "trending":
                tasks.append(feed_service.get_trending_section(user_location, first))
                section_keys.append(section_id)
            elif section_id == "basado_busquedas":
                if user_id:
                    tasks.append(feed_service.get_basado_busquedas_section(user_id, first))
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="omitted",
                        reason="Requiere JWT válido (sin historial de búsquedas de usuario)",
                        total_before_dedup=0,
                        total_after_dedup=0
                    ))
            elif section_id == "nuevos_lugares_favoritos":
                if user_id:
                    tasks.append(feed_service.get_nuevos_lugares_favoritos_section(user_id, first))
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="omitted",
                        reason="Requiere JWT válido (sin favoritos del usuario)",
                        total_before_dedup=0,
                        total_after_dedup=0
                    ))
            elif section_id == "mas_favoriteados":
                tasks.append(feed_service.get_mas_favoriteados_section(user_location, first))
                section_keys.append(section_id)
            elif section_id == "cerca_ti":
                if user_location:
                    tasks.append(feed_service.get_cerca_de_ti_section(user_location, first))
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="omitted",
                        reason="No hay ubicación del usuario disponible",
                        total_before_dedup=0,
                        total_after_dedup=0
                    ))
            elif section_id == "te_podria_gustar":
                if user_id:
                    tasks.append(feed_service.get_te_podria_gustar_section(user_id, user_location, first))
                    section_keys.append(section_id)
                else:
                    title, _ = requested_sections[section_id]
                    section_diagnostics.append(FeedSectionDiagnostic(
                        section_id=section_id,
                        title=title,
                        status="omitted",
                        reason="Requiere JWT válido (personalización no disponible)",
                        total_before_dedup=0,
                        total_after_dedup=0
                    ))

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
                section_diagnostics.append(FeedSectionDiagnostic(
                    section_id=section_id,
                    title=title,
                    status="error",
                    reason=f"Error interno generando sección: {result}",
                    total_before_dedup=0,
                    total_after_dedup=0
                ))
                continue
            raw_sections.append(result)
            valid_keys.append(section_id)

        # Deduplicate products across sections (operates on ScoredFeedProduct)
        deduplicated_sections = feed_service._deduplicate_sections(raw_sections)

        # Convert deduplicated ScoredFeedProduct lists to FeedSection GraphQL types
        final_sections = []
        for i, scored_products in enumerate(deduplicated_sections):
            section_id = valid_keys[i]
            title, description = requested_sections[section_id]
            total_before_dedup = len(raw_sections[i])
            total_after_dedup = len(scored_products)

            if total_before_dedup == 0:
                section_diagnostics.append(FeedSectionDiagnostic(
                    section_id=section_id,
                    title=title,
                    status="omitted",
                    reason="No se encontraron productos para esta sección",
                    total_before_dedup=0,
                    total_after_dedup=0
                ))
                continue

            if total_after_dedup == 0:
                section_diagnostics.append(FeedSectionDiagnostic(
                    section_id=section_id,
                    title=title,
                    status="omitted",
                    reason="Todos los productos quedaron duplicados frente a secciones anteriores",
                    total_before_dedup=total_before_dedup,
                    total_after_dedup=0
                ))
                continue

            products = []
            for sp in scored_products:
                product_data = sp.product.model_dump()
                products.append(FeedProductType(
                    **product_data,
                    score=sp.score,
                    distance_m=None
                ))

            final_sections.append(FeedSection(
                title=title,
                section_id=section_id,
                description=description,
                products=products,
                total_count=len(products)
            ))

            if total_after_dedup < total_before_dedup:
                section_diagnostics.append(FeedSectionDiagnostic(
                    section_id=section_id,
                    title=title,
                    status="partial",
                    reason="Se removieron productos duplicados para evitar repetidos entre secciones",
                    total_before_dedup=total_before_dedup,
                    total_after_dedup=total_after_dedup
                ))
            else:
                section_diagnostics.append(FeedSectionDiagnostic(
                    section_id=section_id,
                    title=title,
                    status="included",
                    reason=None,
                    total_before_dedup=total_before_dedup,
                    total_after_dedup=total_after_dedup
                ))

        return FeedResponse(
            sections=final_sections,
            section_diagnostics=section_diagnostics,
            timestamp=datetime.utcnow()
        )
