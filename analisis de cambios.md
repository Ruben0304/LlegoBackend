# Registro de Análisis de Cambios — LlegoBackend

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
