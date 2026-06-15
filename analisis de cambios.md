# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 15 de Junio, 2026

### Resumen de cambios (últimas 24h)

**1 commit funcional** de Claude (session) — optimizaciones de performance para conexiones lentas y escala: event loop desbloqueado en búsquedas (Gemini en thread vía `asyncio.to_thread`), N+1 eliminado en resolvers de vector search (batch `get_by_ids()`), pool y timeouts de MongoDB configurados, cuatro índices de performance añadidos y umbral GZip bajado de 500 a 200 bytes.

---

### Área 1: Performance de búsqueda y acceso a base de datos (1 commit — Claude, Jun 14 15:00)

- **`perf: optimize search path and DB access for slow connections and scale`** — Cinco optimizaciones simultáneas:
  - **Event loop desbloqueado**: la llamada síncrona a Gemini para embeddings ahora corre en thread separado vía `asyncio.to_thread` en `vector_search_service` y repositorios de productos/branches/negocios. Las búsquedas concurrentes dejan de serializarse.
  - **N+1 eliminado en vector search**: reemplaza loop de `get_by_id()` individual por `get_by_ids()` batch (hasta 200 hits de Qdrant en una sola query MongoDB).
  - **Pool y timeouts de MongoDB configurados**: `maxPoolSize`, `minPoolSize`, `serverSelectionTimeoutMS`, `connectTimeoutMS` y `socketTimeoutMS` ahora tienen valores explícitos para alta concurrencia.
  - **Índices de performance añadidos**: `products.availability`, `branches.tipos`, `payment_methods.code` y text index en `tutorials`. Evitan full collection scans en queries frecuentes.
  - **GZip `minimum_size` bajado 500 → 200 bytes**: comprime más respuestas pequeñas, reduciendo payload de respuestas de tamaño medio.

---

### Puede dar bateo

1. **`asyncio.to_thread` — pool de threads por defecto agotado bajo alta concurrencia**: El executor por defecto de asyncio usa `min(32, os.cpu_count() + 4)` threads. Con muchas búsquedas concurrentes y latencia alta de Gemini, las llamadas se encolarán. Confirmar que el número de workers es suficiente o configurar un `ThreadPoolExecutor` explícito.

2. **`get_by_ids()` — puede no estar implementado en todos los repositorios**: Si alguno de los repositorios de productos, branches o negocios no tiene `get_by_ids()`, el resolver romperá con `AttributeError` en producción sin degradación elegante.

3. **Construcción de índices en colecciones con datos existentes**: En MongoDB ≤5.0, `createIndex` es bloqueante por defecto. Si los índices se crearon sobre colecciones grandes sin opción `background`, las escrituras pudieron quedar bloqueadas durante la construcción. Confirmar que se usó `background=True` o que se ejecutó en horario de baja carga.

4. **GZip sobre respuestas binarias con umbral rebajado**: Al bajar de 500 a 200 bytes, más tipos de respuesta pasan el umbral. Confirmar que el middleware excluye `Content-Type: application/octet-stream`, imágenes y redirects 302 de presigned URLs de S3.

5. **`minPoolSize` en instancias idle con Atlas M0/M2**: Cada pod mantendrá al menos `minPoolSize` conexiones abiertas aunque esté inactivo. En Atlas tiers con límite bajo de conexiones y despliegue multi-instancia, pods idle pueden agotar el pool global. Confirmar que `minPoolSize` es 0 o muy cercano a 0.

---

#### Seguimientos vigentes

- **`apiRequest success:false` — monitorear regresiones post-deploy (SunCarWeb)**: El fix global puede descubrir errores silenciados. Cualquier operación que antes mostraba éxito sin verificar puede ahora romper con toast de error.
- **`showContableFields` en MaterialForm (SunCarWeb)**: Confirmar valor por defecto y que otros usos de `MaterialForm` no perdieron campos contables.
- **`costo` y `material_id` en tipo `Material` (SunCarWeb)**: Confirmar que los endpoints del catálogo devuelven estos campos.
- **Wallet historial por miembro — filtros params (SunCarWeb)**: Confirmar que el backend acepta tipo, fechas y búsqueda en el endpoint de historial por miembro.
- **Excel Fichas de Costo sin cota de registros (SunCarWeb)**: La exportación ignora la paginación; con catálogos grandes puede saturar memoria del navegador.
- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!` en el código fuente. Rotar o desactivar la cuenta tras la aprobación del App Store.
- **Bypass de Stripe activo en producción**: Si `isDemoStore` se activa por error en una branch real, órdenes reales quedarán marcadas como pagadas sin cobro. Agregar doble guarda.
- **Timers de `asyncio.sleep` sin cancelación**: Las tareas de auto-progreso de órdenes demo siguen vivas aunque la orden sea cancelada. Bajo carga, pueden acumularse tareas huérfanas.
- **`seed_demo_store.py` sin idempotencia**: Ejecutarlo de nuevo creará duplicados en producción.
- **`isDemoStore` no debe aparecer en feed público**.
- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) ven el tramo desfasado 5h.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar que el backend aplica la misma convención.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` con params `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador correspondiente.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.
- **Campos de cambio real (SunCarWeb)**: `cambio_real_monto`, `cambio_real_moneda`, `cambio_real_tasa` en `/pagos-ventas/`.
- **Endpoint lazy load obras terminadas (SunCarWeb)**: `GET /obras-terminadas/oferta/{id}/facturas-cliente` — confirmar que existe.
- **Endpoints de notificaciones SunCarWeb**: `GET /mis-notificaciones` con `{ success, data, total }`, filtro bulk por tipo, `dias_alerta` y `link_cliente`.
- **`GET /inventario/stock-historico`**: Confirmar que existe y acepta params de almacén, material y fecha.
- **Agregados solicitudes-ventas**: Confirmar `total_cobrado`, `total_pendiente`, `total_sin_descuento`, `total_con_aumento`, `aumento_monto` en endpoints.
- **`updateSolicitudTransferencia` — validación de estado en backend**.
- **Búsqueda por `numero_serie` (SunCarWeb)**.
- **`stock_disponible_actual` — consistencia entre endpoints**.
- **Excel export de facturas sin cota de registros (SunCarWeb)**.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**.
- **Parsing UTC→local en otras tablas (SunCarWeb)**.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**: Confirmar que POST `/ponderar-costo` incluye `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb)**: Confirmar params `material_id + almacen_id`.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb)**.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**.
- **`discounted_service_fee_rate` sin validación de rango**: Solo valores entre 0 y 1.
- **Signed URLs de S3 para videos promotores sin renovación**.
- **Race condition del descuento por video**.
- **Videos/thumbnails huérfanos en S3 en error parcial**.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb)**.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb)**.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb)**.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**.
- **Endpoint cumpleaños de la semana (SunCarWeb)**.
- **Endpoint contador de instalaciones solares (SunCarWeb)**.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb)**.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb)**.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb)**.
- **Rebrand paleta — componentes con clases hardcoded (SunCarWeb)**.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente (SunCarWeb)**.
- **Worker de borrado de cuentas — sin recuperación tras reinicios**: Confirmar que al arrancar se procesan las cuentas ya vencidas inmediatamente.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes**: Confirmar manejo de `null`/campo ausente (`$exists` / `is not None`).
- **URL prefirmada de APK — TTL del cache vs TTL de la firma**: Confirmar que `cache_ttl < presigned_url_ttl`.
- **ADS — `ad_pricing` sin datos iniciales en producción**: Confirmar que la colección tiene al menos un precio base seedeado.
- **ADS — `approved` desacoplado del pago sin verificación**: Agregar validación de pago en la mutation de aprobación.
- **Cache TTL en proceso — inconsistencia en deploys multi-instancia**: Feeds inconsistentes entre pods durante 2-5 min de TTL.
- **`chore` auth/rate-limit/admin-payouts sin auditoría detallada**: Revisar diff completo del commit agrupado.
- **`asyncio.to_thread` — pool de threads por defecto (nuevo)**: Confirmar que el executor tiene capacidad suficiente para picos de búsquedas concurrentes. Considerar `ThreadPoolExecutor` explícito.
- **`get_by_ids()` en repositorios de vector search — confirmar existencia (nuevo)**: Si falta en algún repositorio, el resolver rompe con `AttributeError` en producción sin degradación elegante.
- **Índices de MongoDB — construcción sin bloquear escrituras (nuevo)**: Confirmar que se usó opción `background` o que se ejecutó en horario de baja carga sobre colecciones existentes.
- **GZip umbral 200 bytes — exclusión de binarios y presigned URLs (nuevo)**: Confirmar que el middleware excluye `application/octet-stream` y redirects 302 de S3 (agravado ahora que el umbral bajó).
- **`minPoolSize` en Atlas tier bajo con escalado horizontal (nuevo)**: Confirmar que `minPoolSize` es 0 o cercano a 0 para evitar agotar el pool de conexiones en despliegues multi-instancia.

---

## 📅 12 de Junio, 2026

### Resumen de cambios (últimas 24h)

**15 commits** de Ruben0304 — día de altísima actividad: sistema completo de campañas de anuncios de pago en el feed (ADS con `AdCampaign`, creativo como foto, moderación admin), 3 mejoras críticas de performance que reducen el feed de ~12s a ~200ms (cache TTL en proceso, eliminación de llamadas S3 bloqueantes, GZip + DataLoader), sección "Explora otras opciones" con infinite scroll, fixes en "Pide de Nuevo" y correcciones de firma S3.

---

### Área 1: Sistema ADS — campañas de visibilidad en el feed (3 commits)

- **`feat(ads): backend de campañas de visibilidad en el feed`** (17:14) — Nueva línea de monetización: los negocios pagan tarifa fija para aparecer en el feed con un creativo. Modelos: `AdCampaign`, `CreativeSpec`, `AdPricing`. Colecciones `ad_campaigns`, `ad_pricing`. Service: quote de precio, compra por wallet, moderación admin y selección para el feed. Schema GraphQL completo con queries (`adPricing`, `myAdCampaigns`, `pendingAdCampaigns`) y mutations (crear/actualizar/eliminar/comprar/pausar, aprobar/rechazar admin, `trackImpression/Click`). Pago por wallet funcional; Stripe/CUP quedan en `pending_payment`.
- **`feat(ads): mostrar campañas aunque estén pendientes de pago`** (18:40) — Incluye `pending_payment` y `pending_review` además de `active` en el query del feed. Los negocios ven su creativo activo desde que lo crean, sin esperar pago ni revisión admin. Excluye `draft`, `paused`, `rejected`, `ended`.
- **`feat(ads): creativo como foto exportada + booleano approved`** (19:30) — Reemplaza el `CreativeSpec` JSON declarativo por una sola foto exportada (`creativeImagePath`, subida vía `/upload/ad-campaign/creative`). Visibilidad controlada por booleano `approved` (puesto por el admin). Feed devuelve `imageUrl + ctaDeeplink`.

---

### Área 2: Performance del feed (3 commits)

- **`perf: eliminate blocking S3/DB calls from image URL resolvers`** (14:42) — Boto3 cacheado como singleton. `generate_image_variant_url_with_fallback` reemplazado por `get_public_image_variant_url` (crypto local). Resolvers async de avatar eliminados. Resultado: feed ~2.5s → ~200ms.
- **`perf: add in-process TTL cache for heavy feed queries`** (15:32) — `InMemoryTTLCache` en `utils/cache.py`. Cachea `get_branch_ids_by_tipo` (5 min), `_build_recent_popularity_scores` (2 min), `get_feed_products` (2 min).
- **`perf: reduce payload size and N+1 queries`** (15:41) — GZip middleware (`min_size=500`): feed ~150KB → ~30KB. Paginación en `allCombos`. DataLoader `branch_loader` en combo resolver. Cache de precios en `_compute_starting_base_price`.

---

### Área 3: Feed — infinite scroll, contexto situacional y sección Explorar (4 commits)

- **`feat(feed): infinite scroll por páginas, contexto situacional`** (16:11) — Parámetro `page` en `get_feed`. `has_more: bool` en `FeedResponse`. Variantes fin de semana y madrugada.
- **`feat(feed): títulos creativos para secciones repetidas en páginas 2+`** (16:17).
- **`feat: add Explora otras opciones vertical infinite-scroll section`** (16:31) — Nueva sección "catch-all" con todos los productos no surfaceados, puntuados por popularidad/frescura/proximidad. Parámetro `explorar_page`.
- **`fix(feed): explorar falls back to full catalog when all products are already shown`** (16:36).

---

### Área 4: Fixes y chore (5 commits)

- **`fix(feed): pide de nuevo muestra cualquier pedido`** (16:14) — Excluye únicamente cancelados.
- **`fix(feed): pide de nuevo incluye también pedidos cancelados`** (16:15) — Ajuste inmediato: incluso cancelados se incluyen.
- **`fix(s3): add expiration param to get_public_image_variant_url`** (18:26).
- **`fix(s3): add expiration param to get_public_url`** (18:34).
- **`chore: commit pending changes (auth, rate limit, admin payouts, test suites)`** (16:38) — Commit agrupado sin descripción individual.

---

### Puede dar bateo

1. **ADS — `approved` desacoplado del pago**: El admin puede aprobar un anuncio sin que el negocio haya pagado. Si la mutation de aprobación no verifica el estado de pago, anuncios no pagados aparecerán en el feed.
2. **Feed muestra `pending_payment` y `pending_review`**: Si el filtro por `business_id` falla, todos los usuarios verían anuncios no moderados.
3. **`/upload/ad-campaign/creative` — validación de archivo sin confirmar**: Confirmar que el endpoint valida tipo MIME y tamaño máximo.
4. **`ad_pricing` sin datos iniciales en producción**: Si la colección está vacía, los negocios no pueden cotizar ni crear campañas.
5. **Cache TTL en proceso — deploys multi-instancia**: Cada instancia tiene su propio cache en memoria. Con balanceador de carga, los usuarios pueden ver respuestas inconsistentes durante el TTL.
6. **GZip sobre respuestas binarias**: Confirmar que el middleware no afecta `application/octet-stream` ni redirects 302.
7. **`explorar_has_more` en el fallback**: Confirmar que cuando `explorar` usa el catálogo completo como fallback, setea `explorar_has_more=False` correctamente.
8. **Dos commits contradictorios en "Pide de Nuevo"** (16:14 excluye cancelados → 16:15 los incluye): Confirmar cuál es el comportamiento final deseado.
9. **`chore` sin detalle en cambios sensibles**: Auth, rate limit y admin payouts agrupados sin descripción individual. Difícil de auditar y revertir selectivamente.

---

#### Seguimientos vigentes

- **`apiRequest success:false` — monitorear regresiones post-deploy (SunCarWeb)**: El fix global puede descubrir errores silenciados. Cualquier operación que antes mostraba éxito sin verificar puede ahora romper con toast de error.
- **`showContableFields` en MaterialForm (SunCarWeb)**: Confirmar valor por defecto y que otros usos de `MaterialForm` no perdieron campos contables.
- **`costo` y `material_id` en tipo `Material` (SunCarWeb)**: Confirmar que los endpoints del catálogo devuelven estos campos.
- **Wallet historial por miembro — filtros params (SunCarWeb)**: Confirmar que el backend acepta tipo, fechas y búsqueda en el endpoint de historial por miembro.
- **Excel Fichas de Costo sin cota de registros (SunCarWeb)**: La exportación ignora la paginación; con catálogos grandes puede saturar memoria del navegador.
- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!` en el código fuente. Rotar o desactivar la cuenta tras la aprobación del App Store.
- **Bypass de Stripe activo en producción**: Si `isDemoStore` se activa por error en una branch real, órdenes reales quedarán marcadas como pagadas sin cobro. Agregar doble guarda (verificar también `business_id` del negocio demo).
- **Timers de `asyncio.sleep` sin cancelación**: Las tareas de auto-progreso de órdenes demo siguen vivas aunque la orden sea cancelada. Bajo carga, pueden acumularse tareas huérfanas.
- **`seed_demo_store.py` sin idempotencia**: Ejecutarlo de nuevo creará duplicados en producción. Agregar verificación previa o upsert.
- **`isDemoStore` no debe aparecer en feed público**: Verificar que el flag no se expone en búsqueda de tiendas ni en respuestas de la API pública.
- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback de proximidad no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar que el backend aplica la misma convención.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` con params `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador correspondiente.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.
- **Campos de cambio real (SunCarWeb)**: `cambio_real_monto`, `cambio_real_moneda`, `cambio_real_tasa` en `/pagos-ventas/`.
- **Endpoint lazy load obras terminadas (SunCarWeb)**: `GET /obras-terminadas/oferta/{id}/facturas-cliente` — confirmar que existe.
- **Endpoints de notificaciones SunCarWeb**: `GET /mis-notificaciones` con `{ success, data, total }`, filtro bulk por tipo, `dias_alerta` y `link_cliente`.
- **`GET /inventario/stock-historico`**: Confirmar que existe y acepta params de almacén, material y fecha.
- **Agregados solicitudes-ventas**: Confirmar `total_cobrado`, `total_pendiente`, `total_sin_descuento`, `total_con_aumento`, `aumento_monto` en endpoints.
- **`updateSolicitudTransferencia` — validación de estado en backend**.
- **Búsqueda por `numero_serie` (SunCarWeb)**.
- **`stock_disponible_actual` — consistencia entre endpoints**.
- **Excel export de facturas sin cota de registros (SunCarWeb)**.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**.
- **Parsing UTC→local en otras tablas (SunCarWeb)**.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**: Confirmar que POST `/ponderar-costo` incluye `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb)**: Confirmar que existe y acepta params `material_id + almacen_id`.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb)**: Confirmar que el endpoint devuelve el campo `materiales` por factura.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**: Confirmar soporte en el backend.
- **`discounted_service_fee_rate` sin validación de rango**: Confirmar que acepta solo valores entre 0 y 1.
- **Signed URLs de S3 para videos promotores sin renovación**: Confirmar TTL configurado.
- **Race condition del descuento por video**: Confirmar que el endpoint lee `has_watched` directamente de la BD.
- **Videos/thumbnails huérfanos en S3 en error parcial**: Agregar lógica de cleanup o transacción compensatoria.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb)**: Confirmar que el backend valida el permiso en el endpoint de creación de movimientos.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb)**.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb)**.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**.
- **Endpoint cumpleaños de la semana (SunCarWeb)**.
- **Endpoint contador de instalaciones solares (SunCarWeb)**.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb)**.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb)**.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb)**.
- **Rebrand paleta — componentes con clases hardcoded (SunCarWeb)**.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación (SunCarWeb)**.
- **Worker de borrado de cuentas — sin recuperación tras reinicios (nuevo)**: El worker de lifespan no captura cuentas vencidas durante los reinicios del servidor.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes (nuevo)**: Confirmar que las queries manejan el caso de documentos sin el campo.
- **URL prefirmada de APK — TTL del cache vs TTL de la firma (nuevo)**: Confirmar que `cache_ttl < presigned_url_ttl`.
- **ADS — `ad_pricing` sin datos iniciales en producción (nuevo)**.
- **ADS — `approved` desacoplado del pago sin verificación (nuevo)**.
- **Cache TTL en proceso — inconsistencia en deploys multi-instancia (nuevo)**.
- **`chore` auth/rate-limit/admin-payouts sin auditoría detallada (nuevo)**.

---

## 📅 11 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos desde el análisis del 9/06.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Los seguimientos del 9/06 siguen vigentes.

---

#### Seguimientos vigentes

- **`apiRequest success:false` — monitorear regresiones post-deploy (SunCarWeb)**.
- **`showContableFields` en MaterialForm (SunCarWeb)**.
- **`costo` y `material_id` en tipo `Material` (SunCarWeb)**.
- **Wallet historial por miembro — filtros params (SunCarWeb)**.
- **Excel Fichas de Costo sin cota de registros (SunCarWeb)**.
- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!`.
- **Bypass de Stripe activo en producción**.
- **Timers de `asyncio.sleep` sin cancelación**.
- **`seed_demo_store.py` sin idempotencia**.
- **`isDemoStore` no debe aparecer en feed público**.
- **Timezone UTC en "Hora del Día"**: Desfase 5h para Cuba.
- **Ranking sin coordenadas**.
- **"Pide de Nuevo" con token expirado**.
- **Performance ranking multi-factor**.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**.
- **Tasa de cambio EUR vs CUP**.
- **Endpoints de paginación**.
- **Rollback de pago**.
- **`recibido_por_ci` en pagos**.
- **Endpoints wallet**.
- **RRHH — nombre y teléfono editables**.
- **`available_orders_for_delivery`**.
- **`averia_id` en trabajos diarios**.
- **Permiso `gestionar_banco_global`**.
- **Campos SunCarWeb → backend pendientes**.
- **Campos de cambio real (SunCarWeb)**.
- **Endpoint lazy load obras terminadas (SunCarWeb)**.
- **Endpoints de notificaciones SunCarWeb**.
- **`GET /inventario/stock-historico`**.
- **Agregados solicitudes-ventas**.
- **`updateSolicitudTransferencia` — validación de estado en backend**.
- **Búsqueda por `numero_serie` (SunCarWeb)**.
- **`stock_disponible_actual` — consistencia entre endpoints**.
- **Excel export de facturas sin cota de registros (SunCarWeb)**.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**.
- **Parsing UTC→local en otras tablas (SunCarWeb)**.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb)**.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb)**.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**.
- **`discounted_service_fee_rate` sin validación de rango**.
- **Signed URLs de S3 para videos promotores sin renovación**.
- **Race condition del descuento por video**.
- **Videos/thumbnails huérfanos en S3 en error parcial**.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb)**.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb)**.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb)**.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**.
- **Endpoint cumpleaños de la semana (SunCarWeb)**.
- **Endpoint contador de instalaciones solares (SunCarWeb)**.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb)**.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb)**.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb)**.
- **Rebrand paleta — componentes con clases hardcoded (SunCarWeb)**.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación (SunCarWeb)**.

---

## 📅 9 de Junio, 2026

### Resumen de cambios (últimas 24h)

**2 commits** — cumplimiento del App Store (Apple): período de gracia para borrado de cuentas con worker en background, páginas legales servidas desde el backend, y nuevo endpoint de descarga del APK con URL prefirmada de S3 cacheada.

---

### Área 1: Borrado de cuentas con gracia + páginas legales (1 commit — Fabian1820, 15:10)

- **`feat(legal): add account deletion grace period + Privacy/Terms pages`** — Agrega `scheduledDeletionAt` al dominio `User` y al `UserType` de GraphQL. Mutations `requestAccountDeletion` / `cancelAccountDeletion`: programan período de gracia de 30 días en lugar de borrar de inmediato. Worker en background que hard-deletes las cuentas cuyo período expiró (corre cada 24h vía tarea de lifespan). Sirve `/privacy` y `/terms` como HTML desde el backend.

---

### Área 2: Descarga del APK con URL prefirmada de S3 (1 commit — Ruben0304, 18:27)

- **`feat: add GET /download/android endpoint for APK presigned URL`** — Genera una URL prefirmada de S3 cacheada para `apps/llego.apk` y retorna una redirección 302.

---

### Puede dar bateo

1. **Worker de borrado — sin recuperación tras reinicios**: El worker corre como tarea de lifespan cada 24h. Si el servidor se reinicia, las cuentas que vencieron en el intervalo no se borran hasta el próximo ciclo.
2. **`scheduledDeletionAt` — campo nuevo en documentos existentes**: Usuarios creados antes de este commit no tienen el campo. Confirmar que el worker y las queries GraphQL manejan `null` / campo ausente correctamente.
3. **`/privacy` y `/terms` como HTML hardcodeado**: Cualquier actualización legal requiere un nuevo deploy.
4. **URL prefirmada de S3 — TTL del cache vs TTL de la firma**: Si el TTL del cache es mayor que el TTL de la URL prefirmada, el endpoint servirá URLs expiradas.
5. **APK sin versión en la ruta**: Siempre sirve `apps/llego.apk`. Con el redirect cacheado localmente, los clientes pueden descargar el APK viejo tras una actualización.

---

#### Seguimientos vigentes

- **`apiRequest success:false` — monitorear regresiones post-deploy (SunCarWeb)**.
- **`showContableFields` en MaterialForm (SunCarWeb)**.
- **`costo` y `material_id` en tipo `Material` (SunCarWeb)**.
- **Wallet historial por miembro — filtros params (SunCarWeb)**.
- **Excel Fichas de Costo sin cota de registros (SunCarWeb)**.
- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!`.
- **Bypass de Stripe activo en producción**.
- **Timers de `asyncio.sleep` sin cancelación**.
- **`seed_demo_store.py` sin idempotencia**.
- **`isDemoStore` no debe aparecer en feed público**.
- **Timezone UTC en "Hora del Día"**.
- **Ranking sin coordenadas**.
- **"Pide de Nuevo" con token expirado**.
- **Performance ranking multi-factor**.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**.
- **Tasa de cambio EUR vs CUP**.
- **Endpoints de paginación**.
- **Rollback de pago**.
- **`recibido_por_ci` en pagos**.
- **Endpoints wallet**.
- **RRHH — nombre y teléfono editables**.
- **`available_orders_for_delivery`**.
- **`averia_id` en trabajos diarios**.
- **Permiso `gestionar_banco_global`**.
- **Campos SunCarWeb → backend pendientes**.
- **Campos de cambio real (SunCarWeb)**.
- **Endpoint lazy load obras terminadas (SunCarWeb)**.
- **Endpoints de notificaciones SunCarWeb**.
- **`GET /inventario/stock-historico`**.
- **Agregados solicitudes-ventas**.
- **`updateSolicitudTransferencia` — validación de estado en backend**.
- **Búsqueda por `numero_serie` (SunCarWeb)**.
- **`stock_disponible_actual` — consistencia entre endpoints**.
- **Excel export de facturas sin cota de registros (SunCarWeb)**.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**.
- **Parsing UTC→local en otras tablas (SunCarWeb)**.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb)**.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb)**.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**.
- **`discounted_service_fee_rate` sin validación de rango**.
- **Signed URLs de S3 para videos promotores sin renovación**.
- **Race condition del descuento por video**.
- **Videos/thumbnails huérfanos en S3 en error parcial**.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb)**.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb)**.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb)**.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**.
- **Endpoint cumpleaños de la semana (SunCarWeb)**.
- **Endpoint contador de instalaciones solares (SunCarWeb)**.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb)**.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb)**.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb)**.
- **Rebrand paleta — componentes con clases hardcoded (SunCarWeb)**.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación (SunCarWeb)**.
- **Worker de borrado de cuentas — sin recuperación tras reinicios (nuevo)**.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes (nuevo)**.
- **URL prefirmada de APK — TTL del cache vs TTL de la firma (nuevo)**.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **5, 6 y 7 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). Anteriores eliminadas: 27, 28, 29, 30 de Mayo, 31 de Mayo, 1, 2, 3 y 4 de Junio.
