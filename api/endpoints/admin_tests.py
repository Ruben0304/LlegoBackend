"""
Admin test runner — panel de pruebas de experiencia de cliente.

GET  /admin/tests          — HTML dashboard
POST /admin/tests/run      — Ejecuta un suite y devuelve JSON con resultados
GET  /admin/tests/suites   — Lista los suites disponibles (JSON)

Protegido por ADMIN_API_KEY igual que el resto de /admin/*.
"""

import asyncio
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from utils.auth import decode_access_token

PROJECT_ROOT = str(Path(__file__).parent.parent.parent)

router = APIRouter(prefix="/admin", tags=["Admin - Tests"])

# ---------------------------------------------------------------------------
# Catálogo de suites
# Cada test tiene: node (pytest node ID), label (texto natural), impact
# ---------------------------------------------------------------------------

SUITES = [
    {
        "id": "qdrant_online",
        "title": "Búsqueda — Conectividad",
        "description": "Qdrant está en línea y tiene los datos de productos, negocios y sucursales.",
        "tests": [
            {
                "node": "tests/test_qdrant.py::TestConnectivity::test_ping",
                "label": "Qdrant responde al ping",
                "impact": "Sin esto, la búsqueda falla completamente para todos los clientes.",
            },
            {
                "node": "tests/test_qdrant.py::TestConnectivity::test_expected_collections_exist",
                "label": "Existen las colecciones de productos, negocios y sucursales",
                "impact": "Si falta alguna, esa categoría de búsqueda devuelve resultados vacíos.",
            },
            {
                "node": "tests/test_qdrant.py::TestConnectivity::test_collections_are_not_empty",
                "label": "Ninguna colección está vacía",
                "impact": "Si está vacía, el cliente ve la pantalla de búsqueda sin resultados.",
            },
        ],
    },
    {
        "id": "qdrant_write_read",
        "title": "Búsqueda — Escritura y lectura",
        "description": "Los nuevos productos se indexan y se pueden recuperar inmediatamente.",
        "tests": [
            {
                "node": "tests/test_qdrant.py::TestInsertReadDelete::test_insert_point",
                "label": "Se puede insertar un nuevo punto de búsqueda",
                "impact": "Si falla, los productos nuevos no aparecerán en ninguna búsqueda.",
            },
            {
                "node": "tests/test_qdrant.py::TestInsertReadDelete::test_read_point_back",
                "label": "El punto insertado es recuperable de inmediato",
                "impact": "Si falla, los productos recién creados no aparecen al instante.",
            },
            {
                "node": "tests/test_qdrant.py::TestInsertReadDelete::test_delete_point",
                "label": "Eliminar un punto lo quita de la búsqueda",
                "impact": "Si falla, productos eliminados siguen apareciendo en búsquedas.",
            },
        ],
    },
    {
        "id": "qdrant_performance",
        "title": "Búsqueda — Rendimiento",
        "description": "Las búsquedas responden dentro de los tiempos aceptables para el usuario.",
        "tests": [
            {
                "node": "tests/test_qdrant.py::TestSearchPerformance::test_search_normal_timing",
                "label": "Una búsqueda típica (20 resultados) responde en menos de 2 segundos",
                "impact": "Si tarda más, el cliente ve el feed lento o con timeout.",
            },
            {
                "node": "tests/test_qdrant.py::TestSearchPerformance::test_search_10_consecutive_requests",
                "label": "10 búsquedas seguidas cumplen el umbral de 2s cada una",
                "impact": "Detecta degradación acumulativa de latencia bajo carga real.",
            },
            {
                "node": "tests/test_qdrant.py::TestSearchPerformance::test_parallel_search_all_collections",
                "label": "Búsqueda simultánea en las 3 colecciones termina en menos de 5s",
                "impact": "Simula la carga real del feed, que consulta las 3 colecciones a la vez.",
            },
        ],
    },
    {
        "id": "qdrant_consistency",
        "title": "Búsqueda — Consistencia de datos",
        "description": "MongoDB y Qdrant están sincronizados: ningún producto faltante ni fantasma.",
        "tests": [
            {
                "node": "tests/test_qdrant.py::TestDataConsistency::test_products_count_matches_mongo",
                "label": "El conteo de productos en Qdrant coincide con MongoDB",
                "impact": "Un desajuste indica productos que existen en una BD pero no en la otra.",
            },
            {
                "node": "tests/test_qdrant.py::TestDataConsistency::test_all_qdrant_ids_exist_in_mongo",
                "label": "Todo ID en Qdrant apunta a un producto real en MongoDB",
                "impact": "Detecta productos fantasma en la búsqueda que ya no existen.",
            },
            {
                "node": "tests/test_qdrant.py::TestDataConsistency::test_all_mongo_ids_exist_in_qdrant",
                "label": "Cada producto de MongoDB tiene su vector en Qdrant",
                "impact": "Detecta productos que existen pero nunca aparecen en búsquedas.",
            },
        ],
    },
    {
        "id": "qdrant_product_creation",
        "title": "Búsqueda — Creación de producto",
        "description": "Flujo de punta a punta: un producto creado aparece en MongoDB y en la búsqueda.",
        "tests": [
            {
                "node": "tests/test_qdrant.py::TestProductCreation::test_create_product_appears_in_mongo_and_qdrant",
                "label": "Un producto nuevo aparece en MongoDB y en Qdrant al crearlo",
                "impact": "Si falla, los negocios pueden crear productos que nunca se muestran a los clientes.",
            },
        ],
    },
    {
        "id": "feed_scoring",
        "title": "Feed — Lógica de personalización",
        "description": "Las secciones del feed ordenan y filtran productos según las preferencias del usuario.",
        "tests": [
            {
                "node": "tests/test_feed_para_ti_scoring.py::test_para_ti_prioritizes_affinity_and_filters_by_radius",
                "label": "«Para Ti» prioriza productos afines y excluye los no disponibles",
                "impact": "Si falla, la sección principal del feed no personaliza ni filtra correctamente.",
            },
            {
                "node": "tests/test_feed_para_ti_scoring.py::test_te_podria_gustar_prioritizes_adjacent_affinity_without_repeating",
                "label": "«Te Podría Gustar» no repite productos ya vistos en otras secciones",
                "impact": "Si falla, el usuario ve los mismos productos en dos secciones distintas.",
            },
            {
                "node": "tests/test_feed_para_ti_scoring.py::test_deduplicate_sections_backfills_with_next_unique_candidate",
                "label": "La deduplicación entre secciones no deja huecos vacíos",
                "impact": "Si falla, las secciones aparecen con menos productos de los esperados.",
            },
            {
                "node": "tests/test_feed_para_ti_scoring.py::test_basado_busquedas_prioritizes_search_affinity_over_global_popularity",
                "label": "«Basado en tus búsquedas» prioriza el historial del usuario",
                "impact": "Si falla, la sección ignora las búsquedas del usuario y muestra lo más popular en general.",
            },
        ],
    },
    {
        "id": "feed_performance",
        "title": "Feed — Rendimiento del algoritmo",
        "description": "El algoritmo de feed calcula todas las secciones dentro de los tiempos permitidos.",
        "tests": [
            {
                "node": "tests/test_feed_performance.py::test_para_ti_performance[large]",
                "label": "«Para Ti» con 1 000 productos se calcula en menos de 300 ms",
                "impact": "Si tarda más, el feed completo supera los tiempos de respuesta aceptables.",
            },
            {
                "node": "tests/test_feed_performance.py::test_trending_performance[large]",
                "label": "«Tendencias» con 1 000 productos se calcula en menos de 300 ms",
                "impact": "Las secciones de tendencias lentas bloquean el resto del feed.",
            },
            {
                "node": "tests/test_feed_performance.py::test_full_parallel_feed_performance[large]",
                "label": "El feed completo (10 secciones, 1 000 productos) termina en menos de 500 ms",
                "impact": "Esta es la prueba más crítica: mide el tiempo real de carga de la pantalla principal.",
            },
            {
                "node": "tests/test_feed_performance.py::test_deduplicate_sections_performance[medium]",
                "label": "Deduplicar 10 secciones con 200 productos cada una tarda menos de 20 ms",
                "impact": "La deduplicación lenta se suma al tiempo total que espera el usuario.",
            },
        ],
    },
    {
        "id": "combo_pricing",
        "title": "Combos — Cálculo de precios",
        "description": "Los combos calculan correctamente el precio base, precio final y ahorro para el cliente.",
        "tests": [
            {
                "node": "tests/test_combo_pricing.py::test_starting_base_price_simple_combo",
                "label": "Precio base de combo simple (un producto por slot)",
                "impact": "Si falla, los combos muestran precios incorrectos a los clientes.",
            },
            {
                "node": "tests/test_combo_pricing.py::test_starting_base_price_with_price_adjustment",
                "label": "El ajuste de precio por opción se incluye en el precio base",
                "impact": "Los ajustes de precio en opciones del combo no se aplicarían.",
            },
            {
                "node": "tests/test_combo_pricing.py::test_starting_final_price_with_percentage_discount",
                "label": "El descuento porcentual se aplica correctamente",
                "impact": "El cliente vería el precio sin descuento o con un descuento incorrecto.",
            },
            {
                "node": "tests/test_combo_pricing.py::test_starting_final_price_with_fixed_discount",
                "label": "El descuento de monto fijo se aplica correctamente",
                "impact": "Los descuentos fijos no funcionarían en ningún combo.",
            },
            {
                "node": "tests/test_combo_pricing.py::test_starting_savings",
                "label": "El ahorro mostrado al cliente es el correcto",
                "impact": "Si falla, el badge «Ahorras X» muestra un número equivocado.",
            },
        ],
    },
    {
        "id": "push_notifications",
        "title": "Notificaciones push",
        "description": "Los payloads de notificación se serializan correctamente antes de enviarse.",
        "tests": [
            {
                "node": "tests/test_push_payload_serialization_regression.py::test_normalize_push_payload_converts_objectid_recursively",
                "label": "Los ObjectIds en los payloads se convierten a texto antes del envío",
                "impact": "Si falla, las notificaciones push fallan silenciosamente con error de serialización.",
            },
        ],
    },
]

# Categorías que agrupan suites relacionadas
CATEGORIES = [
    {
        "id": "qdrant",
        "title": "Qdrant",
        "suite_ids": [
            "qdrant_online",
            "qdrant_write_read",
            "qdrant_performance",
            "qdrant_consistency",
            "qdrant_product_creation",
        ],
    },
    {
        "id": "feed",
        "title": "Feed",
        "suite_ids": ["feed_scoring", "feed_performance"],
    },
    {
        "id": "combos",
        "title": "Combos",
        "suite_ids": ["combo_pricing"],
    },
    {
        "id": "push",
        "title": "Notificaciones push",
        "suite_ids": ["push_notifications"],
    },
]

# Índices para búsqueda rápida
_SUITE_BY_ID = {s["id"]: s for s in SUITES}
_NODE_META: dict[str, dict] = {
    t["node"]: t
    for s in SUITES
    for t in s["tests"]
}


# ---------------------------------------------------------------------------
# Auth dependency — requiere rol "admin" en el JWT
# ---------------------------------------------------------------------------

def _require_admin(authorization: Optional[str] = Header(None)) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="No autenticado.")
    try:
        scheme, token = authorization.split()
    except ValueError:
        raise HTTPException(status_code=401, detail="Header de autorización inválido.")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Se requiere esquema Bearer.")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol de administrador.")


# ---------------------------------------------------------------------------
# Lógica de ejecución
# ---------------------------------------------------------------------------

_RESULT_RE = re.compile(
    r"^(tests/\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED)",
    re.MULTILINE,
)
_SUMMARY_FAIL_RE = re.compile(
    r"^FAILED\s+(\S+)\s+-\s+(.+)$",
    re.MULTILINE,
)
_E_LINE_RE = re.compile(r"^\s*E\s{3}(.+)$", re.MULTILINE)
_FAILURE_BLOCK_RE = re.compile(
    r"_{10,}\s*\S+\s*_{10,}\n(.*?)(?=\n_{10,}|\n={10,})",
    re.DOTALL,
)


def _parse_output(stdout: str, node_ids: list[str]) -> list[dict]:
    """Extrae resultados de la salida de pytest -v --tb=short."""
    # Resultados por node_id (simplificado a la parte relevante)
    status_map: dict[str, str] = {}
    for match in _RESULT_RE.finditer(stdout):
        node, status = match.group(1).strip(), match.group(2)
        status_map[node] = status

    # Errores de una línea desde la sección de resumen
    error_map: dict[str, str] = {}
    for match in _SUMMARY_FAIL_RE.finditer(stdout):
        node, msg = match.group(1).strip(), match.group(2).strip()
        error_map[node] = msg

    # Para los errores que no tienen resumen en una línea, extraer líneas "E   ..."
    # del bloque de FAILURES usando los E-lines más relevantes
    for block_match in _FAILURE_BLOCK_RE.finditer(stdout):
        block = block_match.group(1)
        e_lines = _E_LINE_RE.findall(block)
        if not e_lines:
            continue
        # Asociar este bloque al node_id que falló y aún no tiene error_map
        # Buscamos a qué node corresponde comparando el texto del bloque
        for nid in node_ids:
            func_name = nid.split("::")[-1]
            if func_name in block and nid not in error_map:
                error_map[nid] = " · ".join(e_lines[-3:])  # últimas 3 líneas E

    results = []
    for nid in node_ids:
        status = status_map.get(nid, "not_run")
        error = error_map.get(nid) if status in ("FAILED", "ERROR") else None
        results.append(
            {
                "node": nid,
                "status": status.lower() if status != "not_run" else "not_run",
                "error": error,
            }
        )
    return results


async def _run_suite_tests(node_ids: list[str]) -> dict:
    """Ejecuta los tests indicados en un subprocess y retorna los resultados."""
    start = time.monotonic()

    def _sync():
        return subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "--tb=short", "-v", "--no-header",
                "-p", "no:cacheprovider",
                *node_ids,
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )

    proc = await asyncio.to_thread(_sync)
    elapsed = round((time.monotonic() - start) * 1000)

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    results = _parse_output(stdout, node_ids)

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] in ("failed", "error"))

    return {
        "results": results,
        "passed": passed,
        "failed": failed,
        "total": len(node_ids),
        "duration_ms": elapsed,
        "raw": stdout[-4000:] if stdout else "",  # últimas 4 KB para debug
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    suite_id: Optional[str] = None
    node_ids: Optional[list] = None  # lista de pytest node IDs individuales


@router.get("/tests/suites", dependencies=[Depends(_require_admin)])
async def list_suites():
    """Lista categorías y suites con sus tests (sin ejecutarlos)."""
    categories = []
    for cat in CATEGORIES:
        suites = [_SUITE_BY_ID[sid] for sid in cat["suite_ids"] if sid in _SUITE_BY_ID]
        categories.append({**cat, "suites": suites})
    return {"categories": categories, "suites": SUITES}


@router.post("/tests/run", dependencies=[Depends(_require_admin)])
async def run_tests(body: RunRequest):
    """Ejecuta un suite completo o una lista de tests individuales."""
    if body.suite_id:
        suite = _SUITE_BY_ID.get(body.suite_id)
        if not suite:
            raise HTTPException(status_code=404, detail=f"Suite '{body.suite_id}' no encontrado.")
        node_ids = [t["node"] for t in suite["tests"]]
    elif body.node_ids:
        node_ids = body.node_ids
    else:
        raise HTTPException(status_code=400, detail="Proporciona suite_id o node_ids.")

    result = await _run_suite_tests(node_ids)

    for r in result["results"]:
        meta = _NODE_META.get(r["node"], {})
        r["label"] = meta.get("label", r["node"].split("::")[-1])
        r["impact"] = meta.get("impact", "")

    return result


# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------

_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Llego — Panel de Pruebas</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0a0a;--surface:#111;--surface2:#1a1a1a;
  --border:#222;--border2:#2e2e2e;
  --text:#e2e2e2;--muted:#666;--muted2:#999;
  --green:#22c55e;--green-bg:#052e16;
  --red:#ef4444;--red-bg:#1c0a0a;
  --amber:#f59e0b;--blue:#3b82f6;
  --r:10px;--r-sm:6px;
}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  background:var(--bg);color:var(--text);
  padding:36px 20px 60px;max-width:820px;margin:0 auto;
  font-size:14px;line-height:1.55;
}
header{margin-bottom:28px}
header h1{font-size:20px;font-weight:600;letter-spacing:-.3px}
header p{color:var(--muted2);margin-top:5px;font-size:13px}

.topbar{display:flex;align-items:center;gap:10px;margin-bottom:24px}
.btn-primary{
  background:var(--blue);border:none;color:#fff;
  border-radius:var(--r-sm);padding:7px 16px;
  font-size:13px;font-weight:500;cursor:pointer;
  transition:opacity .15s;white-space:nowrap;
}
.btn-primary:hover{opacity:.85}
.btn-primary:disabled{opacity:.4;cursor:not-allowed}
#global-status{font-size:12px;color:var(--muted2)}

.section{
  border:1px solid var(--border);border-radius:var(--r);
  margin-bottom:12px;overflow:hidden;
}
.section-head{
  display:flex;align-items:center;gap:12px;
  padding:14px 18px;background:var(--surface);
  cursor:default;
}
.section-title{flex:1}
.section-title h2{font-size:14px;font-weight:600}
.section-title p{color:var(--muted2);font-size:12px;margin-top:3px}
.badge{
  font-size:11px;font-weight:600;padding:2px 9px;
  border-radius:100px;white-space:nowrap;
}
.badge-idle{background:var(--surface2);color:var(--muted)}
.badge-pass{background:var(--green-bg);color:var(--green)}
.badge-fail{background:var(--red-bg);color:var(--red)}
.btn-run{
  background:transparent;border:1px solid var(--border2);
  color:var(--muted2);border-radius:var(--r-sm);
  padding:5px 13px;font-size:12px;cursor:pointer;
  transition:all .15s;white-space:nowrap;
}
.btn-run:hover{border-color:var(--blue);color:var(--blue)}
.btn-run:disabled{opacity:.4;cursor:not-allowed}

.section-body{padding:0 18px}
.test-row{
  display:flex;align-items:flex-start;gap:12px;
  padding:11px 0;border-bottom:1px solid var(--border);
}
.test-row:last-child{border-bottom:none}
.dot{
  width:7px;height:7px;border-radius:50%;flex-shrink:0;
  margin-top:5px;background:var(--border2);transition:background .2s;
}
.dot.pass{background:var(--green)}
.dot.fail{background:var(--red)}
.dot.running{background:var(--amber);animation:pulse .7s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.test-info{flex:1;min-width:0}
.test-label{font-size:13px;font-weight:500}
.test-impact{font-size:11.5px;color:var(--muted);margin-top:2px}
.test-timing{font-size:11px;color:var(--muted);margin-top:2px}
.test-error{
  font-family:'JetBrains Mono','Fira Code','Cascadia Code',monospace;
  font-size:11px;color:var(--red);
  background:var(--red-bg);border:1px solid #3a1212;
  border-radius:5px;padding:8px 10px;margin-top:7px;
  white-space:pre-wrap;word-break:break-word;
  display:none;
}
.test-error.show{display:block}

.duration{font-size:11px;color:var(--muted);margin-top:2px}
</style>
</head>
<body>

<header>
  <h1>Panel de Pruebas — Llego Backend</h1>
  <p>Verifica los sistemas que afectan directamente la experiencia del cliente.</p>
</header>

<div class="topbar">
  <button class="btn-primary" id="btn-all" onclick="runAll()">Ejecutar todas</button>
  <span id="global-status"></span>
</div>

<div id="sections"></div>

<script>
// Lee el JWT del query param ?token=... o del localStorage bajo la clave 'access_token'
const token = new URLSearchParams(location.search).get('token')
           || localStorage.getItem('access_token')
           || '';
const headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token };

let suites = [];
let running = false;

async function fetchSuites() {
  const res = await fetch('/admin/tests/suites', { headers });
  if (res.status === 401 || res.status === 403) {
    document.getElementById('sections').innerHTML =
      '<p style="color:var(--red);padding:20px 0">Acceso denegado. Inicia sesión como administrador y agrega ?token=TU_JWT a la URL.</p>';
    return;
  }
  const data = await res.json();
  suites = data.suites;
  renderSuites();
}

function renderSuites() {
  const container = document.getElementById('sections');
  container.innerHTML = suites.map(s => `
    <div class="section" id="section-${s.id}">
      <div class="section-head">
        <div class="section-title">
          <h2>${s.title}</h2>
          <p>${s.description}</p>
        </div>
        <span class="badge badge-idle" id="badge-${s.id}">${s.tests.length} prueba${s.tests.length !== 1 ? 's' : ''}</span>
        <button class="btn-run" id="btn-${s.id}" onclick="runSuite('${s.id}')">Ejecutar</button>
      </div>
      <div class="section-body" id="body-${s.id}">
        ${s.tests.map(t => `
          <div class="test-row" id="row-${nodeKey(t.node)}">
            <div class="dot" id="dot-${nodeKey(t.node)}"></div>
            <div class="test-info">
              <div class="test-label">${t.label}</div>
              <div class="test-impact">${t.impact}</div>
              <div class="test-error" id="err-${nodeKey(t.node)}"></div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function nodeKey(node) {
  return node.replace(/[^a-zA-Z0-9]/g, '_');
}

function setDot(node, state) {
  const el = document.getElementById('dot-' + nodeKey(node));
  if (el) { el.className = 'dot ' + state; }
}

function showError(node, msg) {
  const el = document.getElementById('err-' + nodeKey(node));
  if (el && msg) { el.textContent = msg; el.classList.add('show'); }
  else if (el) { el.textContent = ''; el.classList.remove('show'); }
}

async function runSuite(id) {
  if (running) return;
  running = true;
  disableAll(true);

  const suite = suites.find(s => s.id === id);
  if (!suite) return;

  // Reset UI
  setBadge(id, 'idle', `${suite.tests.length} prueba${suite.tests.length !== 1 ? 's' : ''}`);
  suite.tests.forEach(t => { setDot(t.node, 'running'); showError(t.node, null); });

  try {
    const res = await fetch('/admin/tests/run', {
      method: 'POST',
      headers,
      body: JSON.stringify({ suite_id: id }),
    });
    const data = await res.json();

    data.results.forEach(r => {
      const state = r.status === 'passed' ? 'pass' : (r.status === 'not_run' ? '' : 'fail');
      setDot(r.node, state);
      if (r.status !== 'passed' && r.error) showError(r.node, r.error);
    });

    const allPass = data.failed === 0;
    const label = allPass
      ? `✓ ${data.passed}/${data.total} — ${(data.duration_ms/1000).toFixed(1)}s`
      : `✗ ${data.failed} fallida${data.failed !== 1 ? 's' : ''} · ${data.passed} OK`;
    setBadge(id, allPass ? 'pass' : 'fail', label);
  } catch (e) {
    setBadge(id, 'fail', 'Error de red');
  } finally {
    running = false;
    disableAll(false);
  }
}

async function runAll() {
  if (running) return;
  document.getElementById('global-status').textContent = 'Ejecutando…';
  for (const s of suites) {
    await runSuite(s.id);
  }
  document.getElementById('global-status').textContent = 'Completado.';
}

function setBadge(id, type, text) {
  const el = document.getElementById('badge-' + id);
  if (!el) return;
  el.className = 'badge badge-' + type;
  el.textContent = text;
}

function disableAll(disabled) {
  document.getElementById('btn-all').disabled = disabled;
  suites.forEach(s => {
    const btn = document.getElementById('btn-' + s.id);
    if (btn) btn.disabled = disabled;
  });
}

fetchSuites();
</script>
</body>
</html>
"""


@router.get("/tests", response_class=HTMLResponse)
async def tests_dashboard(request: Request):
    """
    Panel HTML de pruebas de experiencia de cliente.
    Acceso: /admin/tests?token=TU_JWT  (el usuario debe tener role=admin)
    """
    return HTMLResponse(content=_HTML)
