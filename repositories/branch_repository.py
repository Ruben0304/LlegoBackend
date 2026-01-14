"""Branch repository for database operations."""
from typing import List, Optional, Dict, Any
import uuid
from clients import get_qdrant_client
from models import Branch, Coordinates
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct
from services.embeddings.gemini_service import GeminiEmbeddingService
from utils.cache import (
    get_cached, set_cached, invalidate_branch_cache, invalidate_product_cache,
    get_branch_cache_key, TTL_DEFAULT, should_cache_result
)


class BranchRepository:
    qdrant_collection_name = "branches"

    async def create(self, branch: Branch) -> Branch:
        """Create a new branch in Qdrant (only)."""
        # 1. Generate embedding
        embedding_service = GeminiEmbeddingService()
        # Create a rich text representation for embedding
        text_parts = [branch.name, branch.address or "", branch.phone]
        text_parts.extend(branch.facilities)
        text_to_embed = " ".join(filter(None, text_parts))
        
        embedding = embedding_service.generate_embedding(text_to_embed)

        # 2. Insert into Qdrant
        qdrant_client = get_qdrant_client()
        
        # Prepare payload
        payload = {
            "metadata": {
                "mongo_id": str(branch.id),
                "businessId": branch.businessId,
                "name": branch.name,
                "address": branch.address,
                # coordinates should be dict
                "coordinates": branch.coordinates.model_dump(),
                "phone": branch.phone,
                "schedule": branch.schedule,
                "managerIds": branch.managerIds,
                "status": branch.status,
                "deliveryRadius": branch.deliveryRadius,
                "facilities": branch.facilities,
                "tipos": branch.tipos,
                "avatar": branch.avatar,
                "coverImage": branch.coverImage,
                "createdAt": branch.createdAt.isoformat()
            }
        }

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload=payload
        )

        await qdrant_client.upsert(
            collection_name=self.qdrant_collection_name,
            points=[point]
        )

        # Invalidate cache for this business and all branches
        invalidate_branch_cache(business_id=branch.businessId)
        invalidate_branch_cache()  # Invalidate get_all cache

        return branch

    async def get_all(self) -> List[Branch]:
        """Get all branches from Qdrant with caching."""
        cache_key = get_branch_cache_key("all")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Branch(**b) for b in cached]

        try:
            print("→ Fetching all branches from database")
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

            # Cache the results only if not too large
            if should_cache_result(branches):
                serialized = [b.model_dump() for b in branches]
                set_cached(cache_key, serialized, TTL_DEFAULT)
                print(f"✓ Cached {len(branches)} branches (get_all)")
            else:
                print(f"⚠ Skipped caching {len(branches)} branches (exceeds limit)")

            return branches

        except Exception as e:
            print(f"Error fetching all branches from Qdrant: {e}")
            return []

    async def get_by_id(self, branch_id: str) -> Optional[Branch]:
        """Get branch by ID from Qdrant with caching."""
        cache_key = get_branch_cache_key(f"id:{branch_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            return Branch(**cached)

        try:
            print(f"→ Fetching branch {branch_id} from database")
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
                branch = self._point_to_branch(points[0])
                if branch:
                    # Cache the result
                    set_cached(cache_key, branch.model_dump(), TTL_DEFAULT)
                return branch

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
        """Get branches by IDs from Qdrant with caching."""
        cache_key = get_branch_cache_key(f"ids:{','.join(sorted(branch_ids))}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Branch(**b) for b in cached]

        try:
            print(f"→ Fetching {len(branch_ids)} branches from database")
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

            # Cache the results
            serialized = [b.model_dump() for b in branches]
            set_cached(cache_key, serialized, TTL_DEFAULT)

            return branches

        except Exception as e:
            print(f"Error fetching branches from Qdrant: {e}")
            return []

    async def update(self, branch_id: str, updates: Dict[str, Any]) -> Optional[Branch]:
        """Update a branch in Qdrant."""
        try:
            qdrant_client = get_qdrant_client()

            # Find the point by mongo_id
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
                with_vectors=True
            )

            points, _ = result
            if not points:
                return None

            point = points[0]
            metadata = point.payload.get("metadata", {})

            # Update metadata with new values
            for key, value in updates.items():
                metadata[key] = value

            # Regenerate embedding if name, address, phone or facilities changed
            if any(k in updates for k in ["name", "address", "phone", "facilities"]):
                embedding_service = GeminiEmbeddingService()
                text_parts = [
                    metadata.get("name", ""),
                    metadata.get("address", ""),
                    metadata.get("phone", "")
                ]
                facilities = metadata.get("facilities", [])
                if facilities:
                    text_parts.extend(facilities)
                text_to_embed = " ".join(filter(None, text_parts))
                new_vector = embedding_service.generate_embedding(text_to_embed)
            else:
                new_vector = point.vector

            # Update the point
            updated_point = PointStruct(
                id=point.id,
                vector=new_vector,
                payload={"metadata": metadata}
            )

            await qdrant_client.upsert(
                collection_name=self.qdrant_collection_name,
                points=[updated_point]
            )

            # Invalidate cache for this branch, its business, and all branches
            invalidate_branch_cache(branch_id=branch_id)
            business_id = metadata.get("businessId")
            if business_id:
                invalidate_branch_cache(business_id=business_id)
            invalidate_branch_cache()  # Invalidate get_all cache

            # If branch has products, invalidate product cache too
            invalidate_product_cache(branch_id=branch_id)

            return self._point_to_branch(updated_point)
        except Exception as e:
            print(f"Error updating branch {branch_id}: {e}")
            raise e

    async def update_field(self, branch_id: str, field: str, value: Any) -> Optional[Branch]:
        """Update a single field of a branch."""
        return await self.update(branch_id, {field: value})

    async def delete(self, branch_id: str) -> bool:
        """Delete a branch from Qdrant by its mongo_id."""
        try:
            qdrant_client = get_qdrant_client()

            # Find the point by mongo_id to get its Qdrant UUID
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
            if not points:
                return False

            point = points[0]
            metadata = point.payload.get("metadata", {})
            business_id = metadata.get("businessId")

            # Delete the point from Qdrant
            await qdrant_client.delete(
                collection_name=self.qdrant_collection_name,
                points_selector=qdrant_models.PointIdsList(
                    points=[point.id]
                )
            )

            # Invalidate cache
            invalidate_branch_cache(branch_id=branch_id)
            if business_id:
                invalidate_branch_cache(business_id=business_id)
            invalidate_branch_cache()  # Invalidate get_all cache
            invalidate_product_cache(branch_id=branch_id)

            return True

        except Exception as e:
            print(f"Error deleting branch {branch_id}: {e}")
            raise e

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
                "avatar": metadata.get("avatar"),
                "coverImage": metadata.get("coverImage"),
                "deliveryRadius": metadata.get("deliveryRadius"),
                "facilities": metadata.get("facilities", []),
                "tipos": metadata.get("tipos", []),
                "createdAt": metadata.get("createdAt")
            }

            return Branch(**branch_data)

        except Exception as e:
            print(f"Error converting point to branch: {e}")
            return None

    async def get_by_tipo(self, tipo: str) -> List[Branch]:
        """Get branches that have a specific tipo from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            branches = []
            offset = None

            # Filter by metadata.tipos containing the tipo value
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.tipos",
                                match=qdrant_models.MatchAny(any=[tipo])
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
            print(f"Error fetching branches by tipo from Qdrant: {e}")
            return []

    async def get_ids_by_tipo(self, tipo: str) -> List[str]:
        """Get branch IDs that have a specific tipo from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            branch_ids = []
            offset = None

            # Filter by metadata.tipos containing the tipo value
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.tipos",
                                match=qdrant_models.MatchAny(any=[tipo])
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
                    metadata = point.payload.get("metadata", {})
                    mongo_id = metadata.get("mongo_id")
                    if mongo_id:
                        branch_ids.append(mongo_id)

                if offset is None:
                    break

            return branch_ids

        except Exception as e:
            print(f"Error fetching branch IDs by tipo from Qdrant: {e}")
            return []
