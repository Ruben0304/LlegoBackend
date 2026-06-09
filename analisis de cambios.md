# Registro de Análisis de Cambios — LlegoBackend

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

Sin commits de desarrollo nuevos en el backend ni en SunCarWeb desde el análisis de las 23h del 6/06.

---

### Consideraciones del día

- Sin novedades en ningún repo hoy. Los seguimientos del 6/06 siguen vigentes sin cambios.

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

---

## 📅 6 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend ni en SunCarWeb desde el análisis de las 23h del 5/06.

---

### Consideraciones del día

- Sin novedades en ningún repo hoy. Los seguimientos del 5/06 siguen vigentes sin cambios.

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

---

## 📅 5 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. SunCarWeb tuvo 8 commits — corrección crítica del manejo global de errores HTTP, Fichas de Costo reconstruidas dos veces en la misma tarde, nueva vista de billetera por miembro y varios fixes de UI.

---

### Consideraciones del día

**Fix crítico de `apiRequest`** (yany1509, SunCarWeb, 13:39): El error hacía que respuestas 400 de FastAPI (`{detail:"..."}`) se procesaran como éxito. `apiRequest` retornaba el objeto sin `success:false`, `extractApiError` no detectaba el error y los datos corruptos eran procesados como válidos. Resultado: aprobar una solicitud de entrada mostraba toast de éxito aunque el backend la rechazara.

**Fichas de Costo — 2 refactors en la tarde** (Fabian1820, SunCarWeb):
- Primera versión (18:31): corrigió la carga rota (servicio apuntaba a `/fichas-costo-materiales/*` inexistente en backend). Vista contable con tabs (Precios/Margen, Kardex, Compras). Módulo sacado de "Economía oculta" a card propio.
- Segunda versión (20:46): reconstruyó sobre `useMaterials` con filtros completos, paginación client-side (20/pág), exportación Excel, CRUD completo con `MaterialForm` y sección contable gateada (`showContableFields`). Eliminó código muerto: `use-fichas-costo` y `editar-precios-dialog`. Añadió `costo` y `material_id` al tipo `Material`.

**Wallet** (Ruben0304, SunCarWeb, 15:41→15:46): Nueva vista de historial por miembro con filtros independientes (tipo, fechas, búsqueda), paginación y exportación Excel en lotes de 500 para respetar el límite del backend.

**Fix logos y PDF** (yany1509, SunCarWeb, 16:47): Logos actualizados a `/brand/suncar-v1-iso.png` en múltiples vistas. Corrige "Limit should be <= 500" en PDF unificado de obras-terminadas paginando en lotes de 500.

**Vales de Salida** (yany1509, SunCarWeb, 13:46): Toast de error descriptivo cuando todos los materiales tienen cantidad 0 o `material_id` vacío al crear un vale.

---

### Puede dar bateo

1. **`editar-precios-dialog` eliminado — imports residuales**: Si algún componente fuera del módulo de Fichas de Costo lo importa, compilará con error. Verificar con `grep -r "editar-precios-dialog"` antes del próximo deploy.

2. **`showContableFields` en MaterialForm — valor por defecto**: Si el prop tiene default `false`, cualquier uso de `MaterialForm` en otros módulos habrá perdido la sección contable silenciosamente. Confirmar el valor por defecto y los puntos de uso.

3. **`success:false` global en `apiRequest` — posibles regresiones**: Flujos que antes "funcionaban" a pesar de 400s del backend pueden empezar a mostrar toasts de error inesperados. Monitorear tras deploy, especialmente en aprobaciones, vales y operaciones de inventario.

4. **Wallet — filtros por miembro sin contrato de API confirmado**: Confirmar que el backend acepta parámetros de tipo, fechas y búsqueda en el endpoint de historial por miembro; si no, retornará todos los registros sin filtrar.

5. **Excel en lotes de 500 — loop completo**: Confirmar que la lógica itera por todos los lotes. Con >500 registros, el Excel puede estar truncado si el loop no está implementado correctamente.

6. **PDF unificado paginado en 500 — múltiples peticiones HTTP**: Con miles de registros, el nuevo loop generará muchas peticiones sucesivas. Sin cota máxima o timeout, puede bloquear la UI.

7. **2 refactors de Fichas de Costo en <3h**: Confirmar que el deploy en producción usa el estado del último commit (20:46) y no el estado intermedio (18:31).

---

#### Seguimientos vigentes

- **`apiRequest success:false` — monitorear regresiones post-deploy (SunCarWeb, nuevo)**: El fix global puede descubrir errores silenciados. Cualquier operación que antes mostraba éxito sin verificar puede ahora romper con toast de error.
- **`showContableFields` en MaterialForm (SunCarWeb, nuevo)**: Confirmar valor por defecto y que otros usos de `MaterialForm` no perdieron campos contables.
- **`costo` y `material_id` en tipo `Material` (SunCarWeb, nuevo)**: Confirmar que los endpoints del catálogo devuelven estos campos.
- **Wallet historial por miembro — filtros params (SunCarWeb, nuevo)**: Confirmar que el backend acepta tipo, fechas y búsqueda en el endpoint de historial por miembro.
- **Excel Fichas de Costo sin cota de registros (SunCarWeb, nuevo)**: La exportación ignora la paginación; con catálogos grandes puede saturar memoria del navegador.
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

---

## 📅 4 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. SunCarWeb tuvo ~24 commits — día de actividad muy alta con rediseño completo de marca, dashboard, navegación, PWA y exportación Excel.

---

### Consideraciones del día

- Sin novedades en el backend hoy. SunCarWeb concentró las siguientes áreas:

**Rebrand Suncar 2026** (yany1509): nueva paleta verde (Emerald Circuit, Volt Green, Solar Radiance, Midnight Voltage, Clean Current) reemplazando el naranja. Cambio amplio en `globals.css` y `tailwind.config.ts`. Nuevos logos. Tema Ventas (`[data-area=ventas]`) con paleta navy+amarillo. Rebrand de exportaciones de ofertas.

**Dashboard rediseñado** (Ruben): widget de clima horario con Open-Meteo (sin clave, La Habana), carrusel de cumpleaños de la semana, contador de instalaciones solares, avatar de trabajador. Se eliminaron cards de módulos/favoritos. Widget de paneles simplificado a estado único.

**Navegación**: área activa en URL (`?area=`) con `window.history.pushState` para que el botón atrás regrese al área correcta. Se usó API nativa en lugar de `useSearchParams` de Next.js por un bug del router.

**PWA**: iconos regenerados con suncar-v2-iso. Favicon y apple-touch-icon con icono verde para modo oscuro.

**Exportación Excel refactorizada** (Fabian): Material y Cantidad apilados verticalmente con merge de celdas (antes columnas dinámicas), para facturas, solicitudes y vales de salida.

**Transferencias**: botón "Resolver (destrabar)" para solicitudes bloqueadas en estado `procesando`.

**Wallet**: ajuste de cuadrícula de saldos para dispositivos pequeños.

---

### Puede dar bateo

1. **Widget de clima — 3 patches en cascada (16:34→16:35→16:36)**: Los fixes se acumularon en 2 minutos, sugiriendo prueba en desarrollo con StrictMode de React. En producción sin StrictMode, el `AbortController` en el cleanup puede comportarse diferente. Si el usuario navega fuera antes del timeout de 6s, el fetch puede no cancelarse correctamente.

2. **`window.history.pushState` + Next.js App Router desync**: El router de Next.js y la API nativa de historial pueden desincronizarse. El `popstate` listener puede no dispararse en el primer render SSR, mostrando el área por defecto aunque la URL tenga `?area=`. Con `next/link` haciendo pre-fetch, el área activa puede quedar incorrecta al navegar.

3. **Export Excel con merge vertical — 2 refactors en 1.5h**: El primer commit (15:46) implementó columnas dinámicas y el segundo (17:14) lo reemplazó por merge vertical. El nuevo formato con celdas fusionadas puede ser incompatible con Excel 2010/2013. Con número heterogéneo de materiales por registro, la alineación entre columnas fusionadas puede desincronizarse.

4. **Rebrand masivo paleta naranja → verde**: Componentes que usan clases Tailwind `orange-*` directamente (sin tokens CSS) mostrarán colores incorrectos. El tema Ventas (`[data-area=ventas]`) puede no aplicarse a modals/popovers renderizados en el `body` fuera del nodo `data-area`.

5. **Widget de paneles — estado único sin contrato de API confirmado**: Pasó de estructura de períodos (Ahora/Mañana/Tarde) a un único valor. Si el endpoint del backend devuelve la estructura de períodos, el parsing puede fallar silenciosamente o mostrar `undefined`.

6. **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación**: El botón "Resolver" asume que el endpoint existe. Confirmar que está implementado y solo acepta solicitudes en estado `procesando`; de lo contrario retornará 404 o 422.

---

#### Seguimientos vigentes

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
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb, nuevo)**: Confirmar que el backend valida el permiso en el endpoint de creación de movimientos.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb, nuevo)**: Confirmar con el backend la lista completa de estados posibles y mapearlos explícitamente.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb, nuevo)**: Los campos `horas_uso` y `tipo_carga` en modo avanzado deben persistirse; si solo existen en estado React local, se perderán al recargar.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb, nuevo)**: En alta concurrencia, los badges pueden mostrar stock disponible que ya fue reservado.
- **Endpoint cumpleaños de la semana (SunCarWeb, nuevo)**: Confirmar que el backend tiene el endpoint y devuelve nombre, CI y fecha en el formato esperado.
- **Endpoint contador de instalaciones solares (SunCarWeb, nuevo)**: Confirmar que existe y devuelve el dato en el formato esperado.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb, nuevo)**: Si el endpoint devuelve estructura de períodos, el parsing puede fallar o mostrar `undefined`.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb, nuevo)**: Puede desincronizarse en full page reloads o con `next/link`.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb, nuevo)**: Con número heterogéneo de materiales por registro, la alineación de celdas fusionadas puede desincronizarse.
- **Rebrand paleta — componentes con clases hardcoded (SunCarWeb, nuevo)**: Componentes con clases `orange-*` directas pueden mostrar colores incorrectos. El tema Ventas puede no aplicarse a modals/popovers fuera del nodo `data-area`.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente de confirmación (SunCarWeb, nuevo)**: Confirmar que existe en el backend y solo acepta solicitudes en estado `procesando`.

---

## 📅 3 de Junio, 2026

### Resumen de cambios (últimas 24h)

**1 commit** de Ruben0304 — nueva funcionalidad de videos promocionales con subida a S3 y descuento de tarifa por servicio.

---

### Área 1: Videos Promocionales (1 commit)

- **`feat: add promotional videos feature with S3 upload and discounted service fee`** — Nuevo modelo `PromotionalVideo` con repositorio y schema GraphQL completo (types, queries, mutations, inputs). Resolvers de metadatos de branch y generación de URLs firmadas de S3 para reproducción segura. Endpoints REST para subir video promocional y thumbnail a S3. Campo configurable `discounted_service_fee_rate`: tasa de descuento aplicada a la tarifa de servicio después de que el usuario vea el video.

---

### Puede dar bateo

1. **`discounted_service_fee_rate` sin validación de rango**: Si el valor configurado supera 1.0 o es negativo, las tarifas calculadas serán incorrectas o negativas. Agregar validación de rango `[0, 1]` en el mutation de creación/actualización.

2. **Signed URLs de S3 con TTL corto**: Las URLs firmadas expiran. Si el TTL es menor que la duración del video, la reproducción se cortará a mitad sin error visible. Confirmar el TTL configurado y si el cliente puede solicitar renovación antes del vencimiento.

3. **Race condition del descuento por video**: Si el usuario inicia una orden inmediatamente al terminar de ver el video, el flag `has_watched` puede no haberse persistido en BD antes del cálculo del precio. Confirmar que el endpoint de precios de orden lee directamente de la BD y no de una caché de sesión.

4. **Videos/thumbnails huérfanos en S3 en error parcial**: Si la subida del thumbnail tiene éxito pero la del video principal falla (o viceversa), queda contenido en S3 sin entrada en BD. Agregar lógica de cleanup o transacción compensatoria en el handler de upload.

---

#### Seguimientos vigentes

- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!` en el código fuente y en mensajes de commit. Rotar o desactivar la cuenta tras la aprobación del App Store.
- **Bypass de Stripe activo en producción**: Si `isDemoStore` se activa por error en una branch real, órdenes reales quedarán marcadas como pagadas sin cobro. Agregar doble guarda (verificar también `business_id` del negocio demo).
- **Timers de `asyncio.sleep` sin cancelación**: Las tareas de auto-progreso de órdenes demo siguen vivas aunque la orden sea cancelada antes. Bajo carga, pueden acumularse tareas huérfanas.
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
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb, nuevo)**: `tasaMlcUsd` y `tasaCupUsd` se reinician en cada sesión (default = 1). Confirmar que el backend devuelve las tasas al leer la compra.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb, nuevo)**: La respuesta de POST `/ponderar-costo` debe incluir `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb, nuevo)**: Endpoint consumido en `PoolsDistributionDialog` con params `material_id + almacen_id`.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb, nuevo)**: El procesamiento de facturas espera el campo `materiales` por factura.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb, nuevo)**: Confirmar soporte en el backend.
- **`discounted_service_fee_rate` sin validación de rango (nuevo)**: Confirmar que el campo acepta solo valores entre 0 y 1.
- **Signed URLs de S3 para videos promotores sin renovación (nuevo)**: Las URLs firmadas tienen TTL. Confirmar el TTL configurado y si el cliente puede solicitar renovación antes del vencimiento.
- **Race condition del descuento por video (nuevo)**: Confirmar que el endpoint de precios de orden lee directamente de la BD.
- **Videos/thumbnails huérfanos en S3 en error parcial (nuevo)**: Agregar lógica de cleanup o transacción compensatoria.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb, nuevo)**: Confirmar que el backend valida el permiso en el endpoint de creación de movimientos.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb, nuevo)**: Confirmar con el backend la lista completa de estados posibles para solicitudes de transferencia.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb, nuevo)**: Los nuevos campos `horas_uso` y `tipo_carga` en modo avanzado deben persistirse.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb, nuevo)**: En alta concurrencia, los badges pueden mostrar stock disponible que ya fue reservado.

---

## 📅 2 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático "Analisis diario Claude" del 01/06.

---

### Consideraciones del día

- Sin novedades en el backend hoy. SunCarWeb tuvo 23 commits — el día más activo del mes: refactor profundo de la ficha de costos de compras, traspaso entre pools de inventario, fix crítico de `reserva_id` en solicitudes de venta, nuevos filtros y exportación Excel en vales de salida, y mejoras en el procesamiento de facturas.
- Se agregan cinco seguimientos nuevos derivados de cambios en SunCarWeb que requieren soporte o confirmación del backend.

---

#### Seguimientos vigentes

- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!` en el código fuente y en mensajes de commit. Rotar o desactivar la cuenta tras la aprobación del App Store.
- **Bypass de Stripe activo en producción**: Si `isDemoStore` se activa por error en una branch real, órdenes reales quedarán marcadas como pagadas sin cobro. Agregar doble guarda (verificar también `business_id` del negocio demo).
- **Timers de `asyncio.sleep` sin cancelación**: Las tareas de auto-progreso de órdenes demo siguen vivas aunque la orden sea cancelada antes. Bajo carga, pueden acumularse tareas huérfanas.
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

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **27, 28, 29, 30 de Mayo, 31 de Mayo y 1 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal).
