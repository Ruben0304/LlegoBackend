# Registro de Análisis de Cambios — LlegoBackend

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
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**: `tasaMlcUsd` y `tasaCupUsd` se reinician en cada sesión (default = 1). El backend acepta `tasa_conversion_mlc_usd` y `tasa_conversion_cup_usd` en PATCH de compra — confirmar que se leen correctamente al reabrir la ficha para evitar recálculos incorrectos.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**: La respuesta de POST `/ponderar-costo` debe incluir `sin_costo_ficha`, `no_aplicables` y `costos_catalogo_propagados`; de lo contrario la actualización in-place del catálogo y los toasts de ponderar fallarán silenciosamente.
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb)**: Endpoint consumido en `PoolsDistributionDialog` con params `material_id + almacen_id`. Si no existe, el dialog mostrará siempre "Sin kardex" sin indicar error de API.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb)**: El procesamiento de facturas espera el campo `materiales` por factura. Confirmar que el endpoint lo devuelve o la columna quedará vacía silenciosamente.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**: Los params de filtrado en el endpoint de vales deben ser soportados en el backend; de lo contrario retornarán resultados no filtrados o error 422.
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
- **`GET /api/kardex-costo/costo-actual` (SunCarWeb, nuevo)**: Nuevo endpoint consumido en `PoolsDistributionDialog` con params `material_id + almacen_id`. Si no existe, el dialog mostrará siempre "Sin kardex" sin indicar error de API.
- **`materiales` en respuesta de facturas de solicitudes-ventas (SunCarWeb, nuevo)**: El nuevo procesamiento de facturas espera el campo `materiales` por factura. Confirmar que el endpoint lo devuelve o la columna quedará vacía silenciosamente.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb, nuevo)**: Los nuevos params de filtrado en el endpoint de vales deben ser soportados en el backend; de lo contrario retornarán resultados no filtrados o error 422.

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

- Sin novedades en backend ni en SunCarWeb hoy. Los seguimientos del 30/05 siguen vigentes sin cambios.

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

- Sin novedades en backend ni en SunCarWeb hoy. Los seguimientos del 29/05 siguen vigentes sin cambios.

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

## 📅 27 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático "Analisis diario Claude" del 26/05.

---

### Consideraciones del día

- **SunCarWeb implementó hoy agregados del set filtrado completo** para solicitudes de ventas. El backend ahora debe devolver campos de agregados en los endpoints de solicitudes, pagos y facturas: `total`, `total_cobrado`, `total_pendiente`, `total_facturado`, `total_descuentos`. Si no llegan, el frontend cae en fallback a cálculo local — parcialmente mitigado pero los totales pueden ser incorrectos en vistas paginadas.
- **Nuevos campos por ítem en facturas**: `total_sin_descuento`, `total_con_aumento`, `aumento_monto`. Confirmar que el backend los incluye en la respuesta de facturas de ventas o la columna "Aumento" no mostrará datos.
- **Sticky header en tabla solicitudes-ventas revertido dos veces hoy**: El intento de tabla con encabezado fijo fue implementado, corregido y luego revertido en menos de 30 minutos. Es probable que vuelva a intentarse — cuando lo haga, `position: sticky` requiere que ningún ancestro tenga `overflow: auto` (solo `overflow-x: auto` en el wrapper interno).

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
- **Agregados solicitudes-ventas (nuevo)**: Los endpoints de solicitudes, pagos y facturas deben devolver campos de agregados globales y campos por ítem (`total_sin_descuento`, `total_con_aumento`, `aumento_monto`) o los totales serán incorrectos en vistas paginadas.

---

> ⚠️ **Nota de mantenimiento**: La entrada del **26 de Mayo** fue eliminada al superar los 7 días de antigüedad (política de retención semanal).
