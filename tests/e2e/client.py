"""Cliente HTTP de la suite E2E.

Todas las peticiones llevan `X-E2E-Key` y se verifica que CADA respuesta traiga
`X-E2E-Sandbox: 1`. Si alguna no lo trae, el test aborta: nunca se sigue
ejecutando un flujo que pudiera estar escribiendo en produccion.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

SANDBOX_HEADER = "X-E2E-Key"
SANDBOX_RESPONSE_HEADER = "X-E2E-Sandbox"


class SandboxViolation(AssertionError):
    """La respuesta no vino del sandbox: se aborta para no tocar produccion."""


class GraphQLFailure(AssertionError):
    def __init__(self, messages: List[str], codes: List[Optional[str]]):
        super().__init__("; ".join(messages))
        self.messages = messages
        self.codes = codes


class E2EClient:
    def __init__(self, base_url: str, key: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={SANDBOX_HEADER: key},
            timeout=timeout,
        )

    @classmethod
    def from_env(cls) -> "E2EClient":
        return cls(
            base_url=os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000"),
            key=os.environ["E2E_KEY"],
        )

    def clone(self) -> "E2EClient":
        """Cliente independiente (para disparar peticiones en paralelo)."""
        return E2EClient(self.base_url, self.key)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ core

    def _check_sandbox(self, response: httpx.Response) -> None:
        if response.headers.get(SANDBOX_RESPONSE_HEADER) != "1":
            raise SandboxViolation(
                f"{response.request.method} {response.request.url} respondio "
                f"{response.status_code} SIN el header {SANDBOX_RESPONSE_HEADER}. "
                "Se aborta para no operar contra produccion."
            )

    def rest(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        response = self._http.request(method, path, **kwargs)
        self._check_sandbox(response)
        if response.status_code >= 400:
            raise AssertionError(
                f"{method} {path} -> {response.status_code}: {response.text}"
            )
        return response.json()

    def graphql_raw(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        response = self._http.post(
            "/graphql", json={"query": query, "variables": variables or {}}
        )
        self._check_sandbox(response)
        if response.status_code >= 500:
            raise AssertionError(f"/graphql -> {response.status_code}: {response.text}")
        return response.json()

    def gql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ejecuta y devuelve `data`. Lanza GraphQLFailure si hubo errores."""
        body = self.graphql_raw(query, variables)
        errors = body.get("errors") or []
        if errors:
            raise GraphQLFailure(
                [e.get("message", "") for e in errors],
                [(e.get("extensions") or {}).get("code") for e in errors],
            )
        return body["data"]

    def gql_error(self, query: str, variables: Optional[Dict[str, Any]] = None) -> GraphQLFailure:
        """Ejecuta esperando que FALLE; devuelve el error para inspeccionarlo."""
        try:
            data = self.gql(query, variables)
        except GraphQLFailure as failure:
            return failure
        raise AssertionError(f"Se esperaba un error y la operacion tuvo exito: {data}")
