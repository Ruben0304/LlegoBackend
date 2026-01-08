"""Business repository for database operations."""
from typing import List, Optional, Dict, Any
import uuid
from clients import get_qdrant_client
from models import Business
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct
from services.embeddings.gemini_service import GeminiEmbeddingService
from utils.cache import (
    get_cached, set_cached, invalidate_business_cache,
    get_business_cache_key, TTL_DEFAULT, should_cache_result
)


class BusinessRepository:
    qdrant_collection_name = "businesses"

    async def get_all(self) -> List[Business]:
        """Get all businesses from Qdrant with caching."""
        cache_key = get_business_cache_key("all")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Business(**b) for b in cached]

        try:
            print("→ Fetching all businesses from database")
            qdrant_client = get_qdrant_client()
            businesses = []
            offset = None

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
                    business = self._point_to_business(point)
                    if business:
                        businesses.append(business)

                if offset is None:
                    break

            # Cache the results only if not too large
            if should_cache_result(businesses):
                serialized = [b.model_dump() for b in businesses]
                set_cached(cache_key, serialized, TTL_DEFAULT)
                print(f"✓ Cached {len(businesses)} businesses (get_all)")
            else:
                print(f"⚠ Skipped caching {len(businesses)} businesses (exceeds limit)")

            return businesses
        except Exception as e:
            print(f"Error fetching all businesses: {e}")
            return []

    async def get_by_id(self, business_id: str) -> Optional[Business]:
        """Get business by ID from Qdrant with caching."""
        cache_key = get_business_cache_key(f"id:{business_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            return Business(**cached)

        try:
            print(f"→ Fetching business {business_id} from database")
            qdrant_client = get_qdrant_client()
            result = await qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="metadata.mongo_id",
                            match=qdrant_models.MatchValue(value=business_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False
            )

            points, _ = result
            if points:
                business = self._point_to_business(points[0])
                if business:
                    # Cache the result
                    set_cached(cache_key, business.model_dump(), TTL_DEFAULT)
                return business
            return None
        except Exception as e:
            print(f"Error fetching business {business_id}: {e}")
            return None

    async def get_by_ids(self, business_ids: List[str]) -> List[Business]:
        """Get multiple businesses by IDs from Qdrant with caching."""
        if not business_ids:
            return []

        cache_key = get_business_cache_key(f"ids:{','.join(sorted(business_ids))}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Business(**b) for b in cached]

        try:
            print(f"→ Fetching {len(business_ids)} businesses from database")
            qdrant_client = get_qdrant_client()
            result = await qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=qdrant_models.Filter(
                    should=[
                        qdrant_models.FieldCondition(
                            key="metadata.mongo_id",
                            match=qdrant_models.MatchValue(value=bid)
                        )
                        for bid in business_ids
                    ]
                ),
                limit=len(business_ids),
                with_payload=True,
                with_vectors=False
            )

            points, _ = result
            businesses = []
            for point in points:
                business = self._point_to_business(point)
                if business:
                    businesses.append(business)

            # Cache the results
            serialized = [b.model_dump() for b in businesses]
            set_cached(cache_key, serialized, TTL_DEFAULT)

            return businesses
        except Exception as e:
            print(f"Error fetching businesses by IDs: {e}")
            return []

    async def search(self, query: str) -> List[Business]:
        """Search businesses by name or type in Qdrant (client-side filtering for simplicity if no vectors)."""
        # Note: Ideally we should use vector search if we have embeddings, 
        # but the interface asks for 'search' which might imply text match.
        # For consistency with other repos, we scroll and filter.
        try:
            qdrant_client = get_qdrant_client()
            businesses = []
            offset = None
            query_lower = query.lower()

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
                    b_type = metadata.get("type", "").lower()
                    
                    if query_lower in name or query_lower in b_type:
                        business = self._point_to_business(point)
                        if business:
                            businesses.append(business)
                
                if offset is None:
                    break
            
            return businesses
        except Exception as e:
            print(f"Error searching businesses: {e}")
            return []

    async def get_by_owner(self, owner_id: str) -> List[Business]:
        """Get businesses by owner ID from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            businesses = []
            offset = None

            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.ownerId",
                                match=qdrant_models.MatchValue(value=owner_id)
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
                    business = self._point_to_business(point)
                    if business:
                        businesses.append(business)
                
                if offset is None:
                    break
            
            return businesses
        except Exception as e:
            print(f"Error fetching businesses by owner: {e}")
            return []

    async def create(self, business: Business) -> Business:
        """Create a new business in Qdrant."""
        try:
            # Generate embedding
            embedding_service = GeminiEmbeddingService()
            text_to_embed = f"{business.name} {business.type} {business.description or ''} {' '.join(business.tags)}"
            embedding = embedding_service.generate_embedding(text_to_embed)

            qdrant_client = get_qdrant_client()
            
            payload = {
                "metadata": {
                    "mongo_id": str(business.id),
                    "name": business.name,
                    "type": business.type,
                    "ownerId": business.ownerId,
                    "globalRating": business.globalRating,
                    "avatar": business.avatar,
                    "coverImage": business.coverImage,
                    "description": business.description,
                    "socialMedia": business.socialMedia,
                    "tags": business.tags,
                    "isActive": business.isActive,
                    "createdAt": business.createdAt.isoformat()
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

            # Invalidate cache for all businesses
            invalidate_business_cache()

            return business
        except Exception as e:
            print(f"Error creating business in Qdrant: {e}")
            raise e

    async def update(self, business_id: str, updates: Dict[str, Any]) -> Optional[Business]:
        """Update a business in Qdrant."""
        try:
            qdrant_client = get_qdrant_client()

            # Find the point by mongo_id
            result = await qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="metadata.mongo_id",
                            match=qdrant_models.MatchValue(value=business_id)
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

            # Regenerate embedding if name, type, description or tags changed
            if any(k in updates for k in ["name", "type", "description", "tags"]):
                embedding_service = GeminiEmbeddingService()
                tags = metadata.get("tags", [])
                tags_str = " ".join(tags) if tags else ""
                text_to_embed = f"{metadata.get('name', '')} {metadata.get('type', '')} {metadata.get('description', '')} {tags_str}"
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

            # Invalidate cache for this business and all businesses
            invalidate_business_cache(business_id=business_id)
            invalidate_business_cache()  # Invalidate get_all cache

            return self._point_to_business(updated_point)
        except Exception as e:
            print(f"Error updating business {business_id}: {e}")
            raise e

    async def update_field(self, business_id: str, field: str, value: Any) -> Optional[Business]:
        """Update a single field of a business."""
        return await self.update(business_id, {field: value})

    @staticmethod
    def _point_to_business(point) -> Optional[Business]:
        try:
            metadata = point.payload.get("metadata", {})
            return Business(
                _id=metadata.get("mongo_id"),
                name=metadata.get("name"),
                type=metadata.get("type"),
                ownerId=metadata.get("ownerId"),
                globalRating=metadata.get("globalRating"),
                avatar=metadata.get("avatar"),
                coverImage=metadata.get("coverImage"),
                description=metadata.get("description"),
                socialMedia=metadata.get("socialMedia"),
                tags=metadata.get("tags", []),
                isActive=metadata.get("isActive", True),
                createdAt=metadata.get("createdAt")
            )
        except Exception as e:
            print(f"Error converting point to business: {e}")
            return None
