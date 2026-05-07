# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 7 de Mayo, 2026

### Resumen de cambios (últimas 24h)

**Áreas: Pagos Stripe (live), sistema de vehículos de mensajeros, rendimiento del feed**

| Commit | Autor | Descripción |
|--------|-------|-------------|
| `5830594` | Ruben0304 | feat(payments): Stripe live, llamadas async y notificaciones push |
| `96503d8` | Ruben0304 | fix(payments): eliminar requisito prematuro de `paymentIntentId` en creación de orden |
| `dca075c` | brianmojena | feat: catálogo de vehículos y mutación `link_vehicle` |
| `652eee7` | brianmojena | fix: crash en `DeliveryPerson` con valores legacy de `vehicleType` |
| `f1a3ed7` | brianmojena | perf(feed): eliminar N+1 en categorías con batch fetch y DataLoader |

**Contexto general:** Día con actividad intensa y bien documentada. Ruben cerró la integración de Stripe en producción y Brian completó el sistema de vehículos de mensajeros (bicicleta/triciclo) y una mejora de rendimiento significativa en el feed.

### Análisis de riesgos y consideraciones

#### 🔴 Riesgos altos

1. **Stripe key live en el commit**
   - El commit `5830594` menciona explícitamente _"Set live Stripe secret key configuration"_. Si la clave fue incluida literalmente en el código fuente (en lugar de una variable de entorno), está expuesta en el historial de git de forma permanente, incluso si se elimina en un commit posterior.
   - **Acción urgente:** Verificar que `STRIPE_SECRET_KEY` se lee de variable de entorno y no está hardcodeada. Si llegó a estar en el código, rotar la clave en el dashboard de Stripe inmediatamente.

2. **Breaking change en `VehicleType`: eliminación de `moto`, `auto`, `a_pie`**
   - Los tipos antiguos se reemplazan por `bicicleta` y `triciclo`. El validator de Pydantic convierte valores desconocidos a `None` (fix de `652eee7`), lo que evita crashes, pero cualquier lógica downstream que asuma un `vehicleType` no-`None` (cálculos de tarifa, rutas, filtros) recibirá `None` silenciosamente y puede producir comportamiento incorrecto.
   - **Acción recomendada:** Auditar todos los lugares donde se consume `DeliveryPerson.vehicleType` para asegurar que manejan `None` explícitamente.

3. **`A_PIE` fallbacks eliminados completamente**
   - El commit `dca075c` indica _"Remove all A_PIE fallbacks (replaced with None)"_. Si algún endpoint de frontend o app móvil aún envía `a_pie` como valor, el backend lo convertirá a `None` sin error visible. Mensajeros con ese valor en DB quedarán sin tipo de vehículo asignado.
   - **Acción recomendada:** Coordinar con el equipo mobile/frontend para garantizar que ya no se envían los tipos legacy antes del deploy en producción.

#### 🟡 Riesgos medios

4. **Auto-seed del catálogo de vehículos en el lifespan hook**
   - El catálogo (bicicleta + triciclo) se siembra en cada startup. Si el seed usa `upsert`, es seguro. Si usa `insert`, creará documentos duplicados en cada reinicio.
   - **Verificación:** Confirmar que `upsert_seed` es verdaderamente idempotente (verifica existencia antes de insertar o usa `update_one(upsert=True)`).

5. **Stripe SDK envuelto en `asyncio.to_thread()`**
   - Enfoque correcto para SDK bloqueante. Riesgo: si el thread pool del event loop se satura bajo carga alta, las llamadas de Stripe se encolarán. En Railway con pocos workers, monitorear el comportamiento bajo carga concurrente.

6. **Notificaciones APNs/FCM en el flujo de pago**
   - Si el servicio de notificaciones falla, el flujo de pago no debería verse afectado. Verificar que los errores de notificación están capturados y no propagan excepciones que cancelen la transacción.

7. **Scope del DataLoader de categorías**
   - El DataLoader resuelve `category_name` en un solo round-trip. Riesgo clave: si el cache del DataLoader es global (compartido entre requests) en lugar de por-request, usuarios distintos podrían ver nombres de categoría stale o de otro usuario.
   - **Verificación:** Confirmar que el `category_loader` se instancia por request (en el contexto de la request de GraphQL), no a nivel de módulo.

#### 🟢 Mejoras positivas

8. **N+1 eliminado en el feed** — `get_feed_products` pasó de una query por producto a una sola query batch por request. Mejora de rendimiento significativa en el endpoint más usado.

9. **Stripe async no bloquea el event loop** — las llamadas a Stripe ya no degradan el throughput del servidor durante operaciones de pago.

10. **Todos los commits con mensajes descriptivos** — sin commits con mensajes vagos en este día. Excelente.

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

## 📅 30 de Abril, 2026

### Resumen de cambios (últimas 24h)

**Área principal: Sistema de mensajeros (couriers) — unificación de endpoints de mapa**

| Commit | Autor | Descripción |
|--------|-------|-------------|
| `6b81661` | brianmojena | feat(courier): incluye la entrega activa en `available_orders_for_delivery` |

**Contexto:** Antes, el frontend llamaba a `myCurrentDelivery` y `availableOrdersForDelivery` por separado, generando race conditions donde el pin del pedido aceptado desaparecía del mapa. Ahora el backend siempre antepone la entrega activa del courier a la lista `availableOrdersForDelivery`, sin importar el timing del polling.

### Análisis de riesgos y consideraciones

#### 🔴 Riesgos altos

1. **El frontend debe distinguir el primer ítem (entrega activa) del resto (disponibles para aceptar)**
   - Si el frontend renderiza todos los ítems de `availableOrdersForDelivery` de forma idéntica, el courier podría ver su propia entrega actual como un pedido "disponible para aceptar" de nuevo, o peor, intentar aceptarla otra vez.
   - **Acción recomendada:** Verificar que el frontend identifica el primer elemento (la entrega activa) y lo renderiza/trata de forma diferenciada al resto de pins del mapa.

#### 🟡 Riesgos medios

2. **Caso donde el courier no tiene entrega activa**
   - El commit dice que siempre se _prepend_ la entrega activa. Hay que asegurar que cuando `get_current_delivery` retorna `None` (sin entrega activa), la función no intente insertar `None` al inicio de la lista ni lance un error de índice.
   - **Consideración:** Revisar el bloque de código que hace el prepend para confirmar que el caso `None` está manejado.

3. **Acoplamiento entre `get_current_delivery` y `available_orders_for_delivery`**
   - Ahora `available_orders_for_delivery` depende internamente de `get_current_delivery`. Si esta consulta falla o se vuelve lenta, el endpoint de órdenes disponibles también se degrada.
   - **Consideración:** Evaluar si vale la pena atrapar excepciones de `get_current_delivery` dentro del resolver de `available_orders_for_delivery` para que un fallo parcial no rompa el listado completo.

#### 🟢 Mejoras positivas

4. **Eliminación de race condition en el mapa**
   - Con una única fuente de verdad en el backend, el frontend ya no necesita coordinar dos llamadas independientes. Reduce complejidad del cliente y hace el estado del mapa más confiable.

5. **Sesión sin commits con mensajes sin descripción** — a diferencia de días anteriores, todos los commits de hoy tienen mensajes claros.

---
