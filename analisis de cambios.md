# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 16 de Junio, 2026

### Resumen de cambios (últimas 24h)

**14 commits** de Ruben0304 y Fabian1820 — día de alta actividad en tres ejes: (1) estabilización completa de la integración Qdrant con 6 fixes críticos, incluyendo el reemplazo del método `.search()` deprecado que causaba vacíos silenciosos en producción; (2) nuevas features de recomendaciones personalizadas vía Qdrant (productos similares, branches similares, sección "Especialmente para Ti" en el feed); y (3) nueva funcionalidad de horarios excepcionales por día en branches con posibilidad de pausar pedidos temporalmente.

---

### Área 1: Qdrant — estabilización crítica (6 commits — Ruben0304)

- **`fix(qdrant): lazy client init + refactor ads auth to use require_role`** (14:46) — `VectorSearchService` obtiene `qdrant_client` lazily vía propiedad en lugar de en `__init__`, de modo que una caída de Qdrant en startup no rompe búsquedas futuras una vez que se recupera. Ads mutations/queries migran de `admin_api_key` a `require_role` para que managers también puedan moderar campañas.
- **`fix(startup): replace blocking Qdrant probe with async wait_for (5s cap)`** (14:50) — `socket.getaddrinfo` era síncrono y bloqueaba el event loop durante startup. Ahora usa `asyncio.wait_for` con cap de 5s para que la app arranque rápido independientemente de la disponibilidad de Qdrant.
- **`fix(search): mensaje de error amigable cuando Qdrant no está disponible`** (15:19) — Captura `RuntimeError("Qdrant client not initialized")` y lanza excepción con mensaje legible; el SearchView lo muestra con ícono y botón Reintentar.
- **`fix(qdrant): retry startup probe and bump client to 1.18.x`** (15:30) — 3 reintentos con 5s de delay, `check_compatibility=False`, bumped a `qdrant-client >=1.18.0`.
- **`test(qdrant): suite de integración completa contra Railway`** (15:46) — Cubre conectividad, insert/read/delete, rendimiento de búsqueda, consistencia MongoDB↔Qdrant y flujo real de creación de producto vía `ProductRepository`.
- **`fix(qdrant): reemplazar .search() deprecated por .query_points() en repositorios`** (16:49) — **Fix crítico**: `qdrant-client 1.16+` eliminó `.search()`; los tres repositorios (products, branches, businesses) retornaban `[]` silenciosamente en producción. Causa raíz del bug donde `searchProducts` devolvía vacío.

---

### Área 2: Recomendaciones y feed personalizado (2 commits — Ruben0304)

- **`feat(feed): sección 'Especialmente para Ti' usando Qdrant recommend API`** (17:03) — Promedia vectores de productos en favoritos/carrito del usuario y devuelve los más similares vía `query_points + RecommendInput`. Auth-gated; falla silenciosamente si Qdrant no está disponible o el usuario no tiene historial.
- **`feat(recommendations): getSimilarProducts, getSimilarBranches, getBranchesForProduct vía Qdrant`** (17:13) — `getSimilarProducts(productId)` y `getSimilarBranches(branchId)` usan `recommend` de Qdrant con UUID como positivo preservando orden Qdrant. `getBranchesForProduct(productId)` recomienda top-50 productos similares → agrupa por `branchId` desde MongoDB → puntúa branches por suma de scores → devuelve top-K sin el branch origen.

---

### Área 3: Panel de pruebas admin (2 commits — Ruben0304)

- **`feat(admin): panel nativo de pruebas de experiencia de cliente`** (16:56) — Endpoints `/admin/tests/suites` y `/admin/tests/run`, protegidos por JWT con `role=admin`. 9 suites (Qdrant, feed scoring, feed performance, combos, push notifications) ejecutables desde la app Llego BI en iOS.
- **`feat(admin/tests): soporte node_ids + categorías agrupadas`** (17:07) — `RunRequest` acepta `suite_id` o `node_ids` para ejecutar tests individuales. `/admin/tests/suites` devuelve categorías (Qdrant, Feed, Combos, Push) con suites embebidas para construir UI jerárquica en iOS. `_NODE_META` centraliza labels/impact por node ID.

---

### Área 4: MongoDB indexes + limpieza de logging (3 commits — Ruben0304/Fabian1820)

- **`perf: add missing MongoDB indexes and clean up verbose logging`** (18:01 — Ruben0304) — `_create_order_indexes()`: índices en orders por `(branchId+status+date)`, `(businessId+date)`, `(status+deadline)` y compound de reparto; también en `delivery_persons` y `order_location_updates`. `_create_branch_indexes()`: `businessId` y `(businessId+isActive)` en branches (faltaban, causando collection scans en cada carga de la app de negocios). Reemplaza `print()` de nivel info en hot paths de `branch_repository` y `product_repository` con `logger.error`/`logger.warning`.
- **`Merge remote branch: resolve conflicts, add order/branch/search indexes, clean up logging`** (18:05 — Fabian1820) — Merge manual que preserva `maxPoolSize=150` y `_create_search_perf_indexes()` del branch remoto junto con los nuevos índices de orden y branch.

---

### Área 5: Threshold de búsqueda y control de pedidos en branches (2 commits)

- **`fix(search): bajar threshold de productos de 0.60 a 0.45`** (17:45 — Ruben0304) — Captura más resultados de búsqueda vectorial a expensas de menor precisión media.
- **`feat(branches): pausar pedidos + horario excepcional por día`** (21:32 — Fabian1820) — Nuevo campo `acceptingOrders: bool=True` en domain `Branch`, `BranchType` y `UpdateBranchInput`. Mutation `setAcceptingOrders(branchId, accepting)` para toggle rápido. `create_order` valida `acceptingOrders==True` y lanza `BRANCH_NOT_ACCEPTING_ORDERS`. `TemporaryStatus` extendido con `dailyOverride` (campos opcionales: `date YYYY-MM-DD`, `openTime`, `closeTime`). Mutations `setBranchDailyOverride` y `clearBranchDailyOverride`.

---

### Puede dar bateo

1. **`acceptingOrders` — retrocompatibilidad con documentos sin el campo en MongoDB**: `branch_to_dict` hace default a `True`, pero si alguna query filtra directamente en MongoDB por `acceptingOrders == True`, los branches creados antes de este commit (sin el campo) quedarán excluidos y parecerán cerrados sin serlo.

2. **`dailyOverride.date` sin timezone explícita**: La convención exige ignorar el override si `date != hoy`, pero `date` es string `YYYY-MM-DD` sin TZ. Backend en UTC y clientes en Cuba (UTC-5) pueden tener "hoy" diferente justo a medianoche local.

3. **`setBranchDailyOverride` — sin validación de rango de horas confirmada**: Si `openTime > closeTime`, el horario resultante es inválido. Confirmar que la mutation valida la coherencia del intervalo.

4. **Threshold 0.60 → 0.45 — aumento de ruido en resultados de búsqueda**: Más resultados pero potencialmente menos relevantes. Monitorear si usuarios reportan irrelevancia o si el CTR de búsqueda baja.

5. **`getBranchesForProduct` — doble query Qdrant + MongoDB con top-50**: Recomendar top-50 productos en Qdrant y luego agrupar por `branchId` en MongoDB puede ser lento con catálogos grandes. Confirmar timeout adecuado e índice en `branchId` en la colección de productos.

6. **`getSimilarProducts/Branches` — UUID no encontrado en Qdrant**: Si el UUID del producto/branch no existe en Qdrant (producto creado antes de la integración vectorial), el endpoint puede lanzar error o devolver vacío. Confirmar degradación elegante.

7. **`Especialmente para Ti` — vector promedio sin normalización explícita**: Promediar vectores de favoritos/carrito sin re-normalizar puede sesgar los resultados si los embeddings de Gemini no son vectores unitarios. El centroide puede apuntar a un espacio denso incorrecto.

8. **Ads auth migrado de `admin_api_key` a `require_role`**: Managers ahora pueden aprobar/rechazar campañas. Confirmar que el flujo de negocio permite esta moderación y que el role `manager` está correctamente asignado en los JWTs emitidos.

9. **`check_compatibility=False` en qdrant-client**: Desactiva la verificación de versión cliente-servidor. Si hay incompatibilidad real en futuras actualizaciones, los errores serán menos descriptivos.

10. **Merge manual de conflictos (18:05)**: Confirmar que el merge no perdió cambios del branch remoto, especialmente `maxPoolSize=150` y `_create_search_perf_indexes()`.

11. **`_create_order_indexes()` y `_create_branch_indexes()` en colecciones con datos existentes**: Crear índices en colecciones con muchos documentos puede bloquear escrituras. Confirmar que se usó opción de construcción en background en el tier de Atlas.

---

#### Seguimientos vigentes

- **`asyncio.to_thread` — pool de threads por defecto (Jun 15)**: Confirmar capacidad del executor bajo picos de búsquedas concurrentes. Considerar `ThreadPoolExecutor` explícito.
- **`get_by_ids()` en repositorios de vector search (Jun 15)**: Si falta en algún repositorio, el resolver rompe con `AttributeError` sin degradación elegante.
- **GZip umbral 200 bytes — exclusión de binarios y presigned URLs (Jun 15)**: Confirmar que el middleware excluye `application/octet-stream` y redirects 302 de S3.
- **`minPoolSize` en Atlas tier bajo con escalado horizontal (Jun 15)**: Confirmar `minPoolSize` 0 o cercano a 0 para evitar agotar el pool en despliegues multi-instancia.
- **`apiRequest success:false` — monitorear regresiones post-deploy (SunCarWeb)**.
- **`showContableFields` en MaterialForm (SunCarWeb)**.
- **`costo` y `material_id` en tipo `Material` (SunCarWeb)**.
- **Wallet historial por miembro — filtros params (SunCarWeb)**.
- **Excel Fichas de Costo sin cota de registros (SunCarWeb)**.
- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!` en el código fuente.
- **Bypass de Stripe activo en producción**: Si `isDemoStore` se activa por error, órdenes reales quedan marcadas como pagadas sin cobro.
- **Timers de `asyncio.sleep` sin cancelación**: Tareas de auto-progreso de órdenes demo acumulándose bajo carga.
- **`seed_demo_store.py` sin idempotencia**: Ejecutarlo de nuevo crea duplicados en producción.
- **`isDemoStore` no debe aparecer en feed público**.
- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) ven el tramo desfasado 5h.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar convención en backend.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado`.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador correspondiente.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../`.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.
- **Campos de cambio real (SunCarWeb)**: `cambio_real_monto`, `cambio_real_moneda`, `cambio_real_tasa` en `/pagos-ventas/`.
- **Endpoint lazy load obras terminadas (SunCarWeb)**: `GET /obras-terminadas/oferta/{id}/facturas-cliente`.
- **Endpoints de notificaciones SunCarWeb**: `GET /mis-notificaciones` con `{ success, data, total }`, filtro bulk por tipo.
- **`GET /inventario/stock-historico`**: Confirmar que existe y acepta params.
- **Agregados solicitudes-ventas**: Confirmar `total_cobrado`, `total_pendiente`, `total_sin_descuento`, `total_con_aumento`, `aumento_monto` en endpoints.
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
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente (SunCarWeb)**.
- **Worker de borrado de cuentas — sin recuperación tras reinicios**.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes**.
- **URL prefirmada de APK — TTL del cache vs TTL de la firma**.
- **ADS — `ad_pricing` sin datos iniciales en producción**.
- **ADS — `approved` desacoplado del pago sin verificación**.
- **Cache TTL en proceso — inconsistencia en deploys multi-instancia**.
- **`chore` auth/rate-limit/admin-payouts sin auditoría detallada**.
- **`acceptingOrders` — retrocompatibilidad con documentos sin el campo (nuevo)**.
- **`dailyOverride.date` sin timezone explícita (nuevo)**.
- **`setBranchDailyOverride` — sin validación de rango de horas (nuevo)**.
- **Threshold 0.60 → 0.45 — aumento de ruido en búsqueda (nuevo)**.
- **`getBranchesForProduct` — doble query Qdrant + MongoDB (nuevo)**.
- **`getSimilarProducts/Branches` — UUID no encontrado en Qdrant (nuevo)**.
- **`Especialmente para Ti` — vector promedio sin normalización (nuevo)**.
- **Ads auth migrado a `require_role` para managers (nuevo)**.
- **`check_compatibility=False` en qdrant-client (nuevo)**.
- **Merge manual de conflictos — verificar integridad (nuevo)**.
- **Índices en colecciones existentes — confirmar background build (nuevo)**.

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
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación (SunCarWeb)**.
- **Worker de borrado de cuentas — sin recuperación tras reinicios (nuevo)**: Confirmar que al arrancar se procesan las cuentas ya vencidas inmediatamente.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes (nuevo)**: Confirmar manejo de `null`/campo ausente.
- **URL prefirmada de APK — TTL del cache vs TTL de la firma (nuevo)**: Confirmar que `cache_ttl < presigned_url_ttl`.
- **ADS — `ad_pricing` sin datos iniciales en producción (nuevo)**.
- **ADS — `approved` desacoplado del pago sin verificación (nuevo)**.
- **Cache TTL en proceso — inconsistencia en deploys multi-instancia (nuevo)**.
- **`chore` auth/rate-limit/admin-payouts sin auditoría detallada (nuevo)**.
- **`asyncio.to_thread` — pool de threads por defecto (nuevo)**: Confirmar capacidad suficiente o configurar `ThreadPoolExecutor` explícito.
- **`get_by_ids()` en repositorios de vector search — confirmar existencia (nuevo)**.
- **Índices de MongoDB — construcción sin bloquear escrituras (nuevo)**.
- **GZip umbral 200 bytes — exclusión de binarios y presigned URLs (nuevo)**.
- **`minPoolSize` en Atlas tier bajo con escalado horizontal (nuevo)**.

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
