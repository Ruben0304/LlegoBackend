"""Store location repository for geospatial operations in MongoDB."""
from typing import List, Optional, Dict, Any
from clients.mongodb_client import get_database


class StoreLocationRepository:
    """Repository for stores_location collection with geospatial queries."""
    
    collection_name = "stores_location"

    def _get_collection(self):
        """Get the stores_location collection."""
        db = get_database()
        return db[self.collection_name]

    async def create(self, store_id: str, longitude: float, latitude: float, active: bool = True) -> Dict[str, Any]:
        """
        Create a new store location.
        
        Args:
            store_id: The branch ID from Qdrant
            longitude: Longitude coordinate (X)
            latitude: Latitude coordinate (Y)
            active: Whether the store is active
            
        Returns:
            The created document
        """
        collection = self._get_collection()
        
        doc = {
            "store_id": store_id,
            "active": active,
            "location": {
                "type": "Point",
                "coordinates": [longitude, latitude]  # [lon, lat] - GeoJSON format
            }
        }
        
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    async def get_by_store_id(self, store_id: str) -> Optional[Dict[str, Any]]:
        """Get location by store_id."""
        collection = self._get_collection()
        return await collection.find_one({"store_id": store_id})

    async def update_location(self, store_id: str, longitude: float, latitude: float) -> Optional[Dict[str, Any]]:
        """
        Update store coordinates.
        
        Args:
            store_id: The branch ID
            longitude: New longitude
            latitude: New latitude
            
        Returns:
            Updated document or None if not found
        """
        collection = self._get_collection()
        
        result = await collection.find_one_and_update(
            {"store_id": store_id},
            {
                "$set": {
                    "location": {
                        "type": "Point",
                        "coordinates": [longitude, latitude]
                    }
                }
            },
            return_document=True
        )
        return result

    async def set_active(self, store_id: str, active: bool) -> Optional[Dict[str, Any]]:
        """
        Set store active status.
        
        Args:
            store_id: The branch ID
            active: New active status
            
        Returns:
            Updated document or None if not found
        """
        collection = self._get_collection()
        
        result = await collection.find_one_and_update(
            {"store_id": store_id},
            {"$set": {"active": active}},
            return_document=True
        )
        return result

    async def delete(self, store_id: str) -> bool:
        """Delete a store location."""
        collection = self._get_collection()
        result = await collection.delete_one({"store_id": store_id})
        return result.deleted_count > 0

    async def find_nearby(
        self,
        longitude: float,
        latitude: float,
        radius_km: float,
        only_active: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find stores within a radius.
        
        Args:
            longitude: Center longitude
            latitude: Center latitude
            radius_km: Radius in kilometers
            only_active: If True, only return active stores
            
        Returns:
            List of stores with distance_m field, ordered by proximity
        """
        collection = self._get_collection()
        
        # Build $geoNear stage with query filter for compound index
        geo_near_stage = {
            "$geoNear": {
                "near": {
                    "type": "Point",
                    "coordinates": [longitude, latitude]
                },
                "distanceField": "distance_m",
                "maxDistance": radius_km * 1000,  # Convert km to meters
                "spherical": True
            }
        }
        
        # Include active filter in $geoNear query to use compound index
        if only_active:
            geo_near_stage["$geoNear"]["query"] = {"active": True}
        
        pipeline = [
            geo_near_stage,
            {
                "$project": {
                    "_id": 0,
                    "store_id": 1,
                    "distance_m": 1,
                    "location": 1,
                    "active": 1
                }
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def upsert(self, store_id: str, longitude: float, latitude: float, active: bool = True) -> Dict[str, Any]:
        """
        Create or update a store location.
        
        Args:
            store_id: The branch ID
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            active: Whether the store is active
            
        Returns:
            The upserted document
        """
        collection = self._get_collection()
        
        result = await collection.find_one_and_update(
            {"store_id": store_id},
            {
                "$set": {
                    "active": active,
                    "location": {
                        "type": "Point",
                        "coordinates": [longitude, latitude]
                    }
                }
            },
            upsert=True,
            return_document=True
        )
        return result


# Singleton instance
store_locations_repo = StoreLocationRepository()
