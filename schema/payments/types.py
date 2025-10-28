"""GraphQL type definitions for Payment entity."""
import strawberry
from datetime import datetime


@strawberry.type
class PaymentType:
    """Tipo GraphQL para pagos procesados mediante OCR de SMS bancarios."""
    id: str
    quien_envio: str
    banco: str
    fecha: datetime
    es_mensaje_banco: bool
    cantidad_transferida: float
    numero_transferencia: str
    primeros_4_tarjeta: str
    ultimos_4_tarjeta: str
    createdAt: datetime
