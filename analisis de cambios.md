# Registro de Análisis de Cambios — LlegoBackend

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

## 📅 17 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 16 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**1 commit real** — brianmojena (co-authored Claude Opus 5). Commit puramente de documentación: se reorganiza la referencia del proyecto en un `context.md` maestro y se eliminan 19 archivos .md obsoletos o redundantes.

---

### Área 1: docs — consolidar la documentación en context.md maestro (07:28)

- **`docs: consolidar la documentación en un context.md maestro`** — La raíz del repo tenía 19 archivos .md dispersos: una transcripción de chat Codex (103 KB), tres specs de Kiro ya completadas, dos README vacíos, un duplicado con espacio en el nombre e informes puntuales obsoletos.

  Se añade **`context.md`** como documento único de referencia, verificado contra el código con referencias `archivo:línea`: arquitectura, modelo de datos e índices, autenticación, superficie GraphQL y REST, flujo de pedidos, pagos y KYC, IA y búsqueda, workers, trampas conocidas, bugs abiertos y convenciones.

  **Borrado**: `Codex.md`, specs `.kiro/`, `README_QVAPAY.md`, `README_STRIPE.md`, `"analisis de cambios .md"` (duplicado con espacio en el nombre), `IMPLEMENTACION_COMBO_PRICING.md`, `DELIVERY_FLOW_CONTRACT.md`, los tres `FRONTEND_*_DELIVERY.md` (fusionados en `context.md` §7; además listaban 11 estados de `OrderStatus` cuando hay 12), y `runtime_schema.graphql` (era un traceback de un export fallido, no un schema).

  **Movido a `docs/`**: `AI_ASSISTANT_API.md` → `docs/ai-assistant-api.md`, `README_COMBOS.md` → `docs/combos.md`, `README_STRIPE_RECHARGE.md` → `docs/stripe-recharge.md`, con referencias cruzadas corregidas.

  **`README.md`**: corregía prefijos REST erróneos (`/api/users` → `/users`, `/api/uploads` → `/upload`, `/api/push-notifications` → `/api/push`) y mencionaba solo Stripe como pasarela de pago (se añade QvaPay).

  **`CLAUDE.md`**: ahora apunta a `context.md` en vez de duplicar su contenido.

---

### Puede dar bateo

1. **Rutas de docs movidas — links rotos**: `AI_ASSISTANT_API.md`, `README_COMBOS.md` y `README_STRIPE_RECHARGE.md` se movieron a `docs/`. Cualquier herramienta, wiki externa, script CI o bookmark que apunte a las rutas antiguas en la raíz verá 404.

2. **`DELIVERY_FLOW_CONTRACT.md` y `FRONTEND_*_DELIVERY.md` eliminados**: Fusionados en `context.md` §7. Si el frontend de apps móviles o algún cliente usaba estos archivos como contrato de integración, necesita actualizarse a esa sección.

3. **`OrderStatus` listaba 11 estados, hay 12**: Los archivos eliminados tenían este error. Confirmar que el frontend de las apps (móvil, cliente) conoce los 12 estados actuales de `OrderStatus`.

4. **`runtime_schema.graphql` borrado**: Era un traceback de export fallido. Si algún script CI, herramienta de introspección o pipeline de generación de tipos lo busca como input, falla silenciosamente.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **10, 11, 14 y 15 de Septiembre** fueron eliminadas el 23 de Septiembre al superar los 7 días de antigüedad (política de retención semanal). La entrada del **9 de Septiembre** fue eliminada el 17 de Septiembre. La entrada del **7 de Septiembre** fue eliminada el 15 de Septiembre. La entrada del **2 de Septiembre** fue eliminada el 10 de Septiembre. Anteriores eliminadas progresivamente desde Mayo.
