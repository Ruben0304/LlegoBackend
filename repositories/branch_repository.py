"""Branch repository for database operations."""
from typing import List, Optional, Dict, Any
from clients import get_qdrant_client
from models import Branch, Coordinates
from qdrant_client.http import models as qdrant_models


class BranchRepository:
    qdrant_collection_name = "branches"

    async def get_all(self) -> List[Branch]:
        """Get all branches from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            branches = []
            offset = None

            # Scroll through all points in Qdrant
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    branch = self._point_to_branch(point)
                    if branch:
                        branches.append(branch)

                if offset is None:
                    break

            return branches

        except Exception as e:
            print(f"Error fetching all branches from Qdrant: {e}")
            return []

    async def get_by_id(self, branch_id: str) -> Optional[Branch]:
        """Get branch by ID from Qdrant (searches by metadata.mongo_id)."""
        try:
            qdrant_client = get_qdrant_client()

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
                return self._point_to_branch(points[0])

            return None

        except Exception as e:
            print(f"Error fetching branch {branch_id} from Qdrant: {e}")
            return None

    async def search(self, query: str) -> List[Branch]:
        """Search branches by name or address in Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            branches = []
            offset = None
            query_lower = query.lower()

            # Since Qdrant doesn't have native text search on payload,
            # we need to scroll through all branches and filter client-side
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    metadata = point.payload.get("metadata", {})
                    name = metadata.get("name", "").lower()
                    address = metadata.get("address", "").lower()

                    # Check if query matches name or address
                    if query_lower in name or query_lower in address:
                        branch = self._point_to_branch(point)
                        if branch:
                            branches.append(branch)

                if offset is None:
                    break

            return branches

        except Exception as e:
            print(f"Error searching branches in Qdrant: {e}")
            return []

    async def get_by_business(self, business_id: str) -> List[Branch]:
        """Get branches by business ID from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            branches = []
            offset = None

            # Filter by metadata.businessId
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.businessId",
                                match=qdrant_models.MatchValue(value=business_id)
                            )
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    branch = self._point_to_branch(point)
                    if branch:
                        branches.append(branch)

                if offset is None:
                    break

            return branches

        except Exception as e:
            print(f"Error fetching branches by business from Qdrant: {e}")
            return []

    async def get_by_ids(self, branch_ids: List[str]) -> List[Branch]:
        """Get branches by IDs from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
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
                    branch = self._point_to_branch(points[0])
                    if branch:
                        branches.append(branch)

            return branches

        except Exception as e:
            print(f"Error fetching branches from Qdrant: {e}")
            return []

    @staticmethod
    def _point_to_branch(point) -> Optional[Branch]:
        """Convert a Qdrant point to a Branch model."""
        try:
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

            return Branch(**branch_data)

        except Exception as e:
            print(f"Error converting point to branch: {e}")
            return None
