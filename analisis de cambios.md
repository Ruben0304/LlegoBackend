# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 17 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 16 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**1 commit real** — brianmojena (co-authored Claude Opus 5). Commit puramente de documentación: se reorganiza la referencia del proyecto en un `context.md` maestro y se eliminan 19 archivos .md obsoletos o redundantes.

---

### Área 1: docs — consolidar la documentación en context.md maestro (07:28)

- **`docs: consolidar la documentación en un context.md maestro`** — La raíz del repo tenía 19 archivos .md dispersos: una transcripción de chat Codex (103 KB), tres specs de Kiro ya completadas, dos README vacíos, un duplicado con espacio en el nombre e informes puntuales obsoletos.

  Se añade **`context.md`** como documento único de referencia, verificado contra el código con referencias `archivo:línea`: arquitectura, modelo de datos e índices, autenticación, superficie GraphQL y REST, flujo de pedidos, pagos y KYC, IA y búsqueda, workers, trampas conocidas, bugs abiertos y convenciones.

  **Borrado**: `Codex.md`, specs `.kiro/`, `README_QVAPAY.md`, `README_STRIPE.md`, `"analisis de cambios .md"` (duplicado con espacio en el nombre), `IMPLEMENTACION_COMBO_PRICING.md`, `DELIVERY_FLOW_CONTRACT.md`, los tres `FRONTEND_*_DELIVERY.md` (fusionados en `context.md` §7; además listaban 11 estados de `OrderStatus` cuando hay 12), y `runtime_schema.graphql` (era un traceback de un export fallido, no un schema).

  **Movido a `docs/`**: `AI_ASSISTANT_API.md` → `docs/ai-assistant-api.md`, `README_COMBOS.md` → `docs/combos.md`, `README_STRIPE_RECHARGE.md` → `docs/stripe-recharge.md`, con referencias cruzadas corregidas.

  **`README.md`**: corregía prefijos REST erróneos (`/api/users` → `/users`, `/api/uploads` → `/upload`, `/api/push-notifications` → `/api/push`) y mencionaba solo Stripe como pasarela de pago (se añade QvaPay).

  **`CLAUDE.md`**: ahora apunta a `context.md` en vez de duplicar su contenido.

---

### Puede dar bateo

1. **Rutas de docs movidas — links rotos**: `AI_ASSISTANT_API.md`, `README_COMBOS.md` y `README_STRIPE_RECHARGE.md` se movieron a `docs/`. Cualquier herramienta, wiki externa, script CI o bookmark que apunte a las rutas antiguas en la raíz verá 404.

2. **`DELIVERY_FLOW_CONTRACT.md` y `FRONTEND_*_DELIVERY.md` eliminados**: Fusionados en `context.md` §7. Si el frontend de apps móviles o algún cliente usaba estos archivos como contrato de integración, necesita actualizarse a esa sección.

3. **`OrderStatus` listaba 11 estados, hay 12**: Los archivos eliminados tenían este error. Confirmar que el frontend de las apps (móvil, cliente) conoce los 12 estados actuales de `OrderStatus`.

4. **`runtime_schema.graphql` borrado**: Era un traceback de export fallido. Si algún script CI, herramienta de introspección o pipeline de generación de tipos lo busca como input, falla silenciosamente.

---

## 📅 15 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**1 commit real** — brianmojena (co-authored Claude Opus 5). Fix de infraestructura crítico: las notificaciones push a dispositivos Android nunca llegaban.

---

### Área 1: feat(push) — enviar notificaciones FCM reales a dispositivos Android (05:13)

- **`feat(push): send real FCM notifications to Android devices`** — `fcm_configured` estaba hardcodeado a `False` y `_send_fcm` era un stub que logueaba y reportaba éxito sin enviar nada; las actualizaciones de estado de pedidos a tokens Android se perdían en silencio desde siempre.

  `_send_fcm` ahora envía por FCM HTTP v1 autenticado con una cuenta de servicio de Firebase leída desde la variable de entorno `FCM_SERVICE_ACCOUNT_JSON`. Usa `google-auth` y `httpx` (ya dependencias del proyecto). El token OAuth se cachea y se refresca fuera del event loop. `project_id` viene de la credencial y nunca se loguea. Los mensajes llevan `channel_id: llego_orders` y las mismas claves de datos del notificador de estado de pedidos (`type`, `orderId`, `orderNumber`, `status`), como strings. Tokens que FCM reporta como `UNREGISTERED` o `INVALID_ARGUMENT` se desactivan; otros errores fallan ese token sin detener el lote.

  Sin la credencial, FCM ahora devuelve fallo explícito `fcm_not_configured` en vez de faking success. El notificador KYC siempre usa `platform IOS`, por lo que no se ve afectado por este cambio.

---

### Puede dar bateo

1. **`FCM_SERVICE_ACCOUNT_JSON` — confirmar variable de entorno en producción**: Sin ella todos los envíos a Android fallan con `fcm_not_configured`. Es el requisito de deploy más crítico del cambio.

2. **`google-auth` y `httpx` — confirmar en el entorno de producción**: El commit dice "ya dependencias", pero si el contenedor de producción no se ha reconstruido tras añadirlas al `requirements.txt`, el import falla al arrancar.

3. **Token OAuth cacheado — comportamiento bajo alta concurrencia al expirar**: El refresh ocurre fuera del event loop. Si el token expira con múltiples envíos pendientes puede haber una ráfaga de refreshes simultáneos. Confirmar que el mecanismo es thread-safe o coroutine-safe.

4. **Tokens desactivados permanentemente por `UNREGISTERED`/`INVALID_ARGUMENT`**: Si FCM devuelve estos códigos por error transitorio (raro pero posible), el token queda desactivado y el dispositivo deja de recibir notificaciones hasta que el usuario re-registre.

5. **Notificador KYC usa siempre `platform IOS`**: Si en algún momento se necesita notificación KYC a Android, requiere trabajo adicional.

---

## 📅 14 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 11 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 10 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

> ⚠️ **Nota de mantenimiento**: La entrada del **9 de Septiembre** fue eliminada el 17 de Septiembre al superar los 7 días de antigüedad (política de retención semanal). La entrada del **7 de Septiembre** fue eliminada el 15 de Septiembre. La entrada del **2 de Septiembre** fue eliminada el 10 de Septiembre. Anteriores eliminadas progresivamente desde Mayo.
