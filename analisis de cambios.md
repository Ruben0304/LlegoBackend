# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 13 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad directa en el backend hoy.
- **Alerta por cambios en SunCarWeb — Módulo Obras (nuevo, yany1509):** Se introdujeron 6 commits bajo el área "obras terminadas / instaladora" con facturas y pagos en CUP. Presupone endpoints CRUD de obras y sus facturas en el backend. Si no existen, el módulo fallará silenciosamente con 404.
- **Alerta por cambios en SunCarWeb — Módulo Tiendas (nuevo, Fabian1820):** Nueva página de gestión de tiendas con CRUD completo. Verificar que los endpoints de tiendas existen y responden correctamente.
- **Alerta por cambios en SunCarWeb — Estado envíos contenedores:** El frontend reemplazó el valor `'despachado'` por `'solicitado'`, `'enviado'` y `'arribado'`. Si el backend valida el campo `estado` contra un enum, los registros existentes con `'despachado'` quedarán inválidos y las operaciones UPDATE sobre ellos fallarán. Requiere migración de datos o actualización del enum en el backend.
- **Alerta por cambios en SunCarWeb — Wallet paginación server-side:** El hook de historial ahora envía parámetros `page`, `per_page`, `desde`, `hasta`, `q`, `propias`, `tipo`, `contraparte_ci` al backend. Verificar que `GET /wallet/transactions` acepta y procesa todos estos parámetros.
- **Alerta por cambios en SunCarWeb — Vista global de pendientes (`ver_todos`):** El endpoint de transferencias pendientes debe aceptar `direction=all` para retornar todas las pendientes del sistema cuando el usuario tiene el permiso `ver_todos`.
- **Seguimiento activo — `recibido_por_ci` en pagos**: Confirmar que el endpoint de pagos maneja este campo y auto-acredita la billetera del trabajador correspondiente.
- **Seguimiento activo — RRHH nombre y teléfono editables**: Confirmar que el endpoint de actualización de trabajadores acepta y persiste `nombre` y `telefono`.
- Seguimiento vigente: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).

---

## 📅 11 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad directa en el backend hoy.
- **Alerta por cambios en SunCarWeb:** El frontend implementó hoy un módulo wallet con flujo de transferencias pendientes que asume la existencia de los siguientes endpoints en el backend:
  - `POST /wallet/wallets/ensure` — crear billetera automáticamente si el destinatario no tiene una
  - `POST /wallet/pending-transfers` — crear transferencia pendiente
  - `PUT /wallet/pending-transfers/{id}/accept`
  - `PUT /wallet/pending-transfers/{id}/reject`
  - `DELETE /wallet/pending-transfers/{id}` (cancelar)
  - Endpoint de lookup de trabajadores (búsqueda por nombre o CI)
  - Si alguno no existe, el flujo de transferencias del frontend fallará silenciosamente con 404.
- **Campo `recibido_por_ci` en pagos**: El frontend ahora envía este campo al registrar un pago para que el backend auto-acredite la billetera del trabajador correspondiente. Verificar que el endpoint de pagos lo implementa.
- **RRHH — nombre y teléfono editables**: El frontend permite editar `nombre` y `telefono` de trabajadores directamente en la tabla. Confirmar que el endpoint de actualización acepta y persiste ambos campos.
- Seguimiento vigente: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).

---

## 📅 10 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad de backend hoy.
- Seguimientos activos de la semana:
  - **Flag `sin_recargo`**: confirmar en LlegoBackend que el route de generación de link omite la comisión Stripe cuando está presente.
  - **Fichas de costo — doble-apply de fórmula**: verificar que al abrir y guardar repetidamente una ficha existente, los precios no se inflan progresivamente.
  - **Campo `stockaje_minimo`**: confirmar que el backend persiste el campo y que `StockajesMinimosSection` no muestra siempre 0 como mínimo.
  - **Campo `numero_serie`**: confirmar que `FichaCostoService` incluye el campo en el payload de actualización.
- No hay riesgos nuevos que reportar.

---

## 📅 9 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad de backend hoy.
- Seguimiento vigente: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).
- SunCarWeb agregó el flag `sin_recargo` en solicitudes-ventas. Verificar que el backend maneja correctamente ese flag en el route de generación de link de pago y omite la comisión Stripe cuando está presente.
- No hay riesgos nuevos propios del backend que reportar.

---
