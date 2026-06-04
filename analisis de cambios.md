# Registro de Análisis de Cambios — LlegoBackend

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

5. **Widget de paneles — estado único vs respuesta del backend**: Pasó de estructura de períodos (Ahora/Mañana/Tarde) a un único valor. Si el endpoint del backend devuelve la estructura de períodos, el parsing puede fallar silenciosamente o mostrar `undefined`.

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
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb)**: Confirmar que el backend valida el permiso en el endpoint de creación de movimientos.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb)**: Confirmar con el backend la lista completa de estados posibles y mapearlos explícitamente.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb)**: Los campos `horas_uso` y `tipo_carga` en modo avanzado deben persistirse; si solo existen en estado React local, se perderán al recargar.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**: En alta concurrencia, los badges pueden mostrar stock disponible que ya fue reservado.
- **Endpoint cumpleaños de la semana (SunCarWeb, nuevo)**: El widget de bienvenida muestra cumpleaños de trabajadores de la semana. Confirmar que el backend tiene el endpoint y devuelve nombre, CI y fecha en el formato esperado.
- **Endpoint contador de instalaciones solares (SunCarWeb, nuevo)**: Confirmar que existe y devuelve el dato en el formato esperado; si no existe, el contador mostrará 0 o error silencioso.
- **Widget de paneles — estado único vs respuesta del backend (SunCarWeb, nuevo)**: El widget se simplificó a un único estado actual. Si el endpoint devuelve estructura de períodos, el parsing puede fallar o mostrar `undefined`.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb, nuevo)**: Puede desincronizarse en full page reloads o con `next/link`. El `popstate` listener puede no dispararse en el primer render SSR.
- **Export Excel merge vertical — heterogeneidad de materiales (SunCarWeb, nuevo)**: Con número heterogéneo de materiales por registro, la alineación de celdas fusionadas puede desincronizarse. Verificar con datos reales.
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
- **Agregados solicitudes-ventas**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación; de lo contrario se pueden editar solicitudes ya aprobadas o en tránsito.
- **Búsqueda por `numero_serie` (SunCarWeb)**: `SalidaLoteForm` y `CreateValeSalidaDialog` buscan materiales por `numero_serie`. Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente; de lo contrario habrá discrepancias entre vistas del mismo almacén.
- **Excel export de facturas sin cota de registros (SunCarWeb)**: El servicio `export-facturas-excel-service.ts` no tiene límite de registros; con grandes volúmenes puede generar timeout en el endpoint de consulta o saturar memoria del navegador.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**: Confirmar que el backend acepta `'zelle'` en filtros de facturas y en el registro de pagos; de lo contrario los filtros no devolverán resultados y los POSTs de pagos con zelle fallarán con 422.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**: El `useMemo` ordena solo los datos ya cargados; con paginación server-side el orden global no está garantizado.
- **Parsing UTC→local en otras tablas (SunCarWeb)**: Verificar que otros componentes con filtros de mes/año usen el mismo parser local aplicado en `VentasPorComercialTable` y `ValesSalida`.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb, nuevo)**: `tasaMlcUsd` y `tasaCupUsd` se reinician en cada sesión (default = 1). El backend acepta `tasa_conversion_mlc_usd` y `tasa_conversion_cup_usd` en PATCH de compra — confirmar que se leen correctamente al reabrir la ficha para evitar recálculos incorrectos.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb, nuevo)**: La respuesta de POST `/ponderar-costo` debe incluir `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`; de lo contrario la actualización in-place del catálogo y los toasts de ponderar fallarán silenciosamente.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb, nuevo)**: Endpoint consumido en `PoolsDistributionDialog` con params `material_id + almacen_id`. Si no existe, el dialog mostrará siempre "Sin kardex" sin indicar error de API.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb, nuevo)**: El procesamiento de facturas espera el campo `materiales` por factura. Confirmar que el endpoint lo devuelve o la columna quedará vacía silenciosamente.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb, nuevo)**: Los params de filtrado en el endpoint de vales deben ser soportados en el backend; de lo contrario retornarán resultados no filtrados o error 422.
- **`discounted_service_fee_rate` sin validación de rango (nuevo)**: Confirmar que el campo acepta solo valores entre 0 y 1. Un valor > 1 resultaría en tarifas de servicio negativas y uno negativo en cobros inflados.
- **Signed URLs de S3 para videos promotores sin renovación (nuevo)**: Las URLs firmadas tienen TTL. Si el video es más largo que el TTL, la reproducción fallará a mitad. Confirmar el TTL configurado y si el cliente puede solicitar renovación de la URL antes del vencimiento.
- **Race condition del descuento por video (nuevo)**: Si el usuario inicia una orden inmediatamente al terminar de ver el video, el flag `has_watched` puede no haberse persistido en BD antes del cálculo del precio. Confirmar que el endpoint de precios de orden lee directamente de la BD.
- **Videos/thumbnails huérfanos en S3 en error parcial (nuevo)**: Si la subida del thumbnail tiene éxito pero la del video principal falla, queda contenido en S3 sin entrada en BD. Agregar lógica de cleanup o transacción compensatoria.
- **`almacenes-suncar/admin` — gating solo en frontend (SunCarWeb, nuevo)**: El sub-permiso que restringe entrada/salida manual está únicamente en el frontend. Confirmar que el backend valida el permiso en el endpoint de creación de movimientos; de lo contrario el control puede ser bypasseado con llamadas directas a la API.
- **Estados de transferencia no mapeados en `ESTADO_CONFIG` (SunCarWeb, nuevo)**: El fix de hoy agregó `procesando` con un `ESTADO_FALLBACK`. Confirmar con el backend la lista completa de estados posibles para solicitudes de transferencia y mapearlos explícitamente.
- **Campos de dimensionamiento en calculadora sin persistencia confirmada (SunCarWeb, nuevo)**: Los nuevos campos `horas_uso` y `tipo_carga` en modo avanzado deben persistirse con la oferta o configuración guardada; si solo existen en estado React local, se perderán al recargar.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb, nuevo)**: `disponible = pool.cantidad - pool.cantidad_reservada` refleja el momento de la carga. En escenarios de alta concurrencia, los badges pueden mostrar stock disponible que ya fue reservado por otros usuarios.

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
- **Agregados solicitudes-ventas**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación; de lo contrario se pueden editar solicitudes ya aprobadas o en tránsito.
- **Búsqueda por `numero_serie` (SunCarWeb)**: `SalidaLoteForm` y `CreateValeSalidaDialog` buscan materiales por `numero_serie`. Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente; de lo contrario habrá discrepancias entre vistas del mismo almacén.
- **Excel export de facturas sin cota de registros (SunCarWeb)**: El servicio `export-facturas-excel-service.ts` no tiene límite de registros; con grandes volúmenes puede generar timeout en el endpoint de consulta o saturar memoria del navegador.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**: Confirmar que el backend acepta `'zelle'` en filtros de facturas y en el registro de pagos; de lo contrario los filtros no devolverán resultados y los POSTs de pagos con zelle fallarán con 422.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb)**: El `useMemo` ordena solo los datos ya cargados; con paginación server-side el orden global no está garantizado.
- **Parsing UTC→local en otras tablas (SunCarWeb)**: Verificar que otros componentes con filtros de mes/año usen el mismo parser local aplicado en `VentasPorComercialTable` y `ValesSalida`.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb, nuevo)**: `tasaMlcUsd` y `tasaCupUsd` se reinician en cada sesión (default = 1). El backend acepta `tasa_conversion_mlc_usd` y `tasa_conversion_cup_usd` en PATCH de compra — confirmar que se leen correctamente al reabrir la ficha para evitar recálculos incorrectos.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb, nuevo)**: La respuesta de POST `/ponderar-costo` debe incluir `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`; de lo contrario la actualización in-place del catálogo y los toasts de ponderar fallarán silenciosamente.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb, nuevo)**: Endpoint consumido en `PoolsDistributionDialog` con params `material_id + almacen_id`. Si no existe, el dialog mostrará siempre "Sin kardex" sin indicar error de API.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb, nuevo)**: El procesamiento de facturas espera el campo `materiales` por factura. Confirmar que el endpoint lo devuelve o la columna quedará vacía silenciosamente.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb, nuevo)**: Los params de filtrado en el endpoint de vales deben ser soportados en el backend; de lo contrario retornarán resultados no filtrados o error 422.

---

## 📅 1 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático "Analisis diario Claude" del 31/05.

---

### Consideraciones del día

- Sin novedades en el backend hoy. SunCarWeb tuvo 5 commits: exportación Excel de facturas con filtro por método de pago, corrección del filtro en modo server-side, mejora de parsing de fechas en `VentasPorComercialTable` y `ValesSalida`, y ordenamiento de solicitudes pendientes por `fecha_creacion`.
- Se agregan cuatro nuevos seguimientos derivados de las interfaces SunCarWeb → backend que deben confirmarse.

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
- **Agregados solicitudes-ventas**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación; de lo contrario se pueden editar solicitudes ya aprobadas o en tránsito.
- **Búsqueda por `numero_serie` (SunCarWeb)**: `SalidaLoteForm` y `CreateValeSalidaDialog` buscan materiales por `numero_serie`. Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente; de lo contrario habrá discrepancias entre vistas del mismo almacén.
- **Excel export de facturas sin cota de registros (SunCarWeb, nuevo)**: El nuevo servicio `export-facturas-excel-service.ts` no tiene límite de registros; con grandes volúmenes puede generar timeout en el endpoint de consulta o saturar memoria del navegador.
- **`'zelle'` como método de pago — soporte en backend (nuevo)**: SunCarWeb extendió el tipo `MetodoPago` para incluir `'zelle'`. Confirmar que el backend acepta este valor en filtros de facturas y en el registro de pagos; de lo contrario los filtros no devolverán resultados y los POSTs de pagos con zelle fallarán con 422.
- **Sort client-side de solicitudes pendientes en ValesSalida (SunCarWeb, nuevo)**: El `useMemo` de `ValesSalidaPage` ordena solo los datos ya cargados. Si la lista usa paginación server-side, confirmar que el backend también acepta un parámetro de ordenamiento por `fecha_creacion`; de lo contrario el orden global no está garantizado.
- **Parsing UTC→local en otras tablas (SunCarWeb, nuevo)**: La corrección del bug de `new Date(fechaString)` interpretado como UTC se aplicó en `VentasPorComercialTable` y `ValesSalida` el mismo día. Verificar que otros endpoints de fechas devuelvan timestamps con timezone o que todos los componentes con filtros de mes/año usen el mismo parser local.

---

## 📅 31 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático "Analisis diario Claude" del 30/05.

---

### Consideraciones del día

- Sin novedades en el backend hoy. Los seguimientos del 30/05 siguen vigentes sin cambios.

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
- **Agregados solicitudes-ventas**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación; de lo contrario se pueden editar solicitudes ya aprobadas o en tránsito.
- **Búsqueda por `numero_serie` (SunCarWeb)**: `SalidaLoteForm` y `CreateValeSalidaDialog` buscan materiales por `numero_serie`. Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente; de lo contrario habrá discrepancias entre vistas del mismo almacén.

---

## 📅 30 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático "Analisis diario Claude" del 29/05.

---

### Consideraciones del día

- Sin novedades en el backend hoy. Los seguimientos del 29/05 siguen vigentes sin cambios.

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
- **Agregados solicitudes-ventas**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación; de lo contrario se pueden editar solicitudes ya aprobadas o en tránsito.
- **Búsqueda por `numero_serie` (SunCarWeb)**: `SalidaLoteForm` y `CreateValeSalidaDialog` buscan materiales por `numero_serie`. Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente; de lo contrario habrá discrepancias entre vistas del mismo almacén.

---

## 📅 29 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático "Analisis diario Claude" del 28/05.

---

### Consideraciones del día

- Sin novedades en el backend hoy. SunCarWeb tuvo 6 commits: edición de solicitudes de transferencia, búsqueda por `numero_serie`, ajustes de stock fetching en `SolicitudTransferenciaDialog`, normalización del input en historial y eliminación de la pantalla de bienvenida implementada el 26/05.
- Se agregan tres nuevos seguimientos derivados de los cambios de SunCarWeb que requieren soporte del backend.

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
- **Agregados solicitudes-ventas**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.
- **`updateSolicitudTransferencia` — validación de estado en backend**: SunCarWeb implementó edición de solicitudes de transferencia. El backend debe validar que la solicitud esté en estado `pendiente` antes de permitir la modificación; de lo contrario se pueden editar solicitudes ya aprobadas o en tránsito.
- **Búsqueda por `numero_serie` (SunCarWeb)**: `SalidaLoteForm` y `CreateValeSalidaDialog` buscan materiales por `numero_serie`. Confirmar que el endpoint indexa este campo; de lo contrario las consultas devolverán resultados vacíos o serán lentas bajo carga.
- **`stock_disponible_actual` — consistencia entre endpoints**: El nuevo campo en los tipos de SunCarWeb implica que el backend puede devolver el stock ya calculado en algunos endpoints. Confirmar que todos los endpoints de inventario devuelven este campo de forma consistente; de lo contrario habrá discrepancias entre vistas del mismo almacén.

---

## 📅 28 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático "Analisis diario Claude" del 27/05.

---

### Consideraciones del día

- Sin novedades nuevas hoy. Los agregados de solicitudes-ventas implementados ayer en SunCarWeb siguen pendientes de validación en backend.
- El sticky header de la tabla solicitudes-ventas fue intentado dos veces y revertido el 27/05 en SunCarWeb. El problema raíz (`overflow: auto` en un ancestro) probablemente reaparecerá en el próximo intento.

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
- **Agregados solicitudes-ventas**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados (`total_cobrado`, `total_pendiente`, etc.) y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales del frontend serán incorrectos en vistas paginadas.

---

> ⚠️ **Nota de mantenimiento**: La entrada del **27 de Mayo** fue eliminada al superar los 7 días de antigüedad (política de retención semanal).
