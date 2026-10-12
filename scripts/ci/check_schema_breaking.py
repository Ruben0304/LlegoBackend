#!/usr/bin/env python3
"""Compara el schema GraphQL del código con el que sirve PRODUCCIÓN y detecta cambios
incompatibles con los clientes ya publicados.

Por qué existe: las apps (iOS, Android, Business, Mensajeros, web, panel admin) escriben
sus operaciones a mano y no se actualizan al mismo tiempo que el backend. Quitar o
renombrar un campo, endurecer un argumento o cambiar un tipo rompe en tiempo de ejecución
a los usuarios que aún no han actualizado, y ningún test del backend lo ve. Aquí se
compara, con `graphql.find_breaking_changes`, el schema exportado del código (el que se
desplegaría) contra el de producción (el que usan hoy los clientes).

Cómo se permite un cambio incompatible a propósito (p. ej. retirar un campo que ya nadie
usa o tras forzar la actualización de las apps):
  - etiqueta `breaking-schema-ok` en la pull request, o
  - variable de repositorio `ALLOW_BREAKING_SCHEMA=true` (afecta a todas las PR; úsala
    solo mientras dure la migración y quítala después),
  - en local: `ALLOW_BREAKING_SCHEMA=true` o `--allow-breaking`.
El workflow traduce lo anterior a la variable de entorno ALLOW_BREAKING_SCHEMA. Con el
permiso, los cambios incompatibles se informan como aviso pero no fallan el CI.

Códigos de salida:
  0  sin cambios incompatibles (o permitidos conscientemente)
  1  hay cambios incompatibles y no están permitidos
  2  error de infraestructura (no se pudo exportar el schema o descargar el de producción)

Uso local (desde la raíz del repo, con las variables de entorno mínimas de los tests):
  MONGODB_URL=mongodb://localhost:27017 GEMINI_API_KEY=test AWS_ACCESS_KEY_ID=test \\
  AWS_DEFAULT_REGION=us-east-1 AWS_ENDPOINT_URL=http://localhost \\
  AWS_SECRET_ACCESS_KEY=test S3_BUCKET_NAME=test \\
  python scripts/ci/check_schema_breaking.py
  python scripts/ci/check_schema_breaking.py --prod-schema-file otro.graphql   # sin red
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from graphql import (
    GraphQLSchema,
    build_client_schema,
    build_schema,
    find_breaking_changes,
    find_dangerous_changes,
    get_introspection_query,
)

DEFAULT_URL = "https://llegobackend-production.up.railway.app/graphql"
ROOT = Path(__file__).resolve().parents[2]
TRUTHY = {"1", "true", "yes", "si", "sí"}


def fetch_production_schema(url: str, timeout: float, retries: int) -> GraphQLSchema:
    """Descarga el schema de producción por introspección, con reintentos."""
    body = json.dumps({"query": get_introspection_query(descriptions=False)}).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "llego-schema-compat-check/1.0",
    }
    last_error = "sin detalle"
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            if payload.get("errors") or not payload.get("data"):
                raise RuntimeError(
                    "respuesta sin schema (¿introspección desactivada?): "
                    f"{json.dumps(payload.get('errors'))[:300]}"
                )
            return build_client_schema(payload["data"])
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"  intento {attempt}/{retries} fallido: {last_error}", file=sys.stderr)
            if attempt < retries:
                time.sleep(5 * attempt)
    raise RuntimeError(f"no se pudo descargar el schema de {url}: {last_error}")


def load_schema_file(path: Path) -> GraphQLSchema:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        return build_client_schema(data.get("data", data))
    return build_schema(text)


def export_code_schema() -> str:
    """SDL del schema definido en el código (el mismo que expone /graphql al desplegar)."""
    sys.path.insert(0, str(ROOT))
    from main import schema  # noqa: E402  (importa la app: requiere las variables de entorno)

    return schema.as_str()


def _escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--prod-url",
        default=os.environ.get("LLEGO_GRAPHQL_URL") or DEFAULT_URL,
        help=f"endpoint GraphQL de producción (env LLEGO_GRAPHQL_URL; por defecto {DEFAULT_URL})",
    )
    parser.add_argument(
        "--prod-schema-file",
        type=Path,
        help="usar un schema local (.graphql o introspección .json) en lugar de descargar el de producción",
    )
    parser.add_argument(
        "--code-schema-file",
        type=Path,
        help="usar este SDL como schema del código en lugar de importar main.py (para pruebas)",
    )
    parser.add_argument(
        "--write-sdl", type=Path, help="guardar aquí el SDL exportado del código (opcional)"
    )
    parser.add_argument(
        "--allow-breaking",
        action="store_true",
        default=os.environ.get("ALLOW_BREAKING_SCHEMA", "").strip().lower() in TRUTHY,
        help="no fallar ante cambios incompatibles (equivale a ALLOW_BREAKING_SCHEMA=true)",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    github = os.environ.get("GITHUB_ACTIONS") == "true"

    try:
        if args.code_schema_file:
            sdl = args.code_schema_file.read_text(encoding="utf-8")
        else:
            print("Exportando el schema del código ...")
            sdl = export_code_schema()
        if args.write_sdl:
            args.write_sdl.write_text(sdl, encoding="utf-8")
        code_schema = build_schema(sdl)

        if args.prod_schema_file:
            prod_schema = load_schema_file(args.prod_schema_file)
            prod_label = str(args.prod_schema_file)
        else:
            print(f"Descargando el schema de producción de {args.prod_url} ...")
            prod_schema = fetch_production_schema(args.prod_url, args.timeout, args.retries)
            prod_label = args.prod_url
    except Exception as exc:  # noqa: BLE001 - cualquier fallo aquí es de infraestructura
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    # old = producción (lo que usan los clientes), new = el código que se quiere desplegar.
    breaking = find_breaking_changes(prod_schema, code_schema)
    dangerous = find_dangerous_changes(prod_schema, code_schema)

    print(f"\nComparando el schema del código con producción ({prod_label})")
    print(f"  tipos en producción: {len(prod_schema.type_map)}, en el código: {len(code_schema.type_map)}")

    if dangerous:
        print(f"\nCambios a revisar ({len(dangerous)}), no rompen pero cambian el comportamiento:")
        for change in dangerous:
            print(f"  ! [{change.type.name}] {change.description}")
            if github:
                print(f"::warning title=Schema GraphQL::{_escape(f'[{change.type.name}] {change.description}')}")

    if not breaking:
        print("\nOK: ningún cambio incompatible con los clientes que usan producción.")
        return 0

    print(f"\nCambios INCOMPATIBLES con los clientes actuales ({len(breaking)}):")
    for change in breaking:
        print(f"  ✗ [{change.type.name}] {change.description}")
        if github:
            level = "warning" if args.allow_breaking else "error"
            print(f"::{level} title=Schema GraphQL incompatible::{_escape(f'[{change.type.name}] {change.description}')}")

    if args.allow_breaking:
        print(
            "\nPERMITIDO: ALLOW_BREAKING_SCHEMA activo (etiqueta `breaking-schema-ok` o variable "
            "del repositorio). Asegúrate de que los clientes afectados ya no usan esos campos o "
            "de que la actualización de las apps es obligatoria."
        )
        return 0

    print(
        "\nLas apps publicadas siguen usando el schema de producción y fallarían al ejecutar "
        "estas operaciones. Opciones:\n"
        "  1. Mantén el campo/tipo antiguo (puedes marcarlo con `deprecation_reason` en Strawberry) "
        "y retíralo cuando las apps ya no lo usen.\n"
        "  2. Si el cambio es consciente, añade la etiqueta `breaking-schema-ok` a la PR "
        "(o define ALLOW_BREAKING_SCHEMA=true) y coordina el despliegue con la actualización forzada."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
