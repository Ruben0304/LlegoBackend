# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 5 de Octubre, 2026

### Resumen de cambios (últimas 24h)

**2 commits** — Fabian1820 (co-authored Claude Opus 5.5). Fix de concurrencia en mensajeros y commit de merge de la Fase 2a.

---

### Área 1: fix(mensajeros) — Un mensajero solo puede tener una entrega en curso (16:59)

`fix(mensajeros): un mensajero solo puede tener una entrega en curso`

`acceptOrderForPayment` (flujo principal de AppMensajeros) no verificaba si el mensajero ya tenía un pedido activo: podía aceptar un segundo aunque la app trabaja con una sola entrega (`myCurrentDelivery`). El flujo antiguo `acceptDelivery` sí lo impedía, pero `acceptOrderForPayment` no heredó esa guarda.

Cambios aplicados:
- Llama a `get_current_delivery` antes de aceptar; rechaza con "Ya tienes un pedido en curso" si devuelve otro pedido activo.
- Usa el estado real de pedidos en la BD, no `delivery_person.currentOrderId`, que puede quedarse desactualizado.
- Reintentar sobre el propio pedido sigue siendo idempotente.

---

### Área 2: merge(fase-2a) — Integración de la rama de Fase 2a en main (17:05)

`merge: origin/main en la integración de la fase 2a`

Commit de merge. No hay descripción de los cambios incluidos en la rama; requiere revisar el diff completo para identificar qué entró con la Fase 2a.

---

### Puede dar bateo

1. **`get_current_delivery` y estados intermedios — posibles falsos positivos**: Si existen pedidos en estados "limbo" (aceptados pero no reflejados aún en BD por latencia de escritura), el guard puede bloquear al mensajero legítimamente. Confirmar qué estados considera "en curso" la función y que cubre ACCEPTED, IN_PROGRESS pero no COMPLETED/CANCELLED.

2. **Ventana de aceptación concurrente**: Si dos requests de `acceptOrderForPayment` llegan en el mismo instante antes de que el primero se confirme en BD, ambos pueden pasar el guard. Confirmar si hay compare-and-set o transacción atómica protegiendo el accept.

3. **Merge de Fase 2a sin descripción**: El commit de merge no detalla qué entra. Si la Fase 2a incluye cambios de esquema de datos, nuevos campos en modelos Pydantic o nuevos endpoints, puede haber impacto no documentado. Revisar el diff antes del próximo despliegue.

---

## 📅 4 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 3 de octubre (auth de subscriptions, estado `UNDERPAID`, `WEB_AUTH_CALLBACK_URLS`, transacciones con `NameError`, `zoneinfo`/`pytz`, rate limit con `bearer` minúscula, `predefinedDeliveryFee`, `branchOrderUpdated` + `UNDERPAID` circular, timeout del proxy, `require_admin_user_from_header`).

---

## 📅 3 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 2 de octubre (auth de subscriptions, estado `UNDERPAID`, `WEB_AUTH_CALLBACK_URLS`, transacciones con `NameError`, `zoneinfo`/`pytz`, rate limit con `bearer` minúscula, `predefinedDeliveryFee`, `branchOrderUpdated` + `UNDERPAID` circular, timeout del proxy, `require_admin_user_from_header`).

---

## 📅 2 de Octubre, 2026

### Resumen de cambios (últimas 24h / Fase 1 backend mergeada)

**~20 commits** — Fabian1820 (co-authored Claude Opus 5.5). Integración de la **Fase 1**: seis fixes de seguridad críticos (Apple Sign-In, push sin auth, payments/validate sin JWT, subscriptions sin auth, tutoriales sin rol, wallet sin db), publicación en tiempo real de pedidos de sucursal, no confirmar pedidos con pago incompleto (nuevo estado `UNDERPAID`), plazos correctos para pedidos programados, override diario con fecha y fix de integración entre las dos ramas. Nota: el análisis del oct-1 no capturó los commits de la Fase 1 porque el análisis corrió antes de que los merges estuvieran visibles en ese contexto; se documentan aquí.

---

### Área 1: fix(auth) — Lista blanca de destinos en Apple Sign-In (18:00, oct 1)

`fix(auth): lista blanca de destinos en el flujo web de Apple Sign-In`

**Seguridad crítica.** `/apple/start` aceptaba cualquier `redirect_scheme`; con un enlace preparado el atacante podía recibir el JWT de sesión de la víctima al finalizar el login de Apple. Ahora solo acepta `llego`, `llegobusiness` o una URL que coincida exactamente con `WEB_AUTH_CALLBACK_URLS` (configurable, separada por comas). Cualquier otro valor responde 400 sin crear state. Además, `/apple/callback` tenía una referencia a `ANDROID_DEEP_LINK` inexistente que causaba 500 en el flujo de error.

---

### Área 2: fix(businesses) — predefinedDeliveryFee en BusinessWithBranchesType (17:49, oct 1)

`fix(businesses): exponer predefinedDeliveryFee en BusinessWithBranchesType`

La app de negocios pide `predefinedDeliveryFee` en `BusinessWithBranchesType`; el campo solo existía en `BusinessType`. `getMyBusinessesWithBranches` fallaba en validación entera y la app no podía cargar sus negocios. Se declara el campo (opcional) y se rellena desde `Business.predefinedDeliveryFee`. Tests validan el fragment de la app y las 97 operaciones de LlegoBussisnes (0 inválidas).

---

### Área 3: fix(branches) — Override diario aplica solo el día de su fecha (17:58, oct 1)

`fix(branches): el override diario de horario solo aplica el día de su fecha`

Un "cerrado hoy" dejaba la sucursal cerrada para siempre; un "abierto hoy" la abría todos los días indefinidamente. Nueva regla en `services/branch_hours.py`: el override con `date` aplica solo ese día en hora de Cuba (America/Havana). `_is_branch_open_at` aplica el override con la fecha del pedido programado. `schedule_to_type` deja de exponer overrides de otro día (iOS/Android los mostraban sin mirar la fecha). `setBranchDailyOverride` valida y normaliza fecha y horas. Tests: 23 en `test_branch_daily_override.py`.

---

### Área 4: fix(tutorials) — Exigir rol admin para gestionar tutoriales (18:02, oct 1)

`fix(tutorials): exigir rol admin para gestionar tutoriales`

`createTutorial`, `updateTutorial`, `deleteTutorial` y `toggleTutorialActive` solo comprobaban que hubiera JWT; cualquier cliente podía gestionar tutoriales o subir hasta 100 MB a S3. Mutations usan ahora `require_role(jwt, info, ["admin"])`. Para REST se añade `require_admin_user_from_header` en `utils/auth.py` (nuevo helper).

---

### Área 5: fix(push) — ADMIN_API_KEY en endpoints REST de push y tokens (18:04, oct 1)

`fix(push): exigir ADMIN_API_KEY en los endpoints REST de push y tokens`

`GET /api/device-tokens/` listaba todos los tokens; `DELETE /api/device-tokens/cleanup-invalid` los borraba en bloque; `POST /api/push/clientes` y `/api/push/negocios` permitían push masivos a todos los dispositivos sin auth. Se protegen con `require_admin_api_key`. `/register` y `/unregister` siguen abiertos (necesarios antes del login).

---

### Área 6: fix(payments) — JWT y rate limit en /payments/validate (18:09, oct 1)

`fix(payments): exigir JWT y rate limit en POST /payments/validate`

Endpoint público que lanzaba Gemini OCR con coste por llamada. Ahora exige JWT (`get_current_user_id_from_header`) y aplica `RATE_LIMIT_UPLOADS` (6/min por usuario). Corregido el `key_func`: no distinguía mayúsculas en "Bearer"; la app iOS manda "bearer" minúscula y todos los usuarios detrás de la misma NAT caían al límite por IP compartida.

---

### Área 7: fix(orders) — Verificar quién escucha cada subscription de pedidos (18:08, oct 1)

`fix(orders): verificar quién escucha cada subscription de pedidos`

`orderTrackingStream` comprobaba que el pedido existiera pero no el acceso; `deliveryLocationUpdated` y `orderUpdated` no pedían JWT; `newBranchOrder` y `branchOrderUpdated` tampoco; `couriersPresenceStream` daba ubicación de todos los mensajeros a cualquier autenticado. Ahora: pedidos usan `OrderService.user_can_access_order`; sucursales usan `access_checker.check_branch_access`; couriers presencia exige admin/manager. Las cuatro subscriptions sin jwt reciben un argumento `jwt: String = null` (cambio aditivo). **Impacto en la app actual**: LlegoBusiness se suscribe sin jwt; hasta que lo envíe no recibirá eventos.

---

### Área 8: feat(orders) — Publicar en tiempo real pedidos de cada sucursal (18:12, oct 1)

`feat(orders): publicar en tiempo real los pedidos de cada sucursal`

`newBranchOrder` y `branchOrderUpdated` existían en el schema pero nadie publicaba en sus canales. `OrderService._publish_branch_order_event` publica en `branch:{id}` al crear y en `branch_updates:{id}` en cada cambio de estado, pago o modificación. Los webhooks de QvaPay/TronDealer publican vía `publish_branch_order_changed`. Publicar solo encola (fallos silenciosos sin romper la operación principal). Limitación multi-worker documentada en context.md §5. Tests: 12 unitarios + 1 end-to-end.

---

### Área 9: fix(payments) — No confirmar pedidos si llega menos dinero (18:13, oct 1)

`fix(payments): no confirmar pedidos QvaPay/USDT si llega menos dinero`

Los webhooks nunca comparaban monto recibido con esperado: 1 centavo confirmaba cualquier pedido. Nuevo estado `UNDERPAID` (guard atómico sobre `PENDING`): la factura/wallet queda en ese estado, el pedido no cambia de estado ni genera payout, se marca con `requiresAttention` sin deadline (para que el worker de timeout no lo cancele), y se crea una entrada de timeline. QvaPay compara contra `invoicedAmount` (nuevo campo) para mantener `QVAPAY_TEST_AMOUNT` funcional. Un depósito adicional sobre wallet `UNDERPAID` ya no se ignora silenciosamente.

---

### Área 10: fix(wallet) — Definir db en branchTransferMoney y branchWithdrawMoney (18:14, oct 1)

`fix(wallet): definir db en branchTransferMoney y branchWithdrawMoney`

Las dos mutations usaban `db.wallet_transactions` sin definir `db`: el dinero se movía y luego el resolver lanzaba `NameError`, así el cliente veía un error aunque la operación fuera exitosa. Fix mínimo: `db = get_database()` antes de leer la transacción.

---

### Área 11: fix(orders) — Plazos de elaboración respetan la hora de pedidos programados (18:04, oct 1)

`fix(orders): los plazos de elaboración respetan la hora de los pedidos programados`

Un pedido para mañana se cancelaba a los 20 min de `ACCEPTED`. Nueva regla en `services/orders_utils.py`: `deadline = max(ahora + plazo_normal, scheduledFor - 30 min)`. Aplica en `update_status`, `mark_order_paid`, `expire_order` (devuelve "deferred" si aún no es hora) y en `deadlineAt` expuesto por GraphQL. Tests: 10 en `test_order_payment_flow.py`.

---

### Área 12: fix(orders) — Integrar auth de subscriptions y avisar pagos incompletos (13:36, oct 2)

`fix(orders): integrar la auth de subscriptions y avisar a la sucursal de pagos incompletos`

Commit de integración tras mergear las dos ramas de Fase 1:
- Una sola autorización de subscriptions: `_authenticate_subscription + access_checker.check_branch_access + SUBSCRIPTION_DENIED_DELAY_SECONDS`. Los tests que simulaban los helpers de otra rama colgaban la suite; unificados.
- Los webhooks de QvaPay y TronDealer publican `branchOrderUpdated` también al marcar un pedido como `UNDERPAID`, para que la sucursal lo vea en vivo.

---

### Puede dar bateo

1. **LlegoBusiness sin jwt en subscriptions — sin eventos hasta actualizar la app**: `newBranchOrder`, `branchOrderUpdated` y `deliveryLocationUpdated` no emiten si no llega jwt. context.md §5 documenta el orden de despliegue: backend primero, luego la app. Hasta que la app actualizada llegue a producción, la sucursal no ve pedidos en tiempo real.

2. **Estado UNDERPAID no conocido por la app de negocios**: Si la app no mapea `UNDERPAID`, los pedidos con pago incompleto quedarán sin estado visible en la UI. Confirmar que la app lo maneja gracefully o que `requiresAttention` es suficiente señal.

3. **WEB_AUTH_CALLBACK_URLS no configurada en producción — Apple Sign-In falla para LlegoWeb**: Si la variable no está en el entorno, `/apple/start` rechazará con 400 las URLs de callback de la web. Verificar que está seteada en Railway/producción.

4. **fix(wallet) — auditar transacciones previas con dinero movido y error retornado**: En producción puede haber transferencias o retiros donde el dinero se movió pero el cliente recibió `NameError`. Evaluar si hay que auditar la BD y notificar a afectados.

5. **Override diario con America/Havana — confirmar que `zoneinfo`/`pytz` está disponible**: Si la librería de zonas no está instalada o la zona no está en la BD del sistema, el cálculo de hora local fallará o usará UTC.

6. **fix(payments) rate limit por usuario — confirmar que el fix está deployado antes de habilitar carga masiva**: Si el fix del `key_func` ("bearer" minúscula) no está en producción, todos los usuarios de la app iOS detrás de una NAT comparten el límite de 6/min.

7. **fix(businesses) predefinedDeliveryFee — confirmar que no rompe to_strawberry_dict**: La advertencia del CLAUDE.md aplica: un campo nuevo en un modelo Pydantic no declarado en el tipo GraphQL destino revienta la query. Verificar que no hay otro tipo que reciba un `Business` sin declarar este campo.

8. **branchOrderUpdated en UNDERPAID — la sucursal recibe el evento pero no puede actuar sin jwt**: Circular: el evento llega solo si la app manda jwt, pero el fix informa sobre UNDERPAID vía ese canal. Antes de que la app tenga jwt, los pagos incompletos no notifican en tiempo real.

9. **SUBSCRIPTION_DENIED_DELAY_SECONDS = 30 s — confirmar timeout del proxy/load balancer**: Si el proxy tiene un timeout de keepalive menor a 30 s, la conexión se cierra antes de que el error llegue al cliente.

10. **fix(tutorials) require_admin_user_from_header — confirmar que la web de tutoriales envía el header correcto**: Si la web de tutoriales envía la sesión con un header distinto al esperado por el nuevo helper, los uploads de video/thumbnail empezarán a dar 401.

---

## 📅 1 de Octubre, 2026

### Resumen de cambios (últimas 24h)

**1 commit** — Fabian1820 (co-authored Claude Opus 5.5). Día dedicado a endurecer la seguridad y lógica de confirmación de transferencias por Atajos.

---

### Área 1: fix(payments) — Confirmación de transferencias por Atajos endurecida (21:10 commit, 14:07 push)

`fix(payments): endurecer la confirmación de transferencias por Atajos`

`confirmTransferByShortcut` presentaba múltiples vectores de abuso y condiciones de carrera:
- Emparejaba solo por el teléfono del perfil (texto libre, sin verificar).
- Tomaba la primera transferencia pendiente sin comparar monto ni moneda: 1 CUP confirmaba cualquier pedido; una transferencia en CUP podía confirmar un pedido en USD.
- El teléfono del perfil ajeno permitía reclamar la transferencia de otra persona.
- Dos confirmaciones concurrentes podían consumir la misma transferencia.

Cambios aplicados:
- **Solo CUP**: el SMS no indica moneda; solo se procesan transferencias en CUP.
- **Cobertura de monto**: la transferencia debe cubrir el total del pedido (se elige la más ajustada); debe estar registrada después de la creación del pedido.
- **Bloqueo por número compartido**: si otra cuenta tiene el mismo teléfono, se rechaza y se pide el ID de transferencia.
- **compare-and-set** sobre `activated=False`: si una confirmación concurrente ganó la transferencia, se prueba la siguiente candidata.
- **Normalización de teléfonos** (`utils/phone.py`): "+53 5XXX XXXX" del perfil coincide con "5XXXXXXX" del SMS.
- Las transferencias nuevas guardan `phone_national`; las antiguas se buscan por variantes de formato.
- Tests: `tests/test_shortcut_transfer_confirm.py` (40 tests). Suite completa: mismos 36 fallos preexistentes, sin regresiones.

---

### Puede dar bateo

1. **Transferencias antiguas sin `phone_national` — búsqueda por variantes puede no cubrir todos los formatos históricos**: Si el teléfono en BD tiene un formato no contemplado (con guión, con código de país distinto), la confirmación por teléfono fallará para esas transferencias. Confirmar que las variantes cubren todos los casos en producción.

2. **compare-and-set y worker de timeouts — condición de carrera potencial**: Si el worker cancela una transferencia pendiente justo cuando llega un SMS, el compare-and-set puede rechazar la confirmación legítima. Confirmar la interacción entre el worker y el nuevo flujo.

3. **Bloqueo por número compartido — impacto en usuarios con chip compartido**: En Cuba es habitual que varios perfiles tengan el mismo teléfono. Estos usuarios no podrán confirmar por teléfono sin el ID de transferencia. Verificar que el mensaje de error es suficientemente claro.

4. **Período de transición de `phone_national` — confirmar que el endpoint de registro ya lo guarda**: Si el endpoint que registra transferencias aún no guarda `phone_national` en producción, las transferencias "nuevas" tampoco lo tendrán y la búsqueda caerá en las variantes de formato.

---

## 📅 30 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 28 de septiembre (cobertura de tests de push notifications, contrato FCM, JWT de APNs).

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **28 de Septiembre** y anteriores fueron eliminadas el 6 de Octubre al superar los 7 días de antigüedad (política de retención semanal).
