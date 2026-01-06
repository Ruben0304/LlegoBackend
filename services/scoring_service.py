"""Scoring service for ranking results by proximity and other factors."""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from repositories import store_locations_repo, users_repo


@dataclass
class ScoredItem:
    """Item with score and distance information."""
    id: str
    item: Any
    score: float
    distance_m: Optional[float] = None


class ScoringService:
    """
    Service for scoring and ranking items.
    
    Current scoring weights:
    - proximity: 100%
    
    Future weights (to be implemented):
    - popularity
    - ratings
    - relevance
    """
    
    # Scoring weights (must sum to 1.0)
    WEIGHT_PROXIMITY = 1.0
    
    # Max distance for scoring (items beyond this get score 0)
    MAX_DISTANCE_KM = 50.0

    async def get_user_location(self, user_id: str) -> Optional[tuple]:
        """Get user location as (longitude, latitude) tuple."""
        return await users_repo.get_location(user_id)

    async def get_nearby_stores_with_distance(
        self,
        longitude: float,
        latitude: float,
        radius_km: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Get stores near a location with their distances.
        
        Args:
            longitude: Center longitude
            latitude: Center latitude
            radius_km: Optional radius limit in km (None = use MAX_DISTANCE_KM)
            
        Returns:
            Dict mapping store_id to distance in meters
        """
        search_radius = radius_km if radius_km else self.MAX_DISTANCE_KM
        
        nearby = await store_locations_repo.find_nearby(
            longitude=longitude,
            latitude=latitude,
            radius_km=search_radius,
            only_active=True
        )
        
        return {store["store_id"]: store["distance_m"] for store in nearby}

    def calculate_proximity_score(self, distance_m: float, max_distance_m: float) -> float:
        """
        Calculate proximity score (0-1) based on distance.
        
        Closer = higher score. Uses inverse linear scaling.
        
        Args:
            distance_m: Distance in meters
            max_distance_m: Maximum distance for scoring
            
        Returns:
            Score between 0 and 1
        """
        if distance_m >= max_distance_m:
            return 0.0
        
        # Inverse linear: closer = higher score
        return 1.0 - (distance_m / max_distance_m)

    def calculate_total_score(self, proximity_score: float) -> float:
        """
        Calculate total score from all factors.
        
        Currently only uses proximity, but structured for future expansion.
        
        Args:
            proximity_score: Score from proximity (0-1)
            
        Returns:
            Total weighted score (0-1)
        """
        return proximity_score * self.WEIGHT_PROXIMITY

    async def score_branches(
        self,
        branch_ids: List[str],
        user_location: tuple,
        radius_km: Optional[float] = None
    ) -> List[ScoredItem]:
        """
        Score and rank branches by proximity to user.
        
        Args:
            branch_ids: List of branch IDs to score
            user_location: (longitude, latitude) tuple
            radius_km: Optional radius filter in km
            
        Returns:
            List of ScoredItem sorted by score (highest first)
        """
        lon, lat = user_location
        max_distance_m = (radius_km or self.MAX_DISTANCE_KM) * 1000
        
        # Get distances for all nearby stores
        store_distances = await self.get_nearby_stores_with_distance(
            longitude=lon,
            latitude=lat,
            radius_km=radius_km
        )
        
        scored_items = []
        for branch_id in branch_ids:
            distance_m = store_distances.get(branch_id)
            
            # If radius_km specified, filter out branches not in range
            if radius_km and distance_m is None:
                continue
            
            # Calculate score
            if distance_m is not None:
                proximity_score = self.calculate_proximity_score(distance_m, max_distance_m)
            else:
                proximity_score = 0.0
                distance_m = None
            
            total_score = self.calculate_total_score(proximity_score)
            
            scored_items.append(ScoredItem(
                id=branch_id,
                item=None,  # Will be populated by caller
                score=total_score,
                distance_m=distance_m
            ))
        
        # Sort by score descending
        scored_items.sort(key=lambda x: x.score, reverse=True)
        return scored_items

    async def score_products_by_branch(
        self,
        products: List[Any],
        user_location: tuple,
        radius_km: Optional[float] = None
    ) -> List[ScoredItem]:
        """
        Score and rank products by their branch's proximity to user.
        
        Args:
            products: List of product objects (must have branchId attribute)
            user_location: (longitude, latitude) tuple
            radius_km: Optional radius filter in km
            
        Returns:
            List of ScoredItem sorted by score (highest first)
        """
        lon, lat = user_location
        max_distance_m = (radius_km or self.MAX_DISTANCE_KM) * 1000
        
        # Get distances for all nearby stores
        store_distances = await self.get_nearby_stores_with_distance(
            longitude=lon,
            latitude=lat,
            radius_km=radius_km
        )
        
        scored_items = []
        for product in products:
            branch_id = product.branchId
            distance_m = store_distances.get(branch_id)
            
            # If radius_km specified, filter out products from branches not in range
            if radius_km and distance_m is None:
                continue
            
            # Calculate score
            if distance_m is not None:
                proximity_score = self.calculate_proximity_score(distance_m, max_distance_m)
            else:
                proximity_score = 0.0
                distance_m = None
            
            total_score = self.calculate_total_score(proximity_score)
            
            scored_items.append(ScoredItem(
                id=product.id,
                item=product,
                score=total_score,
                distance_m=distance_m
            ))
        
        # Sort by score descending
        scored_items.sort(key=lambda x: x.score, reverse=True)
        return scored_items


# Singleton instance
scoring_service = ScoringService()
