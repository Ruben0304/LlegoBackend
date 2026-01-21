"""Pydantic models for data validation and serialization."""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


class User(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: str
    username: str  # Unique username, defaults to email prefix
    phone: Optional[str] = None
    password: Optional[str] = None
    role: str = "customer"  # "merchant" or "customer"
    avatar: Optional[str] = None
    businessIds: List[str] = []
    branchIds: List[str] = []
    wallet: Dict[str, float] = Field(default_factory=lambda: {"local": 0.00, "usd": 0.00})
    walletStatus: str = "active"  # "active", "frozen", "closed"
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
    ownerId: str
    globalRating: float
    avatar: str
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
    paymentMethodIds: List[str] = []  # IDs de métodos de pago aceptados
    wallet: Dict[str, float] = Field(default_factory=lambda: {"local": 0.00, "usd": 0.00})
    walletStatus: str = "active"  # "active", "frozen", "closed"
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


class ProductCategory(BaseModel):
    """Product category model for organizing products by branch type."""
    id: str = Field(alias="_id")
    branchType: str  # "restaurante", "dulceria", "tienda"
    name: str
    iconIos: str  # iOS SF Symbol name
    iconWeb: str  # Material Design icon name for web
    iconAndroid: str  # Material Design icon name for Android
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
    """
    Payment method model.

    Defines available payment methods with their commission rates,
    refund policies, and configuration.
    """
    id: str = Field(alias="_id")

    # Basic info
    name: str  # "Wallet USD", "Transfermóvil", "Stripe", "Efectivo"
    code: str  # "wallet_usd", "wallet_cup", "transfermovil", "stripe", "cash"
    currency: str  # "CUP", "USD"
    method: str  # "wallet", "transfer", "stripe", "cash"

    # Commission configuration
    commissionPercent: float = 0.0  # e.g., 2.5 = 2.5% charged to customer
    deliveryFeePercent: float = 0.0  # Extra % for cash payments covering delivery

    # Refund and confirmation settings
    isRefundable: bool = True
    requiresProof: bool = False  # True for bank transfers
    requiresBusinessConfirmation: bool = False  # True for manual methods
    expirationMinutes: Optional[int] = None  # Time limit to complete payment (null = no limit)

    # Display configuration
    isActive: bool = True
    displayOrder: int = 0  # Order in UI
    iconUrl: Optional[str] = None
    instructions: Optional[str] = None  # "Transferir a cuenta X..."

    # Timestamps
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class WalletTransaction(BaseModel):
    """Transaction record for wallet operations."""
    id: str = Field(alias="_id")
    fromOwnerId: Optional[str] = None  # None for external deposits
    fromOwnerType: Optional[str] = None  # "user" or "branch"
    toOwnerId: Optional[str] = None  # None for withdrawals
    toOwnerType: Optional[str] = None  # "user" or "branch"
    amount: float
    currency: str  # "local" or "usd"
    type: str  # "transfer", "deposit", "withdrawal"
    status: str = "completed"  # "pending", "completed", "failed", "reversed"
    description: Optional[str] = None
    metadata: Optional[dict] = None  # Additional info (order_id, payment_gateway_id, etc)
    createdAt: datetime
    completedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class WalletBalance(BaseModel):
    """Wallet balance response model."""
    local: float = 0.00
    usd: float = 0.00


class StripePaymentLink(BaseModel):
    """Stripe Payment Link model for tracking recharge links."""
    id: str = Field(alias="_id")
    userId: str
    url: str
    productId: str
    priceId: str
    currency: str
    isActive: bool = True
    totalReceived: float = 0.0
    usageCount: int = 0
    createdAt: datetime
    lastUsedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# Export repository instances for backward compatibility
from repositories import (
    users_repo,
    businesses_repo,
    branches_repo,
    products_repo,
    product_categories_repo,
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
    "ProductCategory",
    "Product",
    "SmsOcr",
    "PaymentMethod",
    "WalletTransaction",
    "WalletBalance",
    "StripePaymentLink",
    "users_repo",
    "businesses_repo",
    "branches_repo",
    "products_repo",
    "product_categories_repo",
    "payments_repo",
    "payment_methods_repo",
]
