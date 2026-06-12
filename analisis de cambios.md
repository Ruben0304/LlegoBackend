# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 12 de Junio, 2026

### Resumen de cambios (últimas 24h)

**15 commits** de Ruben0304 — día de altísima actividad: sistema completo de campañas de anuncios de pago en el feed (ADS con `AdCampaign`, creativo como foto, moderación admin), 3 mejoras críticas de performance que reducen el feed de ~12s a ~200ms (cache TTL en proceso, eliminación de llamadas S3 bloqueantes, GZip + DataLoader), sección "Explora otras opciones" con infinite scroll, fixes en "Pide de Nuevo" y correcciones de firma S3.

---

### Área 1: Sistema ADS — campañas de visibilidad en el feed (3 commits)

- **`feat(ads): backend de campañas de visibilidad en el feed`** (17:14) — Nueva línea de monetización: los negocios pagan tarifa fija para aparecer en el feed con un creativo. Modelos: `AdCampaign`, `CreativeSpec` (fondo/textos/badge/CTA + `animationPreset`), `AdPricing`. Colecciones `ad_campaigns`, `ad_pricing`. Service: quote de precio, compra por wallet, moderación admin y selección para el feed. Schema GraphQL completo con queries (`adPricing`, `myAdCampaigns`, `pendingAdCampaigns`) y mutations (crear/actualizar/eliminar/comprar/pausar, aprobar/rechazar admin, `trackImpression/Click`). Secciones aditivas `destacados`/`ofertas` en el feed. Pago por wallet funcional; Stripe/CUP quedan en `pending_payment`.
- **`feat(ads): mostrar campañas aunque estén pendientes de pago`** (18:40) — Incluye `pending_payment` y `pending_review` además de `active` en el query del feed. Los negocios ven su creativo activo desde que lo crean, sin esperar pago ni revisión admin. Excluye `draft`, `paused`, `rejected`, `ended`. Ordena por `createdAt` en lugar de `approvedAt` (puede ser null).
- **`feat(ads): creativo como foto exportada + booleano approved`** (19:30) — Reemplaza el `CreativeSpec` JSON declarativo por una sola foto exportada (`creativeImagePath`, subida vía `/upload/ad-campaign/creative`). Visibilidad controlada por booleano `approved` (puesto por el admin), desacoplado del pago. Feed devuelve `imageUrl + ctaDeeplink` en vez del spec declarativo.

---

### Área 2: Performance del feed (3 commits)

- **`perf: eliminate blocking S3/DB calls from image URL resolvers`** (14:42) — Boto3 cacheado como singleton (10× más rápido: 4ms → 0.4ms/URL). `generate_image_variant_url_with_fallback` (head_object por URL) reemplazado por `get_public_image_variant_url` (crypto local). Resolvers async de avatar eliminados. Resultado: feed ~2.5s → ~200ms (elimina 36 head_object + 27 queries MongoDB por request).
- **`perf: add in-process TTL cache for heavy feed queries`** (15:32) — `InMemoryTTLCache` en `utils/cache.py` (sin Redis). Cachea `get_branch_ids_by_tipo` (5 min TTL), `_build_recent_popularity_scores` (2 min), `get_feed_products` (2 min). Primer load es frío; los subsiguientes saltan todas las queries MongoDB del feed.
- **`perf: reduce payload size and N+1 queries`** (15:41) — GZip middleware (`min_size=500`): feed ~150KB → ~30KB. Paginación en `allCombos` (default 50, max 100). DataLoader `branch_loader` en combo resolver (N queries → 1). Cache de precios en `_compute_starting_base_price`. Impacto: ~12s → ~2.5s en 1 Mbps.

---

### Área 3: Feed — infinite scroll, contexto situacional y sección Explorar (4 commits)

- **`feat(feed): infinite scroll por páginas, contexto situacional`** (16:11) — Parámetro `page` en `get_feed`: cada página sirve un slice diferente de candidatos pre-puntuados (0-9, 10-19, 20-29) sin nuevas queries a BD. `has_more: bool` en `FeedResponse`. Variantes fin de semana y madrugada en `get_meal_context` ("Antojos de Noche", "Desayunos del Finde", "Almuerzo del Finde").
- **`feat(feed): títulos creativos para secciones repetidas en páginas 2+`** (16:17) — Cada sección recibe un título distinto en `page > 0` para que el scroll se sienta como contenido nuevo.
- **`feat: add Explora otras opciones vertical infinite-scroll section`** (16:31) — Nueva sección "catch-all" con todos los productos no surfaceados en otras secciones, puntuados por popularidad (50%), frescura (30%) y proximidad (20%). Parámetro `explorar_page` para paginación; `explorar_has_more` señaliza si hay más páginas.
- **`fix(feed): explorar falls back to full catalog when all products are already shown`** (16:36) — Fallback al catálogo completo cuando todos los productos ya aparecen en otras secciones.

---

### Área 4: Fixes de "Pide de Nuevo", S3 y chore (5 commits)

- **`fix(feed): pide de nuevo muestra cualquier pedido, no solo entregados`** (16:14) — Excluye únicamente cancelados; cualquier otro estado ya cuenta.
- **`fix(feed): pide de nuevo incluye también pedidos cancelados`** (16:15) — Ajuste inmediato: incluso cancelados se incluyen en la sección.
- **`fix(s3): add expiration param to get_public_image_variant_url`** (18:26) — Callers en `orders/types.py` pasaban `expiration=86400` pero la firma no lo aceptaba. Agrega logging diagnóstico `[ADS]`.
- **`fix(s3): add expiration param to get_public_url`** (18:34) — Mismo fix.
- **`chore: commit pending changes (auth, rate limit, admin payouts, test suites)`** (16:38) — Commit agrupado de cambios en autenticación, rate limiting, payouts de admin y suites de test sin descripción individual.

---

### Puede dar bateo

1. **ADS — `approved` desacoplado del pago**: El admin puede aprobar un anuncio sin que el negocio haya pagado. Si la mutation de aprobación no verifica el estado de pago, anuncios no pagados aparecerán en el feed de producción.

2. **Feed muestra `pending_payment` y `pending_review`**: Las campañas no pagadas son visibles para el negocio propietario. Si el filtro por `business_id` falla, todos los usuarios verían anuncios no moderados.

3. **`/upload/ad-campaign/creative` — validación de archivo sin confirmar**: Confirmar que el endpoint valida tipo MIME y tamaño máximo del creativo para evitar uploads maliciosos.

4. **`ad_pricing` sin datos iniciales en producción**: Si la colección está vacía, `adPricing` devuelve vacío y los negocios no pueden cotizar ni crear campañas.

5. **Cache TTL en proceso — deploys multi-instancia**: Cada instancia tiene su propio cache en memoria. Con balanceador de carga, los usuarios pueden ver respuestas inconsistentes del feed durante el TTL de 2-5 minutos.

6. **GZip sobre respuestas binarias**: Confirmar que el middleware no afecta respuestas `application/octet-stream` ni redirects 302 de presigned URLs.

7. **`explorar_has_more` en el fallback**: Confirmar que cuando `explorar` usa el catálogo completo como fallback, setea `explorar_has_more=False` correctamente.

8. **Dos commits contradictorios en "Pide de Nuevo"** (16:14 excluye cancelados → 16:15 los incluye): Confirmar cuál es el comportamiento final deseado y que el código refleja la intención.

9. **`chore` sin detalle en cambios sensibles**: Auth, rate limit y admin payouts agrupados sin descripción individual. Difícil de auditar y revertir selectivamente si algo falla en producción.

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
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**: `sin_costo_ficha`, `no_aplicables`, `costos_catalogo_propagados`.
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
- **Worker de borrado de cuentas — sin recuperación tras reinicios**.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes**.
- **URL prefirmada de APK — TTL del cache vs TTL de la firma**.
- **ADS — `ad_pricing` sin datos iniciales en producción (nuevo)**: Confirmar que la colección tiene al menos un precio base seedeado antes del primer uso comercial.
- **ADS — `approved` desacoplado del pago sin verificación (nuevo)**: Agregar validación en la mutation de aprobación para verificar el estado de pago antes de aprobar.
- **Cache TTL en proceso — inconsistencia en deploys multi-instancia (nuevo)**: En producción con balanceador de carga, usuarios pueden ver feeds inconsistentes durante el TTL de 2-5 min.
- **`chore` auth/rate-limit/admin-payouts sin auditoría detallada (nuevo)**: Revisar diff completo del commit para confirmar ausencia de regresiones en autenticación y rate limiting.

---

## 📅 11 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos desde el análisis del 9/06.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Los seguimientos del 9/06 siguen vigentes.

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
- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h. Tomar la hora local del cliente en el request o configurar TZ del servidor.
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
- **Campos de cambio real (SunCarWeb)**: `cambio_real_monto`, `cambio_real_moneda`, `cambio_real_tasa` en `/pagos-ventas/` — confirmar que el backend acepta estos campos.
- **Endpoint lazy load obras terminadas (SunCarWeb)**: `GET /obras-terminadas/oferta/{id}/facturas-cliente` — confirmar que existe en el backend.
- **Endpoints de notificaciones SunCarWeb**: `GET /mis-notificaciones` debe devolver `{ success, data, total }`; soportar filtro bulk por tipo; incluir `dias_alerta` y `link_cliente` en la respuesta.
- **`GET /inventario/stock-historico`**: Confirmar que existe y acepta params de almacén, material y fecha.
- **Agregados solicitudes-ventas**: Los endpoints deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación.
- **Búsqueda por `numero_serie` (SunCarWeb)**: Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente.
- **Excel export de facturas sin cota de registros (SunCarWeb)**: Con grandes volúmenes puede generar timeout o saturar memoria del navegador.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**: Confirmar que el backend acepta `'zelle'` en filtros y en el registro de pagos.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**: Con paginación server-side el orden global no está garantizado.
- **Parsing UTC→local en otras tablas (SunCarWeb)**: Verificar que otros componentes con filtros de mes/año usen el mismo parser local.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**: `tasaMlcUsd` y `tasaCupUsd` se reinician en cada sesión (default = 1). Confirmar que el backend devuelve las tasas al leer la compra.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**: Confirmar que POST `/ponderar-costo` incluye `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb)**: Confirmar que existe y acepta params `material_id + almacen_id`.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb)**: Confirmar que el endpoint devuelve el campo `materiales` por factura.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**: Confirmar soporte en el backend.
- **`discounted_service_fee_rate` sin validación de rango**: Confirmar que acepta solo valores entre 0 y 1.
- **Signed URLs de S3 para videos promotores sin renovación**: Confirmar TTL configurado y si el cliente puede solicitar renovación antes del vencimiento.
- **Race condition del descuento por video**: Confirmar que el endpoint de precios de orden lee `has_watched` directamente de la BD.
- **Videos/thumbnails huérfanos en S3 en error parcial**: Agregar lógica de cleanup o transacción compensatoria.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb)**: Confirmar que el backend valida el permiso en el endpoint de creación de movimientos.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb)**: Confirmar con el backend la lista completa de estados posibles y mapearlos explícitamente.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb)**: Los campos `horas_uso` y `tipo_carga` en modo avanzado deben persistirse; si solo existen en estado React local, se perderán al recargar.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**: En alta concurrencia, los badges pueden mostrar stock disponible que ya fue reservado.
- **Endpoint cumpleaños de la semana (SunCarWeb)**: Confirmar que el backend tiene el endpoint y devuelve nombre, CI y fecha en el formato esperado.
- **Endpoint contador de instalaciones solares (SunCarWeb)**: Confirmar que existe y devuelve el dato en el formato esperado.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb)**: Si el endpoint devuelve estructura de períodos, el parsing puede fallar o mostrar `undefined`.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb)**: Puede desincronizarse en full page reloads o con `next/link`.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb)**: Con número heterogéneo de materiales por registro, la alineación de celdas fusionadas puede desincronizarse.
- **Rebrand paleta — componentes con clases hardcoded (SunCarWeb)**: Componentes con clases `orange-*` directas pueden mostrar colores incorrectos. El tema Ventas puede no aplicarse a modals/popovers fuera del nodo `data-area`.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación (SunCarWeb)**: Confirmar que existe en el backend y solo acepta solicitudes en estado `procesando`.
- **Worker de borrado de cuentas — sin recuperación tras reinicios (nuevo)**: El worker de lifespan no captura cuentas vencidas durante los reinicios del servidor. Confirmar que al arrancar se procesan las cuentas ya vencidas inmediatamente.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes (nuevo)**: Confirmar que las queries que filtran este campo manejan el caso de documentos sin el campo (`$exists` / `is not None`).
- **URL prefirmada de APK — TTL del cache vs TTL de la firma (nuevo)**: Confirmar que `cache_ttl < presigned_url_ttl` para evitar que el endpoint sirva URLs expiradas al cliente.

---

## 📅 9 de Junio, 2026

### Resumen de cambios (últimas 24h)

**2 commits** — cumplimiento del App Store (Apple): período de gracia para borrado de cuentas con worker en background, páginas legales servidas desde el backend, y nuevo endpoint de descarga del APK con URL prefirmada de S3 cacheada.

---

### Área 1: Borrado de cuentas con gracia + páginas legales (1 commit — Fabian1820, 15:10)

- **`feat(legal): add account deletion grace period + Privacy/Terms pages`** — Agrega `scheduledDeletionAt` al dominio `User` y al `UserType` de GraphQL. Mutations `requestAccountDeletion` / `cancelAccountDeletion`: programan período de gracia de 30 días en lugar de borrar de inmediato. Worker en background que hard-deletes las cuentas cuyo período expiró (corre cada 24h vía tarea de lifespan). Sirve `/privacy` y `/terms` como HTML desde el backend para que las apps tengan URLs alcanzables (el dominio `llego.app` aún no tiene DNS público).

---

### Área 2: Descarga del APK con URL prefirmada de S3 (1 commit — Ruben0304, 18:27)

- **`feat: add GET /download/android endpoint for APK presigned URL`** — Genera una URL prefirmada de S3 cacheada para `apps/llego.apk` y retorna una redirección 302, de modo que el enlace de descarga no expira en el cliente.

---

### Puede dar bateo

1. **Worker de borrado — sin recuperación tras reinicios**: El worker corre como tarea de lifespan cada 24h. Si el servidor se reinicia, las cuentas que vencieron en el intervalo no se borran hasta el próximo ciclo. Agregar un chequeo al arrancar que procese inmediatamente las cuentas ya vencidas.

2. **`scheduledDeletionAt` — campo nuevo en documentos existentes**: Usuarios creados antes de este commit no tienen el campo. Confirmar que el worker y las queries GraphQL manejan `null` / campo ausente correctamente (`$exists` / `is not None`).

3. **`/privacy` y `/terms` como HTML hardcodeado**: Cualquier actualización legal requiere un nuevo deploy. Si Apple enlaza a estas URLs antes del deploy, el contenido puede no coincidir con lo enviado en la revisión.

4. **URL prefirmada de S3 — TTL del cache vs TTL de la firma**: Si el TTL del cache en la app es mayor que el TTL de la URL prefirmada de S3, el endpoint servirá URLs expiradas. Confirmar que `cache_ttl < presigned_url_ttl`.

5. **APK sin versión en la ruta**: Siempre sirve `apps/llego.apk`. Si se sube una versión nueva al mismo nombre, los clientes con el redirect cacheado localmente descargarán el APK viejo. Considerar incluir hash de versión o verificar `ETag` para invalidar el cache.

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
- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h. Tomar la hora local del cliente en el request o configurar TZ del servidor.
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
- **Campos de cambio real (SunCarWeb)**: `cambio_real_monto`, `cambio_real_moneda`, `cambio_real_tasa` en `/pagos-ventas/` — confirmar que el backend acepta estos campos.
- **Endpoint lazy load obras terminadas (SunCarWeb)**: `GET /obras-terminadas/oferta/{id}/facturas-cliente` — confirmar que existe en el backend.
- **Endpoints de notificaciones SunCarWeb**: `GET /mis-notificaciones` debe devolver `{ success, data, total }`; soportar filtro bulk por tipo; incluir `dias_alerta` y `link_cliente` en la respuesta.
- **`GET /inventario/stock-historico`**: Confirmar que existe y acepta params de almacén, material y fecha.
- **Agregados solicitudes-ventas**: Los endpoints deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación.
- **Búsqueda por `numero_serie` (SunCarWeb)**: Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente.
- **Excel export de facturas sin cota de registros (SunCarWeb)**: Con grandes volúmenes puede generar timeout o saturar memoria del navegador.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**: Confirmar que el backend acepta `'zelle'` en filtros y en el registro de pagos.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**: Con paginación server-side el orden global no está garantizado.
- **Parsing UTC→local en otras tablas (SunCarWeb)**: Verificar que otros componentes con filtros de mes/año usen el mismo parser local.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**: `tasaMlcUsd` y `tasaCupUsd` se reinician en cada sesión (default = 1). Confirmar que el backend devuelve las tasas al leer la compra.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**: Confirmar que POST `/ponderar-costo` incluye `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb)**: Confirmar que existe y acepta params `material_id + almacen_id`.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb)**: Confirmar que el endpoint devuelve el campo `materiales` por factura.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**: Confirmar soporte en el backend.
- **`discounted_service_fee_rate` sin validación de rango**: Confirmar que acepta solo valores entre 0 y 1.
- **Signed URLs de S3 para videos promotores sin renovación**: Confirmar TTL configurado y si el cliente puede solicitar renovación antes del vencimiento.
- **Race condition del descuento por video**: Confirmar que el endpoint de precios de orden lee `has_watched` directamente de la BD.
- **Videos/thumbnails huérfanos en S3 en error parcial**: Agregar lógica de cleanup o transacción compensatoria.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb)**: Confirmar que el backend valida el permiso en el endpoint de creación de movimientos.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb)**: Confirmar con el backend la lista completa de estados posibles y mapearlos explícitamente.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb)**: Los campos `horas_uso` y `tipo_carga` en modo avanzado deben persistirse; si solo existen en estado React local, se perderán al recargar.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**: En alta concurrencia, los badges pueden mostrar stock disponible que ya fue reservado.
- **Endpoint cumpleaños de la semana (SunCarWeb)**: Confirmar que el backend tiene el endpoint y devuelve nombre, CI y fecha en el formato esperado.
- **Endpoint contador de instalaciones solares (SunCarWeb)**: Confirmar que existe y devuelve el dato en el formato esperado.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb)**: Si el endpoint devuelve estructura de períodos, el parsing puede fallar o mostrar `undefined`.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb)**: Puede desincronizarse en full page reloads o con `next/link`.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb)**: Con número heterogéneo de materiales por registro, la alineación de celdas fusionadas puede desincronizarse.
- **Rebrand paleta — componentes con clases hardcoded (SunCarWeb)**: Componentes con clases `orange-*` directas pueden mostrar colores incorrectos. El tema Ventas puede no aplicarse a modals/popovers fuera del nodo `data-area`.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación (SunCarWeb)**: Confirmar que existe en el backend y solo acepta solicitudes en estado `procesando`.
- **Worker de borrado de cuentas — sin recuperación tras reinicios (nuevo)**: El worker de lifespan no captura cuentas vencidas durante los reinicios del servidor. Confirmar que al arrancar se procesan las cuentas ya vencidas inmediatamente.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes (nuevo)**: Confirmar que las queries que filtran este campo manejan el caso de documentos sin el campo (`$exists` / `is not None`).
- **URL prefirmada de APK — TTL del cache vs TTL de la firma (nuevo)**: Confirmar que `cache_ttl < presigned_url_ttl` para evitar que el endpoint sirva URLs expiradas al cliente.

---

## 📅 7 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend ni en SunCarWeb desde el análisis del 6/06.

---

### Consideraciones del día

- Sin novedades en ningún repo hoy. Los seguimientos del 6/06 siguen vigentes sin cambios.

---

#### Seguimientos vigentes

- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!`. Rotar o desactivar tras la aprobación del App Store.
- **Bypass de Stripe activo en producción**: Agregar doble guarda.
- **Timers de `asyncio.sleep` sin cancelación**: Posibles tareas huérfanas.
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

## 📅 6 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend ni en SunCarWeb desde el análisis de las 23h del 5/06.

---

### Consideraciones del día

- Sin novedades en ningún repo hoy. Los seguimientos del 5/06 siguen vigentes sin cambios.

---

#### Seguimientos vigentes

- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!`. Rotar o desactivar tras la aprobación del App Store.
- **Bypass de Stripe activo en producción**: Agregar doble guarda.
- **Timers de `asyncio.sleep` sin cancelación**: Posibles tareas huérfanas.
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

## 📅 5 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. SunCarWeb tuvo 8 commits — corrección crítica del manejo global de errores HTTP, Fichas de Costo reconstruidas dos veces en la misma tarde, nueva vista de billetera por miembro y varios fixes de UI.

---

### Consideraciones del día

**Fix crítico de `apiRequest`** (yany1509, SunCarWeb, 13:39): El error hacía que respuestas 400 de FastAPI (`{detail:"..."}`) se procesaran como éxito. `apiRequest` retornaba el objeto sin `success:false`, `extractApiError` no detectaba el error y los datos corruptos eran procesados como válidos. Resultado: aprobar una solicitud de entrada mostraba toast de éxito aunque el backend la rechazara.

**Fichas de Costo — 2 refactors en la tarde** (Fabian1820, SunCarWeb): Primera versión (18:31): corrigió la carga rota. Vista contable con tabs (Precios/Margen, Kardex, Compras). Segunda versión (20:46): reconstruyó sobre `useMaterials` con filtros completos, paginación, exportación Excel, CRUD completo con `MaterialForm` y sección contable gateada. Eliminó código muerto. Añadió `costo` y `material_id` al tipo `Material`.

**Wallet** (Ruben0304, SunCarWeb): Nueva vista de historial por miembro con filtros independientes y exportación Excel en lotes de 500.

---

### Puede dar bateo

1. **`editar-precios-dialog` eliminado — imports residuales**: Si algún componente fuera del módulo de Fichas de Costo lo importa, compilará con error.
2. **`showContableFields` en MaterialForm — valor por defecto**: Si el prop tiene default `false`, cualquier uso de `MaterialForm` en otros módulos habrá perdido la sección contable silenciosamente.
3. **`success:false` global en `apiRequest` — posibles regresiones**: Flujos que antes "funcionaban" a pesar de 400s del backend pueden empezar a mostrar toasts de error inesperados.
4. **Wallet — filtros por miembro sin contrato de API confirmado**: Confirmar que el backend acepta parámetros de tipo, fechas y búsqueda en el endpoint de historial por miembro.
5. **Excel en lotes de 500 — loop completo**: Confirmar que la lógica itera por todos los lotes. Con >500 registros, el Excel puede estar truncado.
6. **PDF unificado paginado en 500 — múltiples peticiones HTTP**: Con miles de registros, puede bloquear la UI.
7. **2 refactors de Fichas de Costo en <3h**: Confirmar que el deploy en producción usa el estado del último commit (20:46).

---

#### Seguimientos vigentes

- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!`. Rotar o desactivar tras la aprobación del App Store.
- **Bypass de Stripe activo en producción**: Agregar doble guarda.
- **Timers de `asyncio.sleep` sin cancelación**: Posibles tareas huérfanas.
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

> ⚠️ **Nota de mantenimiento**: Las entradas del **27, 28, 29, 30 de Mayo, 31 de Mayo, 1, 2, 3 y 4 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal).
