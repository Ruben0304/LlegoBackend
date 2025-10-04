"""Pydantic models for data validation and serialization."""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime


class User(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: str
    phone: Optional[str] = None
    password: str
    role: str = "customer"  # "merchant" or "customer"
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class Business(BaseModel):
    id: str = Field(alias="_id")
    name: str
    type: str  # "coffee", "restaurant", etc.
    ownerId: str
    globalRating: float
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class Coordinates(BaseModel):
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]


class Branch(BaseModel):
    id: str = Field(alias="_id")
    businessId: str
    name: str
    address: str
    coordinates: Coordinates
    phone: str
    schedule: Dict[str, List[str]]  # {"mon": ["08:00-20:00"], ...}
    managerIds: List[str]
    status: str  # "active", etc.
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class Product(BaseModel):
    id: str = Field(alias="_id")
    branchId: str
    name: str
    description: str
    weight: str
    price: float
    currency: str = "USD"
    image: str
    availability: bool = True
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# Export repository instances for backward compatibility
from repositories import (
    users_repo,
    businesses_repo,
    branches_repo,
    products_repo,
)

__all__ = [
    "User",
    "Business",
    "Coordinates",
    "Branch",
    "Product",
    "users_repo",
    "businesses_repo",
    "branches_repo",
    "products_repo",
]
