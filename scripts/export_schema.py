"""
Exporta el esquema GraphQL definido en main.py a archivos locales:
- schema.graphql (SDL)
- schema.json (introspección JSON)

Uso:
  python scripts/export_schema.py
"""

import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Importa el schema desde la app
from main import schema

OUTPUT_DIR = Path(__file__).resolve().parent
SDL_PATH = OUTPUT_DIR / "schema.graphql"
JSON_PATH = OUTPUT_DIR / "schema.json"


def main() -> None:
    # Exporta SDL
    sdl = schema.as_str()
    SDL_PATH.write_text(sdl, encoding="utf-8")

    # Exporta JSON (introspección) usando GraphQL introspection
    from graphql import get_introspection_query, graphql_sync
    import json

    introspection_query = get_introspection_query()
    result = graphql_sync(schema._schema, introspection_query)
    json_schema = json.dumps(result.data, indent=2)
    JSON_PATH.write_text(json_schema, encoding="utf-8")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Exportado esquema GraphQL:")
    print(f" - SDL:   {SDL_PATH}")
    print(f" - JSON:  {JSON_PATH}")


if __name__ == "__main__":
    main()
