# Registro de Análisis de Cambios — LlegoBackend

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
- **`fix(ai): subir max_tokens de streaming a 5000`** (16:05) — Respuestas que superaban 2048 tokens seguían truncándose.
- **`fix(ai): subir max_tokens al máximo del modelo (8192)`** (16:09) — Segunda subida para garantizar respuestas completas con Claude Haiku 4.5.
- **`fix(ai): usar thread+queue para streaming con Anthropic dentro de async generator`** (16:12) — Reemplaza `AsyncAnthropic` streaming por sync client en thread pool con `asyncio.Queue`. Mismo patrón que el SDK de OpenAI usa internamente. Resuelve conflictos de event loop entre `AsyncAnthropic` y el async generator de Strawberry que cortaban el mensaje a mitad.

---

### Área 3: Bypass de cuota para roles privilegiados (1 commit — Ruben0304, 16:28)

- **`feat(ai): bypass de quota para admins y managers`** — Usuarios con rol `admin` o `manager` no están sujetos al límite de cuota de consultas al LLM.

---

### Puede dar bateo

1. **`ANTHROPIC_API_KEY` no configurada en producción**: La migración de DeepSeek a Anthropic requiere que la nueva API key esté en Railway/entorno de producción. Si falta, los tres servicios de IA lanzarán `AuthenticationError` en tiempo de ejecución.

2. **Sync client en thread pool — pool agotado bajo alta concurrencia**: Cada llamada de streaming ocupa un thread durante toda la duración del stream. Con el pool por defecto de Python (`min(32, cpu_count+4)` threads), un pico de usuarios simultáneos puede agotar los threads y dejar nuevas solicitudes de chat colgadas.

3. **`max_tokens=8192` — costo Anthropic elevado**: Haiku 4.5 a 8192 tokens por llamada multiplica el costo por solicitud respecto a DeepSeek. Confirmar si hay budget mensual o alertas de costo configuradas en Anthropic Console.

4. **Prompts de DeepSeek reutilizados con Claude — formato `suggested_product_ids` puede romperse**: Los system prompts y few-shots diseñados para DeepSeek pueden producir outputs con formato diferente en Claude Haiku 4.5. El evento `suggested_product_ids` depende de que el modelo siga un formato JSON específico; un cambio de comportamiento rompe el parsing.

5. **Bypass de cuota sin audit log**: Admins/managers pueden hacer consultas ilimitadas al LLM sin registro. Si una cuenta privilegiada es comprometida, el abuso no se detectará hasta recibir la factura de Anthropic.

6. **e2e test con API Anthropic real en CI**: Si el test añadido en el commit de migración llama a la API real en cada CI run, cada PR incurrirá en costo Anthropic. Confirmar que está marcado como de integración y excluido de la suite de CI normal.

7. **`asyncio.Queue` sin timeout ni backpressure**: Si el consumer (async generator de Strawberry) va más lento que el producer (thread de streaming), el queue crece sin límite en memoria. Si el cliente corta la conexión antes de que el stream termine, el thread producer continúa hasta completar el stream completo.

8. **Tres servicios migrados simultáneamente sin feature flag**: Si Claude da problemas en uno, no hay forma de revertir solo ese servicio sin rollback completo del commit.

---

#### Seguimientos vigentes

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
- **`chore` auth/rate-limit/admin-payouts sin auditoría detallada**.
- **`apiRequest success:false` — monitorear regresiones post-deploy (SunCarWeb)**.
- **`showContableFields` en MaterialForm (SunCarWeb)**.
- **`costo` y `material_id` en tipo `Material` (SunCarWeb)**.
- **Wallet historial por miembro — filtros params (SunCarWeb)**.
- **Excel Fichas de Costo sin cota de registros (SunCarWeb)**.
- **Permiso `gestionar_banco_global` — validación en backend**.
- **`aumento_porcentaje` y `aumento_tipo` en ofertas (SunCarWeb)**.
- **Tasa de cambio EUR vs CUP — confirmar convención en backend**.
- **Endpoints de paginación `GET /cobros-paginado` y `/personalizadas/pendientes-paginado`**.
- **Rollback de pago — confirmar reversión de saldo de billetera**.
- **`recibido_por_ci` en pagos — auto-acreditación de billetera**.
- **Endpoints wallet: ensure, pending-transfers, accept, reject, delete**.
- **`averia_id` en trabajos diarios — confirmar aceptación en POST/PATCH**.
- **Campos SunCarWeb → backend pendientes: `motivo`, `nota`, `foto`, `ficha_tecnica_url`, `oferta_venta_id`, `descuento_free`**.
- **Campos cambio real SunCarWeb: `cambio_real_monto`, `cambio_real_moneda`, `cambio_real_tasa`**.
- **Endpoint lazy load obras terminadas: `GET /obras-terminadas/oferta/{id}/facturas-cliente`**.
- **Endpoints notificaciones SunCarWeb: `GET /mis-notificaciones`**.
- **`GET /inventario/stock-historico` — confirmar existencia y params**.
- **Agregados solicitudes-ventas — campos de totales en endpoints**.
- **`stock_disponible_actual` — consistencia entre endpoints**.
- **`'zelle'` como método de pago — soporte en backend (SunCarWeb)**.
- **Tasas MLC/CUP sin persistencia entre sesiones (SunCarWeb)**.
- **`PonderarCostoResponse` campos nuevos (SunCarWeb)**.
- **`GET /api/kardex-costo/costo-actual` — confirmar params (SunCarWeb)**.
- **Filtros de vales de salida — `fecha_desde`, `fecha_hasta`, creador (SunCarWeb)**.
- **Badges de disponibilidad por pool — snapshot estático (SunCarWeb)**.
- **`window.history.pushState` + Next.js App Router desync (SunCarWeb)**.
- **`POST /solicitudes-transferencia/{id}/resolver` — endpoint pendiente (SunCarWeb)**.

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

## 📅 19 de Junio, 2026

### Resumen de cambios (últimas 24h)

**10 commits** de Ruben0304 y brianmojena — día de máxima actividad en la capa Qdrant: (1) infraestructura completa de payloads enriquecidos e índices server-side; (2) mejoras de calidad en recomendaciones (BEST_SCORE, embedding con contexto semántico, borrado robusto por `mongo_id`, diversidad MMR-lite); (3) vector de gusto por usuario precalculado con job nocturno; (4) clasificación de tiendas por posición de precio (económica/promedio/cara); y (5) fix crítico de `deliveredOrdersCount` que se reseteaba a 0 al editar el teléfono del repartidor.

---

### Área 1: Qdrant — payloads enriquecidos + payload indexes + sync consistente (1 commit — Ruben0304, 16:59)

- **`feat(qdrant): enriquecer payloads + payload indexes + sync consistente (#1)`** — `qdrant_payloads.py` como única fuente de verdad. Payload enriquecido: productos (+`branchId`, `categoryId`, `currency`, `availability`), branches (+`businessId`, `isActive`, `deliveryRadius`, `location` geo), businesses (+`globalRating`, `approvalStatus`, `isActive`, `tags`). `ensure_collections_and_indexes()` idempotente en lifespan. `update()` en repos: re-embebe solo si cambian campos de texto; si cambian campos de payload hace `set_payload` (sin gastar Gemini). Script `reindex_qdrant_payloads.py` para backfill sin re-embeber. Fix: `reindex_businesses_qdrant.py` usaba `id=mongo_id` crudo → ahora uuid5 consistente (causa raíz de duplicados anteriores).

---

### Área 2: Calidad de recomendaciones (4 commits — Ruben0304, 17:01–17:09)

- **`feat(qdrant): usar estrategia BEST_SCORE en recommend (#2)`** — `BEST_SCORE` puntúa cada candidato por su máxima similitud a CUALQUIER positivo (vs centroide promediado). Respeta gustos diversos. Aplicado en "Especialmente para Ti", `getSimilarProducts`, `getSimilarBranches`, `getBranchesForProduct`.
- **`feat(qdrant): enriquecer el texto del embedding (#3)`** — Productos: +"Categoría: <nombre>". Branches: +dirección. Negocios: +"Tags: ...". `categoryId` y `tags` pasan a `TEXT_FIELDS`: un cambio dispara re-embedding, no solo `set_payload`.
- **`feat(qdrant): borrado robusto por filtro de mongo_id (#4)`** — `clients.delete_by_mongo_id()`: borra TODOS los puntos con ese `mongo_id` en una sola llamada (`FilterSelector`). `delete_product`, `delete_branch`, `delete_business` ahora reales (antes eran stubs).
- **`feat(qdrant): re-ranking por diversidad (MMR-lite) en "Especialmente para Ti" (#5)`** — `recommendation_diversity.py` penaliza claves repetidas (`branchId`/`categoryId`) en un greedy. Solo aplicado al feed personalizado.

---

### Área 3: Vector de gusto por usuario + job nocturno (1 commit — Ruben0304, 17:14)

- **`feat(qdrant): vector de gusto por usuario + job nocturno (#6)`** — `taste_vector_service.py`: promedio ponderado y decaído de embeddings de productos con que el usuario interactuó. Vectores RECUPERADOS de Qdrant (cero llamadas Gemini). Worker nocturno (cada 24h) en lifespan.

---

### Área 4: Robustez de backfill (1 commit — Ruben0304, 17:42)

- **`fix(qdrant): backfill robusto ante docs inválidos + reindex businesses con Gemini`** — Builders tolerantes a objeto-o-dict. Productos sin `weight/image` en prod se backfillean leyendo docs crudos de Mongo. `reindex_businesses_qdrant`: añadido `connect_to_gemini()` + `sys.path` para ejecución directa.

---

### Área 5: Posicionamiento de precios por tienda (2 commits — Ruben0304, 18:11 y 18:30)

- **`feat(qdrant): posicionamiento de precios por tienda (económica/promedio/cara)`** — `price_positioning_service.py`: `precio_relativo = precio / mediana(precios de similares en misma categoría)`, normalizado a USD. Umbrales: ≥1.10 cara, ≤0.90 económica. Campos nuevos: `priceTier`, `priceIndex`, `priceConfidence`. Worker nocturno junto al de vectores de gusto.
- **`fix(branches): excluir pricePositioningUpdatedAt de branch_to_dict`** — Causaba "unexpected keyword argument" al entrar a cualquier tienda.

---

### Área 6: Fix de repartidores (1 commit — brianmojena, 06:48)

- **`Fix updateUser mutation missing deliveredOrdersCount in response`** — `_user_to_type()` helper centraliza la construcción con el campo incluido, evitando que el contador de entregas se reseteara a 0 al editar el teléfono.

---

### Puede dar bateo

1. **Dos workers nocturnos simultáneos — contención en Qdrant**.
2. **`priceConfidence` no verificado antes de usar `priceTier`** — tiendas pequeñas tendrán `priceTier=null`.
3. **MMR-lite penaliza tiendas mono-categoría**.
4. **Colección `users` en Qdrant — existencia no garantizada**.
5. **`exchangeRate` cero o ausente en posicionamiento de precios — división por cero**.
6. **`_user_to_type()` — potencial N+1 en contexto de lista**.
7. **Re-embedding por `TEXT_FIELDS` — costo Gemini en edición masiva de categorías**.
8. **`reindex_businesses_qdrant` ahora re-embebe al ejecutarse — costo involuntario en CI/dev**.
9. **Backfill con docs crudos — tipos no validados silenciosamente**.
10. **`delete_by_mongo_id` depende del payload index de `mongo_id`**.

---

## 📅 18 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit en el rango de las últimas 24h es "Analisis diario Claude" del 17/06 (generado automáticamente). No hay cambios en producción.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 17 de Junio, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos desde el análisis del 16/06. Los seguimientos del 16/06 siguen vigentes.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 16 de Junio, 2026

### Resumen de cambios (últimas 24h)

**14 commits** de Ruben0304 y Fabian1820 — estabilización completa de la integración Qdrant con 6 fixes críticos (incluyendo reemplazo del método `.search()` deprecado que causaba vacíos silenciosos), nuevas features de recomendaciones personalizadas vía Qdrant, y nueva funcionalidad de horarios excepcionales por día en branches con posibilidad de pausar pedidos.

---

### Área 1: Qdrant — estabilización crítica (6 commits — Ruben0304)

- **`fix(qdrant): lazy client init + refactor ads auth to use require_role`** (14:46).
- **`fix(startup): replace blocking Qdrant probe with async wait_for (5s cap)`** (14:50).
- **`fix(search): mensaje de error amigable cuando Qdrant no está disponible`** (15:19).
- **`fix(qdrant): retry startup probe and bump client to 1.18.x`** (15:30).
- **`test(qdrant): suite de integración completa contra Railway`** (15:46).
- **`fix(qdrant): reemplazar .search() deprecated por .query_points() en repositorios`** (16:49) — **Fix crítico**: causa raíz del bug donde `searchProducts` devolvía vacío en producción.

---

### Área 2: Recomendaciones y feed personalizado (2 commits — Ruben0304)

- **`feat(feed): sección 'Especialmente para Ti' usando Qdrant recommend API`** (17:03).
- **`feat(recommendations): getSimilarProducts, getSimilarBranches, getBranchesForProduct vía Qdrant`** (17:13).

---

### Área 3: Panel de pruebas admin + MongoDB indexes (4 commits — Ruben0304)

- **`feat(admin): panel nativo de pruebas de experiencia de cliente`** (16:56).
- **`feat(admin/tests): soporte node_ids + categorías agrupadas`** (17:07).
- **`perf: add missing MongoDB indexes and clean up verbose logging`** (18:01).
- **`Merge remote branch: resolve conflicts`** (18:05).

---

### Área 4: Threshold de búsqueda y control de pedidos en branches (2 commits)

- **`fix(search): bajar threshold de productos de 0.60 a 0.45`** (17:45).
- **`feat(branches): pausar pedidos + horario excepcional por día`** (21:32) — `acceptingOrders`, `setBranchDailyOverride`, `clearBranchDailyOverride`.

---

### Puede dar bateo

1. **`acceptingOrders` — retrocompatibilidad con documentos sin el campo en MongoDB**.
2. **`dailyOverride.date` sin timezone explícita — desfase UTC vs Cuba**.
3. **`setBranchDailyOverride` — sin validación de rango de horas**.
4. **Threshold 0.60 → 0.45 — aumento de ruido en resultados de búsqueda**.
5. **`getBranchesForProduct` — doble query Qdrant + MongoDB con top-50**.
6. **`getSimilarProducts/Branches` — UUID no encontrado en Qdrant**.
7. **`Especialmente para Ti` — vector promedio sin normalización explícita**.
8. **Ads auth migrado de `admin_api_key` a `require_role`**.
9. **`check_compatibility=False` en qdrant-client**.
10. **Merge manual de conflictos (18:05) — confirmar integridad de `maxPoolSize=150`**.
11. **Índices en colecciones existentes — confirmar background build en Atlas**.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **5, 6, 7, 9, 11, 12 y 15 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). Anteriores eliminadas: 27, 28, 29, 30 de Mayo, 31 de Mayo, 1, 2, 3 y 4 de Junio.
