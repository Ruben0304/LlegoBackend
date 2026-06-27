# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 27 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en el rango de las últimas 24h es "Analisis diario Claude" del 26/06 (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 26 de Junio, 2026

### Resumen de cambios (últimas 24h)

**4 commits** de Ruben0304 — jornada centrada íntegramente en la capa de IA de recomendaciones: (1) RAG agéntico con tool use y búsqueda híbrida RRF; (2) recomendador de carrito con lista numerada de índices; (3) índice nocturno de complementos por producto vía Batch API; (4) refactorización del índice a modo incremental (solo deltas, costo O(cambios) vs O(N²) anterior).

---

### Área 1: RAG agéntico con tool use + híbrido RRF (1 commit — Ruben0304, 15:26)

- **`feat(ai): RAG agéntico con tool use (search_products/branches) + híbrido RRF`** — Reemplaza el pipeline de 2 llamadas estáticas por un loop agéntico de máximo 2 turnos en Haiku 4.5: Turn 1 (no-streaming, tool_choice auto) enruta o llama `search_products`/`search_branches` en paralelo con queries expandidas; Turn 2 (streaming) redacta con candidatos. Búsqueda híbrida: vector (Qdrant) + keyword (regex Mongo) fusionados con Reciprocal Rank Fusion. Historial capado a 6. `send_message` no-streaming como fallback.

---

### Área 2: Recomendador de carrito con lista numerada (1 commit — Ruben0304, 15:42)

- **`perf(ai): recomendador de carrito con lista numerada (índices) y prompt conciso`** — El modelo recibe nombres de productos como lista numerada (sin ObjectIds ni descripciones), devuelve solo índices + razón breve; el servidor mapea índice → ID real. `max_tokens` reducido a 400. Tope de 120 candidatos para branches grandes.

---

### Área 3: Índice nocturno de complementos (Batch API) (1 commit — Ruben0304, 17:08)

- **`feat(ai): índice nocturno de complementos por producto (Sonnet + Batch API)`** — Cron nocturno precomputa por producto una lista rankeada de complementos de su misma tienda usando Claude Sonnet 4.6 vía Batch API (50% más barato, offline). Solo re-indexa tiendas cuyo set de productos cambió (detectado por hash de IDs). Guarda en colección `product_complements`. Fallback: Haiku en vivo para productos aún no indexados (arranque en frío).

---

### Área 4: Índice incremental de complementos (solo deltas) (1 commit — Ruben0304, 17:29)

- **`feat(ai): índice de complementos incremental (solo deltas, más barato)`** — El cron nocturno ahora procesa solo lo que cambió desde la última corrida: producto borrado → sin LLM (`$pull` de su id en los demás + borrar doc); producto añadido/cambiado → UNA llamada batch que devuelve en la misma respuesta sus `own` (forward) y `host_of` (backward). Estado por-producto via fingerprint de nombre. Migración transparente desde formato anterior (hash por tienda).

---

### Puede dar bateo

1. **Batch API con polling sin guardia de solapamiento**: Si el batch nocturno no se completa antes del siguiente cron, la nueva ejecución puede iniciar un segundo poll concurrente sobre el mismo batch o abrir un batch duplicado. Sin un lock o verificación de estado previo, los resultados pueden escribirse dos veces o quedar corruptos.

2. **Fingerprint por nombre — cambios no detectados**: El estado por-producto usa hash del nombre. Si un producto cambia precio, imagen u otros atributos relevantes para la complementariedad sin cambiar el nombre, el delta no se detecta y el índice queda desactualizado indefinidamente.

3. **Migración transparente desde hash-por-tienda**: Documentos de estado en formato antiguo se migran en caliente. Un fallo a mitad de la primera corrida incremental deja parte de los productos migrados y parte sin migrar, causando comportamiento mixto en el siguiente cron.

4. **Índice incremental sin rollback**: Si la escritura de un doc de complementos falla tras actualizar el fingerprint (red cortada, timeout Mongo), el estado registra el producto como procesado pero el doc de complementos no se actualizó. El delta nunca se volvería a detectar.

5. **RAG agéntico loop 2 turnos — contexto vacío sin guardia**: Si en el Turn 1 el modelo no llama a ninguna tool cuando debería (e.g. falla de Qdrant silenciosa), el Turn 2 recibe contexto de candidatos vacío y responde con información inventada o genérica.

6. **Queries Qdrant paralelas en Turn 1**: El modelo puede llamar `search_products` y `search_branches` simultáneamente. Si Qdrant tiene baja disponibilidad, ambas fallan a la vez y el segundo turno queda completamente sin contexto real.

7. **Historial capado a 6 — pérdida de contexto**: En flujos de soporte de más de 6 turnos, el contexto previo se pierde, lo que puede causar respuestas repetidas o contradictorias con lo dicho anteriormente.

8. **`send_message` no-streaming como fallback**: Si el sistema cae al fallback, el cliente iOS (que espera un stream SSE) no recibe el evento `suggested_product_ids` correctamente o tiene que manejar una respuesta no-stream diferente.

9. **Múltiples workers nocturnos encadenados sin aislamiento**: El lifespan ahora encadena: taste vector + price positioning + complement indexer. Si uno lanza una excepción no capurada, los siguientes no se ejecutan, sin alertas visibles.

10. **Tope de 120 candidatos en el recomendador**: Branches con más de 120 productos activos truncarán silenciosamente el catálogo enviado al modelo. Productos al final del listado nunca serán recomendados como complementos en esas tiendas.

---

#### Seguimientos vigentes

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

## 📅 23 de Junio, 2026

### Resumen de cambios (últimas 24h)

**6 commits** de Ruben0304 — jornada concentrada en la capa de IA: migración completa de DeepSeek a **Claude Haiku 4.5** (Anthropic SDK) en los tres servicios de IA (`ai_rag_service`, `error_analysis_service`, `product_recommendation_service`), seguida de cuatro fixes progresivos para estabilizar el streaming asíncrono con el nuevo SDK, y un feat que permite a admins y managers saltarse el límite de cuota de consultas.

---

### Área 1: Migración DeepSeek → Claude Haiku 4.5 (1 commit — Ruben0304, 15:49)

- **`feat(ai): migrar chat de DeepSeek a Claude Haiku 4.5 (Anthropic SDK)`** — Reemplaza el cliente `OpenAI+DeepSeek` por `anthropic.Anthropic/AsyncAnthropic` en `ai_rag_service`, `error_analysis_service` y `product_recommendation_service`. Actualiza config, requirements y referencias de texto. Añade test e2e que valida el pipeline completo Claude + Qdrant + MongoDB.

---

### Área 2: Fixes de streaming Anthropic (4 commits — Ruben0304, 16:04–16:12)

- **`fix(ai): corregir streaming con Anthropic SDK dentro de async generator`** (16:04) — Reemplaza `async with messages.stream()` por `create(stream=True)` para que el context manager no cierre el generator antes de emitir el evento final (`suggested_product_ids`). Sube `max_tokens` de 1200 a 2048.
- **`fix(ai): subir max_tokens de streaming a 5000`** (16:05).
- **`fix(ai): subir max_tokens al máximo del modelo (8192)`** (16:09).
- **`fix(ai): usar thread+queue para streaming con Anthropic dentro de async generator`** (16:12) — Reemplaza `AsyncAnthropic` streaming por sync client en thread pool con `asyncio.Queue`. Resuelve conflictos de event loop entre `AsyncAnthropic` y el async generator de Strawberry.

---

### Área 3: Bypass de cuota para roles privilegiados (1 commit — Ruben0304, 16:28)

- **`feat(ai): bypass de quota para admins y managers`** — Usuarios con rol `admin` o `manager` no están sujetos al límite de cuota de consultas al LLM.

---

### Puede dar bateo

1. **`ANTHROPIC_API_KEY` no configurada en producción** — AuthenticationError en los tres servicios de IA.
2. **Sync client en thread pool — pool agotado bajo alta concurrencia**.
3. **`max_tokens=8192` — costo Anthropic elevado por solicitud**.
4. **Prompts de DeepSeek reutilizados con Claude — formato `suggested_product_ids` puede romperse**.
5. **Bypass de cuota sin audit log — abuso con cuenta privilegiada comprometida**.
6. **e2e test con API Anthropic real en CI — costo por PR**.
7. **`asyncio.Queue` sin timeout ni backpressure**.
8. **Tres servicios migrados simultáneamente sin feature flag**.

---

## 📅 21 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en el rango de las últimas 24h es "Analisis diario Claude" del 20/06 (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 20 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en el rango de las últimas 24h es "Analisis diario Claude" del 19/06 (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **16, 17, 18 y 19 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). Anteriores eliminadas: 5, 6, 7, 9, 11, 12 y 15 de Junio, y días de Mayo.
