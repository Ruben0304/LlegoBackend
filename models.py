"""Pydantic models for data validation and serialization."""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


class User(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: str
    phone: Optional[str] = None
    password: Optional[str] = None
    role: str = "customer"  # "merchant" or "customer"
    avatar: Optional[str] = None
    businessIds: List[str] = []
    branchIds: List[str] = []
    createdAt: datetime
    authProvider: str = "local"
    providerUserId: Optional[str] = None
    applePrivateEmail: Optional[str] = None
    location: Optional[Dict[str, Any]] = None  # GeoJSON: {"type": "Point", "coordinates": [lon, lat]}

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class Business(BaseModel):
    id: str = Field(alias="_id")
    name: str
    type: str  # "coffee", "restaurant", etc.
    ownerId: str
    globalRating: float
    avatar: str
    coverImage: Optional[str] = None
    description: Optional[str] = None
    socialMedia: Optional[Dict[str, str]] = None
    tags: List[str] = []
    isActive: bool = True
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
    address: Optional[str] = None
    coordinates: Coordinates
    phone: str
    schedule: Dict[str, List[str]]  # {"mon": ["08:00-20:00"], ...}
    managerIds: List[str]
    status: str  # "active", etc.
    avatar: Optional[str] = None
    coverImage: Optional[str] = None
    deliveryRadius: Optional[float] = None
    facilities: List[str] = []
    tipos: List[str] = []  # ["restaurante", "dulceria", "tienda"]
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class Subcategory(BaseModel):
    name: str
    imageUrl: str


class Category(BaseModel):
    id: str = Field(alias="_id")
    name: str
    imageUrl: str
    subcategories: List[Subcategory]
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
    categoryId: Optional[str] = None
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class SmsOcr(BaseModel):
    """Modelo para datos extraídos de capturas de SMS bancarios mediante OCR."""
    id: str = Field(alias="_id")
    quien_envio: str  # Remitente del mensaje
    banco: str  # Nombre del banco
    fecha: datetime  # Fecha de la transferencia
    es_mensaje_banco: bool  # Validación de que es un mensaje bancario
    cantidad_transferida: float  # Monto de la transferencia
    numero_transferencia: str  # Número de referencia de la transferencia
    primeros_4_tarjeta: str  # Primeros 4 dígitos de la tarjeta
    ultimos_4_tarjeta: str  # Últimos 4 dígitos de la tarjeta
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class PaymentMethod(BaseModel):
    """Payment method model."""
    id: str = Field(alias="_id")
    currency: str  # "CUP", "USD", etc.
    method: str  # "tarjeta", "efectivo", "transferencia", etc.

    class Config:
        populate_by_name = True


# Export repository instances for backward compatibility
from repositories import (
    users_repo,
    businesses_repo,
    branches_repo,
    products_repo,
    payments_repo,
    payment_methods_repo,
)

__all__ = [
    "User",
    "Business",
    "Coordinates",
    "Branch",
    "Subcategory",
    "Category",
    "Product",
    "SmsOcr",
    "PaymentMethod",
    "users_repo",
    "businesses_repo",
    "branches_repo",
    "products_repo",
    "payments_repo",
    "payment_methods_repo",
]
