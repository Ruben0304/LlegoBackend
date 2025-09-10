"""
Exporta el esquema GraphQL definido en main.py a archivos locales:
- schema.graphql (SDL)
- schema.json (introspección JSON)

Uso:
  python export_schema.py
"""
from pathlib import Path
from datetime import datetime

# Importa el schema desde la app
from main import schema

OUTPUT_DIR = Path(__file__).parent
SDL_PATH = OUTPUT_DIR / "schema.graphql"
JSON_PATH = OUTPUT_DIR / "schema.json"

def main() -> None:
    # Exporta SDL
    sdl = schema.as_str()
    SDL_PATH.write_text(sdl, encoding="utf-8")

    # Exporta JSON (introspección)
    json_schema = schema.as_json(indent=2)
    JSON_PATH.write_text(json_schema, encoding="utf-8")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Exportado esquema GraphQL:")
    print(f" - SDL:   {SDL_PATH}")
    print(f" - JSON:  {JSON_PATH}")


if __name__ == "__main__":
    main()
