"""Ad pricing repository — fixed fees per (placement, durationDays)."""

from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.ads import AdPricing


class AdPricingRepository:
    collection_name = "ad_pricing"

    def _col(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def get_all_active(self) -> List[AdPricing]:
        cursor = self._col().find({"isActive": True}).sort(
            [("placement", 1), ("durationDays", 1)]
        )
        docs = await cursor.to_list(length=None)
        return [AdPricing(**self._convert_id(d)) for d in docs]

    async def get(self, placement: str, duration_days: int) -> Optional[AdPricing]:
        doc = await self._col().find_one(
            {"placement": placement, "durationDays": duration_days, "isActive": True}
        )
        return AdPricing(**self._convert_id(doc)) if doc else None

    async def upsert(
        self,
        placement: str,
        duration_days: int,
        price: float,
        currency: str = "usd",
        label: Optional[str] = None,
    ) -> AdPricing:
        """Idempotent upsert keyed by (placement, durationDays)."""
        doc = await self._col().find_one_and_update(
            {"placement": placement, "durationDays": duration_days},
            {
                "$set": {
                    "placement": placement,
                    "durationDays": duration_days,
                    "price": price,
                    "currency": currency,
                    "label": label,
                    "isActive": True,
                }
            },
            upsert=True,
            return_document=True,
        )
        return AdPricing(**self._convert_id(doc))
