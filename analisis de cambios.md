# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 12 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en LlegoBackend hoy. Solo el commit automático de ayer "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad directa en el backend hoy.
- **Alerta crítica — Wallet paginación/filtros server-side (SunCarWeb):** El historial de transacciones fue migrado a un modelo completamente server-side. El endpoint del backend ahora debe soportar los siguientes parámetros:
  - `q` — búsqueda de texto libre
  - `propias` — booleano; cuando es false retorna transacciones de todo el equipo
  - `from_date` / `to_date` — rango de fechas ISO
  - `contraparte_ci` — CI de la contraparte para filtrar por persona
  - `page` / `page_size` — paginación real, 50 registros/página
  - El filtrado client-side fue eliminado. Si el backend ignora estos params, el historial aparecerá vacío o retornará todos los registros sin filtrar.
- **Alerta — Pendientes wallet `direction='all'`:** El fix de hoy hace que usuarios con `ver_todos` llamen al endpoint de pendientes con `direction='all'`. Confirmar que el backend soporta este parámetro y retorna todas las pendientes del sistema, no solo las del requester.
- **Alerta — Nuevo parámetro `contraparte_ci` en historial:** SunCarWeb añadió el filtro "Con persona" que envía `contraparte_ci` al backend. Si el endpoint no lo reconoce, lo ignorará silenciosamente y el filtro no funcionará.
- **Alerta — Estados de envíos de contenedores:** SunCarWeb cambió los valores de estado de `despachado` → `solicitado`, `enviado`, `arribado`. Si el backend tiene validaciones de enum o constraints, los registros existentes con `despachado` fallarán al actualizarse. Se requiere migración o actualización del modelo.
- Seguimiento activo: confirmar que `recibido_por_ci` en endpoint de pagos acredita correctamente la billetera del trabajador correspondiente.
- Seguimiento activo: campos `nombre` y `telefono` editables en RRHH — confirmar que el endpoint de actualización persiste ambos campos.
- Seguimiento activo: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).

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
- Seguimiento vigente: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).
- SunCarWeb agregó el flag `sin_recargo` en solicitudes-ventas. Verificar que el backend maneja correctamente ese flag en el route de generación de link de pago y omite la comisión Stripe cuando está presente.
- No hay riesgos nuevos propios del backend que reportar.

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

## 📅 5 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad de backend hoy.
- Seguimiento vigente: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).
- No hay riesgos nuevos que reportar.

---
