"""Mutations GraphQL de los banners de plataforma (solo admin)."""

from typing import Any, Dict, List

import strawberry
from strawberry.types import Info

from repositories import branches_repo
from repositories.platform_banner_repository import platform_banners_repo
from services.platform_banners import (
    normalize_banner_link,
    normalize_banner_whatsapp,
    to_naive_utc,
    validate_app_target,
    validate_window,
)
from utils.graphql_auth import require_role
from utils.s3 import delete_file

from .inputs import CreatePlatformBannerInput, UpdatePlatformBannerInput
from .types import PlatformBannerType, platform_banner_to_type, platform_banners_to_types

async def _validate_branch(branch_id: str) -> str:
    branch = await branches_repo.get_by_id(branch_id)
    if not branch:
        raise ValueError("La tienda del banner no existe")
    return branch_id


def _clean_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    return value


@strawberry.type
class PlatformBannerMutation:
    @strawberry.mutation(
        description=(
            "[Admin] Crear un banner del carrusel del feed. Sube antes la imagen a "
            "POST /upload/platform-banner/image y pasa aquí el path devuelto."
        )
    )
    async def create_platform_banner(
        self, info: Info, input: CreatePlatformBannerInput, jwt: str
    ) -> PlatformBannerType:
        admin_id = require_role(jwt, info, ["admin"])

        try:
            image_path = (input.imagePath or "").strip()
            if not image_path:
                raise ValueError("El banner necesita una imagen")
            app_target = validate_app_target(input.appTarget)
            start_at, end_at = to_naive_utc(input.startAt), to_naive_utc(input.endAt)
            validate_window(start_at, end_at)
            data: Dict[str, Any] = {
                "imagePath": image_path,
                "title": _clean_text(input.title),
                "link": normalize_banner_link(input.link),
                "whatsapp": normalize_banner_whatsapp(input.whatsapp),
                "branchId": (
                    await _validate_branch(input.branchId) if _clean_text(input.branchId) else None
                ),
                "appTarget": app_target,
                "order": (
                    input.order
                    if input.order is not None
                    else await platform_banners_repo.next_order(app_target)
                ),
                "isActive": input.isActive,
                "startAt": start_at,
                "endAt": end_at,
                "createdByUserId": admin_id,
            }
        except ValueError as exc:
            raise Exception(str(exc))

        banner = await platform_banners_repo.create(data)
        return platform_banner_to_type(banner)

    @strawberry.mutation(description="[Admin] Editar un banner (solo los campos enviados)")
    async def update_platform_banner(
        self, info: Info, id: str, input: UpdatePlatformBannerInput, jwt: str
    ) -> PlatformBannerType:
        require_role(jwt, info, ["admin"])

        existing = await platform_banners_repo.get_by_id(id)
        if not existing:
            raise Exception("Banner no encontrado")

        sent = {
            name: getattr(input, name)
            for name in (
                "imagePath", "title", "link", "whatsapp", "branchId", "appTarget",
                "order", "isActive", "startAt", "endAt",
            )
            if getattr(input, name) is not strawberry.UNSET
        }
        for name in ("imagePath", "appTarget", "order", "isActive"):
            if name in sent and sent[name] is None:
                raise Exception(f"{name} no puede ser null")

        try:
            updates: Dict[str, Any] = {}
            if "imagePath" in sent:
                image_path = sent["imagePath"].strip()
                if not image_path:
                    raise ValueError("El banner necesita una imagen")
                updates["imagePath"] = image_path
            if "title" in sent:
                updates["title"] = _clean_text(sent["title"])
            if "link" in sent:
                updates["link"] = normalize_banner_link(sent["link"])
            if "whatsapp" in sent:
                updates["whatsapp"] = normalize_banner_whatsapp(sent["whatsapp"])
            if "branchId" in sent:
                branch_id = _clean_text(sent["branchId"])
                updates["branchId"] = await _validate_branch(branch_id) if branch_id else None
            if "appTarget" in sent:
                updates["appTarget"] = validate_app_target(sent["appTarget"])
            if "order" in sent:
                updates["order"] = sent["order"]
            if "isActive" in sent:
                updates["isActive"] = sent["isActive"]
            for name in ("startAt", "endAt"):
                if name in sent:
                    updates[name] = to_naive_utc(sent[name])
            validate_window(
                updates["startAt"] if "startAt" in sent else existing.startAt,
                updates["endAt"] if "endAt" in sent else existing.endAt,
            )
        except ValueError as exc:
            raise Exception(str(exc))

        if not updates:
            raise Exception("No hay campos para actualizar")

        updated = await platform_banners_repo.update(id, updates)
        if not updated:
            raise Exception("Banner no encontrado")
        return platform_banner_to_type(updated)

    @strawberry.mutation(description="[Admin] Activar o desactivar un banner")
    async def set_platform_banner_active(
        self, info: Info, id: str, isActive: bool, jwt: str
    ) -> PlatformBannerType:
        require_role(jwt, info, ["admin"])
        updated = await platform_banners_repo.update(id, {"isActive": isActive})
        if not updated:
            raise Exception("Banner no encontrado")
        return platform_banner_to_type(updated)

    @strawberry.mutation(
        description=(
            "[Admin] Reordenar el carrusel: `ids` en el orden deseado (cada banner "
            "queda con order = su posición). Devuelve los banners de esas apps en "
            "el orden nuevo."
        )
    )
    async def reorder_platform_banners(
        self, info: Info, ids: List[str], jwt: str
    ) -> List[PlatformBannerType]:
        require_role(jwt, info, ["admin"])

        if not ids:
            raise Exception("Indica al menos un banner")
        if len(set(ids)) != len(ids):
            raise Exception("Hay banners repetidos en la lista")

        banners = [await platform_banners_repo.get_by_id(banner_id) for banner_id in ids]
        if any(b is None for b in banners):
            raise Exception("Banner no encontrado")
        targets = {b.appTarget for b in banners}
        if len(targets) > 1:
            raise Exception("Solo se pueden reordenar banners de la misma app")

        await platform_banners_repo.reorder(ids)
        return platform_banners_to_types(await platform_banners_repo.list_all(targets.pop()))

    @strawberry.mutation(description="[Admin] Borrar un banner (y su imagen)")
    async def delete_platform_banner(self, info: Info, id: str, jwt: str) -> bool:
        require_role(jwt, info, ["admin"])

        banner = await platform_banners_repo.get_by_id(id)
        if not banner:
            raise Exception("Banner no encontrado")

        deleted = await platform_banners_repo.delete(id)
        if deleted and banner.imagePath and not banner.imagePath.startswith("http"):
            # Best-effort: una imagen huérfana en S3 no debe impedir el borrado.
            try:
                await delete_file(banner.imagePath)
            except Exception:
                pass
        return deleted
