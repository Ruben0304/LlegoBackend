# CLAUDE.md

Guía para Claude Code (claude.ai/code) al trabajar en este repositorio.

## Lee esto primero

**[context.md](context.md) es el documento maestro del proyecto.** Contiene arquitectura,
modelo de datos, autenticación, flujo de pedidos, pagos, trampas conocidas y la lista de
bugs abiertos verificados. Consúltalo antes de planificar cualquier cambio, y **actualízalo**
cuando un cambio tuyo invalide algo de lo que dice.

Contratos de API más largos: `docs/ai-assistant-api.md`, `docs/combos.md`,
`docs/stripe-recharge.md`.

## Resumen

**Llego Backend**: FastAPI con GraphQL (Strawberry) + REST, sobre MongoDB.

```
api/ + schema/   interfaz
services/        lógica de negocio
repositories/    acceso a datos
domain/          modelos Pydantic
clients/         infraestructura (MongoDB, Qdrant, Gemini, S3)
core/            configuración
utils/           auth, serialización, caché, S3, rate limit
scripts/         seeds, migraciones, utilidades de un solo uso
tests/           pytest
```

## Comandos

```bash
python main.py                       # o: uvicorn main:app --reload --host 0.0.0.0 --port 8000
pytest tests/ -v                     # ⚠️ fallos preexistentes: ver tests/known_failures.txt
python scripts/ci/run_tests.py       # como el CI: solo falla ante fallos NUEVOS
python scripts/ci/check_schema_breaking.py   # schema del código vs producción (cambios incompatibles)
python scripts/export_schema.py
```

Entorno: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

## CI (GitHub Actions)

`.github/workflows/ci.yml` corre en cada push a `main` y en cada pull request, con dos jobs
independientes (solo `ubuntu-latest`, sin coste de runners de macOS):

- **`tests`: pytest solo con fallos nuevos.** Ejecuta la suite con un MongoDB vacío (servicio
  `mongo:7`) y las variables de entorno de prueba de abajo. `scripts/ci/run_tests.py` compara
  los fallos con `tests/known_failures.txt` y solo falla si aparece uno que no está en la
  lista. Un fallo nuevo se repite una vez de forma aislada: si pasa, se avisa como
  "inestable" y no rompe el CI. Si un test de la lista ya pasa, el runner lo avisa para que
  lo quites (la lista solo debe encoger).
- **`schema`: compatibilidad con los clientes publicados.** `scripts/ci/check_schema_breaking.py`
  exporta el schema del código, descarga el de producción
  (`https://llegobackend-production.up.railway.app/graphql`, o `LLEGO_GRAPHQL_URL`) y los
  compara con `graphql.find_breaking_changes`. Falla ante campos o tipos quitados, argumentos
  nuevos obligatorios, tipos cambiados, etc., porque las apps ya publicadas siguen usando el
  schema de producción. Los cambios "peligrosos" (p. ej. un valor nuevo en un enum) solo se
  avisan.

Para ejecutarlo en local, desde la raíz y con el entorno virtual activo:

```bash
export MONGODB_URL=mongodb://localhost:27017 GEMINI_API_KEY=test AWS_ACCESS_KEY_ID=test \
  AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 AWS_ENDPOINT_URL=http://localhost \
  S3_BUCKET_NAME=test JWT_SECRET=ci-test-jwt-secret-not-for-production-0123456789

python scripts/ci/run_tests.py                 # pytest + lista de fallos conocidos (necesita MongoDB)
python scripts/ci/run_tests.py tests/test_security.py -x   # los argumentos van a pytest
python scripts/ci/check_schema_breaking.py     # schema del código vs producción (necesita red)
python scripts/ci/check_schema_breaking.py --prod-schema-file otro.graphql   # sin red
```

**Permitir un cambio incompatible del schema a propósito** (retirar un campo que ya no usa
ninguna app, o cuando la actualización forzada ya está en marcha): pon la etiqueta
`breaking-schema-ok` a la pull request (el job se vuelve a evaluar solo) o define la variable
de repositorio `ALLOW_BREAKING_SCHEMA=true` mientras dure la migración y quítala después.
En local: `ALLOW_BREAKING_SCHEMA=true`. En los push a `main` el job solo informa, porque la
PR ya pasó por la puerta. Antes de quitar un campo, prefiere marcarlo con `deprecation_reason`
y retirarlo cuando ningún cliente lo use (los repos cliente validan sus operaciones contra
producción a diario, ver su `CLAUDE.md`).

**Mantener `tests/known_failures.txt`:** un nodeid por línea (`*` como comodín, `#` para
comentarios). Tiene dos bloques: tests que dependen de servicios externos o de la máquina
(Qdrant, API de Anthropic, rendimiento), permitidos por archivo, y fallos deterministas
preexistentes pendientes de arreglar. Al arreglar un test, quítalo de la lista; no añadas
fallos nuevos sin un comentario que explique por qué fallan.

## Convenciones

- Entidades de dominio solo en `domain/`, nunca en la raíz.
- Lógica de negocio en `services/`; persistencia en `repositories/`; proveedores externos en `clients/`.
- Scripts de un solo uso, seeds y migraciones en `scripts/`.
- Importa los repositorios desde las instancias ya exportadas en `repositories/__init__.py`.
- Extrae la lógica pura a funciones testeables sin Mongo (`services/orders_utils.py`,
  `services/user_metrics.py` son el precedente).

## Avisos críticos

- La colección MongoDB `bussisnes` **está mal escrita a propósito**; mantenla así.
- El entrypoint GraphQL es `/graphql`; los endpoints de descarga del schema se montan en `main.py`.
- **No hay middleware de autenticación.** Cada resolver debe llamar a `require_auth` /
  `require_role` en su primera línea; si lo olvidas, el resolver queda abierto.

- ⚠️ **Añadir un campo a `Business`, `Branch`, `Product` o `User` en `domain/models.py`
  rompe queries en tiempo de request.** Esos modelos se convierten a sus tipos GraphQL
  volcando el modelo *entero* con `to_strawberry_dict()` y desempaquetándolo como
  `SomeType(**data)` (78 sitios). Un campo nuevo no declarado en el tipo destino revienta
  toda query que lo use con "unexpected keyword argument" — y `py_compile`, mypy y el
  linter **no lo detectan**. Ya ha pasado dos veces.

  Antes de añadir un campo a esos cuatro modelos:

  ```bash
  grep -rn "BusinessType(\|BranchType(\|ProductType(\|UserType(" schema/
  ```

  Luego, o lo declaras en cada tipo GraphQL afectado, o lo excluyes. Para `Branch` hay un
  único sitio central: el set `exclude` de `branch_to_dict()` en `schema/branches/utils.py`,
  que cubre `BranchType`/`ScoredBranchType`/`NearbyBranchType` de una vez. `Business`,
  `Product` y `User` no tienen helper central: hay que tocar cada call site.

  Ver `context.md` sección 11 para el detalle completo.
