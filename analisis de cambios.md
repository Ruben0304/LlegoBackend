# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 8 de Mayo, 2026

### Resumen de cambios (últimas 24h)

**Áreas: Sistema de vehículos (nuevo módulo), pagos Stripe en producción, feed de productos**

| Commit | Autor | Descripción |
|--------|-------|-------------|
| `f1a3ed7` | brianmojena/Claude | perf(feed): fix N+1 queries en categorías con DataLoader |
| `652eee7` | brianmojena/Claude | Fix crash en DeliveryPerson por legacy vehicleType values |
| `dca075c` | brianmojena/Claude | feat: catálogo de vehículos + mutación link_vehicle |
| `96503d8` | Ruben0304/Claude | fix(payments): quitar requerimiento prematuro de paymentIntentId en órdenes |
| `58305943` | Ruben0304/Claude | feat(payments): Stripe live, llamadas async y notificaciones push en pagos |

### Análisis de riesgos y consideraciones

#### 🔴 Riesgos altos

1. **Stripe en modo live — clave de producción activa**
   - El commit activa la clave de Stripe live. Cualquier error en el flujo de pagos afecta dinero real.
   - Las llamadas están envueltas en `asyncio.to_thread()` (correcto), pero si el thread pool del servidor se agota bajo carga, los pagos se encolarán silenciosamente sin feedback al cliente.
   - **Acción urgente:** Verificar en Stripe Dashboard que los PaymentIntents llegan desde producción. Monitorear logs en Railway para excepciones de Stripe. Confirmar que el webhook (si existe) usa idempotency keys.

2. **Cambio de enum VehicleType — documentos legacy quedan con vehicleType=None**
   - El enum pasó de `moto/auto/a_pie` a `bicicleta/triciclo`. Los documentos legacy se deserializan con `vehicleType=None` via el `field_validator`.
   - Si alguna lógica de negocio hace `if delivery_person.vehicleType:` o asume que el campo no es None, fallará silenciosamente en documentos legacy.
   - **Acción recomendada:** Revisar todos los usos de `vehicleType` en el codebase. Evaluar migración de datos en MongoDB para convertir los valores legacy antes del siguiente despliegue.

3. **Auto-seed de vehículos en el lifespan del servidor**
   - `upsert_seed` corre en cada arranque. Si no es verdaderamente idempotente (upsert por slug o campo único), puede crear duplicados en la colección `vehicles` en reinicios frecuentes.
   - **Acción recomendada:** Confirmar que `upsert_seed` usa `update_one(..., upsert=True)` con un índice único por `slug`.

#### 🟡 Riesgos medios

4. **paymentIntentId eliminado del create_order — flujo en 2 etapas**
   - Ahora el PaymentIntent se crea solo en `initiatePayment()` (post-aceptación). Si una orden llega a `PENDING_PAYMENT` y `initiatePayment()` nunca se llama (abandono del cliente), queda en estado indefinido sin PaymentIntent.
   - **Consideración:** Verificar si existe mecanismo de expiración o limpieza para órdenes en `PENDING_PAYMENT` sin PaymentIntent asociado.

5. **DataLoader para categorías en el feed**
   - El DataLoader agrupa peticiones en el mismo tick del event loop. Si el feed es cargado en múltiples resolvers simultáneos, la batching window puede ser demasiado corta para ser efectiva.
   - **Consideración:** Probar con un feed de 20+ productos distintos y confirmar que los round-trips a MongoDB se reducen significativamente.

6. **link_vehicle — validación de existencia del vehicleId**
   - La mutación vincula el `vehicleId` al mensajero autenticado. No está explícito en el commit que se valide que el `vehicleId` existe en el catálogo antes de persistirlo en DeliveryPerson.
   - **Consideración:** Confirmar que `VehicleRepository.get_by_id(vehicleId)` es invocado y lanza error si no existe, antes de hacer el update en DeliveryPerson.

#### 🟢 Mejoras positivas

7. **Notificaciones push reales en el flujo de pago**
   - Se reemplazaron los `# TODO` de APNs/FCM con llamadas reales. El negocio recibe push al recibir comprobante; el cliente recibe push al confirmar pago. Cierra el loop de comunicación sin polling.

8. **Stripe async con `asyncio.to_thread()`**
   - El SDK sincrónico de Stripe ya no bloquea el event loop de FastAPI. Corrección técnica importante para estabilidad bajo carga concurrente.

9. **Catálogo de vehículos en MongoDB**
   - Reemplaza el enum hardcoded por una colección dinámica, permitiendo agregar tipos de vehículo sin cambios de código.

---

## 📅 5 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad de backend hoy.
- Seguimiento vigente: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).
- No hay riesgos nuevos que reportar.

---

## 📅 4 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad de backend hoy.
- Seguimiento pendiente: verificar en producción que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).
- No hay riesgos nuevos que reportar.

---

## 📅 3 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad de backend hoy.
- Seguimiento pendiente: verificar que el frontend distingue correctamente el primer ítem (entrega activa) del resto de pins en `available_orders_for_delivery` (fix del 30 de abril).
- No hay riesgos nuevos que reportar.

---

## 📅 2 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- Sin actividad de backend hoy. El seguimiento del fix de race condition en `available_orders_for_delivery` (April 30) continúa vigente en producción.
- No hay riesgos nuevos que reportar.

---

## 📅 1 de Mayo, 2026

### Resumen de cambios (últimas 24h)

Sin commits de desarrollo nuevos desde el análisis de ayer. Solo el commit automático de "Analisis diario Claude".

#### Consideraciones del día

- El fix de race condition en `available_orders_for_delivery` (ayer, April 30) merece seguimiento activo hoy en producción: verificar que el frontend diferencia correctamente el primer ítem (entrega activa) del resto de pins disponibles.
- No hay riesgos nuevos que reportar.

---
