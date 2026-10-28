"""Branch menu repository for OCR data operations."""

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.models import BranchMenu


class BranchMenuRepository:
    """Repository for BranchMenu CRUD operations."""

    mongo_collection_name = "branch_menus"

    @staticmethod
    def _to_object_id(value: Any) -> Any:
        """Convert value to ObjectId if possible."""
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(str(value))
        except Exception:
            return value

    async def get_by_id(self, menu_id: str) -> Optional[BranchMenu]:
        """Get menu by ID."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one(
            {"_id": self._to_object_id(menu_id)}
        )
        return BranchMenu(**doc) if doc else None

    async def get_by_branch(self, branch_id: str) -> Optional[BranchMenu]:
        """Get menu by branch ID (unique per branch)."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one(
            {"branchId": self._to_object_id(branch_id)}
        )
        return BranchMenu(**doc) if doc else None

    async def upsert_image(
        self, branch_id: str, image: str
    ) -> tuple[BranchMenu, Optional[str]]:
        """
        Create or replace the menu image for a branch.

        Returns (resulting_menu, previous_image or None).
        On replace: sets image, isActive=True, ocrStatus="pending",
        clears ocrError, quality, lines, tokens, trigrams, processingStartedAt.
        Preserves createdAt.
        """
        db = get_database()
        branch_oid = self._to_object_id(branch_id)
        now = datetime.utcnow()
        now = now.replace(microsecond=now.microsecond // 1000 * 1000)  # MongoDB stores milliseconds.

        fields = {
            "image": image,
            "isActive": True,
            "ocrStatus": "pending",
            "ocrError": None,
            "quality": None,
            "lines": [],
            "tokens": [],
            "trigrams": [],
            "processingStartedAt": None,
            "updatedAt": now,
        }
        inserted = {"_id": ObjectId(), "branchId": branch_oid, "createdAt": now}
        # Return the previous image in the same atomic swap, so concurrent edits
        # each clean up exactly the image they replaced.
        previous = await db[self.mongo_collection_name].find_one_and_update(
            {"branchId": branch_oid},
            {
                "$set": fields,
                "$setOnInsert": inserted,
            },
            upsert=True,
            return_document=False,
        )

        return (
            BranchMenu(**{**(previous or inserted), **fields}),
            previous.get("image") if previous else None,
        )

    async def set_active(self, branch_id: str, is_active: bool) -> Optional[BranchMenu]:
        """Set menu active/inactive for a branch."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one_and_update(
            {"branchId": self._to_object_id(branch_id)},
            {"$set": {"isActive": is_active, "updatedAt": datetime.utcnow()}},
            return_document=True,
        )
        return BranchMenu(**doc) if doc else None

    async def delete_by_branch(self, branch_id: str) -> Optional[BranchMenu]:
        """Delete menu by branch ID (returns deleted doc for S3 cleanup)."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one_and_delete(
            {"branchId": self._to_object_id(branch_id)}
        )
        return BranchMenu(**doc) if doc else None

    async def claim_next_pending(self) -> Optional[BranchMenu]:
        """
        Atomically claim next pending menu for processing.

        Finds one with ocrStatus="pending", updates to "processing",
        sets processingStartedAt, ordered by updatedAt ascending.
        """
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one_and_update(
            {"ocrStatus": "pending"},
            {
                "$set": {
                    "ocrStatus": "processing",
                    "processingStartedAt": datetime.utcnow(),
                }
            },
            sort=[("updatedAt", 1)],
            return_document=True,
        )
        return BranchMenu(**doc) if doc else None

    async def requeue_stale_processing(
        self, older_than_seconds: int = 600
    ) -> int:
        """
        Requeue stale processing tasks back to pending.

        Returns count of requeued documents.
        """
        db = get_database()
        cutoff = datetime.utcnow() - timedelta(seconds=older_than_seconds)
        result = await db[self.mongo_collection_name].update_many(
            {
                "ocrStatus": "processing",
                "processingStartedAt": {"$lt": cutoff},
            },
            {"$set": {"ocrStatus": "pending"}},
        )
        return result.modified_count

    async def set_ocr_result(
        self,
        menu_id: str,
        image: str,
        lines: list,
        tokens: list,
        trigrams: list,
        quality: dict,
    ) -> bool:
        """
        Set successful OCR result.

        Filters by _id and image (fails if image was replaced).
        Returns True if updated, False otherwise.
        """
        db = get_database()
        result = await db[self.mongo_collection_name].update_one(
            {"_id": self._to_object_id(menu_id), "image": image},
            {
                "$set": {
                    "ocrStatus": "done",
                    "lines": lines,
                    "tokens": tokens,
                    "trigrams": trigrams,
                    "quality": quality,
                    "ocrError": None,
                    "processingStartedAt": None,
                    "updatedAt": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    async def set_ocr_failed(
        self, menu_id: str, image: str, error: str
    ) -> bool:
        """
        Set failed OCR result.

        Filters by _id and image (fails if image was replaced).
        Returns True if updated, False otherwise.
        """
        db = get_database()
        truncated_error = error[:500]
        result = await db[self.mongo_collection_name].update_one(
            {"_id": self._to_object_id(menu_id), "image": image},
            {
                "$set": {
                    "ocrStatus": "failed",
                    "ocrError": truncated_error,
                    "processingStartedAt": None,
                    "updatedAt": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    @staticmethod
    def build_candidate_pipeline(
        trigrams: List[str],
        tokens: List[str],
        branch_ids: Optional[List[str]] = None,
        limit: int = 20,
        min_overlap_ratio: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """
        Build aggregation pipeline for menu search candidates.

        Pure function (no Mongo). Returns pipeline stages.

        Match: isActive=True, ocrStatus="done", branchId in branch_ids (if not None),
        and (trigrams contain query trigrams OR tokens contain query tokens).

        Overlap filter: documents matching by trigram overlap >= max(1, ceil(len(trigrams) * min_overlap_ratio)).
        Token matches bypass overlap filter.

        Returns pipeline with $project excluding trigrams and tokens (heavy fields).
        """
        if not trigrams and not tokens:
            # Empty query: return impossible match
            return [{"$match": {"$expr": {"$literal": False}}}]

        # Build query match: must be active, done, and in selected branches
        match_conds = [
            {"isActive": True},
            {"ocrStatus": "done"},
        ]

        # Add branch filter if specified
        if branch_ids is not None:
            branch_oids = [ObjectId(bid) for bid in branch_ids]
            match_conds.append({"branchId": {"$in": branch_oids}})

        # Build trigram and token matching
        search_conds = []
        if trigrams:
            search_conds.append({"trigrams": {"$in": trigrams}})
        if tokens:
            search_conds.append({"tokens": {"$in": tokens}})

        if search_conds:
            if len(search_conds) == 1:
                match_conds.append(search_conds[0])
            else:
                match_conds.append({"$or": search_conds})

        pipeline = [{"$match": {"$and": match_conds}}]

        # Add fields for overlap and token matching
        if trigrams:
            overlap_threshold = max(1, math.ceil(len(trigrams) * min_overlap_ratio))
            pipeline.append(
                {
                    "$addFields": {
                        "overlap": {
                            "$size": {
                                "$setIntersection": ["$trigrams", trigrams]
                            }
                        },
                        "tokenHit": {
                            "$gt": [
                                {
                                    "$size": {
                                        "$setIntersection": ["$tokens", tokens]
                                        if tokens
                                        else []
                                    }
                                },
                                0,
                            ]
                        }
                        if tokens
                        else {"$literal": False},
                    }
                }
            )
            # Filter by overlap or token hit
            pipeline.append(
                {
                    "$match": {
                        "$or": [
                            {"tokenHit": True} if tokens else False,
                            {"overlap": {"$gte": overlap_threshold}},
                        ]
                    }
                }
                if tokens
                else {
                    "$match": {"overlap": {"$gte": overlap_threshold}}
                }
            )
            pipeline.append({"$sort": {"overlap": -1}})
        else:
            # Only tokens, no trigrams — no overlap calculation
            if tokens:
                pipeline.append({"$sort": {"updatedAt": -1}})

        pipeline.append({"$limit": limit})
        pipeline.append(
            {
                "$project": {
                    "trigrams": 0,
                    "tokens": 0,
                    "overlap": 0,
                    "tokenHit": 0,
                }
            }
        )

        return pipeline

    async def find_candidates(
        self,
        trigrams: List[str],
        tokens: List[str],
        branch_ids: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[BranchMenu]:
        """
        Find candidate menus by trigram/token search.

        Returns list of BranchMenu (projections have no tokens/trigrams).
        """
        db = get_database()
        pipeline = self.build_candidate_pipeline(
            trigrams, tokens, branch_ids, limit
        )
        cursor = db[self.mongo_collection_name].aggregate(pipeline)
        docs = await cursor.to_list(length=None)
        return [BranchMenu(**doc) for doc in docs]
