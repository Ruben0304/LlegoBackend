"""Branch repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database, get_qdrant_client
from models import Branch, Coordinates
from qdrant_client.http import models as qdrant_models


class BranchRepository:
    collection_name = "branches"
    qdrant_collection_name = "branches"

    async def get_all(self) -> List[Branch]:
        db = get_database()
        cursor = db[self.collection_name].find()
        branches = await cursor.to_list(length=None)
        return [Branch(**self._convert_id(b)) for b in branches]

    async def get_by_id(self, branch_id: str) -> Optional[Branch]:
        db = get_database()
        # Convert string ID to ObjectId for MongoDB query
        try:
            object_id = ObjectId(branch_id)
        except:
            object_id = branch_id
        branch = await db[self.collection_name].find_one({"_id": object_id})
        return Branch(**self._convert_id(branch)) if branch else None

    async def search(self, query: str) -> List[Branch]:
        db = get_database()
        cursor = db[self.collection_name].find({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"address": {"$regex": query, "$options": "i"}}
            ]
        })
        branches = await cursor.to_list(length=None)
        return [Branch(**self._convert_id(b)) for b in branches]

    async def get_by_business(self, business_id: str) -> List[Branch]:
        db = get_database()
        cursor = db[self.collection_name].find({"businessId": business_id})
        branches = await cursor.to_list(length=None)
        return [Branch(**self._convert_id(b)) for b in branches]

    async def get_by_ids(self, branch_ids: List[str]) -> List[Branch]:
        """Get branches by IDs from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()

            # Retrieve points from Qdrant using scroll with filter
            # We need to filter by metadata.mongo_id
            branches = []

            for branch_id in branch_ids:
                # Search for point with this mongo_id in metadata
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.mongo_id",
                                match=qdrant_models.MatchValue(value=branch_id)
                            )
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False
                )

                points, _ = result

                if points:
                    point = points[0]
                    metadata = point.payload.get("metadata", {})

                    # Reconstruct coordinates
                    coordinates_data = metadata.get("coordinates", {})
                    if isinstance(coordinates_data, dict):
                        coordinates = Coordinates(
                            type=coordinates_data.get("type", "Point"),
                            coordinates=coordinates_data.get("coordinates", [0.0, 0.0])
                        )
                    else:
                        coordinates = Coordinates(type="Point", coordinates=[0.0, 0.0])

                    # Reconstruct Branch from metadata
                    branch_data = {
                        "_id": metadata.get("mongo_id"),
                        "businessId": metadata.get("businessId"),
                        "name": metadata.get("name"),
                        "address": metadata.get("address"),
                        "coordinates": coordinates,
                        "phone": metadata.get("phone"),
                        "schedule": metadata.get("schedule", {}),
                        "managerIds": metadata.get("managerIds", []),
                        "status": metadata.get("status", "active"),
                        "createdAt": metadata.get("createdAt")
                    }

                    branches.append(Branch(**branch_data))

            return branches

        except Exception as e:
            print(f"Error fetching branches from Qdrant: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to empty list if Qdrant fails
            return []

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
