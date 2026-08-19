# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 19 de Agosto, 2026

### Resumen de cambios (últimas 24h)

**2 commits** — brianmojena. Feature grande: métricas de usuarios administradores segmentadas por app, con tracking de actividad en tiempo real y nuevos índices en MongoDB.

---

### Área 1: Users — `admin_user_metrics` con segmentación por app (1 commit — brianmojena, 22:27)

- **`feat(users): admin user metrics segmented by app`** — Cierra dos gaps estructurales importantes y agrega la primera query de time-series al backend:

  1. **Nuevo campo `User.lastSeenAt`** — No existía ninguna señal de actividad (sin `lastSeenAt`/`lastLoginAt`, JWTs stateless de 30 días, sin colección de sesiones ni analytics). Se agrega `lastSeenAt` escrito por `LastSeenExtension` en `on_request_end` con throttle de 1 h en memoria y fire-and-forget, costando como máximo 1 write por usuario/hora/worker sin añadir latencia perceptible.

  2. **Nueva query GraphQL `admin_user_metrics`** — Usuarios registrados vs activos desglosados en 3 segmentos (customers, couriers, businesses) + serie temporal de registros por día (`$dateToString`). Segmentación por joins con `delivery_persons` y `businesses/branches/business_access`. El set "activo" une `lastSeenAt` con proxies conductuales pre-existentes (órdenes, búsquedas, registros de courier) para que la métrica sea útil de inmediato.

  3. **Nuevos índices en colección `users`** — `createdAt` y `lastSeenAt` (antes solo tenía índice text).

  4. **`UserType` actualizado** — `lastSeenAt` declarado en el tipo GraphQL siguiendo el patrón documentado en CLAUDE.md para evitar "unexpected keyword argument".

---

### Puede dar bateo

1. **`LastSeenExtension` con throttle en memoria — no es distribuido ni sobrevive reinicios**: El dict de throttle vive en cada worker Python por separado. Con N workers (uvicorn/gunicorn multi-process), un usuario puede generar hasta N writes/hora. En un reinicio del proceso, el throttle se resetea y todos los usuarios activos en ese momento disparan un write simultáneamente contra MongoDB.

2. **Fire-and-forget sin retry robusto**: Si el write de `lastSeenAt` falla (timeout MongoDB, red), el error se pierde silenciosamente. No hay mecanismo de reintentos ni dead-letter para estos writes.

3. **`$dateToString` con timezone UTC — desfase 5 h para Cuba**: Las series temporales de signups-per-day agrupan por fecha UTC. Un registro hecho a las 21:00 hora Cuba (02:00 UTC del día siguiente) cae en el día incorrecto en las métricas.

4. **Segmentación por joins sin índice compuesto garantizado**: Las queries que cruzan `delivery_persons` y `businesses/branches` para segmentar pueden ser costosas en datasets grandes si no hay índice en los campos de join relevantes.

5. **`multiRoleUsers` — confirmar que no genera double-counting en totales**: Si el campo `multiRoleUsers` no se descuenta al sumar usuarios por segmento, el total puede superar el número real de usuarios únicos activos.

6. **Nuevos índices en colección con docs existentes — confirmar build en background**: Agregar índices a una colección poblada puede causar degradación de escrituras si no se construyen en background en MongoDB Atlas.

7. **`lastSeenAt` en `UserType` — confirmar que todos los resolvers que construyen `UserType(**to_strawberry_dict(user))` siguen funcionando**: El CLAUDE.md documenta este patrón como fuente recurrente de bugs. Cualquier resolver que construya `UserType` sin incluir `lastSeenAt` en el dict fallará con "unexpected keyword argument" en runtime.

---

## 📅 18 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 17 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 15 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 14 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 13 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 12 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

#### Seguimientos vigentes

- **`compute_fee_recommendation` — fees de valor muy bajo no filtrados; filtra negativos pero no $0.00 ni valores anómalos cercanos a cero, lo que podría sesgar la mediana de recomendación hacia abajo sin advertencia (Ago 5)**.
- **Merge conflictos `domain/models.py`/`schema/businesses/types.py` — confirmar que `predefinedDeliveryFee` está correctamente declarado en ambos y no hay campo huérfano que rompa `BusinessType` (Ago 5)**.
- **Índice único parcial branch delivery requests — confirmar drop+recreate del índice previo en MongoDB, no solo el nuevo (Ago 5)**.
- **`bypass_authorization` en `get_order_tracking` — confirmar que no es inyectable como argumento GraphQL desde la query pública (Ago 5)**.
- **Presigned URLs de evidencia KYC — pueden expirar antes de que el admin revisor las visualice si la respuesta es cacheada (Ago 5)**.
- **`services/courier_presence.py` — confirmar thread-safety para requests HTTP concurrentes de `admin_couriers_presence` (Ago 5)**.
- **`admin_orders` sin límite máximo de resultados — riesgo de OOM/timeout en datasets grandes sin filtros (Ago 5)**.
- **`AiRagService` como singleton perezoso — estado mutable compartido entre requests concurrentes, race conditions posibles (Jul 28)**.
- **Índice text sobre `products`/`branches.name` — MongoDB solo permite uno por colección; confirmar no conflicto con índice text existente (Jul 28)**.
- **`query_batch_points` con `with_payload=True` — devuelve vacío silencioso si no soportado; confirmar versión Qdrant en producción (Jul 28)**.
- **Complements con Haiku Batch — confirmar soporte de `json_schema` en endpoint Batch de Haiku 4.5 (Jul 28)**.
- **`generate_embeddings_batch` — orden de vectores no garantizado; asignación cruzada silenciosa posible (Jul 28)**.
- **Sucursales mono-producto excluidas de reevaluación — complements stale si catálogo se redujo a 1 producto (Jul 28)**.
- **Batch API — polling sin guardia de solapamiento entre corridas nocturnas (Jun 26)**.
- **Fingerprint por nombre — cambios no-nombre no detectados en índice incremental (Jun 26)**.
- **Índice incremental sin rollback — fingerprint actualizado pero doc no escrito (Jun 26)**.
- **RAG agéntico Turn 1 sin tool call — Turn 2 con contexto vacío (Jun 26)**.
- **Workers nocturnos encadenados sin aislamiento de errores (Jun 26)**.
- **`ANTHROPIC_API_KEY` no configurada en producción — servicios de IA fallarán (Jun 23)**.
- **Sync client en thread pool — pool agotado bajo alta concurrencia de streaming (Jun 23)**.
- **`max_tokens=8192` — monitorear costos Anthropic (Jun 23)**.
- **Prompts DeepSeek reutilizados en Claude — formato `suggested_product_ids` puede romperse (Jun 23)**.
- **Bypass de cuota sin audit log — abuso con cuenta privilegiada comprometida (Jun 23)**.
- **e2e test con API Anthropic real en CI — costo por PR (Jun 23)**.
- **`asyncio.Queue` sin timeout — consumer lento o cliente desconectado dejan thread corriendo (Jun 23)**.
- **Workers nocturnos coexistiendo — contención Qdrant (Jun 19)**.
- **`priceConfidence` antes de usar `priceTier` en frontend (Jun 19)**.
- **MMR-lite penaliza tiendas mono-categoría (Jun 19)**.
- **Colección `users` en Qdrant para vectores de gusto (Jun 19)**.
- **`exchangeRate` cero/ausente en posicionamiento de precios (Jun 19)**.
- **`_user_to_type()` potencial N+1 en lista de usuarios (Jun 19)**.
- **Re-embedding masivo por `TEXT_FIELDS` — costo Gemini (Jun 19)**.
- **`reindex_businesses_qdrant` puede dispararse involuntariamente (Jun 19)**.
- **Backfill con docs crudos — tipos incorrectos silenciosos (Jun 19)**.
- **`delete_by_mongo_id` requiere payload index de `mongo_id` (Jun 19)**.
- **`acceptingOrders` — retrocompatibilidad con documentos sin el campo**.
- **`dailyOverride.date` sin timezone explícita — desfase UTC vs Cuba**.
- **`setBranchDailyOverride` — sin validación de rango de horas confirmada**.
- **Threshold 0.60 → 0.45 — aumento de ruido en resultados de búsqueda**.
- **`getBranchesForProduct` — doble query Qdrant + MongoDB con top-50**.
- **`getSimilarProducts/Branches` — UUID no encontrado en Qdrant**.
- **`Especialmente para Ti` — vector promedio sin normalización explícita**.
- **Ads auth migrado a `require_role` para managers**.
- **`check_compatibility=False` en qdrant-client**.
- **Merge manual de conflictos (Jun 16) — verificar integridad**.
- **Índices en colecciones existentes — confirmar background build**.
- **`asyncio.to_thread` — pool de threads por defecto agotado bajo alta concurrencia**.
- **`get_by_ids()` en repositorios de vector search — confirmar existencia**.
- **GZip umbral 200 bytes — exclusión de binarios y presigned URLs**.
- **`minPoolSize` en Atlas tier bajo con escalado horizontal**.
- **Credenciales demo hardcodeadas**: `demo@llego.app / LlegoDemo2025!`.
- **Bypass de Stripe activo en producción con `isDemoStore`**.
- **Timers de `asyncio.sleep` sin cancelación en órdenes demo**.
- **`seed_demo_store.py` sin idempotencia**.
- **`isDemoStore` no debe aparecer en feed público**.
- **Timezone UTC en "Hora del Día" — desfase 5h para Cuba**.
- **Ranking sin coordenadas — confirmar fallback sin 500**.
- **"Pide de Nuevo" con token expirado — feed no debe romper**.
- **Performance ranking multi-factor — índice en `(user_id, created_at)`**.
- **`discounted_service_fee_rate` sin validación de rango**.
- **Signed URLs de S3 para videos promotores sin renovación**.
- **Race condition del descuento por video**.
- **Videos/thumbnails huérfanos en S3 en error parcial**.
- **Worker de borrado de cuentas — sin recuperación tras reinicios**.
- **`scheduledDeletionAt` — campo nuevo en documentos existentes**.
- **URL prefirmada de APK — TTL del cache vs TTL de la firma**.
- **ADS — `ad_pricing` sin datos iniciales en producción**.
- **ADS — `approved` desacoplado del pago sin verificación**.
- **Cache TTL en proceso — inconsistencia en deploys multi-instancia**.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **19, 20 y 21 de Junio** y del **23 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). La entrada del **26 de Junio** fue eliminada el 4 de Julio al superar los 7 días. La entrada del **28 de Junio** fue eliminada el 6 de Julio al superar los 7 días. La entrada del **29 de Junio** fue eliminada el 7 de Julio al superar los 7 días. La entrada del **30 de Junio** fue eliminada el 8 de Julio al superar los 7 días. Las entradas del **1 y 2 de Julio** fueron eliminadas el 10 de Julio al superar los 7 días. La entrada del **3 de Julio** fue eliminada el 11 de Julio al superar los 7 días. Las entradas del **4 y 5 de Julio** fueron eliminadas el 13 de Julio al superar los 7 días. La entrada del **6 de Julio** fue eliminada el 14 de Julio al superar los 7 días. La entrada del **7 de Julio** fue eliminada el 15 de Julio al superar los 7 días. La entrada del **8 de Julio** fue eliminada el 17 de Julio al superar los 7 días. La entrada del **10 de Julio** fue eliminada el 18 de Julio al superar los 7 días. La entrada del **11 de Julio** fue eliminada el 19 de Julio al superar los 7 días. La entrada del **13 de Julio** fue eliminada el 21 de Julio al superar los 7 días. La entrada del **14 de Julio** fue eliminada el 22 de Julio al superar los 7 días. La entrada del **15 de Julio** fue eliminada el 23 de Julio al superar los 7 días. La entrada del **17 de Julio** fue eliminada el 25 de Julio al superar los 7 días. La entrada del **18 de Julio** fue eliminada el 26 de Julio al superar los 7 días. La entrada del **19 de Julio** fue eliminada el 27 de Julio al superar los 7 días. La entrada del **20 de Julio** fue eliminada el 28 de Julio al superar los 7 días. La entrada del **21 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **22 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **23 de Julio** fue eliminada el 31 de Julio al superar los 7 días. La entrada del **24 de Julio** fue eliminada el 1 de Agosto al superar los 7 días. La entrada del **25 de Julio** fue eliminada el 2 de Agosto al superar los 7 días. La entrada del **26 de Julio** fue eliminada el 3 de Agosto al superar los 7 días. La entrada del **27 de Julio** fue eliminada el 4 de Agosto al superar los 7 días. La entrada del **28 de Julio** fue eliminada el 5 de Agosto al superar los 7 días. La entrada del **30 de Julio** fue eliminada el 7 de Agosto al superar los 7 días. La entrada del **31 de Julio** fue eliminada el 8 de Agosto al superar los 7 días. Las entradas del **1, 2 y 3 de Agosto** fueron eliminadas el 10 de Agosto al superar los 7 días. La entrada del **4 de Agosto** fue eliminada el 12 de Agosto al superar los 7 días. La entrada del **5 de Agosto** fue eliminada el 13 de Agosto al superar los 7 días. La entrada del **6 de Agosto** fue eliminada el 14 de Agosto al superar los 7 días. La entrada del **7 de Agosto** fue eliminada el 15 de Agosto al superar los 7 días. La entrada del **8 de Agosto** fue eliminada el 17 de Agosto al superar los 7 días. La entrada del **10 de Agosto** fue eliminada el 18 de Agosto al superar los 7 días. La entrada del **11 de Agosto** fue eliminada el 19 de Agosto al superar los 7 días. Anteriores eliminadas: 16, 17 y 18 de Junio, 5, 6, 7, 9, 11, 12 y 15 de Junio, y días de Mayo.
