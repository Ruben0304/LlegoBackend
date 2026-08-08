# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 8 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 7 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 6 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. Los cambios del 5 de Agosto (admin orders, cola de revisión KYC, delivery fee recommendation, concurrency fixes en branch delivery requests) ya fueron cubiertos en la entrada de ayer. No hay cambios en producción hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 5 de Agosto, 2026

### Resumen de cambios (últimas 24h)

**8 commits** — todos de brianmojena. Día muy activo: fix de dos bugs de concurrencia en branch delivery requests, nuevo campo `predefinedDeliveryFee` en Business, recomendación de fee basada en historial de órdenes, cola de revisión KYC admin, y nuevas queries admin de órdenes y presencia de couriers.

---

### Área 1: Orders — fix dos bugs de concurrencia en branch delivery requests (2 commits — brianmojena, 14:18)

- **`fix(orders): resolve two concurrency bugs in branch delivery requests`** — El índice único en `(deliveryPersonId, branchId)` no estaba acotado a `status=pending`, impidiendo que un courier solicitara nuevamente una sucursal tras un rechazo. Se convierte en índice único parcial. `request_branch_link` atrapa `DuplicateKeyError` y lo convierte en el mensaje amistoso existente. `update_status` es ahora un compare-and-swap atómico (filtra en `status=pending`). `respond_branch_link_request`/`cancel_branch_link_request` tratan un `None` de `update_status` como "ya respondido". `add_linked_branch` solo se dispara cuando el update atómico ganó y resultó en ACCEPTED.
- **`test(orders): cover branch delivery request concurrency fixes`** — Tests unitarios con mocks (AsyncMock/SimpleNamespace): race de duplicate-key en request, lost-race en respond (verificando que `add_linked_branch` no se llama), happy-path accept, y lost-race en cancel.

---

### Área 2: Businesses — predefinedDeliveryFee + recomendación basada en datos históricos (3 commits + merge — brianmojena, 14:18-14:23)

- **`feat(businesses): add predefinedDeliveryFee to Business`** — Nuevo campo `predefinedDeliveryFee` en `Business` (puramente informacional, nunca afecta el cálculo real de H3). Wired a través de `UpdateBusinessInput`/`update_business` (con check `>= 0`) y `BusinessType`.
- **`feat(businesses): add data-driven delivery fee recommendation`** — `OrderRepository.get_recent_delivery_fees`: una única aggregation (match delivered + fee>0 → sort por recencia → limit 30 → group en array de fees). `compute_fee_recommendation` en `services/orders_utils.py`: función pura, sin I/O, que devuelve `{recommendedFee, sampleSize, confidence}` usando la mediana (robusta a outliers). Expuesto como `deliveryFeeRecommendation(businessId, jwt)` (solo owner, mismo gating que `update_business`).
- **`test(businesses): cover compute_fee_recommendation`** — Cubre 0/1/2/many records, valores repetidos y dispersos, outlier extremo, contrato de recency-ordering, filtrado de inválidos/negativos, redondeo y confidence scaling por sample size.
- **Merge de conflictos** (14:23) — Resolución manual de conflictos en `domain/models.py` y `schema/businesses/types.py` al incorporar main a la rama de trabajo.

---

### Área 3: KYC — cola de revisión admin para verificaciones de efectivo (1 commit — brianmojena, 19:13)

- **`feat(kyc): expose admin review queue for cash KYC verifications`** — `KycVerificationRepository.list_filtered` + `KycAuditEventRepository.list_by_entity`. Queries GraphQL `admin_kyc_verifications` y `admin_kyc_audit_events` (solo admin/manager). URLs de imágenes de evidencia como presigned URLs generadas al vuelo vía `utils.s3.get_public_url`. `override_cash_kyc_decision` ahora refuerza el rol admin/risk_admin también a nivel de resolver (defense in depth, antes solo validaba dentro del servicio). Índice compuesto `status+createdAt` para la cola de revisión.

---

### Área 4: Orders/Couriers — queries admin de órdenes y presencia de couriers (1 commit — brianmojena, 19:42)

- **`feat(orders): admin live/history orders + order tracking + courier presence`** — `OrderRepository.list_filtered`: listado global de admin sin field obligatorio (statusIn/businessId/branchId/fromDate/toDate), sirve tanto cola en vivo como historial. Nueva query `admin_orders` (require_role admin/manager). `get_order_tracking` gana `bypass_authorization`, solo settable internamente desde la nueva `admin_order_tracking` gateada por require_role. Lógica de snapshot de presencia de couriers extraída de `couriers_presence_stream` a `services/courier_presence.py`, reutilizada por la suscripción existente (sin cambio de comportamiento) y la nueva `admin_couriers_presence` (HTTP pollable para clientes sin WebSocket).

---

### Puede dar bateo

1. **Merge de conflictos en `domain/models.py` y `schema/businesses/types.py` — riesgo de "unexpected keyword argument" en runtime**: CLAUDE.md advierte explícitamente que un campo nuevo en `Business` no declarado en `BusinessType` rompe todas las queries con ese tipo sin error de compilación ni de sintaxis. La resolución manual del conflicto en esos dos archivos es el punto más riesgoso del día: si `predefinedDeliveryFee` quedó en `domain/models.py` pero faltó en `BusinessType` (o a la inversa), todas las queries que usen `BusinessType` fallarán con "unexpected keyword argument" en tiempo de ejecución.

2. **Índice único parcial — migración requiere drop del índice anterior**: MongoDB rechaza crear un índice sobre los mismos campos con opciones distintas si el anterior sigue existiendo. Si no hay un script de migración explícito que haga `dropIndex` antes del `createIndex`, el deploy arrancará con el índice viejo (sin la restricción parcial), dejando el bug de concurrencia sin corregir silenciosamente.

3. **`bypass_authorization` en `get_order_tracking` — superficie de escalada de privilegios**: El parámetro solo debe ser settable desde `admin_order_tracking`. Si el resolver no valida explícitamente que `bypass_authorization` no puede ser seteado vía argumentos GraphQL desde la query pública, cualquier usuario autenticado podría bypasear la autorización de tracking de órdenes ajenas.

4. **Presigned URLs de evidencia KYC — expiración antes de la revisión del admin**: Las URLs se generan en el momento de la query. Si la respuesta es cacheada en el cliente admin o el revisor tarda más que el TTL de la presigned URL, las imágenes de evidencia serán inaccesibles al intentar visualizarlas, sin feedback claro de por qué.

5. **`services/courier_presence.py` — confirmar thread-safety para requests HTTP concurrentes**: La extracción mueve código que antes corría en el contexto de una suscripción WebSocket (un consumer por conexión) a un endpoint HTTP pollable (múltiples requests concurrentes). Estado mutable interno o recursos no thread-safe en el servicio extraído generarían race conditions silenciosas.

6. **`admin_orders` sin límite máximo obligatorio — riesgo de timeout/OOM en datasets grandes**: La query acepta filtros pero no impone un techo de resultados. Una query sin filtros de fecha sobre millones de órdenes puede agotar memoria o generar un timeout sin feedback útil al cliente admin.

7. **`compute_fee_recommendation` — fees de valor muy bajo no filtrados**: La función filtra negativos e inválidos pero no está documentado si filtra fees de `$0.00` o valores anómalos cercanos a cero. Un error de datos con fee `$0.01` repetido en órdenes recientes sesgaría la mediana hacia abajo sin advertencia visible.

---

## 📅 4 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 3 de Agosto, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit en las últimas 24h es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

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

#### Seguimientos vigentes

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

> ⚠️ **Nota de mantenimiento**: Las entradas del **19, 20 y 21 de Junio** y del **23 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). La entrada del **26 de Junio** fue eliminada el 4 de Julio al superar los 7 días. La entrada del **28 de Junio** fue eliminada el 6 de Julio al superar los 7 días. La entrada del **29 de Junio** fue eliminada el 7 de Julio al superar los 7 días. La entrada del **30 de Junio** fue eliminada el 8 de Julio al superar los 7 días. Las entradas del **1 y 2 de Julio** fueron eliminadas el 10 de Julio al superar los 7 días. La entrada del **3 de Julio** fue eliminada el 11 de Julio al superar los 7 días. Las entradas del **4 y 5 de Julio** fueron eliminadas el 13 de Julio al superar los 7 días. La entrada del **6 de Julio** fue eliminada el 14 de Julio al superar los 7 días. La entrada del **7 de Julio** fue eliminada el 15 de Julio al superar los 7 días. La entrada del **8 de Julio** fue eliminada el 17 de Julio al superar los 7 días. La entrada del **10 de Julio** fue eliminada el 18 de Julio al superar los 7 días. La entrada del **11 de Julio** fue eliminada el 19 de Julio al superar los 7 días. La entrada del **13 de Julio** fue eliminada el 21 de Julio al superar los 7 días. La entrada del **14 de Julio** fue eliminada el 22 de Julio al superar los 7 días. La entrada del **15 de Julio** fue eliminada el 23 de Julio al superar los 7 días. La entrada del **17 de Julio** fue eliminada el 25 de Julio al superar los 7 días. La entrada del **18 de Julio** fue eliminada el 26 de Julio al superar los 7 días. La entrada del **19 de Julio** fue eliminada el 27 de Julio al superar los 7 días. La entrada del **20 de Julio** fue eliminada el 28 de Julio al superar los 7 días. La entrada del **21 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **22 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **23 de Julio** fue eliminada el 31 de Julio al superar los 7 días. La entrada del **24 de Julio** fue eliminada el 1 de Agosto al superar los 7 días. La entrada del **25 de Julio** fue eliminada el 2 de Agosto al superar los 7 días. La entrada del **26 de Julio** fue eliminada el 3 de Agosto al superar los 7 días. La entrada del **27 de Julio** fue eliminada el 4 de Agosto al superar los 7 días. La entrada del **28 de Julio** fue eliminada el 5 de Agosto al superar los 7 días. La entrada del **30 de Julio** fue eliminada el 7 de Agosto al superar los 7 días. La entrada del **31 de Julio** fue eliminada el 8 de Agosto al superar los 7 días. Anteriores eliminadas: 16, 17 y 18 de Junio, 5, 6, 7, 9, 11, 12 y 15 de Junio, y días de Mayo.
