# Registro de Análisis de Cambios — LlegoBackend

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

## 📅 24 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit del período es el "Analisis diario Claude" automático generado en el análisis del 23-sep. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 23 de septiembre.

---

> ⚠️ **Nota de mantenimiento**: La entrada del **23 de Septiembre** fue eliminada el 1 de Octubre al superar los 7 días de antigüedad (política de retención semanal). La del **17 de Septiembre** fue eliminada el 25 de Septiembre. Las entradas del **16 de Septiembre** y anteriores fueron eliminadas progresivamente.
