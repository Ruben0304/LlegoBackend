# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 11 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 10 de octubre (guard de vehículo en `acceptOrderForPayment` sin mensaje claro, race condition vehículo vs. aceptación, mensajeros existentes sin vehículo que no pueden aceptar pedidos, código downstream que asume `vehicle` siempre presente, pedidos en curso si se retira el vehículo durante la entrega).

---

## 📅 10 de Octubre, 2026

### Resumen de cambios (últimas 24h)

**1 commit** — Fabian1820. Merge de feature: vehículo desvinculado del modelo base de mensajero pero obligatorio para aceptar pedidos.

---

### Área 1: merge — deliveryPerson sin vehículo, vehículo obligatorio para aceptar pedidos (16:54)

`merge: deliveryPerson sin vehículo y vehículo obligatorio para aceptar pedidos`

Merge de una rama de feature. Cambios combinados:
- Un mensajero puede existir en el sistema sin vehículo asignado (campo ahora opcional en el modelo/BD).
- Al intentar aceptar un pedido, el sistema verifica que el mensajero tenga un vehículo activo; sin él, la aceptación se rechaza.

Probablemente responde al flujo de onboarding donde un mensajero se registra antes de asignarle su vehículo.

---

### Puede dar bateo

1. **Guard de vehículo en `acceptOrderForPayment` — mensaje de error claro**: Si no se devuelve un error descriptivo cuando falta vehículo, la app mostrará un fallo genérico. Confirmar que el mensaje llega al mensajero explicando qué falta.

2. **Race condition vehículo vs. aceptación**: Si entre el check de vehículo y el insert del pedido un admin elimina/desactiva el vehículo del mensajero, el guard pasa pero el mensajero actúa sin vehículo. Confirmar si hay lock/transacción.

3. **Mensajeros existentes sin vehículo**: Los mensajeros ya registrados que no tengan vehículo no podrán aceptar pedidos. La app debe guiarlos a registrar un vehículo en lugar de mostrar un error genérico.

4. **Código downstream que asume `vehicle` siempre presente**: Si el campo vehículo pasó de requerido a opcional, cualquier acceso a `delivery_person.vehicle.X` sin verificar `None` lanzará `AttributeError`. Revisar rutas de tracking, notificaciones y el propio `acceptOrderForPayment`.

5. **Pedidos en curso si se elimina el vehículo**: El guard aplica al aceptar, pero si durante una entrega activa un admin retira el vehículo del mensajero, hay que confirmar que la entrega en curso no se ve afectada.

---

## 📅 8 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit del período fue el "Analisis diario Claude" del bot. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 5 de octubre (guard de mensajero activo, ventana de concurrencia en `acceptOrderForPayment`, merge de Fase 2a sin descripción).

---

## 📅 7 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy. El único commit fue el "Analisis diario Claude" del bot.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 5 de octubre (guard de mensajero activo, ventana de concurrencia en `acceptOrderForPayment`, merge de Fase 2a sin descripción).

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

> ⚠️ **Nota de mantenimiento**: Las entradas del **3 de Octubre** y anteriores fueron eliminadas el 11 de Octubre al superar los 7 días de antigüedad (política de retención semanal).
