# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 8 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

**1 commit real** — Brian. Sesión concentrada en seguridad y exposición del buzón de errores interno vía GraphQL para Panel Admin.

---

### Área 1: feat(errors) — exponer el error inbox por GraphQL y cerrar la REST API (01:43)

- **`feat(errors): expose the error inbox over GraphQL and lock down its REST API`** — El sistema de error-tracking interno (captura vía `ErrorLoggingExtension`, análisis por Gemini, deduplicación por ocurrencia) no tenía interfaz para Panel Admin. Se agregan:
  - **Queries GraphQL**: `admin_error_logs` (paginado, filtrable por source/severity/resolved/fecha/search) y `admin_error_stats` (resumen `$facet` ya existente).
  - **Mutations**: `admin_resolve_error` y `admin_unresolve_error`. Ahora `resolved_by` se escribe con el admin actuante (campo que nunca se llenaba antes).
  - Todas detrás de `require_role([admin, manager])`.
  - **Fix de seguridad crítico**: 8 endpoints REST bajo `/api/error-logs` eran públicamente accesibles — `GET /` y `/stats` exponían stack traces, IPs de clientes y user IDs; `DELETE /cleanup` permitía a cualquiera purgar todos los logs; los dos endpoints `/test-push` permitían enviar push notifications a todos los usuarios de una app sin autenticación. Todos ahora detrás de `require_admin_api_key` extraído a `utils/auth.py`. `POST /mobile-report` permanece abierto intencionalmente (intake de crashes de apps móviles).
  - 7 archivos modificados: 658 líneas añadidas, 9 eliminadas. Test suite nueva: `tests/test_admin_error_inbox.py` (355 líneas).

---

### Puede dar bateo

1. **`require_role([admin, manager])` — confirmar que los tokens JWT incluyen el campo de rol con exactamente esos valores**: Si el campo es `role` vs `roles`, o el valor es `"administrador"` en lugar de `"admin"`, el check falla con 403 para usuarios legítimos sin error claro.

2. **`resolved_by` — confirmar que el campo existe en el documento MongoDB de `ErrorLog`**: Si el campo no estaba declarado en el schema Pydantic, MongoDB lo guarda pero Pydantic puede descartarlo en la lectura. Verificar que `domain/error_logs.py` lo declara.

3. **`admin_error_logs` paginado — confirmar que Panel Admin envía los parámetros de paginación con el nombre exacto esperado por la query GraphQL**: Si el frontend usa nombres distintos, la primera carga funciona pero el scroll infinito o la navegación de páginas puede romper.

4. **`POST /mobile-report` abierto — verificar que la respuesta no expone información interna del error procesado**: El intake debe aceptar el crash pero no devolver el análisis de Gemini ni el stack trace interno.

5. **`require_admin_api_key` extraído a `utils/auth.py` — confirmar que no hay otros archivos que lo importaban con ruta relativa local**: Si algún archivo tenía `from .auth import require_admin_api_key` o equivalente local, el import rompe tras mover la función.

---

## 📅 7 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

## 📅 2 de Septiembre, 2026

### Resumen de cambios (últimas 24h)

Sin commits nuevos de código. El único commit del período es "Analisis diario Claude" (generado automáticamente). No hay cambios en producción en LlegoBackend.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos.

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **31 de Agosto** y **1 de Septiembre** fueron eliminadas el 8 de Septiembre al superar los 7 días de antigüedad (política de retención semanal). Anteriores eliminadas: 19–23 de Junio, 26–30 de Junio, 1–8 de Julio, 10–11, 13–15, 17–23 de Julio, 24–31 de Julio, 1–8, 10–15, 17–23, 24–30 de Agosto.
