# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 2 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 1 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 31 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 30 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 28 de Julio, 2026

### Resumen de cambios (últimas 24h)

**6 commits reales** — 4 de Ruben0304 y 2 de brianmojena. Día muy activo: restricción de creación de promos a admin/manager, exposición del campo `orden` en `FeedSection` para que los clientes puedan levantar secciones pinnadas, migración de complements a Haiku (~1/3 del costo con Batch), creación de índices MongoDB para el chat, corrección del bloqueo del event loop en `aiChat` con recorte de hasta 700 tokens por mensaje, y batch de embeddings + consultas a Qdrant para búsqueda.

---

### Área 1: Promos — restricción a admin/manager (1 commit — brianmojena, 13:36)

- **`feat(promos): restrict promo creation to admin/manager`** — `createPromoRequest` ahora requiere rol admin/manager (antes cualquier cliente autenticado podía crear una). Renombrado `submittedByUserId` → `createdByUserId` (no expuesto en GraphQL, sin breaking change de schema). Eliminado el rate limit anti-abuso de cliente en la creación, ya innecesario.

---

### Área 2: Feed — exponer `orden` en FeedSection (1 commit — brianmojena, 13:49)

- **`feat(feed): expose orden on FeedSection so clients can lift pinned sections`** — Las secciones ya llegaban ordenadas por su `orden` pinneado, pero los clientes no podían identificar cuáles levantar fuera del flujo normal (carruseles fijos como "Para Ti", tiendas, combos). Se expone el campo `orden` en `FeedSection`.

---

### Área 3: Complements — migración a Haiku + skip si no hay cambios (1 commit — Ruben0304, 17:15)

- **`perf(complements): pasar a Haiku y no gastar si no hay cambios`** — Modelo `claude-sonnet-4-6` → `claude-haiku-4-5` (sin thinking). Con Batch API queda en $0.50/$2.50 por millón (antes $1.50/$7.50): ~1/3 del costo. Structured outputs (`json_schema`) para evitar que una respuesta malformada queme un request; si el endpoint lo rechaza, reintenta sin el campo. Migración del estado viejo (solo hash) ya no reindexa sucursales enteras: cruza contra docs existentes y solo toca los que faltan. Fingerprint guardado solo si la respuesta llegó a Mongo. Sin cambios en la noche = no llama al modelo ni reescribe el estado. "why" limitado a 4 palabras, `host_of` con tope, productos sin nombre fuera del catálogo excluidos, sucursales de 1 producto no reevaluadas.

---

### Área 4: Chat — índices MongoDB para memoria y keyword search (1 commit — Ruben0304, 17:52)

- **`perf(chat): indices para memoria y busqueda por keyword del asistente`** — `chat_messages` no tenía ningún índice: leer las últimas N del usuario era un collscan + sort en memoria, dos veces por mensaje, sobre una colección que solo crece. `products`/`branches` ganan índice text sobre `name` para que la pata de keyword del RAG deje de usar `$regex` sin anclar (que nunca puede usar índice). Hasta 12 de esos scans corrían en paralelo por mensaje.

---

### Área 5: Chat — async event loop + recorte de tokens (1 commit — Ruben0304, 17:52)

- **`perf(chat): dejar de bloquear el event loop y recortar tokens por mensaje`** — `_generate_json_output` hacía una llamada síncrona a Claude dentro de un `async def`: congelaba el event loop entero (feed, órdenes, pagos) durante cada mensaje de `aiChat`. Ahora es async con cliente asíncrono. Structured outputs nativos (`messages.parse`) con fallback a schema-en-prompt: quita ~350-700 tokens de input por llamada, elimina fallos de parseo. Temperature 1.0 → 0.0. Tool schemas: ~474 → ~150 tokens. ObjectIds eliminados de resultados de tools. URL de avatar y `branchId` eliminados del contexto del flujo viejo. Card fallback: 8 → 3 items. Historial unificado en 10 mensajes en ambos flujos. `AiRagService` pasa a singleton perezoso (antes instanciado por request con nuevo pool httpx y TLS handshake cada mensaje).

---

### Área 6: Búsqueda — batch de embeddings y consultas a Qdrant (1 commit — Ruben0304, 18:31)

- **`perf(search): batchear embeddings y consultas a Qdrant`** — Cada búsqueda del chat expandía el mensaje hasta 6 términos, cada uno con su propia llamada de embedding a Gemini y consulta a Qdrant; con el executor por defecto, dos usuarios concurrentes ya encolaban. `VectorSearchService` gana `search_{products,branches,businesses}_batch`: una sola llamada de embedding (`generate_embeddings_batch`, ya existía sin usarse) y una sola consulta a Qdrant vía `query_batch_points`. Métodos de una query son envolturas finas sobre los de lote. Bug crítico corregido: `query_batch_points` deja `with_payload=None` y el servidor usa `false` en batch; sin ponerlo explícito, el `mongo_id` no llega y toda búsqueda batch devolvería vacío en silencio. 4 fallbacks automáticos: fallo de embedding batch, conteo de vectores incorrecto (que emparejaría queries con vectores ajenos), y cliente sin endpoint batch. 22 tests con mocks.

---

### Puede dar bateo

1. **`AiRagService` como singleton perezoso — estado mutable compartido entre requests concurrentes**: Al pasar de instancia por request a singleton, cualquier estado interno mutable de `AiRagService` es ahora compartido entre todos los requests simultáneos. Race conditions silenciosas posibles si el servicio mantiene caché interna o estado de sesión no thread-safe.

2. **Dos commits `perf(chat)` con 15 segundos de diferencia (17:52:21 y 17:52:36)** — prácticamente simultáneos; confirmar que el segundo incorporó los cambios del primero sin estado inconsistente.

3. **Temperature 0.0 en `_generate_json_output` — respuestas deterministas pero potencialmente repetitivas**: Para preguntas similares el output puede volverse mecánico. Si algún prompt esperaba variabilidad, esto puede afectar la experiencia de usuario.

4. **Card fallback reducido de 8 a 3 items — menor margen si el modelo descartó incorrectamente**: Si el modelo comete errores de descarte, el fallback de 3 items ofrece menos opciones como red de seguridad.

5. **Índice text sobre `products.name` + `branches.name` — MongoDB solo permite un índice text por colección**: Si ya existe algún índice text en `products` o `branches`, la creación del nuevo falla o reemplaza al anterior, pudiendo romper queries que dependían del índice text existente.

6. **`query_batch_points` con `with_payload=True` explícito — confirmar soporte en versión Qdrant deployada**: El fix de `with_payload` es crítico (sin él toda búsqueda batch devuelve vacío silenciosamente). Verificar que la versión de Qdrant en producción soporta `query_batch_points`.

7. **Migración complements a Haiku — confirmar `json_schema` disponible en endpoint Batch de Haiku 4.5**: Si el endpoint Batch no soporta `json_schema`, el retry sin el campo funciona pero pierde la garantía de formato; posibles respuestas malformadas en complements.

8. **Sucursales de 1 producto excluidas de reevaluación — complements previos stale indefinidamente**: Una sucursal que tenía complements y reduce su catálogo a 1 producto ya no se reevalúa, manteniendo sugerencias desactualizadas.

9. **`generate_embeddings_batch` — orden de vectores no garantizado explícitamente por Gemini**: El fallback de conteo diferente cubre respuesta incompleta, pero no cubre vectores devueltos en orden distinto al input; la asignación incorrecta sería silenciosa.

10. **Fingerprint guardado solo en éxito de Mongo — sucursales con error persistente de Mongo se reintentan indefinidamente**: Una sucursal que falla consistentemente al escribir en Mongo nunca avanzará y generará llamadas a Haiku cada noche sin resultado.

---

## 📅 27 de Julio, 2026

### Resumen de cambios (últimas 24h)

**2 commits reales** de brianmojena — ambos en el feed: primero se añadió la capacidad de pinear secciones del feed a una posición fija, y 37 minutos después se añadió una sección `promo` (banner CTA para negocios no registrados en Llego que quieran enviar promos desde la app cliente).

---

### Área 1: Feed — pinear sección a posición fija (1 commit — brianmojena, 19:33)

- **`feat(feed): allow pinning a feed section to a fixed position`** — Nueva colección `feed_section_config` con repositorio que incluye caché en proceso de 60 segundos. Mutación `setFeedSectionOrden` (admin/manager) para fijar o quitar el pin (`orden=null` quita el pin). Query `getFeedSectionOrden` para leer la configuración actual. `get_feed` ordena `final_sections` por `orden`; el sort es estable, por lo que las secciones sin pin mantienen su orden relativo predeterminado.

---

### Área 2: Feed — sección promo y flujo de envío (1 commit — brianmojena, 20:10)

- **`feat(promo): add promo feed section and submission flow`** — Nueva sección `promo` en el feed: banner CTA sin productos que los negocios no registrados en Llego pueden tocar para enviar una promo desde la app cliente. Los envíos aterrizan en la colección `promo_requests` para revisión administrativa. Nuevo modelo `PromoRequest` (requiere foto o video). Repositorio `promo_request_repository`: crear + listado/paginación admin + aprobar/rechazar. Endpoints `POST /upload/promo/image` y `/upload/promo/video` devuelven el path S3. Mutaciones: `createPromoRequest` (autenticado, rate-limited), `reviewPromoRequest` y `promoRequests` (admin/manager). `FeedSection.banner + FeedPromoBanner`; banner mostrado solo en página 0.

---

### Puede dar bateo

1. **Caché en proceso de 60s para `feed_section_config` — inconsistencia en deploys multi-instancia**: El caché de configuración de secciones vive en memoria de cada proceso. Con múltiples instancias (Railway horizontal), un cambio de `orden` puede tardar hasta 60s en propagarse, y distintas instancias mostrarán órdenes distintos durante ese intervalo.

2. **Sección `promo` solo en página 0 — pinning puede ignorarse en páginas siguientes**: La sección `promo` se muestra únicamente en página 0. Si el admin la pina a una posición concreta con `setFeedSectionOrden` y el usuario solicita el feed desde página 1+, el banner no aparece, contradiciendo el comportamiento esperado del pinning.

3. **`createPromoRequest` rate-limited — límite y ventana no especificados en el commit**: El commit no detalla la ventana de tiempo ni el número máximo de intentos. Sin esa información no se puede evaluar si el límite es efectivo contra spam. Además, si el rate limiter usa IP y la app cliente está detrás de NAT compartido, usuarios legítimos pueden verse bloqueados por el comportamiento de otros en el mismo bloque.

4. **`PromoRequest` uploads sin validación de tamaño/tipo MIME — exposición del bucket S3 a archivos arbitrarios**: Los endpoints `/upload/promo/image` y `/upload/promo/video` devuelven el path S3 pero no se menciona validación de tamaño máximo ni tipos MIME permitidos, exponiendo el bucket a subidas de archivos arbitrarios.

5. **`reviewPromoRequest` sin notificación al negocio autor**: Aprobar o rechazar una solicitud no menciona ningún canal de notificación (push, email). El negocio que envió la promo no se entera del resultado automáticamente.

6. **`FeedPromoBanner` sin click-through definido**: El banner es un CTA puro sin productos. Si la app cliente no tiene lógica de navegación explícita para el tap en el banner, el click puede no hacer nada o navegar a un destino incorrecto.

7. **`promo_requests` colección nueva sin índices definidos en el commit**: El listado/paginación de `promo_requests` para admin puede ser lento sin índices en campos de filtro (`status`, `created_at`, `business_id`).

8. **Dos features en 37 minutos — posible deploy intermedio del primer commit**: Si Railway auto-deploy está activo, el commit de las 19:33 (pinning) hizo deploy sin el promo feed. Pudo haber una ventana con la lógica de pinning activa pero sin la sección `promo` referenciada, causando comportamiento inesperado en `get_feed`.

---

## 📅 26 de Julio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

#### Seguimientos vigentes

- **`AiRagService` como singleton perezoso — estado mutable compartido entre requests concurrentes, race conditions posibles (Jul 28)**.
- **Índice text sobre `products`/`branches.name` — MongoDB solo permite uno por colección; confirmar no conflicto con índice text existente (Jul 28)**.
- **`query_batch_points` con `with_payload=True` — devuelve vacío silencioso si no soportado; confirmar versión Qdrant en producción (Jul 28)**.
- **Complements con Haiku Batch — confirmar soporte de `json_schema` en endpoint Batch de Haiku 4.5 (Jul 28)**.
- **`generate_embeddings_batch` — orden de vectores no garantizado; asignación cruzada silenciosa posible (Jul 28)**.
- **Sucursales mono-producto excluidas de reevaluación — complements stale si catálogo se redujo a 1 producto (Jul 28)**.
- **Caché en proceso de 60s para `feed_section_config` — inconsistencia en multi-instancia, cambios de orden visibles con retraso (Jul 27)**.
- **Sección `promo` solo en página 0 — pinning vía setFeedSectionOrden ignorado en páginas siguientes (Jul 27)**.
- **`createPromoRequest` rate-limited — límite/ventana no especificados, riesgo de bloqueo legítimo por NAT compartido (Jul 27)**.
- **`PromoRequest` uploads sin validación de tamaño/MIME — bucket S3 expuesto a archivos arbitrarios (Jul 27)**.
- **`FeedPromoBanner` sin click-through definido — tap puede navegar a destino incorrecto en app cliente (Jul 27)**.
- **`promo_requests` sin índices — paginación admin puede ser lenta bajo volumen (Jul 27)**.
- **Dos features feed en 37 min — posible build intermedio con pinning activo sin sección promo (Jul 27)**.
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

> ⚠️ **Nota de mantenimiento**: Las entradas del **19, 20 y 21 de Junio** y del **23 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). La entrada del **26 de Junio** fue eliminada el 4 de Julio al superar los 7 días. La entrada del **28 de Junio** fue eliminada el 6 de Julio al superar los 7 días. La entrada del **29 de Junio** fue eliminada el 7 de Julio al superar los 7 días. La entrada del **30 de Junio** fue eliminada el 8 de Julio al superar los 7 días. Las entradas del **1 y 2 de Julio** fueron eliminadas el 10 de Julio al superar los 7 días. La entrada del **3 de Julio** fue eliminada el 11 de Julio al superar los 7 días. Las entradas del **4 y 5 de Julio** fueron eliminadas el 13 de Julio al superar los 7 días. La entrada del **6 de Julio** fue eliminada el 14 de Julio al superar los 7 días. La entrada del **7 de Julio** fue eliminada el 15 de Julio al superar los 7 días. La entrada del **8 de Julio** fue eliminada el 17 de Julio al superar los 7 días. La entrada del **10 de Julio** fue eliminada el 18 de Julio al superar los 7 días. La entrada del **11 de Julio** fue eliminada el 19 de Julio al superar los 7 días. La entrada del **13 de Julio** fue eliminada el 21 de Julio al superar los 7 días. La entrada del **14 de Julio** fue eliminada el 22 de Julio al superar los 7 días. La entrada del **15 de Julio** fue eliminada el 23 de Julio al superar los 7 días. La entrada del **17 de Julio** fue eliminada el 25 de Julio al superar los 7 días. La entrada del **18 de Julio** fue eliminada el 26 de Julio al superar los 7 días. La entrada del **19 de Julio** fue eliminada el 27 de Julio al superar los 7 días. La entrada del **20 de Julio** fue eliminada el 28 de Julio al superar los 7 días. La entrada del **21 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **22 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **23 de Julio** fue eliminada el 31 de Julio al superar los 7 días. La entrada del **24 de Julio** fue eliminada el 1 de Agosto al superar los 7 días. La entrada del **25 de Julio** fue eliminada el 2 de Agosto al superar los 7 días. Anteriores eliminadas: 16, 17 y 18 de Junio, 5, 6, 7, 9, 11, 12 y 15 de Junio, y días de Mayo.
