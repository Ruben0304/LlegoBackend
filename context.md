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

Sirve a seis clientes, todos en repos separados:

| App | Repo | Plataforma | Rol |
|---|---|---|---|
| Llegó (cliente) | `LlegoApk` | Android / Kotlin + Compose | Pedir |
| Llegó (cliente) | `LlegoiOS` | iOS / SwiftUI (Apollo iOS) | Pedir |
| LlegoBusiness | `LlegoBussisnes` (sic) | Kotlin Multiplatform, Android + iOS (Compose Multiplatform, Apollo Kotlin 4) | Negocio: aceptar, preparar |
| AppMensajeros | `AppMensajeros` | Kotlin Multiplatform, Android + iOS | Chofer: recoger, entregar |
| Web | `LlegoWeb` | Astro 5 + Svelte 5, SSR con `@astrojs/node` | Web pública (marketing, legales) y portal de negocios (alta de negocio/sucursal, tutoriales); proxy GraphQL en `/api/graphql` |
| Panel Admin | `llegoadmin` (proyecto Xcode `Panel Admin`) | SwiftUI (macOS + iOS) | Operación interna de los fundadores |

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

Obligatorias (sin default — la app no arranca sin ellas), [core/config.py:12](core/config.py:12), [:27](core/config.py:27), [:188](core/config.py:188):
`MONGODB_URL`, `GEMINI_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_DEFAULT_REGION`, `AWS_ENDPOINT_URL`, `S3_BUCKET_NAME`.

El resto tiene default y está agrupado en [core/config.py](core/config.py): Qdrant (`:15`), IA y
cuotas (`:26`), cash-KYC (`:33`), feature flags de rollout (`:41`), auth (`:64`),
push APNs/FCM (`:72`), Apple web + `WEB_AUTH_CALLBACK_URLS` (`:85`, ver §6), CORS (`:107`),
Redis y caché (`:123`), Stripe (`:149`), QvaPay (`:154`), TronDealer (`:170`),
comisiones (`:178`), `ADMIN_API_KEY` (`:185`).

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
`ad_campaigns`, `promo_requests`, `platform_banners`, `tutorials`, `device_tokens`,
`app_config`/`business_app_config`/`courier_app_config`,
`error_logs`, `business_access`, `branch_invitations`, `delivery_zones`, `chat_messages`…) sigue el
mismo patrón: un repo por colección en `repositories/`.

### Índices

Se crean en el arranque desde [clients/mongodb_client.py:15](clients/mongodb_client.py:15), en ~12 funciones
`_create_*_indexes()`, cada una con su propio `try/except` que solo loguea. **Un fallo
creando índices no tumba el arranque ni bloquea los demás grupos.**

Tienen índices explícitos: `orders`, `users`, `products`, `branches`, `error_logs`,
`branch_invitations`, `business_access`, `favorites_cart`, `searches`, `branch_likes`,
`chat_messages`, `delivery_zones`, `branch_delivery_requests`, `qvapay_invoices`,
`trondealer_wallets`, `pending_payouts`, `payment_methods`, `tutorials`,
`delivery_persons`, `order_location_updates`, `platform_banners`.

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
feedbacks, invitations, orders, payments, platform_banners, product_categories, products, promos,
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

`get_current_user_id_from_header` ([utils/auth.py:246](utils/auth.py:246)) es solo para REST.
`require_admin_user_from_header` ([utils/auth.py:262](utils/auth.py:262)) es su variante para admins con
sesión de usuario (JWT con `role == "admin"`; 401 sin token, 403 con otro rol): el
equivalente REST de `require_role(..., ["admin"])`, usado por `/upload/tutorial/*`,
`/upload/promotion/*` y `/upload/platform-banner/image`.
`require_admin_api_key` ([utils/auth.py:293](utils/auth.py:293)) es una clave estática compartida, solo para
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

`OrderPubSub` ([schema/orders/subscriptions.py:32](schema/orders/subscriptions.py:32)) es un `dict` de colas en memoria
**del proceso**, con un comentario explícito de "reemplazar con Redis en producción".
Si publisher y subscriber caen en workers distintos, el evento no llega nunca.

La excepción es `couriers_presence_stream` ([:205](schema/orders/subscriptions.py:205)), que lee Redis directamente y sí
funciona multi-worker.

**Eventos de sucursal** (`newBranchOrder` → canal `branch:{branchId}`, `branchOrderUpdated`
→ `branch_updates:{branchId}`), para la app de negocios. Los publica
`OrderService._publish_branch_order_event` ([services/orders_service.py:2711](services/orders_service.py:2711)):

- `newBranchOrder`: al crear el pedido y cuando el cliente lo reenvía (vuelve a
  `pending_acceptance`: la tienda tiene que responder otra vez).
- `branchOrderUpdated`: en cada cambio de estado (todo lo que pasa por
  `_emit_tracking_event`: `update_status`, `mark_order_paid`, modificar/reenviar, escalado
  por timeout) y de pago (el cliente pulsa "Pagar", pagos registrados sin cambio de estado,
  y los webhooks de QvaPay/TronDealer vía `publish_branch_order_changed`, porque escriben
  el pedido directo en Mongo). Si añades otro camino que cambie un pedido fuera de
  `update_status`, publica tú también.
- Los pings de ubicación del chofer **no** publican en `branch_updates`: `updateDeliveryLocation`
  (cada ~10 s por pedido activo, AppMensajeros `MapScreen.kt`) llama a
  `_emit_tracking_event(order, publish_to_branch=False)`, porque no cambian ni el estado ni
  el pago. Tampoco mandan pushes (antes cada ping le repetía al cliente "Tu pedido está en
  camino"). El mapa en vivo de la sucursal va por `deliveryLocationUpdated`
  (`delivery_location:{orderId}`). Si añades otro caller de `_emit_tracking_event` que no
  sea un cambio de estado o de pago, pasa también `publish_to_branch=False`.
- Publicar nunca rompe ni frena la operación: solo encola, y un fallo se loguea.
- Mismo límite multi-worker que el resto: la app debe seguir refrescando por HTTP.

`orderUpdated` sigue sin publicador, así que no emite.

**Autorización.** Como en queries y mutations, cada subscription comprueba quién escucha
antes de suscribirse al canal (helpers en [:106](schema/orders/subscriptions.py:106)–[:144](schema/orders/subscriptions.py:144)). El JWT viaja en el
argumento `jwt` (el contexto WebSocket nace sin usuario; `connection_init` no se lee):

| Subscription | Quién puede escuchar |
|---|---|
| `orderTrackingStream`, `orderUpdated`, `deliveryLocationUpdated` | `OrderService.user_can_access_order`: cliente dueño, dueño/manager de la sucursal (`access_checker`), mensajero asignado, o `admin`/`manager` de plataforma |
| `newBranchOrder`, `branchOrderUpdated` | dueño/manager de esa sucursal (`access_checker.check_branch_access`) o `admin`/`manager` |
| `couriersPresenceStream` | solo `admin`/`manager`, igual que la query `adminCouriersPresence` |

**Denegar sin cerrar el stream** (`orderUpdated`, `deliveryLocationUpdated`,
`newBranchOrder`, `branchOrderUpdated`; [:148](schema/orders/subscriptions.py:148)–[:197](schema/orders/subscriptions.py:197)). Ninguna de las cuatro
se suscribe al canal si no hay permiso, pero tampoco termina el stream al momento:

- Sin credenciales (ni `jwt` ni usuario en el contexto): el stream **queda abierto sin
  emitir nada** hasta que el cliente lo cierre. Se loguea un warning al abrirlo.
- `jwt` inválido, pedido inexistente o sin acceso: el error llega tras
  `SUBSCRIPTION_DENIED_DELAY_SECONDS` (30 s, [:165](schema/orders/subscriptions.py:165)).

El motivo es la versión actual de LlegoBusiness. Abre `newBranchOrder` y
`branchOrderUpdated` (dos por sucursal) y `deliveryLocationUpdated` (en
`DriverLocationDialog`) **sin** `jwt`, y su WebSocket tampoco manda `Authorization`.
Si el servidor responde `data{errors}` + `complete` (graphql-ws) o `error`
(graphql-transport-ws), Apollo Kotlin 4 no lanza excepción: completa el flow,
`OrderSubscriptionSource` lo descarta con `mapNotNull` y
`SubscriptionManager.collectWithReconnect` (un `while (true)` que solo espera y cuenta
reintentos en el `catch`) **se vuelve a suscribir al instante**. Con un cierre
inmediato, cada dispositivo entraría en un bucle de reconexión a velocidad de RTT (dos
por sucursal), con un traceback de `strawberry.execution` por intento en el log.
`orderTrackingStream` y `couriersPresenceStream` siguen fallando al momento: ya pedían
JWT antes y sus clientes lo mandan.

Efecto en las apps de negocio que no se actualicen:

- `newBranchOrder` / `branchOrderUpdated`: sin `jwt` no reciben eventos (antes tampoco: no
  había publicador). Los pedidos les siguen llegando por las queries (polling).
- `deliveryLocationUpdated`: el diálogo de ubicación del chofer se queda sin posición
  (sin error visible). Es el precio de cerrar §12.5: antes cualquiera con un `orderId`
  seguía al chofer.

**Orden de despliegue.** Primero este backend (los `jwt` nuevos son opcionales y no
rompen ninguna operación existente); después la versión de LlegoBusiness que añade
`$jwt: String` a `NewBranchOrder.graphql`, `BranchOrderUpdated.graphql` y
`DeliveryLocationUpdated.graphql` y pasa el token de `TokenManager`. Al revés no
funciona: el backend anterior rechaza esas operaciones en la validación
(`Unknown argument 'jwt' on field 'Subscription.newBranchOrder'`). Esa versión de la app debe además esperar y contar el reintento en
`collectWithReconnect` cuando el flow termina normalmente o llega una respuesta con
errores, no solo en el `catch`.

Si necesitas tiempo real fiable hoy, haz polling HTTP, no subscriptions.

### Banners del feed (`platformBanners`)

Carrusel 16:9 que crean los admins y que LlegoiOS (`graphql/feed/GetPlatformBanners.graphql`)
y LlegoApk (`ProductFeedRepository.fetchPlatformBanners`, JSON crudo) piden con
`platformBanners(appTarget: "customer")`. Colección `platform_banners`
([domain/platform_banners.py](domain/platform_banners.py), [schema/platform_banners/](schema/platform_banners/)):

- `platformBanners(appTarget: String! = "customer")` es **pública**: activos y dentro de
  su ventana opcional `[startAt, endAt)`, ordenados por `order`. Un `appTarget`
  desconocido devuelve `[]`. `imageUrl` es la URL firmada del `imagePath`; `actionUrl` es
  `https://wa.me/<dígitos>` si hay `whatsapp` (un número cubano sale con `53`), si no el
  `link`, si no null ([services/platform_banners.py](services/platform_banners.py)). Las apps priorizan
  `branchId` (abrir la tienda) sobre `actionUrl`.
- Gestión solo `admin`: `adminPlatformBanners`, `createPlatformBanner` (sin `order` va al
  final), `updatePlatformBanner` (parcial; un null explícito borra un campo opcional),
  `setPlatformBannerActive`, `reorderPlatformBanners(ids)` (order = posición; todos de la
  misma app) y `deletePlatformBanner` (borra también la imagen, best-effort). La imagen se
  sube antes a `POST /upload/platform-banner/image` (admin, recorte 1920x1080 como las
  portadas). Panel Admin aún no tiene pantalla para esto.

### Versiones mínimas y mantenimiento de las apps

Tres queries públicas (sin JWT: las apps las consultan al arrancar, antes del login)
con la misma forma — `android`/`ios` con `minVersion` y `currentVersion`, `maintenance`
(`enabled`, `message`), `updateMessage`, `changelog`, `releaseDate` — y su mutation de
admin con actualización parcial ([schema/app_config/](schema/app_config/)):

| App | Query | Mutation | Colección (caché Redis) |
|---|---|---|---|
| Cliente | `appConfig` | `updateAppConfig` | `app_config` |
| Negocios | `businessAppConfig` | `updateBusinessAppConfig` | `business_app_config` |
| Choferes (AppMensajeros) | `courierAppConfig` | `updateCourierAppConfig` | `courier_app_config` |

Cada colección tiene un único documento. Las de cliente y negocios se crearon a mano y su
mutation falla si no existe; `courier_app_config` nace vacía, así que `courierAppConfig`
devuelve null (la app no bloquea nada) hasta que la primera `updateCourierAppConfig` crea
la config inicial (versiones `0.0.0`, sin mantenimiento) y aplica los cambios. AppMensajeros
bloquea si la versión instalada < `minVersion`, muestra mantenimiento si `enabled` y avisa
si < `currentVersion`; si la query falla, no bloquea.

---

## 6. REST

`api/routes.py` agrega todos los routers sin prefijo ni dependencia de auth global.

| Router | Prefijo | Auth |
|---|---|---|
| uploads | `/upload` | JWT por cabecera; `/upload/tutorial/*`, `/upload/promotion/*` y `/upload/platform-banner/*` además rol `admin` |
| apple_auth | `/apple` | Público (flujo OAuth, por diseño); destinos del callback en lista blanca (abajo) |
| error_logs | `/api/error-logs` | `ADMIN_API_KEY`, salvo `POST /mobile-report` (público a propósito: intake de crasheos) |
| kyc | `/kyc` | JWT |
| device_tokens | `/api/device-tokens` | `ADMIN_API_KEY` para listar y `cleanup-invalid`; `/register` y `/unregister` públicos a propósito (equivalen a las mutations públicas `registerDeviceToken`/`unregisterDeviceToken`) |
| push_notifications | `/api/push` | `ADMIN_API_KEY` (todo el router) |
| users | `/users` | JWT |
| stripe | `/stripe` | Bearer manual; `/webhook` por firma de Stripe; `/config` público |
| product_detection | `/products` | JWT |
| shortcuts | `/shortcuts` | `X-API-Key` estática |
| qvapay_webhooks | `/api/v1` | HMAC-SHA256 |
| trondealer_webhooks | `/api/v1/webhooks` | HMAC-SHA256 |
| admin_payouts | `/admin` | Bearer estático (`ADMIN_API_KEY`) |
| admin_tests | `/admin` | JWT con `role == "admin"` |
| legal | — | HTML público |
| (raíz, [api/routes.py](api/routes.py)) | `/payments/validate` | JWT por cabecera + rate limit `RATE_LIMIT_UPLOADS` (6/min por usuario) |

`api/endpoints/qvapay_test.py` existe pero **no está montado** — router muerto.

Ninguna app ni el Panel Admin llaman a `/api/push` ni a `/api/device-tokens`: las apps
registran el token por GraphQL y el panel solo usa GraphQL y `/upload/promo/*`.

### Apple Sign-In web: lista blanca de destinos

`GET /apple/start?redirect_scheme=…` guarda en el `state` a dónde redirigirá
`POST /apple/callback` con `?token=JWT`. Por eso solo acepta
([api/endpoints/apple_auth.py:27](api/endpoints/apple_auth.py:27), [:44](api/endpoints/apple_auth.py:44)):

- `llego` → `llego://auth/callback` (LlegoApk). Es también el default sin parámetro.
- `llegobusiness` → `llegobusiness://auth/callback` (LlegoBusiness Android).
- Una URL de `WEB_AUTH_CALLBACK_URLS` (separadas por comas; por defecto
  `https://llegoweb-production.up.railway.app/auth/callback`), comparada exacta salvo la
  barra final. Es la vía de la web: `/apple/start?redirect_scheme=<URL url-encoded>`.

Cualquier otro valor → 400 y no se crea `state`. Antes aceptaba cualquier esquema y
`redirect_scheme=https://atacante/x?` se llevaba el token. Ojo: hoy LlegoWeb llama a
`/apple/start` sin parámetro (vuelve a `llego://`) y LlegoBusiness Android tampoco pasa
`redirect_scheme=llegobusiness`; ambos tienen que pasarlo para volver a su app/web.

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

### Timeouts

`services/order_timeout_worker.py`, cada 60 s ([clients/lifespan.py:66](clients/lifespan.py:66)), actúa sobre
los pedidos con `deadlineAt` vencido. Plazos en `OrderService.STATUS_TIMEOUT_MINUTES`
([services/orders_service.py:79](services/orders_service.py:79)): 15 min en `pending_acceptance`,
`modified_by_store`, `rejected_by_store`, `awaiting_delivery_acceptance` y `pending_payment`;
30 min en `payment_in_progress`; 20 min en `accepted` (empezar la elaboración).
Al vencer se cancela, salvo que haya dinero de por medio (pagado o declarado como
enviado): entonces se escala a soporte (`requiresAttention`) y se borra el deadline
(`expire_order`, [:2470](services/orders_service.py:2470)).

### Pedidos programados (`scheduledFor`)

El cliente puede programar para hoy más tarde o para mañana (hora de Cuba); se valida
contra el horario de la sucursal de ese día, incluido su override diario.

- El plazo de aceptación de la tienda (`pending_acceptance`) y el resto de plazos previos
  (mensajero, pago, reenvío) **no cambian**.
- Los plazos que exigen empezar la elaboración (`accepted` y `payment_in_progress`)
  **nunca vencen antes de `scheduledFor - 30 min`**
  (`SCHEDULED_PREPARATION_LEAD_MINUTES`, [services/orders_utils.py:270](services/orders_utils.py:270)):
  `deadline = max(ahora + plazo normal, scheduledFor - 30 min)`.
- Se aplica al calcular el plazo (`_next_deadline_for_status`), en el worker (si el mínimo
  aún no llegó, corre el deadline y devuelve `"deferred"`: cubre pedidos viejos y los
  webhooks de QvaPay/TronDealer, que pasan a `accepted` sin recalcular el plazo) y en el
  `deadlineAt` expuesto por GraphQL (`order_to_type`), que es lo que usa la cuenta atrás de
  la app de negocios.
- `scheduledFor` puede llegar *aware* desde GraphQL y `deadlineAt` es UTC *naive*: se
  normalizan antes de compararlos.

### Horario de la sucursal: override diario ("solo hoy")

`Branch.schedule.temporaryStatus` lo escribe `setBranchDailyOverride`
([schema/branches/mutations.py:408](schema/branches/mutations.py:408)) desde el chip de estado de la app de
negocios, siempre con `date` = hoy. Reglas en [services/branch_hours.py](services/branch_hours.py):

- Con `date` (YYYY-MM-DD): aplica **solo ese día en hora de Cuba** (`America/Havana`).
  Sin `date` (legacy: seeds como la tienda demo, `updateBranch`): aplica indefinidamente.
- Cuando aplica: `temporallyClosed` cierra el día entero (también la cola de un turno
  nocturno de ayer); `openTime`/`closeTime` sustituyen al horario semanal ese día (pueden
  cruzar la medianoche); cualquier otra cosa no decide y manda el horario semanal.
- **"Abierto hoy" sin horas = horario normal** (decisión de producto). `temporallyOpen`
  sin `openTime`/`closeTime` ya no abre el día entero, con o sin `date`. Antes el switch
  "Abierto hoy" de la app de negocios (`BranchStatusChip.kt`), que manda
  `temporallyOpen=true` sin horas al deshacer un "Cerrado hoy", dejaba la sucursal
  abierta las 24 h. La tienda demo (seed con `temporallyOpen` legacy) sigue abierta
  porque su horario semanal ya es 00:00-23:59. La app de negocios dejará de escribir
  ese caso en la fase 2b (llamará a `clearBranchDailyOverride`).
- Como iOS/Android pintan "Abierto" con `temporallyOpen` sin mirar horas,
  `schedule_to_type` lo expone como `false` cuando el override no tiene horario especial
  (`exposed_temporally_open`), para que las apps calculen el estado con el horario
  semanal igual que el backend. Con horas se sigue exponiendo tal cual (y las apps
  siguen sin mirar esas horas: pintan "Abierto" todo el día).
- Lo usan `_is_branch_open_now` (pedido inmediato) y `_is_branch_open_at` (programado;
  aquí solo cuentan los overrides con fecha, los legacy se ignoran como antes).
- `schedule_to_type` ([schema/branches/utils.py:30](schema/branches/utils.py:30)) no expone un override con fecha
  distinta de hoy: iOS y Android leen `temporallyClosed`/`temporallyOpen` sin mirar la
  fecha.
- La mutación valida fecha y horas (las dos o ninguna, `HH:MM`) y las normaliza. Ojo:
  `updateBranch` con `schedule` reescribe `temporaryStatus` (lo borra si no lo manda).

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
Tiempo real: `newBranchOrder` y `branchOrderUpdated` (con `jwt`, ver sección 5).
Regla: no pasar a `preparing` si es no-efectivo y `paymentStatus != completed`. Desde
`preparing` el pedido ya no es cancelable.

**Chofer** — `availableOrdersForDelivery`, `myCurrentDelivery`, `myDeliveries`,
`myDeliveryStats`, `orderTracking`. Mutations: `acceptOrderForPayment`,
`rejectOrderForPayment`, `acceptDelivery` (legacy), `confirmPickup`,
`updateDeliveryLocation`, `confirmDelivery`.

### Presencia de mensajeros

`updateDeliveryLocation` escribe en Redis (`presence:courier:{id}:online` y `:loc`, TTL
45 s) y en `DeliveryPerson.currentLocation` en Mongo. **Redis es la fuente fiable** para un
mapa en vivo; Mongo solo guarda la última posición. La lógica compartida está en
[services/courier_presence.py](services/courier_presence.py).

"En línea" = la app abierta en el mapa: `availableOrdersForDelivery` (AppMensajeros la
sondea cada ~5 s) también renueva la presencia con la posición del sondeo y el pedido en
curso, si lo hay (para no pisar el `orderId` de `updateDeliveryLocation`). Por eso los
choferes libres aparecen ahora en el mapa de Panel Admin, y son los que reciben "nuevo
pedido disponible".

`latitude`/`longitude` de `availableOrdersForDelivery` son opcionales: sin GPS la app no
las manda. Sin posición real el chofer cuenta como en línea pero no se escribe `:loc` (no
sale en el mapa de Panel Admin) y, si es libre, no ve pedidos cercanos (los vinculados ven
los de sus sucursales igual). Las versiones ya publicadas de AppMensajeros sondean sin GPS
con Ciudad de México (19.4326, -99.1332): esa posición se trata como "sin posición"
(`_courier_poll_position` en [schema/orders/queries.py](schema/orders/queries.py)).

### Pushes a choferes

Audiencia `courier` en `device_tokens` ([repositories/device_token_repository.py](repositories/device_token_repository.py)):
tokens con `bundleId` que empieza por `com.llego.appmensajeros` sin distinguir mayúsculas
(iOS `com.llego.AppMensajeros`, que es también el topic de APNs; Android
`com.llego.appmensajeros`). AppMensajeros registra el token con `registerDeviceToken` al
iniciar sesión y lo da de baja con `unregisterDeviceToken` al cerrarla. Lógica en
[services/courier_push.py](services/courier_push.py); nada de esto rompe la operación que lo dispara.

- **Al chofer asignado** (`type: courier_order_update`), salvo lo que hace él mismo
  (actor `delivery`): asignación por admin (`assignDeliveryPerson`), cancelación, pago
  confirmado (`mark_order_paid`, o `update_status` de pendiente de pago a `accepted`),
  `preparing` y `ready_for_pickup`. Sale de `OrderService.update_status` y `mark_order_paid`.
  Los webhooks de QvaPay/TronDealer escriben el pedido directo y **no** avisan al chofer.
- **Al chofer que se queda sin el pedido** (`courier_order_update`): `modify_order_items`
  (el negocio cambia el pedido) y `resubmit_order` (el cliente lo reenvía) le quitan el
  chofer en el repo (`update_items` / `resubmit_order` ponen `deliveryPersonId: null`) sin
  pasar por `update_status`; `_notify_courier_unassigned` le avisa para que no vaya a
  recogerlo. Si añades otro camino que quite el chofer fuera de `update_status`, llámalo
  también.
- **"Nuevo pedido disponible"** (`type: courier_new_order`), en segundo plano, cuando un
  pedido pasa a `awaiting_delivery_acceptance` sin chofer: a los choferes en línea (Redis)
  que lo verían en `availableOrdersForDelivery` (vinculados: solo sus sucursales; libres: a
  ≤ 30 km de la tienda; sin posición conocida, se les avisa igual), salvo al que lo acaba de
  soltar (`reject_order_for_payment` lo pasa a `update_status` como
  `released_by_delivery_person_id`: el pedido ya llega sin chofer) y a los que ya tienen
  una entrega en curso (`get_delivery_person_ids_with_active_order`, mismos estados que
  `myCurrentDelivery`: la app trabaja con una entrega a la vez). No sale para la tienda
  demo ni para pedidos de recogida. Al tocarla, AppMensajeros busca el pedido entre sus
  disponibles (`order(id)` no se lo devuelve: aún no es suyo).
- Datos de la push: `type`, `orderId`, `orderNumber`, `status`. FCM usa el mismo proyecto
  de Firebase que las otras apps: la app Android `com.llego.appmensajeros` tiene que estar
  dada de alta en él (y su `google-services.json` en AppMensajeros) para que sus tokens
  sirvan.

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

**Monto del webhook.** Antes de completar nada, los dos webhooks comparan lo recibido con
lo esperado ([services/payments/webhook_amounts.py](services/payments/webhook_amounts.py)), con tolerancia de un centavo:
QvaPay contra `QvaPayInvoice.invoicedAmount` (lo facturado, que difiere de `amount` con
`QVAPAY_TEST_AMOUNT`; las facturas anteriores al campo usan `amount`) y TronDealer contra
`TronDealerWallet.expectedAmount`. Si llega menos, o el monto es ilegible: la
factura/wallet queda `underpaid` con `receivedAmount`; el pedido **no** se marca pagado ni
cambia de estado; no hay payout ni transferencia automática; y el pedido queda
`requiresAttention`, sin `deadlineAt` (el worker de timeout no lo cancela) y con una
entrada de timeline para el cliente. Resolverlo es manual (cola `ordersRequiringAttention`).
Un depósito USDT adicional sobre una wallet `underpaid` no se suma solo: vuelve a marcar
el pedido con el detalle.

Las sucursales demo (`branch.isDemoStore`) se auto-completan sin pasar por nada de esto
([services/payments_service.py:330](services/payments_service.py:330)).

### Transferencia confirmada por Atajos (SMS)

Un Atajo de iOS en el teléfono que recibe el SMS de Transfermóvil llama a
`POST /shortcuts/register-transfer` (API key estática) con `transfer_id`, `amount` y el
teléfono del pagador. `confirmTransferByShortcut` (la app iOS lo sondea cada 5 s sin
`transferId`) empareja ese registro con el pago por el teléfono del perfil o por el ID.

El teléfono del perfil es texto libre y **no se verifica**, así que
`confirm_transfer_by_shortcut` exige además: intento en CUP (el SMS no trae moneda),
monto de la transferencia ≥ total, transferencia registrada después de crear el pedido,
que ninguna otra cuenta tenga ese teléfono (solo en el camino por teléfono) y activación
compare-and-set (`activated: False`) para que una transferencia no pague dos pedidos.
Los teléfonos se comparan normalizados a 8 dígitos nacionales con
[utils/phone.py](utils/phone.py): el perfil puede tener `+53 5XXX XXXX` y el SMS `5XXXXXXX`.

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
- `OrderService.CASH_PAYMENT_METHODS` / `NON_CASH_PAYMENT_METHODS` ([services/orders_service.py:107](services/orders_service.py:107)):
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
| `order_timeout_worker` | 60 s | Cancela (o escala si hay dinero) pedidos con `deadlineAt` vencido; difiere los programados (sección 7) ([lifespan.py:66](clients/lifespan.py:66)) |
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
  ([schema/branches/utils.py:92](schema/branches/utils.py:92)), que cubre `BranchType`/`ScoredBranchType`/`NearbyBranchType`
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

## 12. Bugs verificados

Todos comprobados leyendo el código, no reportados por nadie. Los marcados ✅ se
arreglaron en la rama `fix/f1-backend-seguridad` (con tests); el resto siguen abiertos.

1. ✅ **Resuelto — `branchTransferMoney` y `branchWithdrawMoney` lanzaban `NameError`
   después de mover el dinero.** Usaban `db.wallet_transactions` sin definir `db`. Ahora
   hacen `db = get_database()` como las otras tres mutations del archivo
   ([schema/wallet/mutations.py:226](schema/wallet/mutations.py:226), [:288](schema/wallet/mutations.py:288)). Arreglo mínimo a propósito: la wallet no es
   feature del MVP (la app de negocios la tiene comentada). Sigue abierto en esas dos
   mutations que `is_manager = user_id in branch.managerIds` compara un `str` con
   `ObjectId`s, así que solo el dueño del negocio pasa la comprobación.

2. **Las recargas de wallet por Stripe no acreditan nada.**
   `WalletRepository.add_balance` ([repositories/wallet_repository.py:67](repositories/wallet_repository.py:67)) llama a
   `self._to_object_id`, que solo existe en la clase hermana `WalletTransactionRepository`
   ([:12](repositories/wallet_repository.py:12)) → `AttributeError` siempre. Y aunque se arreglara, hace
   `$inc: {"wallet.balance": ...}` cuando el esquema real de `User.wallet` es
   `{"local", "usd"}` ([domain/models.py:70](domain/models.py:70)) — crearía un campo fantasma. Los dos call
   sites están envueltos en `try/except` que solo loguea
   ([api/endpoints/stripe_payments.py:338](api/endpoints/stripe_payments.py:338), [:396](api/endpoints/stripe_payments.py:396)): **Stripe cobra y el usuario no
   ve el saldo.**

3. ✅ **Resuelto — endpoints de push y device tokens sin autenticación.** `GET
   /api/device-tokens/`, `DELETE /api/device-tokens/cleanup-invalid` (borraba **todos** los
   tokens) y todo `/api/push` (notificación a todos los dispositivos de una app) exigen
   ahora `ADMIN_API_KEY`, el mismo patrón que `/api/error-logs`
   ([api/endpoints/device_tokens.py:13](api/endpoints/device_tokens.py:13), [api/endpoints/push_notifications.py:20](api/endpoints/push_notifications.py:20)). `/register` y
   `/unregister` siguen públicos a propósito (ver §6). Ningún cliente los llamaba.

4. ✅ **Resuelto — los webhooks de QvaPay y TronDealer no validaban el monto recibido.**
   Un pago de menos confirmaba el pedido y generaba el payout por lo que llegara. Ahora la
   factura/wallet queda `underpaid`, sin pago ni payout, y el pedido `requiresAttention`
   ([services/payments/qvapay_service.py:223](services/payments/qvapay_service.py:223), [trondealer_service.py:193](services/payments/trondealer_service.py:193)). Detalle en §8
   ("Monto del webhook").

5. ✅ **Resuelto — `order_tracking_stream` no verificaba propiedad.** Cualquiera con un
   `orderId` podía seguir un pedido ajeno. Ahora usa `user_can_access_order`, y de paso se
   cerraron `orderUpdated`, `deliveryLocationUpdated`, `newBranchOrder` y
   `branchOrderUpdated` (no pedían ni JWT) y `couriersPresenceStream` (cualquier usuario veía
   a todos los mensajeros). Tabla de permisos en §5. LlegoBusiness aún no manda `jwt`:
   para que no entre en un bucle de reconexión, esas subscriptions no se cierran al
   denegar (se quedan abiertas sin emitir, o el error llega tras 30 s). Orden de
   despliegue y efecto en la app en §5 ("Denegar sin cerrar el stream").

6. ✅ **Resuelto — `POST /payments/validate` era público y sin rate limit.** Ahora exige
   JWT por cabecera y aplica `RATE_LIMIT_UPLOADS` (6/min por usuario) ([api/routes.py:185](api/routes.py:185)).
   El `key_func` del rate limit (`get_user_or_ip`, [utils/rate_limit.py:194](utils/rate_limit.py:194)) reconoce ahora
   `bearer` en minúsculas, que es lo que manda la app iOS; antes caía al límite por IP.

7. ✅ **Resuelto — código muerto en `api/endpoints/kyc.py`.** El `return` iba antes del log
   `kyc_evaluation_completed`, que nunca se emitía; ahora se asigna `response`, se loguea y
   se devuelve.

8. ✅ **Resuelto — Apple Sign-In web aceptaba cualquier `redirect_scheme`**, y
   `/apple/callback` redirigía allí con `?token=JWT` (robo de sesión con
   `redirect_scheme=https://atacante/x?`). Ahora hay lista blanca (ver §6). De paso,
   `GET /apple/callback` referenciaba `ANDROID_DEEP_LINK`, inexistente, y respondía 500.

9. ✅ **Resuelto — tutoriales sin comprobación de rol.** `createTutorial`, `updateTutorial`,
   `deleteTutorial`, `toggleTutorialActive` y `POST /upload/tutorial/*` dejaban hacerlo a
   cualquier usuario autenticado (TODO explícito). Ahora exigen rol `admin`
   (`require_role` / `require_admin_user_from_header`). La web de tutoriales necesita una
   cuenta con `role: "admin"` en la BD.

10. ✅ **Resuelto — vídeos promocionales sin comprobación de rol.** Mismo agujero que
    tenían los tutoriales: `createPromotionalVideo`, `updatePromotionalVideo`,
    `deletePromotionalVideo`, `togglePromotionalVideoActive`
    ([schema/promotional_videos/mutations.py](schema/promotional_videos/mutations.py)) y
    `POST /upload/promotion/video|thumbnail` ([api/endpoints/uploads.py](api/endpoints/uploads.py)) solo pedían JWT
    (`TODO: Add admin role check`). Ahora exigen rol `admin` (`require_role` /
    `require_admin_user_from_header`), con tests en
    `tests/test_promotional_videos_admin_only.py` (rama `feat/f2a-backend-mensajeros`).
    Ningún cliente las usaba aún.

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
- Tiempo real fiable → polling, no subscriptions (sección 5). Si cambias un pedido fuera de
  `OrderService.update_status`, publica el evento de sucursal (`publish_branch_order_changed`).
- Exportar el schema: `python scripts/export_schema.py`, o `GET /graphql/schema.graphql` en vivo.
