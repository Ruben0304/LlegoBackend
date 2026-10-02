# Registro de Análisis de Cambios — LlegoBackend

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

### Área 10: fix(kyc) — Emitir log de finalización de /kyc/global/evaluate (18:13, oct 1)

`fix(kyc): emitir el log de finalización de /kyc/global/evaluate`

El endpoint devolvía la respuesta con `return` directo antes del `logger.info("kyc_evaluation_completed...")`; las evaluaciones KYC completadas no dejaban rastro en logs. Fix mínimo: asignar a `response`, loguear, devolver.

---

### Área 11: fix(wallet) — Definir db en branchTransferMoney y branchWithdrawMoney (18:14, oct 1)

`fix(wallet): definir db en branchTransferMoney y branchWithdrawMoney`

Las dos mutations usaban `db.wallet_transactions` sin definir `db`: el dinero se movía y luego el resolver lanzaba `NameError`, así el cliente veía un error aunque la operación fuera exitosa. Fix mínimo: `db = get_database()` antes de leer la transacción.

---

### Área 12: fix(orders) — Plazos de elaboración respetan la hora de pedidos programados (18:04, oct 1)

`fix(orders): los plazos de elaboración respetan la hora de los pedidos programados`

Un pedido para mañana se cancelaba a los 20 min de `ACCEPTED`. Nueva regla en `services/orders_utils.py`: `deadline = max(ahora + plazo_normal, scheduledFor - 30 min)`. Aplica en `update_status`, `mark_order_paid`, `expire_order` (devuelve "deferred" si aún no es hora) y en `deadlineAt` expuesto por GraphQL. Tests: 10 en `test_order_payment_flow.py`.

---

### Área 13: fix(orders) — No cerrar al instante las subscriptions denegadas (18:54, oct 1)

`fix(orders): no cerrar al instante las subscriptions denegadas`

Con Apollo Kotlin 4, `error + complete` en graphql-ws no lanza excepción: `collectWithReconnect` se volvía a suscribir inmediatamente, creando un bucle de reconexión a velocidad de RTT por sucursal y dispositivo. Ahora: sin credenciales, el stream queda abierto sin emitir hasta que el cliente lo cierre (warning único al abrirlo); con jwt inválido o sin acceso, el error llega tras `SUBSCRIPTION_DENIED_DELAY_SECONDS` (30 s).

---

### Área 14: fix(orders) — Pings de ubicación del chofer no publican branchOrderUpdated (18:40, oct 1)

`fix(orders): los pings de ubicación del chofer no publican branchOrderUpdated`

`updateDeliveryLocation` (llamado cada 10 s por AppMensajeros) publicaba el pedido entero en `branch_updates:{branchId}` en cada ping. `_emit_tracking_event` acepta ahora `publish_to_branch` (True por defecto); `updateDeliveryLocation` lo pasa como `False`. Los canales `deliveryLocationUpdated` y `orderTracking` del cliente siguen recibiendo cada ping.

---

### Área 15: fix(orders) — Integrar auth de subscriptions y avisar pagos incompletos (13:36, oct 2)

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

5. **Tests que mockean el flujo anterior — posible falso positivo**: Si otros tests del sistema mockean `confirmTransferByShortcut` con el comportamiento viejo, seguirán en verde aunque el contrato haya cambiado. Revisar mocks existentes.

---

## 📅 30 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 28 de septiembre (cobertura de tests de push notifications, contrato FCM, JWT de APNs).

---

## 📅 28 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**1 commit** — brianmojena (co-authored Claude Opus 5.5). Día dedicado a ampliar la cobertura de tests de push notifications: contrato de payload FCM, pushes de pagos, mutations de business_types y JWT de APNs.

---

### Área 1: test(push) — Cobertura completa del contrato de payload y JWT de APNs (17:02)

- **`test(push): contrato de payload, pagos, business_types y JWT de APNs`** (17:02, brianmojena) — Nuevo archivo `tests/test_push_notification_contract.py` (311 líneas). Completa la cobertura de notificaciones push:
  - **Contrato FCM por tipo**: `data` solo strings (no objetos), claves que consumen las apps (`type`, `orderId`, `status`) y `channel_id llego_orders`. Garantiza que un campo de tipo dict/list en el payload no rompa silenciosamente el envío en FCM.
  - **Pushes de pagos**: "comprobante enviado" (`payment_proof_submitted`) y "pago confirmado por el negocio". Verifica que llegan al bundle y audiencia correctos según el fix de enrutamiento del 25-sep.
  - **Mutations de business_types**: audiencia, bundle y payload. Confirma que `updateBusinessType` y similares envían el push al segmento correcto.
  - **JWT de APNs real**: firmado con clave EC P-256 efímera (ES256, `kid`, `iss`, `iat`); testea el caché del JWT y su renovación antes de expirar.
  - **Resiliencia a timeouts**: FCM/APNs con timeout no rompen el flujo del pedido ni desactivan el token.

---

### Puede dar bateo

1. **Clave EC P-256 efímera — `kid` debe coincidir con el registrado en Apple Developer**: Si el código genera un `kid` distinto en cada arranque o no coincide con el configurado en el Apple Developer Portal, APNs rechazará todos los JWT con 403 `InvalidProviderToken`. Confirmar que el `kid` es estático o se carga desde config y coincide con el registrado.

2. **Caché del JWT de APNs en memoria — se pierde en cada reinicio**: Si el caché se almacena en memoria de proceso (no Redis ni DB), cada deploy o reinicio arranca sin caché. No es un bug crítico (APNs admite nuevos JWT), pero si la renovación ocurre muy cerca de la expiración (~5 min de margen de APNs) puede haber una ventana de rechazo. Confirmar el almacenamiento del caché.

3. **Contrato FCM `data` solo strings — un campo `int`/`bool`/`dict` añadido después rompe silenciosamente todo el envío**: El test lo verifica en el estado actual, pero no hay validación en runtime que lo garantice para campos futuros. Considerar una función helper `to_fcm_data_dict()` que convierta todos los valores a string antes de enviar.

4. **Tests con mocks de FCM/APNs — comportamiento real puede diferir**: Si FCM cambia el formato del error de timeout o APNs cambia el código de un JWT inválido, los tests seguirán en verde pero producción fallará. Complementar con un test de integración contra sandbox de APNs o proyecto FCM de prueba si es posible.

5. **`channel_id llego_orders` fijo en Android — usuarios que desactivaron el canal no reciben nada**: Si un usuario de Android desactivó el canal `llego_orders` en los ajustes del sistema, ningún push de pedidos llegará. No hay fallback a otro canal. Confirmar si es un caso conocido y si se quiere manejar.

---

## 📅 27 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit del período es el "Analisis diario Claude" automático generado en el análisis del 26-sep. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 25 de septiembre (enrutamiento de push notifications, tokens sin bundleId, desactivación de tokens APNs).

---

## 📅 26 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit del período es el "Analisis diario Claude" automático del 25-sep. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 25 de septiembre (enrutamiento de push notifications, tokens sin bundleId, desactivación de tokens APNs).

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

> ⚠️ **Nota de mantenimiento**: Las entradas del **24 de Septiembre** y anteriores fueron eliminadas el 2 de Octubre al superar los 7 días de antigüedad (política de retención semanal).
