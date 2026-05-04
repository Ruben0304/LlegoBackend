# Registro de Análisis de Cambios — LlegoBackend

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

## 📅 29 de Abril, 2026

### Resumen de cambios (últimas 24h)

**Área principal: Sistema de mensajeros (couriers)**

| Commit | Autor | Descripción |
|--------|-------|-------------|
| `0b4fe77` | brianmojena | fix(courier): `accept_delivery` idempotente + manejo de race conditions |
| `e9aa50b` | brianmojena | fix(courier): captura todas las excepciones en mutaciones de courier + logging |
| `0ec439a` | brianmojena | fix(courier): añade `AWAITING_DELIVERY_ACCEPTANCE` a `get_current_delivery` + logs |
| `37f6aba` | brianmojena | fix(couriers): limpia estado del mensajero al cancelar/entregar pedido |
| `24784cf` | brianmojena | fix(couriers): auto-crea registro `delivery_person` en primera aceptación |
| `09ab052` | brianmojena | Añade `PENDING_PAYMENT` al query de estado de pedidos |
| `c60045c` | Ruben0304 | feat(couriers): mutación `adminPushCourierLocation` para simulación en mapa |
| `948613c` | Ruben0304 | feat(couriers): enriquece `CourierPresenceType` con perfil del mensajero |
| `82fa35b` | Fabian1820 | *(mensaje sin descripción: "fdvfdvb")* |
| `1c1220c` | Fabian1820 | *(mensaje sin descripción: "hvhj")* |

### Análisis de riesgos y consideraciones

#### 🔴 Riesgos altos

1. **Commits sin mensajes descriptivos (`fdvfdvb`, `hvhj`) de Fabian1820**
   - Es imposible saber qué cambiaron sin inspeccionar el diff directamente.
   - Si introducen bugs, serán muy difíciles de rastrear en el historial.
   - **Acción recomendada:** Revisar estos diffs manualmente. Adoptar convención de mensajes descriptivos.

2. **Auto-creación de `delivery_person` en primera aceptación**
   - Si dos requests llegan simultáneamente para el mismo usuario, podría haber race condition en la creación del documento, generando duplicados en MongoDB.
   - Depende de si hay un índice único por `user_id` en la colección `delivery_persons`.
   - **Acción recomendada:** Confirmar que existe un índice único o usar `upsert` atómico.

#### 🟡 Riesgos medios

3. **Idempotencia de `accept_delivery` basada en `deliveryPersonId`**
   - La lógica retorna el estado actual si el courier ya está asignado. Correcto para reintentos.
   - Pero si el check de idempotencia ocurre justo cuando otro courier también ganó la carrera y se está actualizando, podría retornar un falso positivo.
   - **Consideración:** Verificar que el re-fetch tras `None` en `set_delivery_person` es verdaderamente atómico.

4. **Limpieza de estado del mensajero en cancel/deliver**
   - `update_status` ahora llama a `delivery_repo.complete_delivery()` cuando el estado pasa a `CANCELLED` o `DELIVERED`.
   - Si `complete_delivery()` falla silenciosamente, el mensajero queda bloqueado.
   - **Acción recomendada:** Asegurarse de que `complete_delivery()` loguea errores y que el error no sea silenciado.

5. **`AWAITING_DELIVERY_ACCEPTANCE` en `get_current_delivery`**
   - Cubre la ventana de race entre `set_delivery_person` y `update_status`. Es una buena solución.
   - Riesgo menor: si un pedido queda en este estado indefinidamente (fallo entre los dos pasos), el mensajero aparecerá con un pedido "fantasma".
   - **Consideración:** Evaluar si hace falta un timeout o limpieza periódica para este estado intermedio.

#### 🟢 Mejoras positivas

6. **`adminPushCourierLocation` para simulación**
   - Facilita el testing del mapa en vivo sin mensajeros reales. Muy útil para QA.

7. **Enriquecimiento de `CourierPresenceType` con perfil**
   - Batch query de Mongo por snapshot es eficiente. Bien implementado.

8. **Logging `[COURIER]` en mutaciones**
   - Mejora significativa para diagnóstico en Railway.

---
