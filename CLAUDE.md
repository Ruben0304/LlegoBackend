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
pytest tests/ -v                     # ⚠️ 46-48 fallos preexistentes: compara contra esa base
python scripts/export_schema.py
```

Entorno: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

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
