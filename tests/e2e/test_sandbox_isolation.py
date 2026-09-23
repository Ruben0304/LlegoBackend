"""El sandbox esta de verdad aislado de produccion.

Las peticiones sin clave de este archivo son de las que el backend rechaza sin
ejecutar nada (403 del middleware / 404 de rutas ocultas, que no se registran
en error_logs): no escriben en produccion.
"""

import httpx

from .client import SANDBOX_HEADER


def test_ping_reports_a_separate_database(client):
    info = client.rest("GET", "/e2e/ping")
    assert info["sandbox"] is True
    assert info["database"]


def test_wrong_key_is_rejected_instead_of_falling_back_to_production(base_url):
    with httpx.Client(base_url=base_url, timeout=30) as http:
        response = http.get("/e2e/ping", headers={SANDBOX_HEADER: "clave-incorrecta"})
    assert response.status_code == 403
    response_graphql = httpx.post(
        f"{base_url}/graphql",
        json={"query": "{ __typename }"},
        headers={SANDBOX_HEADER: "clave-incorrecta"},
        timeout=30,
    )
    assert response_graphql.status_code == 403


def test_sandbox_endpoints_do_not_exist_without_the_key(raw_http):
    assert raw_http.get("/e2e/ping").status_code == 404
    assert raw_http.post("/e2e/world").status_code == 404
    assert raw_http.delete("/e2e/sandbox").status_code == 404


def test_worlds_are_isolated_from_each_other(world, client):
    from .flows import World

    other = World.create(client)
    order = world.create_order()
    # El dueno de otro mundo no ve ni toca este pedido.
    assert "No autorizado" in str(other.get_order_error(order["id"], "owner"))
    assert order["id"] not in {o["id"] for o in other.my_orders()}
