# Validación de cartas y menús — 28 de octubre de 2026

La integración se probó sobre `origin/main` en `a2ac3d60720d8cad20eec4d1aadab81778e405ad`.
La rama original `feat/menu-ocr-search` estaba 103 commits por detrás. Se resolvieron
los conflictos de índices, repositorios y documentación conservando las funciones de main.

## Resultados

| Comprobación | Resultado |
| --- | --- |
| Cartas, permisos, búsqueda, OCR y persistencia | 173 pasan, sin omisiones |
| Suite general integrada, Python 3.12 | 1.074 pasan, 13 fallos conocidos, 82 E2E omitidas en esta ejecución |
| Misma suite sobre main sin cartas | 901 pasan, los mismos 13 fallos, 82 E2E omitidas |
| Suite E2E completa contra backend local y sandbox | 82 pasan |
| Compatibilidad GraphQL contra producción | Ningún cambio incompatible; 302 tipos actuales, 306 con cartas |
| Dependencias fijadas y `pip check` | Sin dependencias incompatibles |
| `git diff --check` | Sin errores |

El runner `scripts/ci/run_tests.py` terminó con código 0: **13 fallos conocidos,
0 nuevos y 0 inestables**. Se compararon también los identificadores de los fallos
entre main y la integración; son exactamente los mismos.
Los 13 corresponden a 3 pruebas de pagos/KYC, 7 de precios de combos y 3 de feed.
No se modificó `tests/known_failures.txt` para ocultar fallos.

## Correcciones verificadas

- La subida requiere `branch_id` en el multipart y comprueba acceso antes de subir.
  Las claves S3 se guardan bajo `branch_menus/<branchId>/`.
- Una sucursal no puede asociar ni borrar la imagen de otra. La limpieza también
  comprueba el prefijo, incluso si un documento antiguo contiene una clave ajena.
- `first` y el límite del servicio rechazan cero y negativos; máximo 20 resultados.
- El reemplazo de imagen devuelve la imagen anterior atómicamente. La prueba con
  16 reemplazos simultáneos conserva todas las referencias para limpiar S3.
- Veinte primeras subidas simultáneas dejan un único documento por sucursal.
- Veinticuatro workers reclamando 12 cartas no procesan una misma carta dos veces.
- Se respeta la precisión de milisegundos de las fechas de MongoDB.
- La prueba de timeout usa una función síncrona lenta en un hilo y comprueba que
  se guarda `TimeoutError`, en lugar de simular incorrectamente una función async.

El flujo de cartas por HTTP recorre autenticación JWT, denegación de usuario ajeno,
subida, GraphQL, OCR real, guardado en MongoDB real, búsqueda con polígonos,
ocultación de carta, acceso privado del propietario y borrado. Solo se simula S3.
También se comprueban errores de lectura, resultados de OCR obsoletos tras cambiar
la imagen, reencolado de trabajos atascados, tildes, erratas y alcance de búsqueda.

## Entorno y reproducción

Python 3.12, dependencias exactas de `requirements.txt` más pytest 9.1.1 y
pytest-asyncio 1.4.0. MongoDB 8.0.34 local en el puerto 27128. Cada prueba nueva de
integración crea una base con nombre aleatorio y la elimina al terminar. Solo admite
localhost mediante `MENU_TEST_MONGODB_URL`. El CI también configura esa variable
para ejecutar estas pruebas con su MongoDB 7.

Desde la raíz de la integración, con un entorno Python 3.12 y MongoDB local:

```sh
export MONGODB_URL=mongodb://127.0.0.1:27128
export MENU_TEST_MONGODB_URL="$MONGODB_URL"
export MONGODB_DATABASE=llego_menu_validation
export GEMINI_API_KEY=test AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1 AWS_ENDPOINT_URL=http://127.0.0.1:27129
export S3_BUCKET_NAME=test JWT_SECRET=ci-test-jwt-secret-not-for-production-0123456789
export ANTHROPIC_API_KEY= REDIS_URL=redis://127.0.0.1:6399

python scripts/ci/run_tests.py tests -q --disable-warnings --tb=short \
  --continue-on-collection-errors \
  --ignore=tests/test_qdrant.py --ignore=tests/test_anthropic_migration.py \
  --ignore=tests/test_qvapay_webhook.py --ignore=tests/test_feed_e2e_performance.py
python scripts/ci/check_schema_breaking.py
```

Para E2E se arrancó la aplicación en localhost:8128 con `E2E_SANDBOX_KEY` y
`E2E_KEY` iguales (clave ficticia), y `E2E_BASE_URL=http://127.0.0.1:8128`.
Después se ejecutó `python -m pytest tests/e2e -q`. El cliente verifica que el
servidor confirma el sandbox y que la base tiene el sufijo `_e2e` antes de escribir.

## Límites de esta validación

- No se escribieron datos ni imágenes en producción. La comparación GraphQL fue de lectura.
- Se excluyeron cuatro archivos de pruebas externas/manuales: Qdrant apunta a un
  servicio real y escribe puntos; Anthropic consume una API real; QvaPay simula pagos
  contra otro servidor; el benchmark del feed requiere datos externos.
- S3 se probó con un cliente simulado en memoria; no con un bucket real.
- Se ejecutó en macOS ARM64. No se ha ejecutado todavía el CI en Linux ni el arranque
  en el contenedor de Railway con las nuevas dependencias nativas de OCR.
- La calidad de OCR se comprobó con imágenes sintéticas y las regresiones existentes;
  faltan fotos reales de los negocios para calibrar los umbrales.
- El timeout de asyncio deja de esperar, pero no termina el hilo nativo del OCR.
  Los errores de OCR quedan en `failed` y requieren volver a subir la imagen.

La validación y las correcciones no implican que ya se haya desplegado en main.
