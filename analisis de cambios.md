# Registro de Análisis de Cambios — LlegoBackend

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
  - **RRHH — nombre y teléfono editables:** Confirmar que el endpoint de actualización acepta y persiste ambos campos.
  - **`available_orders_for_delivery`:** Verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins.

---

## 📅 17 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad directa en el backend hoy.
- Seguimientos vigentes de días anteriores:
  - **`aumento_porcentaje` y `aumento_tipo` en ofertas:** Verificar que el endpoint de creación/actualización de ofertas acepta y persiste estos campos en el modelo de materiales.
  - **Tasa de cambio EUR vs CUP:** Convención final del frontend: EUR multiplica (`monto × tasa`), CUP divide (`monto / tasa`). Confirmar que el backend aplica la misma lógica.
  - **Endpoints de paginación:** `GET /cobros-paginado` y `GET /personalizadas/pendientes-paginado` deben existir con parámetros `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha y devoluciones.
  - **Rollback de pago:** Verificar que el endpoint de eliminación de pago revierte correctamente el saldo de billetera cuando aplica.
  - **`recibido_por_ci` en pagos:** Confirmar que el endpoint auto-acredita la billetera del trabajador correspondiente.
  - **Endpoints de transferencias del wallet:** `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
  - **RRHH — nombre y teléfono editables:** Confirmar que el endpoint de actualización acepta y persiste ambos campos.
  - **`available_orders_for_delivery`:** Verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins.

---

## 📅 15 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad directa en el backend hoy.
- **Alerta por cambios en SunCarWeb — campo `aumento_porcentaje` en ofertas:** El frontend implementó un nuevo campo de aumento por material (simétrico al descuento) con fórmula `precio × (1 - desc/100) × (1 + aum/100)`. El backend debe aceptar y persistir `aumento_porcentaje` y `aumento_tipo` (% o $) por cada material en las ofertas. Si el backend los ignora, el precio que muestra el frontend diferirá del que procesa el backend.
  - **Acción urgente:** Verificar que el endpoint de creación/actualización de ofertas incluye estos campos en el modelo y los persiste.

- **Alerta por cambios en SunCarWeb — tasa de cambio EUR vs CUP:** Hubo 3 commits consecutivos sobre la lógica de tasa (fix → revert → fix final). La conclusión final es: para CUP la tasa se divide (CUP por 1 USD) y para EUR se multiplica (USD por 1 EUR). El backend debe aplicar la misma convención o recibirá montos USD incorrectos para pagos en EUR.
  - **Acción urgente:** Confirmar cómo espera el backend la tasa en cada moneda y que el frontend envía el valor correcto tras el último fix.

- **Alerta — paginación server-side en cobros y anticipos/finales pendientes:** El frontend ahora consume los endpoints `/cobros-paginado` y `/personalizadas/pendientes-paginado`. Si estos no existen en el backend, las tabs de cobros y pagos pendientes romperán completamente.
  - **Acción urgente:** Verificar que ambos endpoints existen y paginan correctamente con los parámetros `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha y devoluciones.

- **Alerta — rollback manual de pago si falla la creación de factura:** El frontend ahora llama a un nuevo método `PagoVentaService.eliminarPago` si `crearFactura` lanza error. Verificar que el endpoint de eliminar pago existe y aplica correctamente el rollback contable (revertir saldo de billetera si aplica).

- Seguimientos vigentes de días anteriores:
  - **`recibido_por_ci` en pagos:** Verificar que el endpoint de pagos maneja este campo y auto-acredita la billetera del trabajador correspondiente.
  - **Endpoints de transferencias pendientes del wallet:** `POST /wallet/wallets/ensure`, `POST /wallet/pending-transfers`, `PUT .../accept`, `PUT .../reject`, `DELETE .../` — confirmar que todos existen.
  - **RRHH — nombre y teléfono editables:** Confirmar que el endpoint de actualización de trabajadores acepta y persiste ambos campos.
  - **`available_orders_for_delivery`:** Verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins.

---
