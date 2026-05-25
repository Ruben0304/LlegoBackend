# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 25 de Mayo, 2026

### Resumen de cambios (últimas 24h)

**3 commits** de Ruben0304 — todos relacionados con el **modo demo para revisión del App Store de Apple**.

---

#### 1. `feat: add App Store review demo mode`

- Campo `isDemoStore: bool` en el modelo `Branch` (marca la tienda de revisión del App Store).
- **`orders_service`**: auto-acepta y auto-progresa órdenes demo por todos los estados con timers en background (`asyncio.sleep`): accept ~4s, payment complete ~7s, preparing ~13s, estado final ~21s.
- **`payments_service`**: bypass completo de Stripe para órdenes de una branch con `isDemoStore=True`; marca el pago como completado inmediatamente.
- **`seed_demo_store.py`**: script one-time para crear usuario demo, negocio, branch (24/7, `isDemoStore=True`) y productos directamente en la BD de producción.
- Credenciales demo: `demo@llego.app` / `LlegoDemo2025!` — Tienda: _Llego Demo Store_.

#### 2. `fix: add isDemoStore field to BranchType GraphQL schema`

- El tipo Strawberry `BranchType` no tenía el campo `isDemoStore` que sí existía en el modelo Pydantic, causando errores `__init__() got an unexpected keyword argument 'is_demo_store'`.

#### 3. `fix: use valid BranchVehicle enum value 'caminando' instead of 'a_pie'`

- El enum `BranchVehicle` no tiene el valor `a_pie`; el seed usaba ese valor inválido. Corregido a `caminando`.
- Además se parchó directamente la rama demo en la BD de producción.

---

### Puede dar bateo

1. **Credenciales demo hardcodeadas en repositorio púBlico**: `demo@llego.app / LlegoDemo2025!` están en el código fuente y en el mensaje del commit. Cualquier persona con acceso al repo puede autenticarse en la app de producción con esas credenciales. Después de la aprobación del App Store deberían rotarse o desactivarse.

2. **Bypass de Stripe activo en producción**: Si `isDemoStore` se activa por error en una branch real, o si hay un bug en la verificación del flag, órdenes reales quedarían marcadas como pagadas sin haber cobrado. Alto riesgo financiero. Considerar una doble guarda (e.g., verificar también que el `business_id` sea el demo registrado).

3. **Timers de `asyncio.sleep` en background sin cancelación**: El auto-progreso de órdenes lanza tareas con `asyncio.sleep`. Si la orden es cancelada antes de que los timers completen, las tareas siguen vivas e intentarán actualizar un estado de orden ya cancelada. Bajo carga (múltiples revisores de Apple abriendo la app simultáneamente), pueden acumularse tareas huerfanas.

4. **`seed_demo_store.py` sin idempotencia**: El script crea usuario, negocio, branch y productos directamente. Si se ejecuta de nuevo (accidentalmente), creará duplicados en producción. Debería verificar si ya existen antes de insertar (`upsert` o check previo).

5. **Desarrollo en caliente sobre producción**: El patrón `feat` (18:38) → `fix GraphQL` (18:56) → `fix enum` (19:01) en 22 minutos sugiere que el seed fue ejecutado contra la BD de producción antes de validar el esquema GraphQL y los valores de enum. Los dos fixes post-deploy son señal de que hubo errores en producción durante esa ventana.

6. **`isDemoStore` no debe ser visible para usuarios normales**: Verificar que el campo no aparezca en el feed público de tiendas ni en las respuestas de búsqueda. Un usuario malicioso que vea el flag en la respuesta de la API podría intentar explotarlo.

---

#### Seguimientos vigentes

- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h. Tomar la hora local del cliente en el request o configurar TZ del servidor.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback de proximidad no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar que el backend aplica la misma convención.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` con params `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.
- **Nuevos campos de cambio real (SunCarWeb)**: `cambio_real_monto`, `cambio_real_moneda`, `cambio_real_tasa` en `/pagos-ventas/` — confirmar que el backend acepta estos campos.
- **Endpoint lazy load obras terminadas (SunCarWeb)**: `GET /obras-terminadas/oferta/{id}/facturas-cliente` — confirmar que existe en el backend.

---

## 📅 24 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático "Analisis diario Claude" del 23/05.

> ⚠️ **Nota:** SunCarWeb agregó hoy paginación server-side y filtros por estado de pago en solicitudes de ventas (`feat(solicitudes-ventas)`). Esto implica que el backend de Llego deberá soportar parámetros equivalentes si los endpoints de paginación todavía están pendientes (ver seguimiento abajo).

#### Seguimientos vigentes

- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h. Tomar la hora local del cliente en el request o configurar TZ del servidor.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback de proximidad no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar que el backend aplica la misma convención.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` con params `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.

---

## 📅 23 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático "Analisis diario Claude" del 22/05.

#### Seguimientos vigentes

- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h. Tomar la hora local del cliente en el request o configurar TZ del servidor.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback de proximidad no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar que el backend aplica la misma convención.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` con params `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.

---

## 📅 22 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático "Analisis diario Claude" del 21/05.

#### Seguimientos vigentes

- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h. Tomar la hora local del cliente en el request o configurar TZ del servidor.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback de proximidad no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar que el backend aplica la misma convención.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` con params `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.

---

## 📅 21 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos desde el último análisis. El commit de Brian del 20/05 ("Pide de Nuevo" y "Hora del Día") ya fue registrado ayer.

#### Seguimientos vigentes

- **Timezone UTC en "Hora del Día"**: Usuarios en Cuba (UTC-5) verán el tramo del día desfasado 5h. Tomar la hora local del cliente en el request o configurar TZ del servidor.
- **Ranking sin coordenadas**: Si lat/lng es `null`, verificar que el fallback de proximidad no genere 500 en el feed.
- **"Pide de Nuevo" con token expirado**: El feed completo no debe romper; la sección debe retornar array vacío.
- **Performance ranking multi-factor**: Verificar índice en `(user_id, created_at)` en la tabla de órdenes.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Confirmar que el endpoint persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: EUR multiplica, CUP divide. Confirmar que el backend aplica la misma convención.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` con params `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha.
- **Rollback de pago**: Confirmar que eliminar un pago revierte correctamente el saldo de billetera.
- **`recibido_por_ci` en pagos**: Confirmar auto-acreditación de billetera del trabajador.
- **Endpoints wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar diferenciación entre entrega activa y pins adicionales.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH y lo indexa.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso, el control de acceso de banco/wallet queda roto.
- **Campos SunCarWeb → backend pendientes**: `motivo` y `nota` en asignaciones; `foto` y `ficha_tecnica_url` en materiales; `oferta_venta_id`, `descuento_free`, `motivo_descuento_free`, `precio` en solicitudes desde oferta.

---

## 📅 20 de Mayo, 2026

### Resumen de cambios (últimas 24h)

**1 commit** de Brian (`brianmojena`):

- **`feat: "Pide de Nuevo" y "Hora del Día"`** — Dos nuevas secciones en el feed del usuario:
  - **"Pide de Nuevo"**: muestra productos previamente pedidos por el usuario, requiere autenticación, ranking por recencia + frecuencia + proximidad.
  - **"Hora del Día"**: ajusta título y descripción según la hora UTC actual, ranking por popularidad reciente + proximidad + frescura del producto.

#### Puede dar bateo

- **Timezone UTC hardcodeado**: "Hora del Día" usa la hora UTC para determinar el tramo del día. Los usuarios en Cuba (UTC-5) podrían ver "buenas tardes" cuando aún es mañana. Valorar tomar la hora local del cliente en el request o configurar la zona horaria del servidor según la región objetivo.
- **Ranking de proximidad sin coordenadas**: Si el request no incluye lat/lng (permiso de ubicación denegado o no enviado por el cliente), el ranking de proximidad puede fallar con 500 o devolver resultados sin orden. Verificar el fallback cuando las coordenadas son `null`.
- **"Pide de Nuevo" sin autenticación no debe romper el feed**: Si el token ha expirado o el endpoint falla, la respuesta debe retornar un array vacío para esta sección y no propagar una excepción que haga fallar todo el feed.
- **Performance — ranking multi-factor sobre historial de órdenes**: Combinar recencia + frecuencia + proximidad requiere agregar órdenes por usuario. Si la tabla de órdenes no tiene índice en `(user_id, created_at)`, la query puede ser lenta bajo carga alta.

#### Seguimientos vigentes

- **`aumento_porcentaje` y `aumento_tipo` en ofertas**: Verificar que el endpoint de creación/actualización de ofertas acepta y persiste estos campos por material.
- **Tasa de cambio EUR vs CUP**: Convención final: EUR multiplica (`monto × tasa`), CUP divide (`monto / tasa`). Confirmar que el backend aplica la misma lógica.
- **Endpoints de paginación**: `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` — verificar parámetros `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha y devoluciones.
- **Rollback de pago**: Confirmar que el endpoint de eliminación de pago revierte correctamente el saldo de billetera cuando aplica.
- **`recibido_por_ci` en pagos**: Confirmar que el endpoint auto-acredita la billetera del trabajador correspondiente.
- **Endpoints de transferencias del wallet**: `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
- **RRHH — nombre y teléfono editables**: Confirmar que el endpoint de actualización acepta y persiste ambos campos.
- **`available_orders_for_delivery`**: Verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins.
- **`averia_id` en trabajos diarios**: Confirmar que el backend acepta este campo en POST/PATCH de `/trabajos-diarios/` y lo indexa para búsquedas eficientes por avería.
- **Permiso `gestionar_banco_global`**: Si el backend no valida este permiso en los endpoints de banco/wallet, el control de acceso queda roto.

---

## 📅 18 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático de "Analisis diario Claude" del día anterior.

#### Consideraciones del día

- Sin actividad directa en el backend hoy.
- **Alerta — tasa de cambio en `/pagos-ventas/` (tercer fix en 3 días):** El frontend volvió a corregir la convención. La UI ahora convierte "moneda por USD" → "USD por moneda" antes del POST. Confirmar que el backend recibe la tasa con convención "USD por moneda" y no re-invierte internamente. Este es el punto de mayor riesgo de regresión esta semana.
- **Alerta — nuevo permiso `gestionar_banco_global`:** El frontend implementó "Banco CubespAuto" con sync de pagos Stripe, controlado por el permiso `gestionar_banco_global`. Si el backend no reconoce ni valida este permiso en los endpoints de banco/wallet, el control de acceso queda roto (abierto o cerrado para todos).
- **Alerta — campo `averia_id` en trabajos diarios:** El nuevo flujo de averías envía `averia_id` en el POST/PATCH de `/trabajos-diarios/`. Confirmar que el backend acepta este campo y lo indexa para búsquedas eficientes por avería específica.
- **Alerta — flujo de averías muy complejo con múltiples fallbacks:** En SunCarWeb se hicieron 12+ commits hoy sobre el mismo flujo de trabajos diarios de averías, introduciendo capas de fallback (`looksLikeTrabajoDiario`, `getTrabajosByCliente` → `getTrabajos`, `parsed.data` antes del raíz, etc.). Alta deuda técnica; cualquier cambio futuro puede romper uno de los fallbacks silenciosamente.
- Seguimientos vigentes de días anteriores:
  - **`aumento_porcentaje` y `aumento_tipo` en ofertas:** Verificar que el endpoint de creación/actualización de ofertas acepta y persiste estos campos en el modelo de materiales.
  - **Tasa de cambio EUR vs CUP:** Convención final: EUR multiplica (`monto × tasa`), CUP divide (`monto / tasa`). Confirmar que el backend aplica la misma lógica.
  - **Endpoints de paginación:** `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` deben existir con parámetros `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha y devoluciones.
  - **Rollback de pago:** Verificar que el endpoint de eliminación de pago revierte correctamente el saldo de billetera cuando aplica.
  - **`recibido_por_ci` en pagos:** Confirmar que el endpoint auto-acredita la billetera del trabajador correspondiente.
  - **Endpoints de transferencias del wallet:** `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
  - **RRHH — nombre y teléfono editables:** Confirmar que el endpoint de actualización de trabajadores acepta y persiste ambos campos.
  - **`available_orders_for_delivery`:** Verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins.

---
