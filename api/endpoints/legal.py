"""Legal pages (Privacy Policy, Terms of Service) served as static HTML.

These URLs are linked from the Llego mobile apps (cliente, business, chofer)
to satisfy Apple App Store Guideline 5.1.1 (Privacy) and 3.3.41 (EULA).
The pages live on the backend instead of a marketing site so that the URL
is always reachable as long as the API is up.
"""
from datetime import date
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Legal"])

_HERE = Path(__file__).parent
_PRIVACY_PATH = _HERE / "_legal_privacy.html"
_TERMS_PATH = _HERE / "_legal_terms.html"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy() -> HTMLResponse:
    """Política de Privacidad — visible para Apple App Store y usuarios finales."""
    return HTMLResponse(content=_load(_PRIVACY_PATH))


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service() -> HTMLResponse:
    """Términos y Condiciones — visible para Apple App Store y usuarios finales."""
    return HTMLResponse(content=_load(_TERMS_PATH))


@router.get("/legal", response_class=HTMLResponse, include_in_schema=False)
async def legal_index() -> HTMLResponse:
    """Índice simple con enlaces a las dos páginas legales."""
    today = date.today().isoformat()
    return HTMLResponse(
        content=f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>LLego — Documentos legales</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:-apple-system,system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 24px;color:#222}}</style>
</head><body>
<h1>LLego — Documentos legales</h1>
<ul><li><a href="/privacy">Política de Privacidad</a></li>
<li><a href="/terms">Términos y Condiciones</a></li></ul>
<p style="color:#666">Última actualización: {today}</p>
</body></html>"""
    )
