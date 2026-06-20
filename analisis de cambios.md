# Registro de Análisis de Cambios — LlegoBackend

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

- **`feat(qdrant): usar estrategia BEST_SCORE en recommend (#2)`** — `BEST_SCORE` puntúa cada candidato por su máxima similitud a CUALQUIER positivo (vs centroide promediado). Respeta gustos diversos (usuario que consume sushi Y pasteles). Aplicado en "Especialmente para Ti", `getSimilarProducts`, `getSimilarBranches`, `getBranchesForProduct`.
- **`feat(qdrant): enriquecer el texto del embedding (#3)`** — Productos: +"Categoría: <nombre>" (resuelve `categoryId → nombre`). Branches: +dirección. Negocios: +"Tags: ...". `categoryId` y `tags` pasan a `TEXT_FIELDS`: un cambio dispara re-embedding, no solo `set_payload`. Para datos existentes: scripts de reindex dedicados.
- **`feat(qdrant): borrado robusto por filtro de mongo_id (#4)`** — `clients.delete_by_mongo_id()`: borra TODOS los puntos con ese `mongo_id` en una sola llamada (`FilterSelector`). Robusto ante duplicados y puntos con id crudo o uuid5. `qdrant_indexing_service`: `delete_product`, `delete_branch`, `delete_business` ahora reales (antes eran stubs "no implementado").
- **`feat(qdrant): re-ranking por diversidad (MMR-lite) en "Especialmente para Ti" (#5)`** — `recommendation_diversity.py` penaliza claves repetidas (`branchId`/`categoryId`) en un greedy: la relevancia sigue mandando pero los repetidos bajan, intercalando tiendas y categorías. Solo aplicado al feed personalizado; `getSimilarProducts` se deja como similitud pura.

---

### Área 3: Vector de gusto por usuario + job nocturno (1 commit — Ruben0304, 17:14)

- **`feat(qdrant): vector de gusto por usuario + job nocturno (#6)`** — `taste_vector_service.py`: promedio ponderado y decaído de embeddings de productos con que el usuario interactuó (clicks/favoritos/carrito/órdenes con half-life). Vectores RECUPERADOS de Qdrant (cero llamadas Gemini). Guardado en colección `users`. Feed: "Especialmente para Ti" usa el vector de gusto si existe (1 query), con fallback al recommend en vivo para usuarios nuevos sin historial. Worker nocturno (cada 24h, con warmup) en lifespan. Script `recompute_taste_vectors.py` on-demand.

---

### Área 4: Robustez de backfill (1 commit — Ruben0304, 17:42)

- **`fix(qdrant): backfill robusto ante docs inválidos + reindex businesses con Gemini`** — `qdrant_payloads`: builders tolerantes a objeto-o-dict (`_get/_entity_id`). Productos sin `weight/image` en prod se backfillean leyendo docs crudos de Mongo sin `Product(**doc)`. `reindex_qdrant_payloads`: lee documentos crudos por colección. `reindex_businesses_qdrant`: añadido `connect_to_gemini()` (crasheaba sin él) + `sys.path` para ejecución directa.

---

### Área 5: Posicionamiento de precios por tienda (2 commits — Ruben0304, 18:11 y 18:30)

- **`feat(qdrant): posicionamiento de precios por tienda (económica/promedio/cara)`** — `price_positioning_service.py`: `precio_relativo = precio / mediana(precios de similares en misma categoría, otra tienda)`, normalizado a USD vía `exchangeRate`. Índice de tienda = mediana de relativos. Umbrales: ≥1.10 cara, ≤0.90 económica, resto promedio. Muestra mínima: ≥3 vecinos por producto, ≥3 productos por tienda. Campos nuevos en Branch/`BranchType`/`NearbyBranchType`/`ScoredBranchType`: `priceTier`, `priceIndex`, `priceConfidence`. Worker nocturno junto al de vectores de gusto. Script on-demand.
- **`fix(branches): excluir pricePositioningUpdatedAt de branch_to_dict`** — `pricePositioningUpdatedAt` fue añadido al modelo Branch pero no a `BranchType`. `branch_to_dict` lo volcaba → `BranchType(**branch_to_dict(branch))` reventaba con "unexpected keyword argument" al entrar a cualquier tienda. Se excluye del dict; `priceTier`/`priceIndex`/`priceConfidence` siguen expuestos.

---

### Área 6: Fix de repartidores (1 commit — brianmojena, 06:48)

- **`Fix updateUser mutation missing deliveredOrdersCount in response`** — `update_user`, `add_branch_to_user`, `remove_branch_from_user` construían `UserType` manualmente omitiendo `deliveredOrdersCount`. Al actualizar el teléfono, el contador de entregas del repartidor se reseteaba a 0 en su perfil. Fix: `_user_to_type()` helper centraliza la construcción con el campo incluido.

---

### Puede dar bateo

1. **Dos workers nocturnos simultáneos — contención en Qdrant**: Lifespan lanza el worker de vectores de gusto Y el de posicionamiento de precios. Ambos hacen queries intensivas a Qdrant. Confirmar que el tier contratado de Qdrant aguanta la carga combinada sin rate limiting ni timeouts cruzados.

2. **`priceConfidence` no verificado antes de usar `priceTier`**: Tiendas nuevas o con catálogos pequeños (<3 productos elegibles por categoría) no obtienen clasificación (`priceTier=null`). Si el frontend/app mobile muestra el badge de precio sin verificar `priceConfidence > 0`, mostrará valores nulos o el valor por defecto incorrecto.

3. **MMR-lite penaliza tiendas mono-categoría**: Una tienda especializada (solo carnes, solo tecnología) tiene todos sus productos con el mismo `categoryId`. La penalización de diversidad los bajará sistemáticamente en el ranking personalizado aunque el usuario tenga historial claro con esa categoría.

4. **Colección `users` en Qdrant — existencia no garantizada**: Si `ensure_collections_and_indexes()` no crea la colección `users`, el worker de gusto fallará silenciosamente al hacer upsert. Confirmar que la colección se inicializa en el lifespan antes de que el worker arranque.

5. **`exchangeRate` cero o ausente en posicionamiento de precios**: Si un producto tiene `exchangeRate=0` o el campo falta, la normalización a USD resultará en división por cero o `inf/nan`. Confirmar guard explícito en `price_positioning_service.py` antes de normalizar.

6. **`_user_to_type()` — potencial N+1 en contexto de lista**: Si el helper hace una query adicional para `deliveredOrdersCount` y se llama en un resolver que devuelve lista de usuarios, cada usuario genera una query extra. Confirmar que usa el documento ya cargado sin round-trip adicional.

7. **Re-embedding por `TEXT_FIELDS` — costo Gemini en edición masiva de categorías**: Si se cambia la categoría de muchos productos a la vez (ej. renombrar una categoría), se dispara re-embedding vía Gemini por cada uno. Confirmar throttling o cap de llamadas para evitar costo descontrolado.

8. **`reindex_businesses_qdrant` ahora re-embebe al ejecutarse**: Con el fix de `connect_to_gemini()`, el script re-embebe todos los negocios. Confirmar que no se dispara involuntariamente en CI, scripts de migración o arranques de dev, generando costo Gemini innecesario.

9. **Backfill con docs crudos — tipos no validados silenciosamente**: Si un doc tiene un campo con tipo incorrecto (ej. `branchId` como string en vez de ObjectId), el payload se construye con tipo incorrecto y los filtros de Qdrant por ese campo no funcionarán hasta corregir el doc.

10. **`delete_by_mongo_id` depende del payload index de `mongo_id`**: Sin el index (que crea `ensure_collections_and_indexes()`), la operación hace full scan en Qdrant. Confirmar que el lifespan siempre crea los indexes antes de que cualquier código de borrado sea invocado.

---

#### Seguimientos vigentes

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

**14 commits** de Ruben0304 y Fabian1820 — día de alta actividad en tres ejes: (1) estabilización completa de la integración Qdrant con 6 fixes críticos, incluyendo el reemplazo del método `.search()` deprecado que causaba vacíos silenciosos en producción; (2) nuevas features de recomendaciones personalizadas vía Qdrant (productos similares, branches similares, sección "Especialmente para Ti" en el feed); y (3) nueva funcionalidad de horarios excepcionales por día en branches con posibilidad de pausar pedidos temporalmente.

---

### Área 1: Qdrant — estabilización crítica (6 commits — Ruben0304)

- **`fix(qdrant): lazy client init + refactor ads auth to use require_role`** (14:46) — `VectorSearchService` obtiene `qdrant_client` lazily vía propiedad en lugar de en `__init__`, de modo que una caída de Qdrant en startup no rompe búsquedas futuras una vez que se recupera. Ads mutations/queries migran de `admin_api_key` a `require_role` para que managers también puedan moderar campañas.
- **`fix(startup): replace blocking Qdrant probe with async wait_for (5s cap)`** (14:50) — `socket.getaddrinfo` era síncrono y bloqueaba el event loop durante startup. Ahora usa `asyncio.wait_for` con cap de 5s para que la app arranque rápido independientemente de la disponibilidad de Qdrant.
- **`fix(search): mensaje de error amigable cuando Qdrant no está disponible`** (15:19) — Captura `RuntimeError("Qdrant client not initialized")` y lanza excepción con mensaje legible; el SearchView lo muestra con ícono y botón Reintentar.
- **`fix(qdrant): retry startup probe and bump client to 1.18.x`** (15:30) — 3 reintentos con 5s de delay, `check_compatibility=False`, bumped a `qdrant-client >=1.18.0`.
- **`test(qdrant): suite de integración completa contra Railway`** (15:46) — Cubre conectividad, insert/read/delete, rendimiento de búsqueda, consistencia MongoDB↔Qdrant y flujo real de creación de producto vía `ProductRepository`.
- **`fix(qdrant): reemplazar .search() deprecated por .query_points() en repositorios`** (16:49) — **Fix crítico**: `qdrant-client 1.16+` eliminó `.search()`; los tres repositorios (products, branches, businesses) retornaban `[]` silenciosamente en producción. Causa raíz del bug donde `searchProducts` devolvía vacío.

---

### Área 2: Recomendaciones y feed personalizado (2 commits — Ruben0304)

- **`feat(feed): sección 'Especialmente para Ti' usando Qdrant recommend API`** (17:03) — Promedia vectores de productos en favoritos/carrito del usuario y devuelve los más similares vía `query_points + RecommendInput`. Auth-gated; falla silenciosamente si Qdrant no está disponible o el usuario no tiene historial.
- **`feat(recommendations): getSimilarProducts, getSimilarBranches, getBranchesForProduct vía Qdrant`** (17:13) — `getSimilarProducts(productId)` y `getSimilarBranches(branchId)` usan `recommend` de Qdrant con UUID como positivo preservando orden Qdrant. `getBranchesForProduct(productId)` recomienda top-50 productos similares → agrupa por `branchId` desde MongoDB → puntúa branches por suma de scores → devuelve top-K sin el branch origen.

---

### Área 3: Panel de pruebas admin (2 commits — Ruben0304)

- **`feat(admin): panel nativo de pruebas de experiencia de cliente`** (16:56) — Endpoints `/admin/tests/suites` y `/admin/tests/run`, protegidos por JWT con `role=admin`. 9 suites (Qdrant, feed scoring, feed performance, combos, push notifications) ejecutables desde la app Llego BI en iOS.
- **`feat(admin/tests): soporte node_ids + categorías agrupadas`** (17:07) — `RunRequest` acepta `suite_id` o `node_ids` para ejecutar tests individuales. `/admin/tests/suites` devuelve categorías con suites embebidas para UI jerárquica en iOS. `_NODE_META` centraliza labels/impact por node ID.

---

### Área 4: MongoDB indexes + limpieza de logging (3 commits — Ruben0304/Fabian1820)

- **`perf: add missing MongoDB indexes and clean up verbose logging`** (18:01) — `_create_order_indexes()`: índices compound en orders. `_create_branch_indexes()`: `businessId` y `(businessId+isActive)` en branches. Reemplaza `print()` de nivel info en hot paths con `logger.error`/`logger.warning`.
- **`Merge remote branch: resolve conflicts`** (18:05) — Merge manual que preserva `maxPoolSize=150` y `_create_search_perf_indexes()` del branch remoto.

---

### Área 5: Threshold de búsqueda y control de pedidos en branches (2 commits)

- **`fix(search): bajar threshold de productos de 0.60 a 0.45`** (17:45) — Captura más resultados de búsqueda vectorial a expensas de menor precisión media.
- **`feat(branches): pausar pedidos + horario excepcional por día`** (21:32) — `acceptingOrders: bool=True` en Branch. Mutation `setAcceptingOrders`. `create_order` valida `acceptingOrders==True`. `TemporaryStatus` extendido con `dailyOverride`. Mutations `setBranchDailyOverride` y `clearBranchDailyOverride`.

---

### Puede dar bateo

1. **`acceptingOrders` — retrocompatibilidad con documentos sin el campo en MongoDB**: `branch_to_dict` hace default a `True`, pero si alguna query filtra directamente en MongoDB por `acceptingOrders == True`, los branches creados antes de este commit quedarán excluidos.
2. **`dailyOverride.date` sin timezone explícita**: Backend en UTC y clientes en Cuba (UTC-5) pueden tener "hoy" diferente justo a medianoche local.
3. **`setBranchDailyOverride` — sin validación de rango de horas**: Si `openTime > closeTime`, el horario resultante es inválido.
4. **Threshold 0.60 → 0.45 — aumento de ruido en resultados de búsqueda**.
5. **`getBranchesForProduct` — doble query Qdrant + MongoDB con top-50**.
6. **`getSimilarProducts/Branches` — UUID no encontrado en Qdrant**.
7. **`Especialmente para Ti` — vector promedio sin normalización explícita**.
8. **Ads auth migrado de `admin_api_key` a `require_role`**: Confirmar que el role `manager` está correctamente asignado en los JWTs.
9. **`check_compatibility=False` en qdrant-client**: Desactiva la verificación de versión cliente-servidor.
10. **Merge manual de conflictos (18:05)**: Confirmar que el merge no perdió `maxPoolSize=150` y `_create_search_perf_indexes()`.
11. **Índices en colecciones existentes — confirmar background build en Atlas**.

---

## 📅 15 de Junio, 2026

### Resumen de cambios (últimas 24h)

**1 commit funcional** de Claude — optimizaciones de performance: event loop desbloqueado en búsquedas (Gemini en thread vía `asyncio.to_thread`), N+1 eliminado en resolvers de vector search (batch `get_by_ids()`), pool y timeouts de MongoDB configurados, cuatro índices de performance añadidos y umbral GZip bajado de 500 a 200 bytes.

---

### Área 1: Performance de búsqueda y acceso a base de datos (1 commit — Claude, Jun 14 15:00)

- **`perf: optimize search path and DB access for slow connections and scale`** — Cinco optimizaciones simultáneas: event loop desbloqueado con `asyncio.to_thread`, N+1 eliminado con `get_by_ids()` batch, pool y timeouts de MongoDB configurados, índices de performance añadidos (`products.availability`, `branches.tipos`, `payment_methods.code`, text index en `tutorials`), GZip `minimum_size` bajado 500 → 200 bytes.

---

### Puede dar bateo

1. **`asyncio.to_thread` — pool de threads por defecto agotado bajo alta concurrencia**.
2. **`get_by_ids()` — puede no estar implementado en todos los repositorios**.
3. **Construcción de índices en colecciones con datos existentes — posible bloqueo**.
4. **GZip sobre respuestas binarias — confirmar exclusión de `application/octet-stream`**.
5. **`minPoolSize` en instancias idle con Atlas M0/M2 — puede agotar el pool global**.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **5, 6, 7, 9, 11 y 12 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). Anteriores eliminadas: 27, 28, 29, 30 de Mayo, 31 de Mayo, 1, 2, 3 y 4 de Junio.
