# Registro de Análisis de Cambios — LlegoBackend

---

## 📅 14 de Octubre, 2026

### Resumen de cambios (últimas 24h)

**2 commits** — Fabian1820. Día de infraestructura: CI completo en GitHub Actions y merges de la fase 2b con rate limit mejorado, enmascaramiento de errores inesperados y detección de IP del cliente.

---

### Área 1: CI del backend y lock de dependencias (15:11)

`merge: fase 2b CI del backend y lock de dependencias`

Infraestructura de CI añadida de una vez:
- **GitHub Actions** (`.github/workflows/ci.yml`, 91 líneas): dos jobs independientes — `tests` (pytest con lista de fallos conocidos sobre MongoDB vacío) y `schema` (compara el schema del código con producción detectando cambios incompatibles con `graphql.find_breaking_changes`).
- **Gestión de dependencias**: `requirements.in` con rangos editables como fuente; `requirements.txt` regenerado como lock file con versiones exactas (+247/-24). `.python-version` fija Python 3.12.
- **Scripts CI**: `scripts/ci/run_tests.py` (189 líneas — solo falla ante fallos nuevos, no ante los de la lista conocida) y `scripts/ci/check_schema_breaking.py` (221 líneas — schema actual vs. producción).
- **`tests/known_failures.txt`**: 54 líneas con tests que dependen de servicios externos o fallos preexistentes conocidos.
- `CLAUDE.md` actualizado (+57/-2) con la nueva sección de CI y convenciones de dependencias.

---

### Área 2: Rate limit, errores enmascarados y platformFeatures (15:11)

`merge: fase 2b rate limit, errores enmascarados y platformFeatures`

- **Enmascaramiento de errores inesperados** (`utils/exception_handler.py` +3/-16, `schema/extensions.py` +101/-7): excepciones no controladas ya no filtran stack traces al cliente — se loguean internamente y devuelven un mensaje genérico. Cubierto por el nuevo `tests/test_mask_unexpected_errors.py` (135 líneas).
- **Detección de IP del cliente** (`utils/client_ip.py`, 94 líneas nuevas): utilidad para extraer la IP real detrás de proxies/load balancers. Cubierta por `tests/test_client_ip.py` (265 líneas).
- **Rate limiting** (`utils/rate_limit.py` +10/-14): lógica refactorizada, integrada con la nueva extensión de schema.
- **`platformFeatures`** en `schema/app_config/queries.py` (+24) y `types.py` (+19): nueva query/tipo para exponer flags de características por plataforma a los clientes móviles.
- **Variables de entorno**: `.env.example` ampliado con 5 nuevas vars (para rate limit y/o configuración de IP de confianza).
- **`context.md`**: actualizado (+62/-6) para reflejar la nueva arquitectura de seguridad.

---

### Puede dar bateo

1. **CI — `tests/known_failures.txt` con 54 entradas desde el primer día**: Si algún test de la lista ya pasa en CI, el runner avisará para quitarlo. Limpiar la lista periódicamente o el CI acumulará "ruido verde" que enmascara fallos reales nuevos.

2. **CI schema check — requiere red hacia producción**: `check_schema_breaking.py` descarga el schema de `llegobackend-production.up.railway.app`. Si Railway está caído durante el CI, el job de schema falla aunque el código esté bien. Confirmar que el fallback `--prod-schema-file` está documentado y accesible para ese caso.

3. **Enmascaramiento de errores — logging interno crítico antes de producción**: Con el nuevo masking los errores inesperados no se ven en la respuesta GraphQL. Si el logging interno (Railway logs, Sentry u otro) no está configurado correctamente, los bugs silenciosos serán imposibles de rastrear. Verificar que los logs llegan a un destino observable antes del siguiente deploy.

4. **`utils/client_ip.py` — confianza en X-Forwarded-For**: La detección de IP real típicamente lee `X-Forwarded-For`. Si el servidor no está detrás de un proxy de confianza configurado, cualquier cliente puede falsificar su IP y evadir el rate limit por IP. Confirmar que la utilidad valida el número de saltos o usa una lista blanca de proxies de confianza.

5. **`platformFeatures` en schema — verificar que no rompe queries existentes**: Si `platformFeatures` se añadió a un tipo GraphQL que usa `to_strawberry_dict()` + desempaquetado `**data`, un campo no declarado en el tipo destino puede reventar las queries que lo usen (ver aviso CLAUDE.md). Ejecutar el grep indicado en CLAUDE.md para confirmar que todos los call sites tienen el campo declarado.

6. **Rate limit refactorizado — confirmar que los límites no cambiaron sin querer**: Con +101/-7 en `schema/extensions.py`, pueden haberse cambiado valores de límite o la lógica de ventana de tiempo. Si los límites son más estrictos, las apps en producción pueden empezar a recibir 429 inesperadamente tras el deploy.

---

## 📅 13 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit del período fue el "Analisis diario Claude" del bot. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 10 de octubre (guard de vehículo en `acceptOrderForPayment` sin mensaje claro, race condition vehículo vs. aceptación, mensajeros existentes sin vehículo que no pueden aceptar pedidos, código downstream que asume `vehicle` siempre presente, pedidos en curso si se retira el vehículo durante la entrega).

---

## 📅 12 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 10 de octubre (guard de vehículo en `acceptOrderForPayment` sin mensaje claro, race condition vehículo vs. aceptación, mensajeros existentes sin vehículo que no pueden aceptar pedidos, código downstream que asume `vehicle` siempre presente, pedidos en curso si se retira el vehículo durante la entrega).

---

## 📅 11 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 10 de octubre (guard de vehículo en `acceptOrderForPayment` sin mensaje claro, race condition vehículo vs. aceptación, mensajeros existentes sin vehículo que no pueden aceptar pedidos, código downstream que asume `vehicle` siempre presente, pedidos en curso si se retira el vehículo durante la entrega).

---

## 📅 10 de Octubre, 2026

### Resumen de cambios (últimas 24h)

**1 commit** — Fabian1820. Merge de feature: vehículo desvinculado del modelo base de mensajero pero obligatorio para aceptar pedidos.

---

### Área 1: merge — deliveryPerson sin vehículo, vehículo obligatorio para aceptar pedidos (16:54)

`merge: deliveryPerson sin vehículo y vehículo obligatorio para aceptar pedidos`

Merge de una rama de feature. Cambios combinados:
- Un mensajero puede existir en el sistema sin vehículo asignado (campo ahora opcional en el modelo/BD).
- Al intentar aceptar un pedido, el sistema verifica que el mensajero tenga un vehículo activo; sin él, la aceptación se rechaza.

Probablemente responde al flujo de onboarding donde un mensajero se registra antes de asignarle su vehículo.

---

### Puede dar bateo

1. **Guard de vehículo en `acceptOrderForPayment` — mensaje de error claro**: Si no se devuelve un error descriptivo cuando falta vehículo, la app mostrará un fallo genérico. Confirmar que el mensaje llega al mensajero explicando qué falta.

2. **Race condition vehículo vs. aceptación**: Si entre el check de vehículo y el insert del pedido un admin elimina/desactiva el vehículo del mensajero, el guard pasa pero el mensajero actúa sin vehículo. Confirmar si hay lock/transacción.

3. **Mensajeros existentes sin vehículo**: Los mensajeros ya registrados que no tengan vehículo no podrán aceptar pedidos. La app debe guiarlos a registrar un vehículo en lugar de mostrar un error genérico.

4. **Código downstream que asume `vehicle` siempre presente**: Si el campo vehículo pasó de requerido a opcional, cualquier acceso a `delivery_person.vehicle.X` sin verificar `None` lanzará `AttributeError`. Revisar rutas de tracking, notificaciones y el propio `acceptOrderForPayment`.

5. **Pedidos en curso si se elimina el vehículo**: El guard aplica al aceptar, pero si durante una entrega activa un admin retira el vehículo del mensajero, hay que confirmar que la entrega en curso no se ve afectada.

---

## 📅 8 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. El único commit del período fue el "Analisis diario Claude" del bot. No hay cambios en producción en LlegoBackend hoy.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 5 de octubre (guard de mensajero activo, ventana de concurrencia en `acceptOrderForPayment`, merge de Fase 2a sin descripción).

---

## 📅 7 de Octubre, 2026

### Resumen de cambios (últimas 24h)

Sin commits de código nuevos. No hay cambios en producción en LlegoBackend hoy. El único commit fue el "Analisis diario Claude" del bot.

---

### Puede dar bateo

Sin cambios nuevos — sin riesgos nuevos. Se mantienen las consideraciones del 5 de octubre (guard de mensajero activo, ventana de concurrencia en `acceptOrderForPayment`, merge de Fase 2a sin descripción).

---

> ⚠️ **Nota de mantenimiento**: Las entradas del **5 de Octubre** y anteriores fueron eliminadas el 13 de Octubre al superar los 7 días de antigüedad (política de retención semanal).
