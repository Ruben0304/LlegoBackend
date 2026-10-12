#!/usr/bin/env python3
"""Ejecuta la suite de pytest y falla solo ante fallos NUEVOS.

Por qué existe: la suite arrastra fallos preexistentes (tests desactualizados, servicios
externos como Qdrant o la red, tests de rendimiento sensibles a la máquina). Exigir "0
fallos" dejaría el CI en rojo desde el primer día y nadie le haría caso; ignorar los fallos
dejaría pasar regresiones. Este runner compara los fallos de la ejecución con la lista
versionada `tests/known_failures.txt` y solo falla si aparece uno que no está en la lista.

Reglas:
  - Fallo nuevo = test (o módulo, si falla al importarse) que falla y no está en la lista.
    Antes de darlo por regresión se repite una vez de forma aislada: si pasa, se informa
    como "inestable" y no rompe el CI. (--reruns 0 lo desactiva.)
  - Fallo conocido = el nodeid figura en la lista (o encaja con un patrón con `*`).
  - Los fallos conocidos que ahora pasan se avisan para que se retiren de la lista
    (la lista solo debe encoger).
  - Si pytest termina de forma anormal (error interno, uso incorrecto, ningún test
    recogido, interrupción) el runner falla aunque no haya fallos nuevos.

Formato de tests/known_failures.txt: un nodeid de pytest por línea, `#` para comentarios.
Una línea con `*` se trata como patrón (p. ej. `tests/test_qdrant.py::*`); el resto, como
nodeid exacto. Se acepta el prefijo `FAILED `/`ERROR ` de la salida de pytest.

Uso (desde la raíz del repo; las variables de entorno de prueba las define el workflow):
  python scripts/ci/run_tests.py
  python scripts/ci/run_tests.py tests/test_security.py -x      # los argumentos van a pytest
  python scripts/ci/run_tests.py --known-failures otra_lista.txt --reruns 0
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARGS = [
    "tests/",
    "-q",
    "-p",
    "no:cacheprovider",
    "-rfE",
    "-o",
    "faulthandler_timeout=300",
    # Un módulo que no importa no debe ocultar el resto de la suite.
    "--continue-on-collection-errors",
]
ABNORMAL = {
    2: "ejecución interrumpida",
    3: "error interno de pytest",
    4: "uso incorrecto de pytest",
    5: "no se recogió ningún test",
}


class KnownFailures:
    def __init__(self, path: Path):
        self.exact: set[str] = set()
        self.patterns: list[re.Pattern[str]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("  #", 1)[0].strip()
            if not line or line.startswith("#"):
                continue
            summary = re.match(r"(?:FAILED|ERROR)\s+(\S.*)", line)
            if summary:  # línea copiada del resumen de pytest: "FAILED nodeid - mensaje"
                line = summary.group(1).split(" - ", 1)[0].strip()
            if "*" in line:
                # `[` en un nodeid parametrizado no es una clase de caracteres de fnmatch.
                self.patterns.append(re.compile(fnmatch.translate(line.replace("[", "[[]"))))
            else:
                self.exact.add(line)

    def __contains__(self, nodeid: str) -> bool:
        return nodeid in self.exact or any(p.match(nodeid) for p in self.patterns)


class Collector:
    """Plugin de pytest: recoge los nodeid que fallan y los que pasan."""

    def __init__(self) -> None:
        self.failed: dict[str, str] = {}
        self.passed: set[str] = set()

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.failed[report.nodeid] = "colección"

    def pytest_runtest_logreport(self, report) -> None:
        if report.failed:
            self.failed.setdefault(report.nodeid, report.when)
        elif report.when == "call" and report.passed:
            self.passed.add(report.nodeid)


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--known-failures", type=Path, default=ROOT / "tests" / "known_failures.txt"
    )
    parser.add_argument("--reruns", type=int, default=1,
                        help="repeticiones aisladas de los fallos nuevos antes de darlos por regresión")
    args, pytest_args = parser.parse_known_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    os.chdir(ROOT)
    # Equivale al `python -m pytest` con el que se ejecuta la suite: los tests importan
    # `main`, `services`, ... desde la raíz del repo.
    sys.path.insert(0, str(ROOT))
    known = KnownFailures(args.known_failures)
    known_label = _display(args.known_failures)

    collector = Collector()
    # --rootdir fija la base de los nodeid (tests/...), que es la que usa la lista de conocidos.
    code = int(pytest.main(["--rootdir", str(ROOT), *(pytest_args or DEFAULT_ARGS)],
                           plugins=[collector]))

    new = sorted(n for n in collector.failed if n not in known)
    unstable: list[str] = []
    for _ in range(max(args.reruns, 0)):
        if not new:
            break
        print(f"\nRepitiendo de forma aislada {len(new)} fallo(s) nuevo(s) ...", flush=True)
        retry = Collector()
        pytest.main(
            [*new, "--rootdir", str(ROOT), "-q", "-p", "no:cacheprovider",
             "-o", "faulthandler_timeout=300"],
            plugins=[retry],
        )
        # Solo cuenta como recuperado el test que pasó de verdad al repetirlo.
        recovered = [n for n in new if n in retry.passed]
        unstable += recovered
        new = [n for n in new if n not in recovered]

    fixed = sorted(n for n in known.exact if n in collector.passed)
    known_failed = sorted(n for n in collector.failed if n in known)

    print("\n" + "=" * 78)
    print(f"Fallos: {len(collector.failed)} en total | conocidos: {len(known_failed)} "
          f"| nuevos: {len(new)} | inestables (pasan al repetir): {len(unstable)}")
    if unstable:
        print("\nInestables (fallaron una vez y pasaron al repetir; revísalos si se repiten):")
        for nodeid in unstable:
            print(f"  ~ {nodeid}")
            if github:
                print(f"::warning title=Test inestable::{_escape(nodeid)}")
    if fixed:
        print(f"\nAhora PASAN {len(fixed)} test(s) de la lista de fallos conocidos; "
              f"quítalos de {known_label}:")
        for nodeid in fixed:
            print(f"  + {nodeid}")
            if github:
                print(f"::notice title=known_failures.txt desactualizado::{_escape(nodeid)} ya pasa")
    if new:
        print(f"\nFALLOS NUEVOS ({len(new)}): no están en {known_label}")
        for nodeid in new:
            print(f"  ✗ {nodeid}  [{collector.failed.get(nodeid, '?')}]")
            if github:
                print(f"::error title=Fallo nuevo en pytest::{_escape(nodeid)}")
        print("\nCorrige la regresión. Solo si el fallo es ajeno al cambio y ya existía, "
              "añade el nodeid a la lista con un comentario que explique por qué falla.")
        return 1

    if code in ABNORMAL:
        print(f"\nERROR: pytest terminó de forma anormal (código {code}: {ABNORMAL[code]}).")
        return code
    print("\nOK: ningún fallo nuevo respecto a la lista de fallos conocidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
