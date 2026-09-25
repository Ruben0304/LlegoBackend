# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 25 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**2 commits** — brianmojena (co-authored Claude Opus 5.5). Día enfocado en push notifications: fix crítico de enrutamiento de pushes por app + suite de tests.

---

### Área 1: fix(push) + test(push) — Enrutamiento correcto de pushes y cobertura de tests (16:31–16:45)

- **`fix(push): enrutar pushes a su app y no desactivar tokens válidos`** (16:31, brianmojena) — Fix de alta importancia en el sistema de notificaciones push:
  - **Separación por app según `bundleId`**: los device tokens se clasifican en app de clientes (sin bundleId o bundleId que no empieza con `com.llego.business*`) o app de negocio (LlegoBusiness). Cada push solo llega a la app correcta: `new_order`, `order_status_update_business`, `payment_proof_submitted` y KYC usan el bundle de LlegoBusiness; pushes de clientes y broadcasts de tipos de negocio van solo a la app de clientes.
  - **`registerDeviceToken` con `bundleId` opcional**: retro-compatible con clientes que no lo envían. Al actualizar un token existente no se borra el `bundleId` ya guardado.
  - **APNs desactiva tokens solo en 410 Unregistered o 400 BadDeviceToken**: antes cualquier 400 desactivaba el token. `DeviceTokenNotForTopic` (token de otra app) desactivaba tokens válidos, p.ej. el token de clientes de dueños por el flujo de KYC.
  - **`notify_critical_error` solo a admins**: antes enviaba a todos los iPhones de clientes; ahora solo a usuarios con `role=admin`.
  - Tests en `tests/test_push_audience_routing.py`.

- **`test(push): cubrir el enrutado de cada punto que envía pushes`** (16:45, brianmojena) — Suite de tests con mocks (sin red ni base de datos) que verifica que cada envío pide los tokens de su app y usa el bundle correcto:
  - Pedidos: estado al cliente (app clientes), nuevo pedido y estado al negocio (app negocio, bundle LlegoBusiness).
  - KYC: solo tokens de la app de negocio de los managers.
  - Alertas de errores: solo admins; sin admins no se envía nada.
  - Endpoints `/api/push/clientes`, `/api/push/negocios` y test-push de admin en `/api/error-logs`.

---

### Puede dar bateo

1. **Tokens registrados antes del fix no tienen `bundleId` — dueños de negocio pierden pushes de negocio**: Todos los tokens pre-existentes sin `bundleId` se tratan como clientes. Los dueños que solo tienen la app de negocio instalada no recibirán `new_order` ni `order_status_update_business` hasta que vuelvan a registrar el token con el `bundleId` correcto. Confirmar si hay notificación al usuario o si se requiere re-registro manual.

2. **APNs ya no desactiva en `DeviceTokenNotForTopic` — tokens stale de otra app quedan en BD indefinidamente**: No es un bug activo, pero la colección de tokens puede crecer con tokens inservibles de otra app. Considerar una tarea de limpieza periódica.

3. **`notify_critical_error` solo a admins — confirmar que hay admins con token registrado en producción**: Si ningún usuario con `role=admin` tiene token registrado, los errores críticos no llegan a nadie por push. Verificar que los admins de producción tienen la app instalada y token activo.

4. **Patrón `com.llego.business*` — confirmar que cubre todas las variantes del bundle de la app de negocio**: Si la app usa `com.llego.businesspro` u otro prefijo diferente, no matcheará y los pushes de negocio irán a la app de clientes. Confirmar el glob exacto contra el `bundleId` real publicado en App Store.

5. **Tests con mocks — el mock puede diferir del comportamiento real de APNs**: Si el código de error real de APNs difiere del simulado (p.ej. formato distinto del body de error), los tests pasan pero en producción el token no se desactiva cuando debería.

---

## 📅 24 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit del período es el "Analisis diario Claude" automático generado en el análisis del 23-sep. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 23 de septiembre.

---

## 📅 23 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**2 commits** — Ruben0304 (co-authored Claude Opus 5.5). Día muy significativo: un commit de protección de pagos de gran envergadura más su merge desde main.

---

### Área 1: fix(pagos) — proteger el dinero del cliente en todo el flujo de pedidos + suite E2E (14:00)

- **`fix(pagos): proteger el dinero del cliente en todo el flujo de pedidos + suite E2E`** — Commit de alta densidad que refuerza la integridad financiera en el flujo completo de pedidos:

  - **Worker de timeouts seguro**: ya no cancela pedidos con dinero de por medio (pagados, pago enviado o en disputa); los marca `requiresAttention` para soporte. Solo cancela si el estado evaluado sigue vencido y sin pago.
  - **Nuevo estado `PAYMENT_IN_PROGRESS`**: se activa al marcar "pago enviado". El negocio tiene 30 min para confirmar; al confirmar, se reinicia el plazo del pedido.
  - **`initiatePayment` idempotente**: retoma el intento activo en lugar de crear uno nuevo. Confirmaciones también idempotentes. Pago tardío sobre pedido cancelado se registra y se marca para reembolso en vez de revivir el pedido.
  - **Bloqueos en estado con pago iniciado**: modificar, rechazar, reenviar, soltar pedido y cambiar el envío quedan bloqueados cuando el pago ya empezó.
  - **Compare-and-set en cambios de estado**: evita race conditions en actualizaciones concurrentes.
  - **Permisos ampliados**: `updateOrderStatus`, `markOrderReady`, `forceOrderStatus`, `assignDeliveryPerson`, queries de pedidos/pagos. Staff invitado puede confirmar pagos. Query admin `ordersRequiringAttention`.
  - **Fix crash `VehicleType.A_PIE`**: corregido para mensajeros nuevos.
  - **Refactor proveedores de pago**: reorganizado en `services/payments/providers`.
  - **Suite E2E** (`tests/e2e`, `scripts/run_e2e.sh`): modo sandbox por header `X-E2E-Key = E2E_SANDBOX_KEY` (BD aislada, JWT aislados, sin caché ni logs de error). 75 tests de flujos completos + 5 xfail que documentan bugs conocidos; suite de pagos con marker `pagos`.

- **`Merge origin/main: integrar tracking admin, FCM y metricas con la proteccion de pagos`** (14:03) — Merge que resolvió conflictos en imports de `mongodb_client` (sandbox + `DeliveryRequestStatus`) y en `orders_service` (`user_can_access_order` + `get_order_tracking` con bypass admin). Las lecturas de pedidos permiten el rol `platform_manager` igual que el panel admin.

---

### Puede dar bateo

1. **Estado `PAYMENT_IN_PROGRESS` nuevo — clientes móviles o frontends que no lo manejen**: Cualquier app que haga switch/if sobre `OrderStatus` sin manejar este valor mostrará un estado desconocido o puede crashear. Confirmar que todos los consumidores conocen el nuevo estado.

2. **Compare-and-set en cambios de estado — 409 inesperados en frontend**: Si el frontend no maneja `409 Conflict` del backend (respuesta del compare-and-set cuando el estado ya cambió), el usuario verá un error genérico sin mensaje claro. Confirmar que el frontend de la app de negocio maneja este caso.

3. **`PAYMENT_IN_PROGRESS` ventana de 30 min — race condition con worker de timeouts**: Si el worker corre antes de que el negocio confirme y el estado es exactamente `PAYMENT_IN_PROGRESS`, confirmar que el worker respeta la ventana y no marca `requiresAttention` prematuramente.

4. **`E2E_SANDBOX_KEY` en producción — sandbox activo si la variable está configurada**: Si `E2E_SANDBOX_KEY` está seteada en el entorno de producción por accidente, cualquier petición con ese header opera sobre la BD de sandbox. Confirmar que la variable no existe en producción.

5. **Refactor `services/payments/providers` — imports directos rotos**: Si cualquier módulo fuera del refactor importaba directamente de las rutas antiguas de proveedores de pago, fallará con `ModuleNotFoundError` en tiempo de request. Confirmar con `grep -rn "from services/payments"` en el código.

6. **`initiatePayment` idempotente — comportamiento con intento activo en Stripe/QvaPay**: Retomar un intento activo asume que el proveedor externo no lo ha expirado. Si el proveedor expiró el intento en su lado pero el backend aún lo considera activo, la confirmación posterior fallará. Confirmar TTL de intentos en Stripe y QvaPay versus la ventana del backend.

7. **Pago tardío marcado para reembolso — confirmar que el flujo de reembolso está implementado**: El commit dice que se "marca para reembolso", pero si no hay worker o endpoint que ejecute el reembolso real en Stripe/QvaPay, el dinero quedará retenido indefinidamente sin acción automática.

8. **Fix `VehicleType.A_PIE` — confirmar ausencia en documentos MongoDB de mensajeros existentes**: Si mensajeros creados antes del fix tienen `vehicle_type` como `None` o string vacío en vez de `A_PIE`, el fix puede no cubrirlos. Confirmar migración o fallback.

---

> ⚠️ **Nota de mantenimiento**: La entrada del **17 de Septiembre** fue eliminada el 25 de Septiembre al superar los 7 días de antigüedad (política de retención semanal). Las entradas del **16 de Septiembre** y anteriores fueron eliminadas progresivamente.
