"""AI Assistant quota service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from pymongo import ReturnDocument

from clients import get_database
from core.config import settings


@dataclass
class QuotaDecision:
    allowed: bool
    limit: int
    used: int
    remaining: int
    source: str
    reason: Optional[str] = None
    error_code: Optional[str] = None


class AiQuotaService:
    """Resolves and consumes AI chat quota with atomic Mongo updates."""

    RANGE_ALIASES = {
        "diario": "diario",
        "daily": "diario",
        "semanal": "semanal",
        "weekly": "semanal",
        "mensual": "mensual",
        "monthly": "mensual",
        "por_vida": "por_vida",
        "por vida": "por_vida",
        "lifetime": "por_vida",
    }

    async def check_and_consume(self, user_id: str, device_id: Optional[str]) -> QuotaDecision:
        """Apply quota priority and consume one AI query if allowed."""
        db = get_database()
        user_doc = await db["users"].find_one({"_id": self._to_object_id(user_id)})
        if not user_doc:
            raise Exception("Usuario no encontrado")

        custom_limit = user_doc.get("aiConsultasLimit")
        if custom_limit:
            return await self._consume_custom_limit(user_id=user_id, custom_limit=custom_limit)

        if bool(user_doc.get("isPro", False)):
            return await self._consume_period_limit(
                user_id=user_id,
                limit=settings.ai_pro_monthly_limit,
                range_name="mensual",
                source="global_pro_monthly"
            )

        if not device_id:
            return QuotaDecision(
                allowed=False,
                limit=settings.ai_free_lifetime_limit,
                used=0,
                remaining=0,
                source="global_free_device_lifetime",
                reason="device_id requerido para usuarios free",
                error_code="AI_DEVICE_ID_REQUIRED",
            )

        return await self._consume_free_lifetime_limit(
            user_id=user_id,
            device_id=device_id,
            limit=settings.ai_free_lifetime_limit,
        )

    async def _consume_custom_limit(self, user_id: str, custom_limit: dict) -> QuotaDecision:
        cantidad = custom_limit.get("cantidad")
        rango = self._normalize_range(custom_limit.get("rango"))

        if not isinstance(cantidad, int) or cantidad < 0:
            raise Exception("aiConsultasLimit.cantidad inválido")
        if not rango:
            raise Exception("aiConsultasLimit.rango inválido")

        return await self._consume_period_limit(
            user_id=user_id,
            limit=cantidad,
            range_name=rango,
            source="user_custom_limit",
        )

    async def _consume_period_limit(
        self,
        user_id: str,
        limit: int,
        range_name: str,
        source: str,
    ) -> QuotaDecision:
        if limit <= 0:
            return QuotaDecision(
                allowed=False,
                limit=limit,
                used=0,
                remaining=0,
                source=source,
                reason="Límite de consultas AI alcanzado",
                error_code="AI_QUOTA_EXCEEDED",
            )

        db = get_database()
        now = datetime.utcnow()
        period_start = self._period_start(now, range_name)
        period_key = period_start.isoformat() if period_start else "lifetime"

        query = {
            "scope": source,
            "userId": user_id,
            "range": range_name,
            "periodKey": period_key,
            "used": {"$lt": limit},
        }
        update = {
            "$inc": {"used": 1},
            "$set": {"updatedAt": now},
            "$setOnInsert": {
                "createdAt": now,
                "scope": source,
                "userId": user_id,
                "range": range_name,
                "periodKey": period_key,
            },
        }

        result = await db[settings.ai_usage_collection].find_one_and_update(
            query,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result:
            used = int(result.get("used", 0))
            return QuotaDecision(
                allowed=True,
                limit=limit,
                used=used,
                remaining=max(0, limit - used),
                source=source,
            )

        existing = await db[settings.ai_usage_collection].find_one({
            "scope": source,
            "userId": user_id,
            "range": range_name,
            "periodKey": period_key,
        })
        used = int(existing.get("used", 0)) if existing else limit
        return QuotaDecision(
            allowed=False,
            limit=limit,
            used=used,
            remaining=0,
            source=source,
            reason="Límite de consultas AI alcanzado",
            error_code="AI_QUOTA_EXCEEDED",
        )

    async def _consume_free_lifetime_limit(self, user_id: str, device_id: str, limit: int) -> QuotaDecision:
        if limit <= 0:
            return QuotaDecision(
                allowed=False,
                limit=limit,
                used=0,
                remaining=0,
                source="global_free_device_lifetime",
                reason="Límite free por dispositivo alcanzado",
                error_code="AI_FREE_QUOTA_EXCEEDED",
            )

        db = get_database()
        now = datetime.utcnow()
        query = {
            "scope": "global_free_device_lifetime",
            "userId": user_id,
            "deviceId": device_id,
            "used": {"$lt": limit},
        }
        update = {
            "$inc": {"used": 1},
            "$set": {"updatedAt": now},
            "$setOnInsert": {
                "createdAt": now,
                "scope": "global_free_device_lifetime",
                "userId": user_id,
                "deviceId": device_id,
            },
        }

        result = await db[settings.ai_usage_collection].find_one_and_update(
            query,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result:
            used = int(result.get("used", 0))
            return QuotaDecision(
                allowed=True,
                limit=limit,
                used=used,
                remaining=max(0, limit - used),
                source="global_free_device_lifetime",
            )

        existing = await db[settings.ai_usage_collection].find_one({
            "scope": "global_free_device_lifetime",
            "userId": user_id,
            "deviceId": device_id,
        })
        used = int(existing.get("used", 0)) if existing else limit
        return QuotaDecision(
            allowed=False,
            limit=limit,
            used=used,
            remaining=0,
            source="global_free_device_lifetime",
            reason="Límite free por dispositivo alcanzado",
            error_code="AI_FREE_QUOTA_EXCEEDED",
        )

    def _normalize_range(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return self.RANGE_ALIASES.get(str(value).strip().lower())

    def _period_start(self, now: datetime, range_name: str) -> Optional[datetime]:
        if range_name == "por_vida":
            return None
        if range_name == "diario":
            return datetime(now.year, now.month, now.day)
        if range_name == "semanal":
            start = now - timedelta(days=now.weekday())
            return datetime(start.year, start.month, start.day)
        if range_name == "mensual":
            return datetime(now.year, now.month, 1)
        raise Exception("Rango de cuota no soportado")

    def _to_object_id(self, user_id: str):
        try:
            return ObjectId(user_id)
        except Exception:
            return user_id


ai_quota_service = AiQuotaService()
