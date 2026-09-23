# Llegó Backend — Contexto maestro

Documento único de referencia para trabajar en este repo. Sustituye a los `.md` sueltos
que había en la raíz (Kiro specs, transcripciones de Codex, READMEs de features).

Todo lo que dice este documento está verificado contra el código con referencias
`archivo:línea`. Si algo no cuadra, **gana el código** — y corrige este archivo.

---

## 1. Qué es

API de Llegó: plataforma de delivery multi-negocio para Cuba. FastAPI + GraphQL
(Strawberry) + MongoDB, con Qdrant para búsqueda semántica y Gemini/Anthropic para
el asistente de IA.

Sirve a cinco clientes, todos en repos separados:

| App | Repo | Plataforma | Rol |
|---|---|---|---|
| Llegó (cliente) | `LlegoApk` | Android / Kotlin + Compose | Pedir |
| Llegó (cliente) | `LlegoiOS` | iOS / SwiftUI | Pedir |
| LlegoBusiness | `LlegoBusiness` | iOS / SwiftUI | Negocio: aceptar, preparar |
| AppMensajeros | `AppMensajeros` | — | Chofer: recoger, entregar |
| Panel Admin | `Panel Admin` | SwiftUI (macOS + iOS) | Operación interna |

No hay codegen automático de GraphQL desde este repo: no existe `codegen.yml` ni
`.graphqlconfig`. Cada app maneja su propio schema. `LlegoApk` en concreto tiene el
`schema.graphqls` desactualizado, y por eso su código de pagos usa JSON crudo en vez de
Apollo codegen.

---

## 2. Cómo se ejecuta

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # y rellenar
python main.py           # o: uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- GraphQL: `/graphql` (GraphiQL solo si `environment == "development"`, [main.py:170](main.py:170))
- SDL en vivo: `GET /graphql/schema` y `GET /graphql/schema.graphql` ([main.py:194](main.py:194))
- Docs REST: `/docs` — **solo en development** ([main.py:34](main.py:34))
- Health: `GET /` y `GET /health/redis` ([main.py:182](main.py:182))

Python 3.11+ (el `.venv` local es 3.12). `strawberry-graphql==0.232.0` y
`pydantic <2.11` están pineados; no los subas sin revisar.

**Deploy:** Railway, pero **no hay Procfile, Dockerfile ni railway.toml en el repo**.
El comando de arranque vive en el dashboard de Railway. Si necesitas cambiarlo, no lo
busques aquí.

### Variables de entorno

Obligatorias (sin default — la app no arranca sin ellas), [core/config.py:12](core/config.py:12), [:27](core/config.py:27), [:164](core/config.py:164):
`MONGODB_URL`, `GEMINI_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL`, `S3_BUCKET_NAME`.

El resto tiene default y está agrupado en [core/config.py](core/config.py): Qdrant (`:16`), IA y
cuotas (`:27`), cash-KYC (`:34`), feature flags de rollout (`:42`), auth (`:65`),
push APNs/FCM (`:72`), CORS (`:94`), Redis y caché (`:106`), Stripe (`:126`),
QvaPay (`:131`), TronDealer (`:147`), comisiones (`:154`), `ADMIN_API_KEY` (`:161`).

---

## 3. Arquitectura por capas

```
api/ + schema/   ← interfaz (REST y GraphQL)
services/        ← lógica de negocio
repositories/    ← acceso a datos (Mongo + Qdrant)
domain/          ← modelos Pydantic
clients/         ← infraestructura (Mongo, Qdrant, Gemini, S3)
core/            ← configuración
utils/           ← auth, serialización, caché, S3, rate limit
scripts/         ← seeds, migraciones, utilidades de un solo uso
```

Reglas:
- Entidades solo en `domain/`, nunca en la raíz.
- Lógica de negocio en `services/`, persistencia en `repositories/`.
- Importa repos desde las instancias ya exportadas en [repositories/__init__.py:59](repositories/__init__.py:59), no instancies clases nuevas.
- Scripts de un solo uso en `scripts/`.

**Convención rota hoy:** hay scripts sueltos en la raíz que deberían estar en `scripts/`:
`create_kyc_indexes.py`, `create_test_invoice.py`, `export_schema.py`,
`export_schema_direct.py`, `seed_demo_store.py`.

---

## 4. Datos

### MongoDB

Base `llego`. **La colección de negocios se llama `bussisnes`** — el typo es
intencional y hay que mantenerlo por compatibilidad ([repositories/business_repository.py:44](repositories/business_repository.py:44)).

Colecciones principales y su repo:

| Colección | Entidad | Repo |
|---|---|---|
| `users` | `User` | `user_repository.py`, `auth_repository.py` |
| `bussisnes` ⚠️ | `Business` | `business_repository.py` |
| `branches` | `Branch` | `branch_repository.py` |
| `products` | `Product` | `product_repository.py` |
| `orders` | `Order` | `orders_repository.py` |
| `delivery_persons` | `DeliveryPerson` | `orders_repository.py:884` |
| `order_location_updates` | `OrderLocationUpdate` | `orders_repository.py:1083` (TTL 24 h) |
| `branch_delivery_requests` | `BranchDeliveryRequest` | `orders_repository.py:1136` |
| `payment_attempts` | `PaymentAttempt` | `payments_attempt_repository.py` |
| `payment_methods` | `PaymentMethod` | `payment_method_repository.py` |
| `wallet_transactions` | `WalletTransaction` | `wallet_repository.py` |
| `qvapay_invoices` | `QvaPayInvoice` | `qvapay_repository.py` |
| `trondealer_wallets` | `TronDealerWallet` | `trondealer_repository.py` |
| `pending_payouts` | `PendingPayout` | `payout_repository.py` |
| `kyc_verifications` | `KycVerification` | `kyc_verification_repository.py` |
| `kyc_audit_events` | `KycAuditEvent` | `kyc_audit_event_repository.py` |
| `pagos` | `SmsOcr` (capturas OCR de SMS bancarios, **no** pagos genéricos) | `payment_repository.py` |
| `platform` | `Platform` (doc único, `_id: "platform"`) | `platform_repository.py` |

El resto (`combos`, `showcases`, `variant_lists`, `searches`, `feedbacks`, `surveys`,
`ad_campaigns`, `promo_requests`, `tutorials`, `device_tokens`, `error_logs`,
`business_access`, `branch_invitations`, `delivery_zones`, `chat_messages`…) sigue el
mismo patrón: un repo por colección en `repositories/`.

### Índices

Se crean en el arranque desde [clients/mongodb_client.py:15](clients/mongodb_client.py:15), en ~12 funciones
`_create_*_indexes()`, cada una con su propio `try/except` que solo loguea. **Un fallo
creando índices no tumba el arranque ni bloquea los demás grupos.**

Tienen índices explícitos: `orders`, `users`, `products`, `branches`, `error_logs`,
`branch_invitations`, `business_access`, `favorites_cart`, `searches`, `branch_likes`,
`chat_messages`, `delivery_zones`, `branch_delivery_requests`, `qvapay_invoices`,
`trondealer_wallets`, `pending_payouts`, `payment_methods`, `tutorials`,
`delivery_persons`, `order_location_updates`.

**No tienen ninguno**: `bussisnes`, `payment_attempts`, `kyc_verifications`, `combos`,
`showcases`, `variant_lists`, `wallet_transactions`, `promo_requests`, `ad_campaigns`.
`bussisnes` es de las colecciones más consultadas y va a `_id` pelado.

### Qdrant

Cuatro colecciones: `products`, `branches`, `businesses`, `users`
([clients/qdrant_client.py:15](clients/qdrant_client.py:15)). Los repos de business/branch/product escriben en
Mongo **y** en Qdrant en cada write (atributos `mongo_collection_name` +
`qdrant_collection_name`). No hay abstracción que garantice que no se desincronicen: si
añades búsqueda a una entidad nueva tienes que replicar el patrón a mano.

`ensure_collections_and_indexes()` es idempotente y **nunca tumba el arranque** si falla.

---

## 5. GraphQL

`Query` y `Mutation` se componen por herencia múltiple de ~24 clases por feature
([schema/schema.py:67](schema/schema.py:67), [:106](schema/schema.py:106)); `Subscription` solo de `OrderSubscription` +
`AiAssistantSubscription` ([:137](schema/schema.py:137)).

Módulos en `schema/`: `ads, ai_assistant, app_config, auth, branch_likes, branches,
business_types, businesses, categories, combos, error_logs, favorites_cart, feed,
feedbacks, invitations, orders, payments, product_categories, products, promos,
promotional_videos, searches, shortcut_transfers, showcases, surveys, sync, tutorials,
users, variant_lists, wallet`. Los más grandes con diferencia son `orders`
(24 queries / 26 mutations / 6 subscriptions) y `payments` (16 / 16).

### Autenticación — esto es lo que más sorprende

**No hay middleware de auth.** El contexto GraphQL nace con `user_id = None` y
`user_role = None` en cada request ([main.py:119](main.py:119)). Se rellena **dentro de cada
resolver**, llamando en la primera línea a `apply_optional_jwt` / `require_auth` /
`require_role` ([utils/graphql_auth.py:9](utils/graphql_auth.py:9)).

Por eso casi todos los resolvers declaran un argumento `jwt: String!`: el token viaja en
la operación, no en la cabecera. Es deliberado (sirve igual para HTTP y para WebSocket).

- JWT: HS256, **dura 30 días**, sin refresh token ([utils/auth.py:18](utils/auth.py:18), [:137](utils/auth.py:137)).
- `decode_access_token` se traga toda excepción y devuelve `None` ([utils/auth.py:162](utils/auth.py:162)).
- Roles reales: `customer`, `admin`, `manager`, `risk_admin`.
- **`role` está hardcodeado a `"customer"` en el registro** ([schema/auth/mutations.py:46](schema/auth/mutations.py:46)).
  No hay mutation para cambiarlo: los roles admin se ponen a mano en la BD.
- `require_role` se invoca a mano en 43 sitios. No hay `PermissionExtension` ni registro
  central: **si olvidas la llamada, el resolver queda abierto.**

`get_current_user_id_from_header` ([utils/auth.py:242](utils/auth.py:242)) es solo para REST.
`require_admin_api_key` ([utils/auth.py:261](utils/auth.py:261)) es una clave estática compartida, solo para
endpoints REST de ops — **nunca para GraphQL**, porque una clave estática embebida en una
app distribuida la puede extraer cualquiera.

### Convenciones

- snake_case en Python → camelCase en GraphQL (Strawberry por defecto, sin override).
- **Dos estilos de paginación conviven**:
  - Relay (`edges` + `pageInfo`, cursores) en [schema/pagination.py](schema/pagination.py) → búsqueda y browse público.
  - Offset (`rows` + `totalCount` + `hasMore`) → listados de admin.
- Errores: `raise Exception("mensaje en español")`. No hay jerarquía de errores tipados.
- `ErrorLoggingExtension` ([schema/extensions.py:27](schema/extensions.py:27)) captura toda excepción no
  controlada, la guarda en `error_logs` y lanza un análisis con Gemini en background.
- `LastSeenExtension` ([schema/extensions.py:96](schema/extensions.py:96)) escribe `users.lastSeenAt`, throttled a
  una vez por hora por usuario. Es la **única** señal de actividad que tiene el backend:
  el login no escribe nada y el JWT es stateless. El tráfico REST no pasa por aquí.

### Subscriptions — rotas con más de un worker

`OrderPubSub` ([schema/orders/subscriptions.py:26](schema/orders/subscriptions.py:26)) es un `dict` de colas en memoria
**del proceso**, con un comentario explícito de "reemplazar con Redis en producción".
Si publisher y subscriber caen en workers distintos, el evento no llega nunca.

La excepción es `couriers_presence_stream` ([:83](schema/orders/subscriptions.py:83)), que lee Redis directamente y sí
funciona multi-worker.

`order_tracking_stream` ([:172](schema/orders/subscriptions.py:172)) tiene un `TODO` en [:225](schema/orders/subscriptions.py:225): solo comprueba que
el pedido exista, **no que quien escucha sea su dueño**.

Si necesitas tiempo real fiable hoy, haz polling HTTP, no subscriptions.

---

## 6. REST

`api/routes.py` agrega todos los routers sin prefijo ni dependencia de auth global.

| Router | Prefijo | Auth |
|---|---|---|
| uploads | `/upload` | JWT por cabecera |
| apple_auth | `/apple` | Público (flujo OAuth, por diseño) |
| error_logs | `/api/error-logs` | `ADMIN_API_KEY`, salvo `POST /mobile-report` (público a propósito: intake de crasheos) |
| kyc | `/kyc` | JWT |
| device_tokens | `/api/device-tokens` | **ninguna** ⚠️ |
| push_notifications | `/api/push` | **ninguna** ⚠️ |
| users | `/users` | JWT |
| stripe | `/stripe` | Bearer manual; `/webhook` por firma de Stripe; `/config` público |
| product_detection | `/products` | JWT |
| shortcuts | `/shortcuts` | `X-API-Key` estática |
| qvapay_webhooks | `/api/v1` | HMAC-SHA256 |
| trondealer_webhooks | `/api/v1/webhooks` | HMAC-SHA256 |
| admin_payouts | `/admin` | Bearer estático (`ADMIN_API_KEY`) |
| admin_tests | `/admin` | JWT con `role == "admin"` |
| legal | — | HTML público |

`api/endpoints/qvapay_test.py` existe pero **no está montado** — router muerto.

---

## 7. Pedidos

### Estados

`OrderStatus` tiene **12** valores ([domain/orders.py:13](domain/orders.py:13)):

`pending_acceptance`, `modified_by_store`, `rejected_by_store`,
`awaiting_delivery_acceptance`, `pending_payment`, `payment_in_progress`, `accepted`,
`preparing`, `ready_for_pickup`, `on_the_way`, `delivered`, `cancelled`.

`PaymentStatus`: `pending`, `validated`, `completed`, `failed`, `cancelled` ([:33](domain/orders.py:33)).

Las transiciones válidas están en `ALLOWED_TRANSITIONS` ([domain/orders.py:389](domain/orders.py:389)).

### Flujo

1. Cliente crea → `pending_acceptance`
2. Negocio modifica → `modified_by_store` · rechaza → `rejected_by_store` · acepta → `awaiting_delivery_acceptance`
3. Cliente reenvía desde cualquiera de esos → `pending_acceptance`
4. Chofer acepta: efectivo → `accepted`; no efectivo → `pending_payment`
5. Cliente paga → `accepted`
6. Negocio: `accepted → preparing → ready_for_pickup`
7. Chofer recoge (desde `preparing` o `ready_for_pickup`) → `on_the_way`
8. Chofer entrega con código → `delivered`

### Timeout de 15 minutos

`services/order_timeout_worker.py`, cada 60 s ([clients/lifespan.py:66](clients/lifespan.py:66)). Cancela
automáticamente si vence `deadlineAt` en: `pending_acceptance`, `modified_by_store`,
`rejected_by_store`, `awaiting_delivery_acceptance`, `pending_payment`.

### Código de entrega

`deliveryVerificationCode` solo se expone al cliente dueño del pedido y solo en
`on_the_way`. El chofer **no** debe verlo: se lo dicta el cliente. Las apps de negocio y
chofer no pueden depender de ese campo.

### Qué consume cada app

**Cliente** — `myOrders`, `order`, `orderByNumber`, `orderTracking`. Mutations:
`createOrder`, `acceptOrderModifications`, `rejectOrderModifications`, `resubmitOrder`,
`cancelOrder`, `addOrderComment`, `rateOrder`. Pago (solo en `pending_payment`):
`initiateQvapayPayment`, `initiateTrondealerPayment`, `initiatePayment`,
`confirmPaymentSent`, `confirmTransferByShortcut`.

UI por estado: countdown con `deadlineAt` en los estados pre-elaboración; botones de pago
solo en `pending_payment`; `ready_for_pickup` y `on_the_way` se muestran ambos como
"En camino"; el código de entrega se muestra en `on_the_way`; calificar en `delivered`.

**Negocio** — `pendingBranchOrders`, `branchOrders`, `order`, `orderStats`. Mutations:
`acceptOrder`, `modifyOrderItems`, `rejectOrder`, `updateOrderStatus`, `markOrderReady`.
Regla: no pasar a `preparing` si es no-efectivo y `paymentStatus != completed`. Desde
`preparing` el pedido ya no es cancelable.

**Chofer** — `availableOrdersForDelivery`, `myCurrentDelivery`, `myDeliveries`,
`myDeliveryStats`, `orderTracking`. Mutations: `acceptOrderForPayment`,
`rejectOrderForPayment`, `acceptDelivery` (legacy), `confirmPickup`,
`updateDeliveryLocation`, `confirmDelivery`.

### Presencia de mensajeros

`updateDeliveryLocation` escribe en Redis (`presence:courier:{id}:loc`, TTL 45 s) y en
`DeliveryPerson.currentLocation` en Mongo. **Redis es la fuente fiable** para un mapa en
vivo; Mongo solo guarda la última posición. La lógica compartida está en
[services/courier_presence.py](services/courier_presence.py).

---

## 8. Pagos

### Métodos y por dónde van

| Método | Mutation | Servicio | Confirmación | Colecciones |
|---|---|---|---|---|
| efectivo | `initiatePayment` | `payments_service.py` | `confirmCashReceived` (chofer), con posible gate de KYC | `payment_attempts`, `wallet_transactions` |
| transferencia manual | `initiatePayment` → `AWAITING_PROOF` | `payments_service.py` | `confirmPaymentSent` → `confirmPaymentReceived`, o auto por `confirmTransferByShortcut` | `payment_attempts`, `wallet_transactions` |
| QvaPay | `initiateQvapayPayment` | `services/payments/qvapay_service.py` | webhook `POST /api/v1/webhooks/qvapay` | `qvapay_invoices`, `pending_payouts` |
| USDT (TronDealer) | `initiateTrondealerPayment` | `services/payments/trondealer_service.py` | webhook `POST /api/v1/webhooks/trondealer` | `trondealer_wallets`, `pending_payouts` |
| Stripe | `initiatePayment` | `payments_service.py` | webhook `POST /stripe/webhook` | `payment_attempts`, `wallet_transactions` |
| wallet | `initiatePayment` | `payments_service.py` | inmediata, sin webhook | `payment_attempts`, `wallet_transactions` |

**QvaPay y TronDealer se saltan por completo el sistema de `PaymentAttempt`.** No crean
documento en `payment_attempts`; mutan `orders` directamente desde el webhook. Consecuencia
práctica: `paymentAttemptsByOrder`, `activePaymentAttempt` y `adminPaymentAttempts` **no
muestran nada** para pedidos pagados por esas dos vías. Solo aparecen en
`pending_payouts` / `admin_payouts`.

Las sucursales demo (`branch.isDemoStore`) se auto-completan sin pasar por nada de esto
([services/payments_service.py:330](services/payments_service.py:330)).

### Habilitar métodos por sucursal

Dos mecanismos distintos, y hay que conocer los dos:

- La mayoría: `Branch.paymentMethodIds` ([domain/models.py:209](domain/models.py:209)), lista de IDs. La query
  `paymentMethods(branchId)` ([schema/payments/queries.py:55](schema/payments/queries.py:55)) resuelve esa lista.
- QvaPay y USDT: **booleanos dedicados en `Branch`** — `acceptsQvapay` ([:234](domain/models.py:234)) y
  `acceptsZelle` ([:235](domain/models.py:235), que además hace de interruptor de TronDealer). Se comprueban
  en las propias mutations ([schema/payments/mutations.py:600](schema/payments/mutations.py:600), [:667](schema/payments/mutations.py:667)).

**`paymentMethods` no expone `acceptsQvapay` ni `acceptsZelle`** — los clientes tienen que
leerlos del `Branch`. No existe un `acceptsUsdt`: USDT va colgado de `acceptsZelle`.

### Efectivo vs no efectivo

Dos clasificadores independientes que pueden divergir:
- `OrderService.CASH_PAYMENT_METHODS` / `NON_CASH_PAYMENT_METHODS` ([services/orders_service.py:75](services/orders_service.py:75)):
  sets estáticos, normaliza el token, cae a buscar el doc en `payment_methods`, y ante la
  duda asume **no efectivo** (conservador).
- `PaymentService` confía directamente en `PaymentMethod.method == "cash"` de la BD.

### KYC de efectivo

`services/kyc/` evalúa documento + selfie con Gemini y produce un veredicto
(`valid|invalid|needs_review|insufficient_data|error`) con `confidenceScore`.
Solo `valid` con confianza ≥ 0.85 aprueba automáticamente; 0.60–0.85 va a `needs_review`.
Todo queda en `kyc_verifications`, con auditoría en `kyc_audit_events`.

`overrideCashKycDecision` ([schema/payments/mutations.py:537](schema/payments/mutations.py:537)) permite a un humano
aprobar/rechazar/forzar reevaluación. Está protegida dos veces (en el resolver y dentro
del servicio) con `["admin", "risk_admin"]`. **Ojo:** Panel Admin deja entrar a `manager`,
que puede *ver* la cola pero recibirá error al intentar el override. Es intencional.

### Wallet

Los saldos viven **inline** en `User.wallet`, `Branch.wallet` y `Platform.wallet`, todos
`Dict[str, float]` con claves `local` y `usd`. No hay entidad `Wallet`.
`wallet_transactions` es el libro mayor.

`services/wallet_service.py` solo conoce `user` y `branch`. El wallet de plataforma se
mueve con `db.platform.update_one` crudo desde `PaymentService`
([services/payments_service.py:170](services/payments_service.py:170), [:1069](services/payments_service.py:1069), [:1703](services/payments_service.py:1703)) — fuera de las garantías de
`WalletService`.

Las operaciones son `$inc` atómicos con filtro de guarda (`wallet.{currency}: {$gte: amount}`)
para no dejar saldos negativos; **no** usan transacciones de Mongo salvo que
`MONGODB_USE_TRANSACTIONS=true`.

### Payouts

Liquidación a negocios de lo cobrado por QvaPay/TronDealer: `pending_payouts` +
`api/endpoints/admin_payouts.py` (Bearer estático). Para QvaPay con `auto_transfer` y
`qvapay_platform_pin` configurado, intenta la transferencia automática antes de marcar
confirmado.

---

## 9. IA y búsqueda

- **Embeddings e indexado**: `services/embeddings/gemini_service.py`, `qdrant_indexing_service.py`.
- **Asistente**: `services/ai_assistant_service.py` en dos fases — primero un análisis de
  intención con salida estructurada (`services/ai_models.py:AiIntentAnalysis`, tipos
  `search_products`, `search_branches`, `create_draft_order`, `request_details`,
  `general_response`), luego generación de respuesta. Expuesto por `aiChat` y por una
  subscription de streaming.
- **RAG**: `services/ai_rag_service.py`. Se usan Gemini y Anthropic (`anthropic_model`
  en config); `openai` también está en `requirements.txt`.
- **Cuotas**: `services/ai_quota_service.py`, límites `ai_free_lifetime_limit` /
  `ai_pro_monthly_limit`, con tracking anónimo por cabecera `x-device-id`.
- **Feed y ranking**: `feed_service.py`, `scoring_service.py`, `reranking_service.py`,
  `recommendation_diversity.py`, `taste_vector_service.py`, `price_positioning_service.py`.

---

## 10. Workers en background

Todos se registran en [clients/lifespan.py](clients/lifespan.py) como `asyncio.create_task`, cada uno con su
try/except propio para que un fallo no impida arrancar.

| Worker | Cadencia | Qué hace |
|---|---|---|
| `order_timeout_worker` | 60 s | Cancela pedidos con `deadlineAt` vencido ([lifespan.py:66](clients/lifespan.py:66)) |
| `access_expiration_worker` | 15 min | Revoca `business_access` e invitaciones caducadas ([:44](clients/lifespan.py:44)) |
| `account_deletion_worker` | 24 h | Borrado definitivo tras los 30 días de gracia de Apple ([:91](clients/lifespan.py:91)) |
| recomendaciones nocturnas | 24 h (tras 180 s de warmup) | Recalcula taste vectors, price positioning y complementos ([:116](clients/lifespan.py:116)) |

El nocturno **no** tiene su propio `_worker.py`: se ensambla inline en `lifespan` a partir
de tres servicios.

---

## 11. Trampas conocidas

### ⚠️ La grande: añadir un campo a un modelo de dominio rompe queries en runtime

`to_strawberry_dict` ([utils/serialization.py:26](utils/serialization.py:26)) hace `model_dump()` de **todos** los
campos, sin lista blanca. Hay **78 sitios** que hacen `SomeGraphQLType(**to_strawberry_dict(modelo))`.

Si añades un campo a `Business`, `Branch`, `Product` o `User` en `domain/models.py` y no lo
declaras también en el tipo GraphQL correspondiente, **todas** esas queries revientan con
`unexpected keyword argument` — **en tiempo de request**. `py_compile`, mypy y el linter no
lo detectan. Ya ha pasado dos veces.

Antes de añadir un campo a esos modelos:

```bash
grep -rn "BusinessType(\|BranchType(\|ProductType(\|UserType(" schema/
```

Y entonces o lo declaras en cada tipo GraphQL, o lo excluyes.

- **Branch** tiene un único sitio central: `branch_to_dict()` con su set `exclude`
  ([schema/branches/utils.py:76](schema/branches/utils.py:76)), que cubre `BranchType`/`ScoredBranchType`/`NearbyBranchType`
  de una vez.
- **Business, Product y User no tienen helper central**: hay que tocar cada call site.
- El aviso está escrito en el propio código, encima de `Business` ([domain/models.py:102](domain/models.py:102)) y
  encima de `User.lastSeenAt` ([:90](domain/models.py:90)).

### Otras

- **`_to_object_id` copiado en cada repo**, y ante un id inválido **devuelve el string
  original en vez de lanzar** ([repositories/orders_repository.py:31](repositories/orders_repository.py:31) y gemelos). Un id
  malformado se convierte en una query que no encuentra nada, no en un error.
- **Fechas naive vs aware**: 47 archivos usan `datetime.utcnow()` (naive), unos pocos usan
  `datetime.now(timezone.utc)` (aware). Restarlos entre sí lanza `TypeError`.
- **Excepciones tragadas en repositorios**: `try/except Exception` que loguea y devuelve
  `None`/`[]`/`False` por todas partes. El llamante no distingue "no existe" de "falló la BD".
- **Clases duplicadas**: `TransferAccount`, `QrPayment` y `TransferPhone` están definidas
  dos veces, en [domain/models.py:16](domain/models.py:16) (las usa `Branch`) y en [domain/platform.py:16](domain/platform.py:16)
  (las usa `Platform`), con campos distintos. Es fácil importar la equivocada.
- **IDs de tipo mixto**: `PaymentMethod.id`, `Branch.paymentMethodIds` y
  `PaymentAttempt.paymentMethodId` son `Union[PyObjectId, str]` porque algunos métodos usan
  códigos literales como `"cash"`. Un `ObjectId(...)` a ciegas revienta con esos.
- **Sin convención de borrado**: conviven flags `isActive` y `delete_one` real, sin regla de
  cuál usar ni cascada (borrar un `Branch` no limpia sus productos, combos ni showcases).

---

## 12. Bugs abiertos verificados

Todos comprobados leyendo el código, no reportados por nadie. No están arreglados.

1. **`branchTransferMoney` y `branchWithdrawMoney` lanzan `NameError` después de mover el
   dinero.** Usan `db.wallet_transactions` sin que `db` exista en ese scope
   ([schema/wallet/mutations.py:226](schema/wallet/mutations.py:226), [:286](schema/wallet/mutations.py:286)). Las otras tres mutations del mismo
   archivo sí hacen `db = get_database()` antes ([:70](schema/wallet/mutations.py:70), [:115](schema/wallet/mutations.py:115), [:160](schema/wallet/mutations.py:160)). La
   transferencia se ejecuta y el cliente recibe un error.

2. **Las recargas de wallet por Stripe no acreditan nada.**
   `WalletRepository.add_balance` ([repositories/wallet_repository.py:67](repositories/wallet_repository.py:67)) llama a
   `self._to_object_id`, que solo existe en la clase hermana `WalletTransactionRepository`
   ([:12](repositories/wallet_repository.py:12)) → `AttributeError` siempre. Y aunque se arreglara, hace
   `$inc: {"wallet.balance": ...}` cuando el esquema real de `User.wallet` es
   `{"local", "usd"}` ([domain/models.py:70](domain/models.py:70)) — crearía un campo fantasma. Los dos call
   sites están envueltos en `try/except` que solo loguea
   ([api/endpoints/stripe_payments.py:338](api/endpoints/stripe_payments.py:338), [:396](api/endpoints/stripe_payments.py:396)): **Stripe cobra y el usuario no
   ve el saldo.**

3. **Endpoints de push y device tokens sin autenticación ninguna.**
   - `GET /api/device-tokens/` lista tokens y metadatos ([api/endpoints/device_tokens.py:11](api/endpoints/device_tokens.py:11)).
   - `DELETE /api/device-tokens/cleanup-invalid` borra **todos** los tokens ([:106](api/endpoints/device_tokens.py:106)).
   - `POST /api/push/clientes` y `POST /api/push/negocios` permiten a cualquiera mandar una
     notificación a todos los dispositivos de cualquiera de las dos apps
     ([api/endpoints/push_notifications.py:54](api/endpoints/push_notifications.py:54)).

   Es el mismo agujero que se cerró en `/api/error-logs`, pero estos quedaron fuera.

4. **Los webhooks de QvaPay y TronDealer no validan el monto recibido.**
   QvaPay lee `amount_float` del cuerpo y nunca lo compara con `invoice.amount`
   ([services/payments/qvapay_service.py:214](services/payments/qvapay_service.py:214)). TronDealer es peor: el registro guarda
   `expectedAmount` ([trondealer_service.py:171](services/payments/trondealer_service.py:171)) y aun así `handle_webhook`
   ([:185](services/payments/trondealer_service.py:185)) nunca lo compara con lo recibido. **Un pago de menos confirma el pedido
   igual** y genera el payout por lo que sea que llegó.

5. **`order_tracking_stream` no verifica propiedad.** Solo comprueba que el pedido exista
   ([schema/orders/subscriptions.py:225](schema/orders/subscriptions.py:225), con `TODO` escrito). Cualquiera con un `orderId`
   puede seguir la ubicación de un pedido ajeno.

6. **`POST /payments/validate` es público y sin rate limit** ([api/routes.py:183](api/routes.py:183)):
   corre OCR de Gemini sobre imágenes subidas y puede persistir un registro de pago.

7. **Código muerto** en [api/endpoints/kyc.py:132](api/endpoints/kyc.py:132): un `return response` inalcanzable con
   `response` sin definir. Inofensivo, pero el log de finalización nunca se emite.

---

## 13. Tests

```bash
pytest tests/ -v
pytest tests/test_combo_pricing.py -v
```

**No hay `conftest.py` ni configuración de pytest** (`pytest.ini`, `pyproject.toml`,
`setup.cfg`) en ningún sitio. Los tests dependen del entorno.

Estilo dominante: `AsyncMock` + `SimpleNamespace` para mockear repos y servicios; las
funciones puras (`services/orders_utils.py::compute_fee_recommendation`,
`services/user_metrics.py`) se extraen a propósito para poder testearlas sin Mongo. Ese
es el patrón a seguir para lógica nueva.

**Hay entre 46 y 48 fallos preexistentes** no relacionados (Qdrant, `JWT_SECRET` real,
QvaPay). Compara contra esa línea base, no contra cero.

Ojo: `scripts/test_*.py` y `tests/create_qvapay_test_invoice.py` **no son tests de pytest**,
son scripts manuales.

---

## 14. Al escribir código aquí

- Entidad nueva → `domain/`, lógica → `services/`, datos → `repositories/`, script → `scripts/`.
- Repos: importa las instancias de `repositories/__init__.py`.
- Campo nuevo en `Business`/`Branch`/`Product`/`User` → lee la sección 11 primero.
- Resolver de admin nuevo → **no olvides `require_role(jwt, info, [...])` en la primera línea**.
- Colección nueva que se vaya a consultar en caliente → añádele índices en
  `clients/mongodb_client.py`.
- Entidad nueva con búsqueda semántica → replica el patrón dual Mongo+Qdrant a mano.
- Tiempo real fiable → polling, no subscriptions (sección 5).
- Exportar el schema: `python scripts/export_schema.py`, o `GET /graphql/schema.graphql` en vivo.
