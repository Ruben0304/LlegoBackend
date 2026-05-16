# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 16 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos en el backend. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad directa en el backend hoy.
- Los riesgos críticos identificados el 15 de mayo permanecen **abiertos y sin confirmar**:

  - **[URGENTE] `aumento_porcentaje` y `aumento_tipo` en ofertas:** El frontend calcula `precio × (1 - desc/100) × (1 + aum/100)` y muestra el resultado al cliente. Si el backend no persiste estos campos, el precio procesado diferirá del precio mostrado.
  - **[URGENTE] Tasa de cambio EUR vs CUP:** El frontend tuvo 3 cambios contradictorios en un día. La convención final es: EUR multiplica (`monto × tasa`), CUP divide (`monto / tasa`). Confirmar que el backend aplica la misma lógica o los montos USD en EUR serán incorrectos.
  - **[URGENTE] Endpoints de paginación server-side:** Verificar existencia de `/cobros-paginado` y `/personalizadas/pendientes-paginado` con parámetros `skip`, `limit`, `q`, `estado_pendiente`, filtros de fecha y devoluciones. Sin ellos, las tabs de cobros y anticipos/finales pendientes rompen completamente.
  - **[URGENTE] Endpoint eliminar pago:** Confirmar que existe y aplica el rollback contable correcto (reversa de saldo en billetera si aplica).
  - **Pendientes acumulados anteriores:** Endpoints wallet (`ensure`, `pending-transfers`, `accept`, `reject`, `DELETE`), campo `recibido_por_ci` en pagos, campos editables de RRHH (`nombre`, `telefono`), diferenciación de `available_orders_for_delivery`, flag `sin_recargo` en link de pago Stripe.

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
