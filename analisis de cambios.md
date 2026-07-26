# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 26 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 25 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 24 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 23 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 22 de Julio, 2026

### Resumen de cambios (últimas 24h)

**8 commits reales** — 7 de Ruben0304 y 1 de Fabian1820 (cherry-pick del 29 de Junio). Día muy activo: nuevo sistema de sync incremental, corrección de bug crítico de `updatedAt` que rompió toda la app GraphQL durante ~21 minutos, validación de moneda por sucursal en pedidos, y mejoras en filtrado de similitud de sucursales/productos.

---

### Área 1: Validación de moneda por sucursal y congelamiento de tasa (1 commit — Ruben0304, 12:10)

- **`fix(orders): validar moneda de pago por sucursal y congelar tasa de cambio`** — Cada sucursal cubana acepta CUP, USD o ambas con su propia tasa manual, y antes no se validaba: se podía pagar con moneda que la sucursal no acepta, la tasa se recalculaba al modificar/reenviar un pedido ya aceptado, y se podían crear productos/combos en moneda incompatible con la sucursal. Ahora la tasa de cambio se congela al momento de crear el pedido.

---

### Área 2: Filtrado de sucursales similares (2 commits — Ruben0304, 12:44 y 12:53)

- **`fix(branches): filtrar getBranchesForProduct por branchType`** — Primer fix: compara el branchType via `categoryId → ProductCategory` antes de acumular el score de similitud, evitando que un producto (ej. perfume) sugiera sucursales de otro vertical (ej. restaurante).
- **`fix(branches): filtrar similitud por categoria exacta y por tipo de sucursal`** — Ampliación inmediata: `getBranchesForProduct` ahora exige el mismo `categoryId` exacto (no solo el vertical), evitando mezclar categorías del mismo vertical (ej. Postres vs Platos principales). `getSimilarBranches` también filtra por tipos compartidos en `Branch.tipos`.

---

### Área 3: Sync incremental + cascada de isActive + moneda de sucursal (1 commit — Ruben0304, 15:22)

- **`feat(sync): sync incremental, cascada de isActive y moneda de sucursal`** — Agrega `updatedAt` a Business/Branch/Product (sellado en cada `update()`). Nueva query `syncCheckpoint` (ids activos + timestamp del servidor) y parámetro `since` (opcional, retrocompatible) en las 3 queries de sync para descargar solo lo nuevo/modificado. `approve_business`/`reject_business` ahora cascadan `isActive` a todas las sucursales del negocio (antes quedaban `isActive=true` aunque el negocio fuera rechazado). `syncProducts`/`syncImages` excluyen inactivos/no aprobados. `BranchSyncType.acceptedCurrency`/`exchangeRate` ahora se poblan correctamente (estaban declarados pero siempre quedaban `null`).

---

### Área 4: Fix crítico — updatedAt rompía toda la app GraphQL (2 commits — Ruben0304, 15:43 y 15:47)

- **`fix(schema): agregar updatedAt a BusinessType/ProductType y excluirlo en BranchType`** — El campo `updatedAt` añadido en el commit anterior rompía cualquier query que construyera `BusinessType`, `BranchType`, `ProductType` o `ScoredProductType` con `**to_strawberry_dict(...)` (TypeError: unexpected keyword argument). Afectaba prácticamente toda la app: home, búsqueda, tiendas, productos, combos, showcases, feed, AI chat, invitaciones. Fix: `BusinessType`, `ProductType` y `ScoredProductType` declaran `updatedAt`; `branch_to_dict()` excluye `updatedAt` (igual que ya hacía con `pricePositioningUpdatedAt`).
- **`docs: documentar el riesgo de agregar campos a Business/Branch/Product`** — Aviso preventivo en 3 lugares: antes de las 3 clases en `domain/models.py`, en el docstring de `to_strawberry_dict()` en `utils/serialization.py`, y en `CLAUDE.md` con el grep a correr antes de agregar un campo nuevo.

---

### Área 5: FeedProductType también faltaba updatedAt (1 commit — Ruben0304, 16:41)

- **`fix(feed): agregar updatedAt a FeedProductType`** — `FeedProductType` (feed "Para ti" de Home) se construye con `FeedProductType(**to_strawberry_dict(product), score=..., distance_m=...)` y tampoco declaraba `updatedAt`. Se escapó del fix anterior porque el grep tenía un bug en el patrón de exclusión que también excluía este tipo. Verificado con grep exhaustivo de todas las clases terminadas en ProductType/BranchType/BusinessType: `OrderPreviewProductType` y `TopProductType` usan argumentos explícitos (no unpacking) y no les afecta.

---

### Área 6: Blindar listado de pedidos y mapa en vivo del chofer (1 commit — Fabian1820, 19:16 — cherry-pick del 29 de Junio)

- **`fix(orders): blindar listado y alimentar el mapa en vivo del chofer`** — `order_to_type` ahora tolera `status`/`paymentStatus` `None` o inválidos (pedidos antiguos) con `_coerce_order_status`/`_coerce_payment_status` en lugar de romper con `.value`. El resolver `customer()` devuelve placeholder "Cliente no disponible" cuando el id quedó huérfano, en lugar de tumbar toda la query. `update_delivery_location` ahora publica en `delivery_location:{orderId}`, el canal que consume la subscription `deliveryLocationUpdated` de la app de negocios (antes `publish_delivery_location` no se llamaba desde ningún sitio y el mapa en vivo nunca recibía datos).

---

### Puede dar bateo

1. **Ventana de app completamente rota ~21 min (15:22–15:43) — confirmar si llegó a producción**: El feat(sync) añadió `updatedAt` rompiendo toda la app GraphQL, y el fix llegó 21 minutos después. Si Railway auto-deploy está activo, hubo una ventana real con todas las queries fallando en producción.

2. **`FeedProductType` detectado en segundo grep pass — posibles tipos adicionales sin cubrir**: El commit `bfedc8a` admite que el primer grep tenía un bug en el patrón de exclusión. Aunque el segundo pass fue exhaustivo, solo se puede confiar en el mensaje del commit sin correrlo localmente contra producción.

3. **`updatedAt` en documentos históricos sin el campo — posibles `NoneType` errors**: Business/Branch/Product ya existentes en MongoDB no tienen `updatedAt`. Si algún resolver o lógica downstream trata `updatedAt` como no-nulo, puede lanzar `NoneType` errors para docs históricos hasta que reciban su primer `update()`.

4. **`customer()` con placeholder — resolvers downstream pueden acceder a campos reales y fallar**: El placeholder devuelve un objeto básico. Cualquier resolver aguas abajo que acceda a campos específicos del cliente (teléfono, dirección) asumiendo datos reales lanzará `AttributeError`.

5. **Cherry-pick del 29 de Jun committeado hoy — 23 días de desfase lógico**: El commit `af590ed` fue desarrollado el 29 de Junio. Puede haber incompatibilidades lógicas con 3 semanas de cambios intermedios, especialmente con el nuevo sistema de validación de monedas añadido hoy.

6. **Cascada isActive en approve/reject_business — sucursales con isActive=false por razón propia se activan**: Si una sucursal tenía `isActive=false` independientemente del negocio (ej. cierre temporal), `approve_business` la activará junto con todas las demás del negocio.

7. **`syncCheckpoint` sin señalización de bajas — productos/sucursales desactivados persisten en catálogos offline**: El sync incremental solo trae novedades. Un producto desactivado después del último sync del cliente permanece en su catálogo offline hasta el próximo sync completo.

8. **Dos commits de branches en 8 min — confirmar coexistencia de ambos filtros**: El segundo commit amplía al primero. Verificar que `getBranchesForProduct` aplica `branchType AND categoryId` simultáneamente y no solo el último.

9. **`_coerce_order_status/_coerce_payment_status` — estados inválidos silenciados sin log/alerta**: Los pedidos con status corrompido en DB devuelven un default sin ningún log. El equipo puede no detectar datos inconsistentes hasta que causen problemas downstream.

---

## 📅 21 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 20 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 19 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

#### Seguimientos vigentes

- **Ventana de app rota ~21 min (feat sync → fix schema) — confirmar si auto-deploy la llevó a producción (Jul 22)**.
- **`updatedAt` en docs históricos sin el campo — NoneType errors posibles en Business/Branch/Product (Jul 22)**.
- **`customer()` placeholder — resolvers downstream que accedan a campos reales del cliente pueden lanzar AttributeError (Jul 22)**.
- **Cherry-pick Jun 29 (af590ed) — 23 días de desfase, verificar incompatibilidades con cambios intermedios (Jul 22)**.
- **Cascada isActive en approve/reject_business — sucursales con isActive=false por razón propia se activan con el negocio (Jul 22)**.
- **`syncCheckpoint` sin señalización de bajas — productos/sucursales desactivados persisten en catálogos offline (Jul 22)**.
- **`_coerce_order_status/_coerce_payment_status` — estados inválidos silenciados sin log/alerta (Jul 22)**.
- **Batch API — polling sin guardia de solapamiento entre corridas nocturnas (Jun 26)**.
- **Fingerprint por nombre — cambios no-nombre no detectados en índice incremental (Jun 26)**.
- **Índice incremental sin rollback — fingerprint actualizado pero doc no escrito (Jun 26)**.
- **RAG agéntico Turn 1 sin tool call — Turn 2 con contexto vacío (Jun 26)**.
- **Workers nocturnos encadenados sin aislamiento de errores (Jun 26)**.
- **`ANTHROPIC_API_KEY` no configurada en producción — servicios de IA fallarán (Jun 23)**.
- **Sync client en thread pool — pool agotado bajo alta concurrencia de streaming (Jun 23)**.
- **`max_tokens=8192` — monitorear costos Anthropic (Jun 23)**.
- **Prompts DeepSeek reutilizados en Claude — formato `suggested_product_ids` puede romperse (Jun 23)**.
- **Bypass de cuota sin audit log — abuso con cuenta privilegiada comprometida (Jun 23)**.
- **e2e test con API Anthropic real en CI — costo por PR (Jun 23)**.
- **`asyncio.Queue` sin timeout — consumer lento o cliente desconectado dejan thread corriendo (Jun 23)**.
- **Workers nocturnos coexistiendo — contención Qdrant (Jun 19)**.
- **`priceConfidence` antes de usar `priceTier` en frontend (Jun 19)**.
- **MMR-lite penaliza tiendas mono-categoría (Jun 19)**.
- **Colección `users` en Qdrant para vectores de gusto (Jun 19)**.
- **`exchangeRate` cero/ausente en posicionamiento de precios (Jun 19)**.
- **`_user_to_type()` potencial N+1 en lista de usuarios (Jun 19)**.
- **Re-embedding masivo por `TEXT_FIELDS` — costo Gemini (Jun 19)**.
- **`reindex_businesses_qdrant` puede dispararse involuntariamente (Jun 19)**.
- **Backfill con docs crudos — tipos incorrectos silenciosos (Jun 19)**.
- **`delete_by_mongo_id` requiere payload index de `mongo_id` (Jun 19)**.
- **`acceptingOrders` — retrocompatibilidad con documentos sin el campo**.
- **`dailyOverride.date` sin timezone explícita — desfase UTC vs Cuba**.
- **`setBranchDailyOverride` — sin validación de rango de horas confirmada**.
- **Threshold 0.60 → 0.45 — aumento de ruido en resultados de búsqueda**.
- **`getBranchesForProduct` — doble query Qdrant + MongoDB con top-50**.
- **`getSimilarProducts/Branches` — UUID no encontrado en Qdrant**.
- **`Especialmente para Ti` — vector promedio sin normalización explícita**.
- **Ads auth migrado a `require_role` para managers**.
- **`check_compatibility=False` en qdrant-client**.
- **Merge manual de conflictos (Jun 16) — verificar integridad**.
- **Índices en colecciones existentes — confirmar background build**.
- **`asyncio.to_thread` — pool de threads por defecto agotado bajo alta concurrencia**.
- **`get_by_ids()` en repositorios de vector search — confirmar existencia**.
- **GZip umbral 200 bytes — exclusión de binarios y presigned URLs**.
- **`minPoolSize` en Atlas tier bajo con escalado horizontal**.
- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!`.
- **Bypass de Stripe activo en producción con `isDemoStore`**.
- **Timers de `asyncio.sleep` sin cancelación en órdenes demo**.
- **`seed_demo_store.py` sin idempotencia**.
- **`isDemoStore` no debe aparecer en feed público**.
- **Timezone UTC en "Hora del Día" — desfase 5h para Cuba**.
- **Ranking sin coordenadas — confirmar fallback sin 500**.
- **"Pide de Nuevo" con token expirado — feed no debe romper**.
- **Performance ranking multi-factor — índice en `(user_id, created_at)`**.
- **`discounted_service_fee_rate` sin validación de rango**.
- **Signed URLs de S3 para videos promotores sin renovación**.
- **Race condition del descuento por video**.
- **Videos/thumbnails huérfanos en S3 en error parcial**.
- **Worker de borrado de cuentas — sin recuperación tras reinicios**.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes**.
- **URL prefirmada de APK — TTL del cache vs TTL de la firma**.
- **ADS — `ad_pricing` sin datos iniciales en producción**.
- **ADS — `approved` desacoplado del pago sin verificación**.
- **Cache TTL en proceso — inconsistencia en deploys multi-instancia**.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **19, 20 y 21 de Junio** y del **23 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). La entrada del **26 de Junio** fue eliminada el 4 de Julio al superar los 7 días. La entrada del **28 de Junio** fue eliminada el 6 de Julio al superar los 7 días. La entrada del **29 de Junio** fue eliminada el 7 de Julio al superar los 7 días. La entrada del **30 de Junio** fue eliminada el 8 de Julio al superar los 7 días. Las entradas del **1 y 2 de Julio** fueron eliminadas el 10 de Julio al superar los 7 días. La entrada del **3 de Julio** fue eliminada el 11 de Julio al superar los 7 días. Las entradas del **4 y 5 de Julio** fueron eliminadas el 13 de Julio al superar los 7 días. La entrada del **6 de Julio** fue eliminada el 14 de Julio al superar los 7 días. La entrada del **7 de Julio** fue eliminada el 15 de Julio al superar los 7 días. La entrada del **8 de Julio** fue eliminada el 17 de Julio al superar los 7 días. La entrada del **10 de Julio** fue eliminada el 18 de Julio al superar los 7 días. La entrada del **11 de Julio** fue eliminada el 19 de Julio al superar los 7 días. La entrada del **13 de Julio** fue eliminada el 21 de Julio al superar los 7 días. La entrada del **14 de Julio** fue eliminada el 22 de Julio al superar los 7 días. La entrada del **15 de Julio** fue eliminada el 23 de Julio al superar los 7 días. La entrada del **17 de Julio** fue eliminada el 25 de Julio al superar los 7 días. La entrada del **18 de Julio** fue eliminada el 26 de Julio al superar los 7 días. Anteriores eliminadas: 16, 17 y 18 de Junio, 5, 6, 7, 9, 11, 12 y 15 de Junio, y días de Mayo.
