"""Business repository for database operations."""
from typing import List, Optional, Dict, Any
import uuid
from clients import get_qdrant_client
from models import Business
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct
from services.embeddings.gemini_service import GeminiEmbeddingService


class BusinessRepository:
    qdrant_collection_name = "businesses"

    async def get_all(self) -> List[Business]:
        """Get all businesses from Qdrant."""
        try:
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
                    
            return businesses
        except Exception as e:
            print(f"Error fetching all businesses: {e}")
            return []

    async def get_by_id(self, business_id: str) -> Optional[Business]:
        """Get business by ID from Qdrant."""
        try:
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
                return self._point_to_business(points[0])
            return None
        except Exception as e:
            print(f"Error fetching business {business_id}: {e}")
            return None

    async def get_by_ids(self, business_ids: List[str]) -> List[Business]:
        """Get multiple businesses by IDs from Qdrant in a single query."""
        if not business_ids:
            return []
        try:
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
