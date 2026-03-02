"""Pydantic models for data validation and serialization."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId

# =============================================================================
# Transfer/Payment Models (shared by Platform and Branch)
# =============================================================================


class TransferAccount(BaseModel):
    """A bank card account for receiving CUP transfers."""

    cardNumber: str
    cardHolderName: str
    bankName: str  # "Bandec", "BPA", "Metropolitano", etc.
    isActive: bool = True


class QrPayment(BaseModel):
    """A QR code value for online payments (EnZona, etc.)."""

    value: str
    isActive: bool = True


class TransferPhone(BaseModel):
    """A phone number for mobile transfers (Transfermóvil, etc.)."""

    phone: str
    isActive: bool = True


class SavedAddress(BaseModel):
    """A saved delivery address stored in the user's profile."""

    id: str                                # UUID generated at creation
    label: str                             # Alias visible (ej: "Casa", "Trabajo")
    street: str
    city: Optional[str] = None
    reference: Optional[str] = None
    addressType: str = "house"             # "house" | "apartment" | "office" | "other"
    buildingName: Optional[str] = None
    floor: Optional[str] = None
    apartment: Optional[str] = None
    deliveryInstructions: Optional[str] = None
    latitude: float
    longitude: float


class User(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    email: str
    username: str  # Unique username, defaults to email prefix
    phone: Optional[str] = None
    password: Optional[str] = None
    role: str = "customer"  # "merchant" or "customer"
    avatar: Optional[str] = None
    businessIds: List[PyObjectId] = []
    branchIds: List[PyObjectId] = []
    businessAccessIds: List[
        PyObjectId
    ] = []  # IDs de BusinessAccess activos (acceso a negocios completos)
    wallet: Dict[str, float] = Field(
        default_factory=lambda: {"local": 0.00, "usd": 0.00}
    )
    walletStatus: str = "active"  # "active", "frozen", "closed"
    createdAt: datetime
    authProvider: str = "local"
    providerUserId: Optional[str] = None
    applePrivateEmail: Optional[str] = None
    location: Optional[Dict[str, Any]] = (
        None  # GeoJSON: {"type": "Point", "coordinates": [lon, lat]}
    )
    isPro: bool = False
    aiConsultasLimit: Optional[Dict[str, Any]] = None
    # Saved delivery addresses (Uber Eats / Glovo style)
    savedAddresses: List["SavedAddress"] = []
    defaultAddressId: Optional[str] = None  # ID of the default address

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class Business(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    ownerId: PyObjectId
    globalRating: float
    avatar: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    isActive: bool = True
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class Coordinates(BaseModel):
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]


class Branch(BaseModel):
    id: PyObjectId = Field(alias="_id")
    businessId: PyObjectId
    name: str
    address: Optional[str] = None
    coordinates: Coordinates
    phone: str
    schedule: Dict[str, List[str]]  # {"mon": ["08:00-20:00"], ...}
    managerIds: List[PyObjectId]
    isActive: bool = True
    status: Optional[str] = None
    avatar: Optional[str] = None
    coverImage: Optional[str] = None
    socialMedia: Optional[Dict[str, str]] = None
    tipos: List[str] = []  # ["restaurante", "dulceria", "tienda", "perfumeria"]
    paymentMethodIds: List[Union[PyObjectId, str]] = []  # IDs de métodos de pago aceptados
    wallet: Dict[str, float] = Field(
        default_factory=lambda: {"local": 0.00, "usd": 0.00}
    )
    walletStatus: str = "active"  # "active", "frozen", "closed"
    useAppMessaging: bool = (
        True  # True = mensajería por la app, False = mensajería por cuenta propia
    )
    vehicles: List[str] = []  # ["moto", "bicicleta", "carro", "camion", "a_pie"]
    deliveryRadius: Optional[float] = None  # Radio de entrega en km
    # Transfer payment info
    accounts: List[TransferAccount] = []
    qrPayments: List[QrPayment] = []
    phones: List[TransferPhone] = []
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class Subcategory(BaseModel):
    name: str
    imageUrl: str


class Category(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    imageUrl: str
    subcategories: List[Subcategory]
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class ProductCategory(BaseModel):
    """Product category model for organizing products by branch type."""

    id: PyObjectId = Field(alias="_id")
    branchType: str  # "restaurante", "dulceria", "tienda", "perfumeria"
    name: str
    iconIos: str  # iOS SF Symbol name
    iconWeb: str  # Material Design icon name for web
    iconAndroid: str  # Material Design icon name for Android
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class Product(BaseModel):
    id: PyObjectId = Field(alias="_id")
    branchId: PyObjectId
    name: str
    description: str
    weight: str
    price: float
    currency: str = "USD"
    image: str
    availability: bool = True
    categoryId: Optional[PyObjectId] = None
    variantListIds: List[PyObjectId] = []  # Referencias a listas globales de variantes
    createdAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class ShowcaseItem(BaseModel):
    """Ítem opcional detectado/manual dentro de una vitrina."""

    id: str
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    availability: bool = True


class Showcase(BaseModel):
    """Vitrina de una sucursal con foto principal y lista opcional de ítems."""

    id: PyObjectId = Field(alias="_id")
    branchId: PyObjectId
    title: str
    image: str
    description: Optional[str] = None
    items: Optional[List[ShowcaseItem]] = None
    isActive: bool = True
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class SmsOcr(BaseModel):
    """Modelo para datos extraídos de capturas de SMS bancarios mediante OCR."""

    id: PyObjectId = Field(alias="_id")
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
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class PaymentMethod(BaseModel):
    """
    Payment method model.

    Defines available payment methods with their commission rates,
    refund policies, and configuration.
    """

    id: Union[PyObjectId, str] = Field(alias="_id")

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
    expirationMinutes: Optional[int] = (
        None  # Time limit to complete payment (null = no limit)
    )

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
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class WalletTransaction(BaseModel):
    """Transaction record for wallet operations."""

    id: PyObjectId = Field(alias="_id")
    fromOwnerId: Optional[PyObjectId] = None  # None for external deposits
    fromOwnerType: Optional[str] = None  # "user" or "branch"
    toOwnerId: Optional[PyObjectId] = None  # None for withdrawals
    toOwnerType: Optional[str] = None  # "user" or "branch"
    amount: float
    currency: str  # "local" or "usd"
    type: str  # "transfer", "deposit", "withdrawal"
    status: str = "completed"  # "pending", "completed", "failed", "reversed"
    description: Optional[str] = None
    metadata: Optional[dict] = (
        None  # Additional info (order_id, payment_gateway_id, etc)
    )
    createdAt: datetime
    completedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class WalletBalance(BaseModel):
    """Wallet balance response model."""

    local: float = 0.00
    usd: float = 0.00


class StripePaymentLink(BaseModel):
    """Stripe Payment Link model for tracking recharge links."""

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId
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
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class BranchInvitation(BaseModel):
    """
    Código de invitación para administrar sucursales o negocios completos.
    Permite a dueños de negocios invitar usuarios con acceso temporal o indefinido.
    """

    id: PyObjectId = Field(alias="_id")
    code: str  # Código único, ej. "INV-A7B3C2-D9E4F1"

    # Tipo de invitación
    invitationType: (
        str  # "branch" (sucursal específica) o "business" (negocio completo)
    )
    branchId: Optional[PyObjectId] = None  # Específico para tipo "branch"
    businessId: PyObjectId  # Siempre presente

    # Control de acceso temporal
    accessDurationDays: Optional[int] = None  # None = indefinido, int = días de acceso

    # Metadatos
    createdBy: PyObjectId  # ID del usuario dueño del negocio
    createdAt: datetime

    # Estado del código
    status: str = "pending"  # "pending", "used", "revoked"
    usedBy: Optional[PyObjectId] = None  # ID del usuario que canjeó el código
    usedAt: Optional[datetime] = None

    # Expiración del acceso (calculado al momento del canje)
    accessExpiresAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class BusinessAccess(BaseModel):
    """
    Registro de acceso de usuario a nivel de negocio completo.
    Permite acceso automático a todas las sucursales (presentes y futuras).
    """

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId
    businessId: PyObjectId
    invitationId: PyObjectId  # Referencia al código que otorgó el acceso

    # Control temporal
    grantedAt: datetime
    expiresAt: Optional[datetime] = None  # None = indefinido

    # Estado
    isActive: bool = True
    revokedAt: Optional[datetime] = None
    revokedBy: Optional[PyObjectId] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class AndroidConfig(BaseModel):
    """Android app version configuration."""

    minVersion: str  # Minimum version allowed
    currentVersion: str  # Latest available version
    updateUrl: str  # URL to download the update
    storeUrl: str  # Google Play Store URL
    appSize: str  # App size (e.g., "25 MB")


class IosConfig(BaseModel):
    """iOS app version configuration."""

    minVersion: str  # Minimum version allowed
    currentVersion: str  # Latest available version
    storeUrl: str  # App Store URL


class MaintenanceConfig(BaseModel):
    """Maintenance mode configuration."""

    enabled: bool  # Whether maintenance mode is active
    message: Optional[str] = None  # Message to display during maintenance


class AppConfig(BaseModel):
    """
    App version and configuration management for customer app.
    Controls minimum versions, update URLs, maintenance mode, etc.
    """

    id: PyObjectId = Field(alias="_id")
    android: AndroidConfig
    ios: IosConfig
    maintenance: MaintenanceConfig
    updateMessage: Optional[str] = None  # Message to show when update is available
    changelog: Optional[str] = None  # Release notes
    releaseDate: datetime  # Date of the latest release

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class BusinessAppConfig(BaseModel):
    """
    App version and configuration management for business/merchant app.
    Controls minimum versions, update URLs, maintenance mode, etc.
    """

    id: PyObjectId = Field(alias="_id")
    android: AndroidConfig
    ios: IosConfig
    maintenance: MaintenanceConfig
    updateMessage: Optional[str] = None  # Message to show when update is available
    changelog: Optional[str] = None  # Release notes
    releaseDate: datetime  # Date of the latest release

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class FeedbackType(str):
    """Enum for feedback types."""

    BUG = "BUG"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    IMPROVEMENT = "IMPROVEMENT"


class FeedbackStatus(str):
    """Enum for feedback status."""

    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class Feedback(BaseModel):
    """
    User feedback model for bug reports, feature requests, and improvements.
    Allows users to provide feedback and ratings about the app.
    """

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId  # Reference to User
    type: str  # FeedbackType enum value
    description: str
    rating: int = Field(ge=1, le=5)  # 1-5 stars validation
    status: str = "PENDING"  # FeedbackStatus enum value
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class QuestionType(str):
    """Enum for survey question types."""

    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TEXT = "TEXT"


class SurveyQuestion(BaseModel):
    """Embedded survey question model."""

    questionId: str  # Unique ID for this question
    text: str  # Question text
    type: str  # QuestionType enum value
    options: Optional[List[str]] = None  # Only for MULTIPLE_CHOICE
    required: bool = True


class Survey(BaseModel):
    """
    Survey model with embedded questions.
    Allows admins to create surveys for user feedback.
    """

    id: PyObjectId = Field(alias="_id")
    title: str
    description: Optional[str] = None
    questions: List[SurveyQuestion]  # Embedded questions
    isActive: bool = True
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class QuestionResponse(BaseModel):
    """Embedded question response model."""

    questionId: str
    answer: str  # Selected option or free text


class SurveyResponse(BaseModel):
    """
    User response to a survey.
    Stores answers to all questions in a survey.
    """

    id: PyObjectId = Field(alias="_id")
    surveyId: PyObjectId  # Reference to Survey
    userId: PyObjectId  # Reference to User
    responses: List[QuestionResponse]  # Embedded responses
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class FavoriteCart(BaseModel):
    """
    User favorites and cart items.
    Stores product favorites and cart items for users.
    """

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId  # Reference to User
    productId: PyObjectId  # Reference to Product
    type: str  # "favorite" or "cart"
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class ClickedItem(BaseModel):
    """Embedded clicked item in search."""

    itemId: str  # Product or Business ID
    itemType: str  # "product" or "business"
    clicks: List[datetime]  # Array of click timestamps


class Search(BaseModel):
    """
    User search history with clicked items tracking.
    Stores search queries and tracks which items were clicked.
    """

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId  # Reference to User
    query: str  # Search query text
    clickedItems: List[ClickedItem] = []  # Items clicked from this search
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class ChatMessage(BaseModel):
    """
    Chat message for AI assistant conversation memory.
    Stores user and AI messages for context in conversations.
    """

    id: PyObjectId = Field(alias="_id")
    sessionId: str  # user_id from JWT
    role: str  # "user" or "assistant"
    content: str  # Message text
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class DraftOrderItem(BaseModel):
    """Item in a draft order."""

    productId: str
    name: str
    price: float
    quantity: int
    imageUrl: str


class DraftOrder(BaseModel):
    """
    Draft order created by AI assistant.
    Pending user confirmation before creating real order.
    """

    id: PyObjectId = Field(alias="_id")
    sessionId: str  # user_id from JWT
    customerId: PyObjectId  # Same as sessionId
    branchId: PyObjectId
    businessId: PyObjectId
    branchAvatar: Optional[str] = None  # Denormalized branch avatar URL
    items: List[DraftOrderItem]
    subtotal: float
    deliveryFee: float
    total: float
    currency: str = "USD"
    deliveryAddress: Optional[Dict[str, Any]] = (
        None  # Will be structured as DeliveryAddress
    )
    paymentMethodId: Optional[Union[PyObjectId, str]] = None
    status: str = (
        "pending_confirmation"  # "pending_confirmation", "confirmed", "cancelled"
    )
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    expiresAt: datetime  # Auto-expire after 1 hour

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class BranchLike(BaseModel):
    """
    User likes for branches.
    Stores branch likes for users (similar to FavoriteCart but for branches).
    """

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId  # Reference to User
    branchId: PyObjectId  # Reference to Branch
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class DeliveryZone(BaseModel):
    """Zona hexagonal H3 con configuración de precios de envío para delivery por la app."""

    id: PyObjectId = Field(alias="_id")
    h3Index: str  # H3 index at resolution 7, e.g. "872a1008fffffff"
    resolution: int = 7  # H3 resolution level
    name: Optional[str] = None  # "La Habana Centro", "Vedado", etc.

    # Pricing
    baseFee: float  # Tarifa base para entregar EN esta zona
    perKmFee: float = 50.0  # Costo adicional por km
    currency: str = "CUP"  # Moneda de los precios de envío
    surchargePercent: float = 0.0  # Recargo % (zona de alta demanda, etc.)

    # Rules
    isActive: bool = True
    minOrderAmount: Optional[float] = None  # Monto mínimo para pedir en esta zona
    maxDeliveryFee: Optional[float] = None  # Tope máximo del envío

    # Metadata
    city: Optional[str] = None
    province: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class Tutorial(BaseModel):
    """
    Tutorial model for app usage guides.
    Stores video tutorials with metadata for customer and merchant apps.
    """

    id: PyObjectId = Field(alias="_id")
    title: str  # Tutorial title
    description: str  # Tutorial description
    videoUrl: str  # S3 path to video (without signature)
    duration: int  # Video duration in seconds
    appTarget: str  # Target app: "customer", "merchant", "both"
    thumbnailUrl: Optional[str] = None  # S3 path to thumbnail image
    order: int = 0  # Display order (lower = first)
    isActive: bool = True  # Whether tutorial is active/published
    tags: List[str] = []  # Tags for categorization
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class ComboModifier(BaseModel):
    """Modificador para un producto dentro del combo (ej: sin cebolla, extra queso)."""

    name: str
    priceAdjustment: float = 0.0  # Costo adicional/descuento


class ComboOption(BaseModel):
    """Producto seleccionable dentro de un slot del combo."""

    productId: PyObjectId
    isDefault: bool = False  # Opción pre-seleccionada
    priceAdjustment: float = 0.0  # Costo extra si elige esta opción
    availableModifiers: List[ComboModifier] = []  # Modificadores permitidos


class ComboSlot(BaseModel):
    """Listado de productos a elegir (nombre libre definido por el negocio)."""

    id: str  # UUID generado
    name: str  # "Plato Fuerte", "Batidos", "Entrantes" (escrito por el negocio)
    description: Optional[str] = None

    # Productos disponibles (pueden ser de diferentes categorías)
    options: List[ComboOption]

    # Reglas de selección
    minSelections: int = 1  # Mínimo a elegir
    maxSelections: int = 1  # Máximo a elegir
    isRequired: bool = True

    displayOrder: int = 0  # Orden de visualización


class Combo(BaseModel):
    """
    Combo personalizable de productos.
    El precio se calcula sumando los productos elegidos.
    El negocio puede aplicar descuento en % o cantidad fija.
    """

    id: PyObjectId = Field(alias="_id")
    branchId: PyObjectId
    name: str
    description: str
    image: Optional[str] = None  # OPCIONAL - si no existe, frontend genera composición

    # Slots (listados de productos)
    slots: List[ComboSlot]

    # Discount (solo uno aplica)
    discountType: str = "none"  # "none" | "percentage" | "fixed"
    discountValue: float = 0.0  # Valor del descuento (% o cantidad fija)

    currency: str = "USD"

    # Metadata
    availability: bool = True
    categoryId: Optional[PyObjectId] = None  # Categoría del combo (opcional)
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class VariantOption(BaseModel):
    """Opción individual dentro de una lista de variantes."""

    id: str  # UUID generado
    name: str  # "Grande", "Extra queso", "Sin cebolla"
    priceAdjustment: float = 0.0  # Costo adicional/descuento


class VariantList(BaseModel):
    """Lista global de variantes reutilizable por negocio."""

    id: PyObjectId = Field(alias="_id")
    businessId: PyObjectId  # Pertenece al negocio (global)
    name: str  # "Tamaños", "Extras", "Ingredientes"
    description: Optional[str] = None
    options: List[VariantOption]  # Opciones disponibles
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


__all__ = [
    "User",
    "SavedAddress",
    "Business",
    "Coordinates",
    "Branch",
    "Subcategory",
    "Category",
    "ProductCategory",
    "Product",
    "ShowcaseItem",
    "Showcase",
    "SmsOcr",
    "PaymentMethod",
    "WalletTransaction",
    "WalletBalance",
    "StripePaymentLink",
    "BranchInvitation",
    "BusinessAccess",
    "AndroidConfig",
    "IosConfig",
    "MaintenanceConfig",
    "AppConfig",
    "BusinessAppConfig",
    "Feedback",
    "Survey",
    "SurveyQuestion",
    "SurveyResponse",
    "QuestionResponse",
    "FavoriteCart",
    "VariantOption",
    "VariantList",
    "ClickedItem",
    "Search",
    "ChatMessage",
    "DraftOrder",
    "DraftOrderItem",
    "BranchLike",
    "Tutorial",
    "ComboModifier",
    "ComboOption",
    "ComboSlot",
    "Combo",
]
