# Llegó Backend

API de la plataforma de delivery Llegó. FastAPI + GraphQL (Strawberry) + MongoDB.

## 📖 Documentación

- **[context.md](context.md) — empieza por aquí.** Documento maestro: arquitectura, modelo
  de datos, autenticación, flujo de pedidos, pagos, trampas conocidas y bugs abiertos.
- [docs/ai-assistant-api.md](docs/ai-assistant-api.md) — contrato de la API del asistente de IA para los frontends.
- [docs/combos.md](docs/combos.md) — sistema de combos y sus campos de pricing.
- [docs/stripe-recharge.md](docs/stripe-recharge.md) — recarga internacional por Stripe Payment Links.

## 🚀 Stack

- **Framework:** FastAPI · **GraphQL:** Strawberry · **DB:** MongoDB (Motor)
- **Vectorial:** Qdrant (búsqueda semántica) · **Caché / presencia:** Redis
- **IA:** Google Gemini (embeddings, chat, OCR, KYC) y Anthropic (RAG)
- **Auth:** JWT propio, Google OAuth, Apple Sign In
- **Pagos:** efectivo, transferencia manual, QvaPay, USDT (TronDealer), Stripe, wallet interna
- **Storage:** S3 · **Push:** APNs (iOS) y FCM (Android)

## 🛠️ Instalación

Requisitos: Python 3.11+, MongoDB. Qdrant y Redis son opcionales en desarrollo.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # y rellenar
```

Variables obligatorias (sin ellas la app no arranca): `MONGODB_URL`, `GEMINI_API_KEY`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL`,
`S3_BUCKET_NAME`. El resto está documentado en [context.md](context.md), sección 2.

Seeds opcionales:

```bash
python scripts/seed_business_types.py
python scripts/seed_delivery_zones.py
python scripts/seed_product_categories.py
```

## 🚦 Ejecutar

```bash
python main.py
```

o con uvicorn:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- GraphQL: `http://localhost:8000/graphql` (GraphiQL solo si `ENVIRONMENT=development`)
- Docs REST: `http://localhost:8000/docs` (solo en development)
- Schema SDL en vivo: `http://localhost:8000/graphql/schema.graphql`

## 📡 API

**GraphQL** en `/graphql` es la superficie principal: ~24 módulos de feature bajo `schema/`.
La mayoría de resolvers reciben el token como argumento `jwt`, no por cabecera — ver
[context.md](context.md), sección 5.

**REST** (prefijos reales):

| Prefijo | Qué hace |
|---|---|
| `/upload` | Subida de imágenes |
| `/users` | Perfil de usuario |
| `/apple` | Apple Sign In (web) |
| `/kyc` | Verificación de identidad |
| `/products` | Detección de productos por imagen |
| `/stripe` | Pagos y webhook de Stripe |
| `/shortcuts` | Integración con Atajos de iOS |
| `/api/v1/webhooks` | Webhooks de QvaPay y TronDealer |
| `/api/error-logs` | Inbox de errores (admin) |
| `/api/device-tokens`, `/api/push` | Push notifications |
| `/admin` | Payouts y utilidades internas |
| `/privacy`, `/terms` | Textos legales |

## 🧪 Tests

```bash
pytest tests/ -v
```

⚠️ Hay entre 46 y 48 fallos preexistentes no relacionados (Qdrant, `JWT_SECRET` real,
QvaPay). Compara contra esa línea base, no contra cero.

## 🔧 Utilidades

```bash
python scripts/export_schema.py            # exporta SDL + introspección a scripts/
python scripts/validate_products.py        # valida catálogo
python scripts/reindex_businesses_qdrant.py
python scripts/sync_qdrant_mongo_ids.py
python scripts/cleanup_qdrant_duplicates.py
```

## 🏛️ Arquitectura

```
api/ + schema/   interfaz (REST y GraphQL)
services/        lógica de negocio
repositories/    acceso a datos (Mongo + Qdrant)
domain/          modelos Pydantic
clients/         infraestructura (Mongo, Qdrant, Gemini, S3)
core/            configuración
utils/           auth, serialización, caché, S3, rate limit
scripts/         seeds, migraciones, utilidades
tests/           pytest
```

Antes de tocar nada, lee [context.md](context.md) — en particular la sección 11, que explica por qué
añadir un campo a `Business`, `Branch`, `Product` o `User` puede romper todas las queries
en tiempo de request sin que ningún linter lo detecte.
