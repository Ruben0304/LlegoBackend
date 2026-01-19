"""Error log repository for database operations."""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId

from clients import get_database
from models_error_logs import ErrorLog, ErrorSource, ErrorSeverity


class ErrorLogRepository:
    collection_name = "error_logs"

    async def create(self, error_data: Dict[str, Any]) -> ErrorLog:
        """Create a new error log."""
        db = get_database()
        if "_id" not in error_data:
            error_data["_id"] = str(ObjectId())
        if "created_at" not in error_data:
            error_data["created_at"] = datetime.utcnow()
        if "resolved" not in error_data:
            error_data["resolved"] = False
        if "occurrence_count" not in error_data:
            error_data["occurrence_count"] = 1
        if "last_occurrence_at" not in error_data:
            error_data["last_occurrence_at"] = datetime.utcnow()

        await db[self.collection_name].insert_one(error_data)
        return ErrorLog(**self._convert_id(error_data))

    async def get_by_id(self, error_id: str) -> Optional[ErrorLog]:
        """Get error log by ID."""
        db = get_database()
        doc = await db[self.collection_name].find_one({"_id": error_id})
        return ErrorLog(**self._convert_id(doc)) if doc else None

    async def update_analysis(self, error_id: str, analysis: Dict[str, Any]) -> bool:
        """Update Gemini analysis for an error log."""
        db = get_database()
        result = await db[self.collection_name].update_one(
            {"_id": error_id},
            {"$set": {"gemini_analysis": analysis}}
        )
        return result.modified_count > 0

    async def mark_resolved(self, error_id: str, resolved_by: Optional[str] = None) -> bool:
        """Mark error as resolved."""
        db = get_database()
        result = await db[self.collection_name].update_one(
            {"_id": error_id},
            {"$set": {
                "resolved": True,
                "resolved_at": datetime.utcnow(),
                "resolved_by": resolved_by
            }}
        )
        return result.modified_count > 0

    async def mark_unresolved(self, error_id: str) -> bool:
        """Mark error as unresolved (reopen)."""
        db = get_database()
        result = await db[self.collection_name].update_one(
            {"_id": error_id},
            {"$set": {
                "resolved": False,
                "resolved_at": None,
                "resolved_by": None
            }}
        )
        return result.modified_count > 0

    async def get_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        days: Optional[int] = None,
        source: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
        search: Optional[str] = None
    ) -> tuple[List[ErrorLog], int]:
        """Get paginated error logs with filters."""
        db = get_database()
        query: Dict[str, Any] = {}

        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            query["created_at"] = {"$gte": cutoff}

        if source:
            query["source"] = source

        if severity:
            query["gemini_analysis.severidad"] = severity

        if resolved is not None:
            query["resolved"] = resolved

        if search:
            query["$or"] = [
                {"error_type": {"$regex": search, "$options": "i"}},
                {"error_message": {"$regex": search, "$options": "i"}},
                {"endpoint": {"$regex": search, "$options": "i"}}
            ]

        total = await db[self.collection_name].count_documents(query)
        skip = (page - 1) * page_size

        cursor = db[self.collection_name].find(query).sort("created_at", -1).skip(skip).limit(page_size)
        docs = await cursor.to_list(length=page_size)

        return [ErrorLog(**self._convert_id(doc)) for doc in docs], total

    async def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get error statistics for the last N days."""
        db = get_database()
        cutoff = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            {"$match": {"created_at": {"$gte": cutoff}}},
            {"$facet": {
                "total": [{"$count": "count"}],
                "resolved": [{"$match": {"resolved": True}}, {"$count": "count"}],
                "by_severity": [
                    {"$match": {"gemini_analysis.severidad": {"$exists": True}}},
                    {"$group": {"_id": "$gemini_analysis.severidad", "count": {"$sum": 1}}}
                ],
                "by_source": [
                    {"$group": {"_id": "$source", "count": {"$sum": 1}}}
                ],
                "by_type": [
                    {"$group": {"_id": "$error_type", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 10}
                ],
                "critical_unresolved": [
                    {"$match": {
                        "resolved": False,
                        "gemini_analysis.severidad": "critica"
                    }},
                    {"$count": "count"}
                ]
            }}
        ]

        result = await db[self.collection_name].aggregate(pipeline).to_list(1)
        if not result:
            return {
                "total_errors": 0,
                "resolved_errors": 0,
                "pending_errors": 0,
                "by_severity": {},
                "by_source": {},
                "by_type": {},
                "critical_unresolved": 0,
                "period_days": days
            }

        data = result[0]
        total = data["total"][0]["count"] if data["total"] else 0
        resolved = data["resolved"][0]["count"] if data["resolved"] else 0

        return {
            "total_errors": total,
            "resolved_errors": resolved,
            "pending_errors": total - resolved,
            "by_severity": {item["_id"]: item["count"] for item in data["by_severity"]},
            "by_source": {item["_id"]: item["count"] for item in data["by_source"]},
            "by_type": {item["_id"]: item["count"] for item in data["by_type"]},
            "critical_unresolved": data["critical_unresolved"][0]["count"] if data["critical_unresolved"] else 0,
            "period_days": days
        }

    async def cleanup_old_resolved(self, days: int = 30) -> int:
        """Delete resolved errors older than N days."""
        db = get_database()
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db[self.collection_name].delete_many({
            "resolved": True,
            "created_at": {"$lt": cutoff}
        })
        return result.deleted_count

    async def find_similar_pending(
        self,
        error_type: str,
        error_message: str,
        source: str
    ) -> Optional[ErrorLog]:
        """Find a similar unresolved error to avoid duplicates."""
        db = get_database()
        doc = await db[self.collection_name].find_one({
            "error_type": error_type,
            "error_message": error_message,
            "source": source,
            "resolved": False
        })
        return ErrorLog(**self._convert_id(doc)) if doc else None

    async def increment_occurrence(self, error_id: str) -> bool:
        """Increment occurrence count for an existing error."""
        db = get_database()
        result = await db[self.collection_name].update_one(
            {"_id": error_id},
            {
                "$inc": {"occurrence_count": 1},
                "$set": {"last_occurrence_at": datetime.utcnow()}
            }
        )
        return result.modified_count > 0

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc


# Singleton instance
error_log_repo = ErrorLogRepository()
