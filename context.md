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
| Web | `LlegoWeb` | Astro 5 + Svelte 5, SSR con `@astrojs/node` | Web pública (marketing, legales), registro de socios en `/negocios` (§15) y paneles de tutoriales/tipos de negocio; proxy GraphQL en `/api/graphql` |
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
| `delivery_persons` | `DeliveryPerson` (`approved`: acceso de chofer, §15) | `orders_repository.py:1028` |
| `partner_requests` | `PartnerRequest` (registro de socios, §15) | `partner_request_repository.py` |
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
`delivery_persons`, `order_location_updates`, `partner_requests`.

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
feedbacks, invitations, orders, partner_requests, payments, product_categories, products,
promos, promotional_videos, searches, shortcut_transfers, showcases, surveys, sync,
tutorials, users, variant_lists, wallet`. Los más grandes con diferencia son `orders`
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
equivalente REST de `require_role(..., ["admin"])`, usado por `/upload/tutorial/*`.
`require_admin_api_key` ([utils/auth.py:293](utils/auth.py:293)) es una clave estática compartida, solo para
endpoints REST de ops — **nunca para GraphQL**, porque una clave estática embebida en una
app distribuida la puede extraer cualquiera.

### Convenciones

- snake_case en Python → camelCase en GraphQL (Strawberry por defecto, sin override).
- **Dos estilos de paginación conviven**:
  - Relay (`edges` + `pageInfo`, cursores) en [schema/pagination.py](schema/pagination.py) → búsqueda y browse público.
  - Offset (`rows` + `totalCount` + `hasMore`) → listados de admin.
- Errores: `raise Exception("mensaje en español")`. No hay jerarquía de errores tipados.
- `ErrorLoggingExtension` ([schema/extensions.py:35](schema/extensions.py:35)) captura toda excepción no
  controlada, la guarda en `error_logs` y lanza un análisis con Gemini en background (que
  acaba en un push a los admins). Se salta los errores esperados de
  `EXPECTED_ERROR_PREFIXES` ([:17](schema/extensions.py:17)): hoy solo `COURIER_NOT_APPROVED`, que la
  app de mensajeros de un usuario sin aprobar recibe en cada sondeo.
- `LastSeenExtension` ([schema/extensions.py:121](schema/extensions.py:121)) escribe `users.lastSeenAt`, throttled a
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
  el pago. El mapa en vivo de la sucursal va por `deliveryLocationUpdated`
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

---

## 6. REST

`api/routes.py` agrega todos los routers sin prefijo ni dependencia de auth global.

| Router | Prefijo | Auth |
|---|---|---|
| uploads | `/upload` | JWT por cabecera; `/upload/tutorial/*` además rol `admin` |
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
`redirect_scheme=https://atacante/x?` se llevaba el token. El registro de socios de la web
(`/negocios`) ya pasa `redirect_scheme=<origen>/auth/callback`; el panel de tutoriales de
LlegoWeb aún llama a `/apple/start` sin parámetro (vuelve a `llego://`) y LlegoBusiness
Android tampoco pasa `redirect_scheme=llegobusiness`; tienen que pasarlo para volver a su
app/web.

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
  cruzar la medianoche); `temporallyOpen` sin horas abre todo el día; sin flags ni horas
  no decide.
- Pendiente de producto: el switch "Abierto hoy" de la app de negocios (`BranchStatusChip.kt`)
  manda `temporallyOpen=true` sin horas al deshacer un "Cerrado hoy", y con esta regla
  la sucursal queda abierta las 24 h de ese día. Si encenderlo debe volver al horario
  semanal, lo coherente es que la app llame a `clearBranchDailyOverride` cuando no hay
  horario especial (iOS/Android muestran `temporallyOpen` como "abierto" sin mirar horas).
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
`myDeliveredOrders`, `myDeliveryStats`, `myBranchLinkRequests`, `orderTracking`. Mutations:
`setDeliveryOnlineStatus`, `acceptOrderForPayment`, `rejectOrderForPayment`,
`acceptDelivery` (legacy), `confirmPickup`, `updateDeliveryLocation`, `confirmDelivery`,
`requestBranchLink`, `cancelBranchLinkRequest`, `linkVehicle`, `confirmCashReceived`, y
`updateOrderStatus` a `AWAITING_DELIVERY_ACCEPTANCE` cuando no lo pide staff de la
sucursal (es el "Cancelar pedido" de la app: se enruta a `rejectOrderForPayment`).

**Todas exigen mensajero aprobado** (o rol `admin`/`manager`): llaman a
`require_courier` ([services/courier_access.py:79](services/courier_access.py:79)) justo después de `require_auth`.
Si no, error cuyo mensaje empieza por `COURIER_NOT_APPROVED:` (con
`extensions.code = "COURIER_NOT_APPROVED"`). Ya **no** se crea un registro en
`delivery_persons` al primer uso: nace al aprobar la solicitud de mensajero (§15).
`orderTracking`/`order` no pasan por aquí: los protege `user_can_access_order` (el
mensajero asignado puede verlos). Detalle de la regla en §15.

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

10. **Vídeos promocionales sin comprobación de rol.** Mismo patrón que tenían los
    tutoriales: las mutations de [schema/promotional_videos/mutations.py](schema/promotional_videos/mutations.py) y
    `POST /upload/promotion/video|thumbnail` ([api/endpoints/uploads.py](api/endpoints/uploads.py)) solo piden JWT, con
    `TODO: Add admin role check`. Abierto.

11. ✅ **Resuelto — cualquier usuario autenticado podía operar como mensajero.** Las
    operaciones de chofer solo llamaban a `require_auth` y la primera le creaba un registro
    en `delivery_persons`. Ahora exigen mensajero aprobado (§7 "Chofer", §15).

12. **`confirmCashReceived` no puede confirmar nunca.** El resolver pasa el `user_id` como
    `delivery_person_id` y `confirm_cash_received` lo compara con `order.deliveryPersonId`,
    que es el `_id` del registro de `delivery_persons`
    ([services/payments_service.py:1421](services/payments_service.py:1421)): nunca coinciden y responde "No autorizado".
    Ninguna app lo usa (el efectivo se cierra con `confirmDelivery`). Abierto.

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

Excepción al estilo de mocks: los tests "Mongo real" de `tests/test_partner_requests.py`
(índice único parcial, upsert del registro de mensajero) crean una base temporal
`llego_test_partner_*` en `MONGODB_URL`, la borran al terminar y se saltan si no hay Mongo.

---

## 14. Al escribir código aquí

- Entidad nueva → `domain/`, lógica → `services/`, datos → `repositories/`, script → `scripts/`.
- Repos: importa las instancias de `repositories/__init__.py`.
- Campo nuevo en `Business`/`Branch`/`Product`/`User` → lee la sección 11 primero.
- Resolver de admin nuevo → **no olvides `require_role(jwt, info, [...])` en la primera línea**.
- Operación de chofer nueva → `require_auth` y justo después `await require_courier(info, user_id)`
  (§15), fuera del `try` para que el error llegue con su `extensions.code`.
- Colección nueva que se vaya a consultar en caliente → añádele índices en
  `clients/mongodb_client.py`.
- Entidad nueva con búsqueda semántica → replica el patrón dual Mongo+Qdrant a mano.
- Tiempo real fiable → polling, no subscriptions (sección 5). Si cambias un pedido fuera de
  `OrderService.update_status`, publica el evento de sucursal (`publish_branch_order_changed`).
- Exportar el schema: `python scripts/export_schema.py`, o `GET /graphql/schema.graphql` en vivo.

---

## 15. Registro de socios y acceso de mensajeros

Quien quiere vender en Llegó o ser mensajero lo pide en la web (`/negocios` de LlegoWeb):
inicia sesión con Google o Apple y envía una **solicitud** (`partner_requests`). El equipo
la gestiona desde el Panel Admin (sección "Solicitudes"): llama al solicitante, la marca
como contactada y la aprueba o la rechaza. **Aprobar da acceso.**

Código: [domain/partner_requests.py](domain/partner_requests.py), [repositories/partner_request_repository.py](repositories/partner_request_repository.py),
[services/partner_requests_service.py](services/partner_requests_service.py), [schema/partner_requests/](schema/partner_requests/),
[services/courier_access.py](services/courier_access.py), [services/business_approval.py](services/business_approval.py).

### Solicitudes

- Tipos `business` (vender) y `courier` (repartir). Estados `pending` → `contacted` →
  `approved` | `rejected`.
- **Una sola solicitud activa** (`pending`/`contacted`) por usuario y tipo. El servicio lo
  comprueba y el índice único parcial `idx_partner_requests_user_type_active_unique` lo
  garantiza ante envíos simultáneos. Filtra por el booleano `active` (copia de "estado
  activo") porque un `partialFilterExpression` con `$in` no existe antes de MongoDB 6.
- Tampoco se puede pedir un acceso que ya se tiene (mensajero aprobado o legado, o una
  solicitud `business` aprobada). Tras un rechazo sí se puede volver a pedir.
- El teléfono se valida y normaliza con `normalize_phone` ([utils/phone.py:75](utils/phone.py:75)): un
  número cubano de 8 dígitos en cualquier formato habitual queda `+53XXXXXXXX`; con otro
  código de país (`+`/`00`) se respeta, sin separadores; cualquier otra cosa es un error
  claro. Se guarda el email de la cuenta (no lo escribe el solicitante).
- Fechas *aware* en UTC: el repositorio marca como UTC las que Mongo devuelve sin zona,
  para que GraphQL las emita con `+00:00` (la web hace `new Date()` con ellas).

GraphQL (contrato compartido de la fase 2a):

| Operación | Auth | Qué hace |
|---|---|---|
| `submitPartnerRequest(input, jwt)` | JWT | Crea la solicitud `pending` |
| `myPartnerAccess(jwt)` | JWT | `courierApproved`, `merchantApproved` y la última solicitud de cada tipo |
| `adminPartnerRequests(status, type, limit, offset, jwt)` | admin/manager | Página `{items, total}`, de la más nueva a la más antigua (`limit` ≤ 100) |
| `adminUpdatePartnerRequest(id, status, adminNotes, jwt)` | admin/manager | Cambia el estado y aplica el acceso; guarda `reviewedAt`/`reviewedBy` |

- Lo que ve el solicitante (`submitPartnerRequest`, `myPartnerAccess`) no incluye
  `adminNotes` ni `reviewedBy` (llegan a `null`): son internos del equipo.
- `adminNotes: null` deja las notas como estaban; `""` las borra.
- Una solicitud aprobada o rechazada **no vuelve** a `pending`/`contacted`: se aprueba o se
  rechaza (pasar de rechazada a aprobada y al revés sí vale). Repetir la aprobación vuelve
  a aplicar el acceso (idempotente).
- El acceso se aplica **antes** de guardar el estado (si falla, la solicitud no cambia y
  basta con repetir), y el cambio de estado es condicional al estado leído: si otro admin
  la cambió entretanto, error "La solicitud cambió mientras la revisabas".

### Qué da aprobar

- **COURIER aprobada** → mensajero aprobado: `delivery_persons.approved = True`
  (`DeliveryPersonRepository.approve_user`, upsert por `userId`). Si no tenía registro, nace
  con el nombre y el teléfono de la solicitud; si lo tenía, solo cambia `approved`.
- **BUSINESS aprobada** → se aprueban los negocios `pending` que el usuario posee
  (`approvalStatus "approved"`, `approvedAt`, activos, sucursales reactivadas; los
  `rejected` no se tocan), y `registerBusiness`/`registerMultipleBusinesses` de ese usuario
  crean el negocio **ya aprobado** (`is_merchant_approved`: tiene una solicitud `business`
  aprobada). El resto de usuarios sigue como antes: negocio `pending` hasta aprobarlo.
- **REJECTED** no da acceso. Si la solicitud de mensajero estaba aprobada, se lo quita
  (`approved = False`). Rechazar una `business` aprobada no rechaza sus negocios (se hace
  uno a uno con `rejectBusiness`), pero los nuevos vuelven a nacer pendientes.
- `merchantApproved`/`courierApproved` de `myPartnerAccess` reflejan exactamente esto.
  `courierApproved` es el mismo criterio que las operaciones de chofer (rol incluido).

`approveBusiness`/`rejectBusiness` aceptan JWT de admin/manager (Panel Admin) además de
`adminKey` (`ADMIN_API_KEY`, se mantiene por compatibilidad y se compara en tiempo
constante). Si llega un JWT, manda el JWT.

### Acceso de mensajeros

Regla de `require_courier` ([services/courier_access.py:79](services/courier_access.py:79)), que llaman todas las
operaciones de chofer (§7):

- Registro con `approved = True` → acceso.
- Registro **sin el campo** `approved` (anterior al registro de socios) → acceso: los
  mensajeros que ya trabajaban no lo pierden.
- Registro con `approved = False` (rechazado) o sin registro → `COURIER_NOT_APPROVED: …`.
  Ya **no** se crean registros al primer uso.
- `admin`/`manager` entran por su rol. Si no tienen registro se les crea con
  `approved = False`: el acceso les dura lo que dure el rol.

`COURIER_NOT_APPROVED` no se registra en `error_logs` (§5). `adminPushCourierLocation` sigue
creando registros sintéticos (con un `userId` inventado) para simular el mapa en vivo.
El mundo E2E (`POST /e2e/world`) crea a `courier` y `courier2` ya aprobados.

Clientes: la web `/negocios` envía la solicitud y muestra su estado con
`myPartnerAccess`; el Panel Admin las gestiona; AppMensajeros debe tratar
`COURIER_NOT_APPROVED` como "cuenta pendiente de aprobación" y no como un fallo.
