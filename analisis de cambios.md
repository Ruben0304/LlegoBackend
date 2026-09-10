# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 10 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 9 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**1 commit real** — brianmojena (co-authored Claude Opus 5). Commit de seguridad importante: expone el sistema de tracking de errores a GraphQL y blinda los endpoints REST que estaban públicos.

---

### Área 1: feat(errors) — exponer el inbox de errores por GraphQL y blindar su REST API (05:43)

- **`feat(errors): expose the error inbox over GraphQL and lock down its REST API`** — El backend ya contaba con un sistema completo de tracking de errores (captura via `ErrorLoggingExtension`, análisis por Gemini con resumen/causa probable/sugerencias/severidad/archivo:línea, deduplicación por ocurrencia, y métodos `mark_resolved`/`mark_unresolved`) pero sin ninguna forma de accederlo desde Panel Admin (que habla GraphQL).

  **Nuevas queries/mutations GraphQL** (todas detrás de `require_role([admin, manager])`):
  - `admin_error_logs` — paginado, filtrable por fuente/severidad/resuelto/fecha/búsqueda
  - `admin_error_stats` — resumen `$facet` ya existente
  - `admin_resolve_error` / `admin_unresolve_error` — ahora graba el actor en `resolved_by` (antes ese campo nunca se escribía)

  **Fix de seguridad:** Todos los endpoints bajo `/api/error-logs` eran públicos. GET `/` y `/stats` exponían stack traces, endpoints, IPs y user IDs; DELETE `/cleanup` permitía a cualquiera purgar el log completo; los dos `/test-push` permitían enviar push a todos los usuarios de una app sin autenticación. Ahora todos protegidos con la clave estática de admin, extraída al helper `utils.auth.require_admin_api_key`. POST `/mobile-report` sigue abierto intencionalmente: es el intake de crasheos de las apps móviles.

---

### Puede dar bateo

1. **`require_role([admin, manager])` en GraphQL — verificar asignaciones en BD**: Si un admin o manager no tiene el rol correcto en MongoDB, no podrá acceder a las queries de errores aunque esté autenticado.

2. **`utils.auth.require_admin_api_key` centralizado — confirmar variable de entorno en todos los environments**: La clave ahora vive en un solo lugar. Verificar que está definida en prod y staging con el mismo valor que usaban los otros routers ya deployados.

3. **"Ningún client app llama a estos endpoints" — verificar antes del deploy**: Si la app móvil o algún otro cliente llama a cualquier endpoint de `/api/error-logs` (excepto `/mobile-report`), recibirá un 401 inesperado tras el deploy.

4. **Campo `resolved_by` — confirmar tolerancia en documentos existentes**: Si el campo es nuevo en la colección, los documentos históricos de errores no lo tendrán. Confirmar que el código de lectura maneja `resolved_by: null/undefined` sin romper las queries.

5. **Paginación en `admin_error_logs` — confirmar implementación en Panel Admin**: Si Panel Admin carga todo de golpe (sin botón "cargar más"), con una colección grande puede causar timeout o cargar miles de documentos en memoria.

---

## 📅 7 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

> ⚠️ **Nota de mantenimiento**: La entrada del **2 de Septiembre** fue eliminada el 10 de Septiembre al superar los 7 días de antigüedad (política de retención semanal). Las entradas del **31 de Agosto** y **1 de Septiembre** fueron eliminadas el 9 de Septiembre al superar los 7 días de antigüedad (política de retención semanal). Las entradas del **19, 20 y 21 de Junio** y del **23 de Junio** fueron eliminadas al superar los 7 días de antigüedad (política de retención semanal). La entrada del **26 de Junio** fue eliminada el 4 de Julio al superar los 7 días. La entrada del **28 de Junio** fue eliminada el 6 de Julio al superar los 7 días. La entrada del **29 de Junio** fue eliminada el 7 de Julio al superar los 7 días. La entrada del **30 de Junio** fue eliminada el 8 de Julio al superar los 7 días. Las entradas del **1 y 2 de Julio** fueron eliminadas el 10 de Julio al superar los 7 días. La entrada del **3 de Julio** fue eliminada el 11 de Julio al superar los 7 días. Las entradas del **4 y 5 de Julio** fueron eliminadas el 13 de Julio al superar los 7 días. La entrada del **6 de Julio** fue eliminada el 14 de Julio al superar los 7 días. La entrada del **7 de Julio** fue eliminada el 15 de Julio al superar los 7 días. La entrada del **8 de Julio** fue eliminada el 17 de Julio al superar los 7 días. La entrada del **10 de Julio** fue eliminada el 18 de Julio al superar los 7 días. La entrada del **11 de Julio** fue eliminada el 19 de Julio al superar los 7 días. La entrada del **13 de Julio** fue eliminada el 21 de Julio al superar los 7 días. La entrada del **14 de Julio** fue eliminada el 22 de Julio al superar los 7 días. La entrada del **15 de Julio** fue eliminada el 23 de Julio al superar los 7 días. La entrada del **17 de Julio** fue eliminada el 25 de Julio al superar los 7 días. La entrada del **18 de Julio** fue eliminada el 26 de Julio al superar los 7 días. La entrada del **19 de Julio** fue eliminada el 27 de Julio al superar los 7 días. La entrada del **20 de Julio** fue eliminada el 28 de Julio al superar los 7 días. La entrada del **21 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **22 de Julio** fue eliminada el 30 de Julio al superar los 7 días. La entrada del **23 de Julio** fue eliminada el 31 de Julio al superar los 7 días. La entrada del **24 de Julio** fue eliminada el 1 de Agosto al superar los 7 días. La entrada del **25 de Julio** fue eliminada el 2 de Agosto al superar los 7 días. La entrada del **26 de Julio** fue eliminada el 3 de Agosto al superar los 7 días. La entrada del **27 de Julio** fue eliminada el 4 de Agosto al superar los 7 días. La entrada del **28 de Julio** fue eliminada el 5 de Agosto al superar los 7 días. La entrada del **30 de Julio** fue eliminada el 7 de Agosto al superar los 7 días. La entrada del **31 de Julio** fue eliminada el 8 de Agosto al superar los 7 días. Las entradas del **1, 2 y 3 de Agosto** fueron eliminadas el 10 de Agosto al superar los 7 días. La entrada del **4 de Agosto** fue eliminada el 12 de Agosto al superar los 7 días. La entrada del **5 de Agosto** fue eliminada el 13 de Agosto al superar los 7 días. La entrada del **6 de Agosto** fue eliminada el 14 de Agosto al superar los 7 días. La entrada del **7 de Agosto** fue eliminada el 15 de Agosto al superar los 7 días. La entrada del **8 de Agosto** fue eliminada el 17 de Agosto al superar los 7 días. La entrada del **10 de Agosto** fue eliminada el 18 de Agosto al superar los 7 días. La entrada del **11 de Agosto** fue eliminada el 19 de Agosto al superar los 7 días. La entrada del **12 de Agosto** fue eliminada el 20 de Agosto al superar los 7 días. La entrada del **13 de Agosto** fue eliminada el 21 de Agosto al superar los 7 días. La entrada del **14 de Agosto** fue eliminada el 22 de Agosto al superar los 7 días. La entrada del **15 de Agosto** fue eliminada el 23 de Agosto al superar los 7 días. La entrada del **17 de Agosto** fue eliminada el 25 de Agosto al superar los 7 días. La entrada del **18 de Agosto** fue eliminada el 26 de Agosto al superar los 7 días. La entrada del **19 de Agosto** fue eliminada el 27 de Agosto al superar los 7 días. La entrada del **20 de Agosto** fue eliminada el 28 de Agosto al superar los 7 días. La entrada del **21 de Agosto** fue eliminada el 29 de Agosto al superar los 7 días. La entrada del **22 de Agosto** fue eliminada el 30 de Agosto al superar los 7 días. La entrada del **23 de Agosto** fue eliminada el 31 de Agosto al superar los 7 días. La entrada del **24 de Agosto** fue eliminada el 1 de Septiembre al superar los 7 días. La entrada del **25 de Agosto** fue eliminada el 2 de Septiembre al superar los 7 días. Las entradas del **26, 27, 28, 29 y 30 de Agosto** fueron eliminadas el 7 de Septiembre al superar los 7 días. Anteriores eliminadas: 16, 17 y 18 de Junio, 5, 6, 7, 9, 11, 12 y 15 de Junio, y días de Mayo.
