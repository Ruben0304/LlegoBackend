"""Service for detecting products from images using Gemini Vision."""

from __future__ import annotations

from typing import List

from google.genai import types as genai_types
from pydantic import BaseModel

from clients.gemini_client import get_gemini_client
from core.config import settings

# =============================================================================
# Response Models
# =============================================================================


class DetectedProduct(BaseModel):
    """A single product detected from an image."""

    name: str
    description: str
    price: float = 0.0
    currency: str = "USD"
    weight: str = ""


class DetectedProductList(BaseModel):
    """List of products detected from an image."""

    products: List[DetectedProduct]


# =============================================================================
# System Instructions
# =============================================================================

SHOWCASE_SYSTEM_INSTRUCTION = """Eres un asistente experto en identificar productos a partir de fotos de vitrinas, estantes, mesas o exhibidores de negocios locales.

Tu tarea es analizar la imagen y detectar CADA producto individual visible.

Reglas importantes:
- Cada variante de un producto es un producto separado. NUNCA agrupes variantes bajo un solo producto. Incluye en el nombre del producto lo que lo diferencia de las demás variantes.
- Si ves agregados, extras o complementos (como "Extra queso", "Salsa adicional"), cada uno es un producto separado.
- Si ves etiquetas de precio, pizarras con precios o cualquier indicación de precio visible, extrae el precio. Si no hay precio visible, usa 0.0.
- Genera una descripción breve y útil basada en lo que ves del producto (color, tamaño, presentación, ingredientes visibles).
- Para el peso, solo inclúyelo si es visible en el empaque o etiqueta. Si no, deja el campo vacío.
- Para la moneda, usa "USD" por defecto a menos que veas otra moneda indicada.
- No inventes productos que no se ven en la imagen.

Ejemplos de cómo separar variantes en distintos contextos:

Perfumería: Si ves un perfume Sauvage de 60ml y otro de 100ml, son 2 productos:
  - "Dior Sauvage 60ml" y "Dior Sauvage 100ml". Incluye el tamaño/volumen en el nombre.

Supermercado: Si ves Coca-Cola en lata de 355ml y en botella de 1.5L, son 2 productos:
  - "Coca-Cola Lata 355ml" y "Coca-Cola Botella 1.5L". Incluye la presentación y volumen.

Panadería/Dulcería: Si ves tortas de chocolate y de vainilla, son 2 productos:
  - "Torta de Chocolate" y "Torta de Vainilla". Incluye el sabor en el nombre.

Restaurante/Comida: Si ves pizza de queso y pizza de jamón, son 2 productos:
  - "Pizza de Queso" y "Pizza de Jamón". Incluye el tipo/sabor en el nombre.

Ropa/Calzado: Si ves una camiseta talla M y otra talla L del mismo modelo, son 2 productos:
  - "Camiseta Nike Dri-Fit Talla M" y "Camiseta Nike Dri-Fit Talla L". Incluye la talla.

Electrónica: Si ves un iPhone de 128GB y otro de 256GB, son 2 productos:
  - "iPhone 15 128GB" y "iPhone 15 256GB". Incluye la capacidad.

Bebidas: Si ves un café americano y un café con leche, son 2 productos:
  - "Café Americano" y "Café con Leche". Incluye el tipo de preparación.

En resumen: cualquier diferencia en tamaño, volumen, peso, sabor, color, talla, capacidad, presentación o tipo hace que sea un producto separado con esa diferencia reflejada en el nombre."""

MENU_SYSTEM_INSTRUCTION = """Eres un asistente experto en leer menús, cartas de restaurantes y listas de precios a partir de fotos.

Tu tarea es analizar la imagen del menú y extraer CADA producto listado con su precio.

Reglas importantes:
- Cada variante de un producto es un producto separado. NUNCA agrupes variantes bajo un solo producto. Incluye en el nombre lo que lo diferencia.
- Si hay una sección de agregados, extras o complementos (como "Extras: Queso $0.50, Salsa $0.30"), cada agregado es un producto separado.
- Extrae el precio exacto que aparece en el menú. Un menú siempre debe tener precios.
- La descripción debe incluir los ingredientes o detalles que aparezcan en el menú para ese producto.
- Para el peso, solo inclúyelo si aparece en el menú. Si no, deja el campo vacío.
- Para la moneda, usa "USD" por defecto a menos que el menú indique otra moneda (CUP, EUR, etc.).
- No inventes productos que no aparecen en el menú.
- Lee el menú completo, incluyendo bebidas, postres y cualquier sección adicional.

Ejemplos de cómo separar variantes:

Si el menú dice "Pizza: Queso $5, Jamón $6, Pepperoni $7", son 3 productos:
  - "Pizza de Queso" ($5), "Pizza de Jamón" ($6), "Pizza de Pepperoni" ($7).

Si el menú dice "Jugo Natural: Pequeño $2, Mediano $3, Grande $4", son 3 productos:
  - "Jugo Natural Pequeño" ($2), "Jugo Natural Mediano" ($3), "Jugo Natural Grande" ($4).

Si el menú dice "Perfume Sauvage: 60ml $80, 100ml $120", son 2 productos:
  - "Perfume Sauvage 60ml" ($80), "Perfume Sauvage 100ml" ($120).

Si el menú dice "Café: Americano $1.50, Con Leche $2, Capuchino $2.50", son 3 productos:
  - "Café Americano" ($1.50), "Café con Leche" ($2), "Capuchino" ($2.50).

Si hay sección de extras: "Extras: Queso extra $0.50, Tocineta $1, Salsa especial $0.30", son 3 productos:
  - "Extra Queso" ($0.50), "Extra Tocineta" ($1), "Extra Salsa Especial" ($0.30).

En resumen: cualquier diferencia en tamaño, sabor, tipo, presentación o volumen hace que sea un producto separado con esa diferencia reflejada en el nombre."""


# =============================================================================
# Detection Functions
# =============================================================================


async def detect_from_showcase(
    file_bytes: bytes,
    content_type: str,
) -> DetectedProductList:
    """
    Detect products from a showcase/shelf/display photo.

    Args:
        file_bytes: Raw bytes of the uploaded image.
        content_type: MIME type of the image.

    Returns:
        DetectedProductList with all detected products.
    """
    client = get_gemini_client()

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=[
            genai_types.Part.from_bytes(data=file_bytes, mime_type=content_type),
        ],
        config=genai_types.GenerateContentConfig(
            system_instruction=SHOWCASE_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=DetectedProductList,
            temperature=0.2,
        ),
    )

    return DetectedProductList.model_validate_json(response.text)


async def detect_from_menu(
    file_bytes: bytes,
    content_type: str,
) -> DetectedProductList:
    """
    Detect products from a menu/price list photo.

    Args:
        file_bytes: Raw bytes of the uploaded image.
        content_type: MIME type of the image.

    Returns:
        DetectedProductList with all detected products.
    """
    client = get_gemini_client()

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=[
            genai_types.Part.from_bytes(data=file_bytes, mime_type=content_type),
        ],
        config=genai_types.GenerateContentConfig(
            system_instruction=MENU_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=DetectedProductList,
            temperature=0.1,
        ),
    )

    return DetectedProductList.model_validate_json(response.text)
