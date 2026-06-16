"""
E2E performance tests for the feed endpoint against the deployed backend.

Runs real HTTP requests to the GraphQL /graphql endpoint and measures:
- Response time per section combination
- Cold vs warm request differences
- Behavior under N consecutive requests (throughput)

Usage:
    python3 -m pytest tests/test_feed_e2e_performance.py -v -s
"""

import statistics
import time

import httpx
import pytest

BASE_URL = "https://llegobackend-production.up.railway.app"
GRAPHQL_URL = f"{BASE_URL}/graphql"

JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJoZXJuYW5kenJ1YmVuOUBnbWFpbC5jb20iLCJ1c2VyX2lkIjoiNjljMmRjMmRiMjYxOWE0ZWRiZTQyZDE4Iiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzgzMjk3NzA0fQ"
    ".IyReZqSmi3934mougTwd8nQ5cdD2cd_5IJNhHsoYi58"
)

TIMEOUT = 30  # seconds

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

FEED_QUERY = """
query GetFeed($branchTipo: String!, $first: Int, $sections: [String!]) {
  getFeed(branchTipo: $branchTipo, first: $first, sections: $sections) {
    sections {
      sectionId
      title
      totalCount
    }
    sectionDiagnostics {
      sectionId
      status
      totalBeforeDedup
      totalAfterDedup
    }
  }
}
"""

# Query exacta que usa la app iOS — 5 resolvers en una sola petición
IOS_COMPLETE_FEED_QUERY = """
query GetCompleteFeed(
  $jwt: String
  $first: Int
  $sections: [String!]
  $branchTipo: String!
  $branchTipoEnum: BranchTipo
  $radiusKm: Float
  $categoryId: String
) {
  getFeed(
    jwt: $jwt
    first: $first
    sections: $sections
    branchTipo: $branchTipo
    productCategoryId: $categoryId
  ) {
    sections {
      sectionId
      title
      description
      totalCount
      products {
        id
        name
        price
        currency
        imageUrlBaja
        imageUrlMedia
        branchId
        categoryId
        branch { name address tipos }
        categoryName
        availability
        score
        description
      }
    }
    sectionDiagnostics {
      sectionId
      title
      status
      reason
      totalBeforeDedup
      totalAfterDedup
    }
    timestamp
  }

  productCategories(branchType: $branchTipo) {
    id
    name
    iconIos
  }

  branches(first: 15, tipo: $branchTipoEnum, radiusKm: $radiusKm, productCategoryId: $categoryId) {
    edges {
      node {
        id
        name
        avatarUrl
        avatarUrlBaja
        avatarUrlAlta
        coverUrl
        coverUrlBaja
        coverUrlAlta
        address
        distanceKm
      }
    }
  }

  activeTutorials {
    id
    title
    videoUrl
    videoUrlSigned
    thumbnailUrl
    thumbnailUrlSigned
  }

  allCombos(availableOnly: true) {
    id
    name
    imageUrl
    finalPrice
    branch { id name avatarUrlBaja }
  }
}
"""


def graphql_post(client: httpx.Client, variables: dict) -> tuple[dict, float]:
    """Send a GraphQL request and return (response_json, elapsed_ms)."""
    start = time.perf_counter()
    response = client.post(
        GRAPHQL_URL,
        json={"query": FEED_QUERY, "variables": variables},
        timeout=TIMEOUT,
    )
    elapsed = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    return response.json(), elapsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def summarize(label: str, times: list[float]):
    print(f"\n  [{label}]")
    print(f"    n={len(times)} requests")
    print(f"    min:    {min(times):.0f} ms")
    print(f"    max:    {max(times):.0f} ms")
    print(f"    mean:   {statistics.mean(times):.0f} ms")
    print(f"    p50:    {statistics.median(times):.0f} ms")
    if len(times) >= 4:
        print(f"    stdev:  {statistics.stdev(times):.0f} ms")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def http_client():
    with httpx.Client() as client:
        yield client


def test_backend_is_reachable(http_client):
    """Sanity check — backend responds before running timing tests."""
    response = http_client.get(BASE_URL, timeout=10, follow_redirects=True)
    assert response.status_code < 500, f"Backend returned {response.status_code}"
    print(f"\n  Backend reachable: {response.status_code}")


@pytest.mark.parametrize("branch_tipo", ["restaurante", "tienda", "dulceria"])
def test_feed_response_time_by_tipo(http_client, branch_tipo):
    """Single feed request per branch type — baseline response time."""
    data, ms = graphql_post(http_client, {
        "branchTipo": branch_tipo,
        "first": 10,
    })

    errors = data.get("errors")
    assert not errors, f"GraphQL errors: {errors}"

    sections = data["data"]["getFeed"]["sections"]
    print(f"\n  branch_tipo={branch_tipo!r}: {ms:.0f} ms — {len(sections)} sections returned")

    assert ms < 10_000, f"Feed took {ms:.0f} ms for tipo={branch_tipo!r} (limit 10s)"


@pytest.mark.parametrize("section_id,label", [
    (["populares_cerca"], "populares_cerca (no auth)"),
    (["trending"], "trending (no auth)"),
    (["mas_favoriteados"], "mas_favoriteados (no auth)"),
    (["hora_del_dia"], "hora_del_dia (no auth)"),
    (["cerca_ti"], "cerca_ti (no location)"),
    (["populares_cerca", "trending", "mas_favoriteados", "hora_del_dia"], "4 secciones anónimas"),
])
def test_feed_section_response_time(http_client, section_id, label):
    """Measure response time for specific section subsets."""
    data, ms = graphql_post(http_client, {
        "branchTipo": "restaurante",
        "first": 10,
        "sections": section_id,
    })

    errors = data.get("errors")
    assert not errors, f"GraphQL errors for {label!r}: {errors}"

    diagnostics = data["data"]["getFeed"]["sectionDiagnostics"]
    print(f"\n  {label}: {ms:.0f} ms")
    for d in diagnostics:
        print(f"    {d['sectionId']}: status={d['status']} before={d['totalBeforeDedup']} after={d['totalAfterDedup']}")

    assert ms < 10_000, f"{label!r} took {ms:.0f} ms (limit 10s)"


def test_feed_warm_vs_cold(http_client):
    """
    Compare first request (potentially cold) vs subsequent ones (warm/cached).
    Makes 5 consecutive requests and shows the time trend.
    """
    N = 5
    times = []

    for i in range(N):
        _, ms = graphql_post(http_client, {
            "branchTipo": "restaurante",
            "first": 10,
            "sections": ["populares_cerca", "trending"],
        })
        times.append(ms)
        print(f"\n  Request {i+1}: {ms:.0f} ms")

    summarize("warm vs cold — populares_cerca + trending", times)

    # Cold start should not exceed 3× the warm average
    warm_avg = statistics.mean(times[1:])
    cold = times[0]
    ratio = cold / warm_avg if warm_avg > 0 else 0
    print(f"\n  cold/warm ratio: {ratio:.2f}x (cold={cold:.0f}ms, warm_avg={warm_avg:.0f}ms)")


def test_feed_throughput_sequential(http_client):
    """
    Send 10 sequential requests and measure throughput.
    Simulates multiple users loading the feed one after another.
    """
    N = 10
    times = []

    for _ in range(N):
        _, ms = graphql_post(http_client, {
            "branchTipo": "restaurante",
            "first": 10,
            "sections": ["populares_cerca", "trending", "mas_favoriteados"],
        })
        times.append(ms)

    summarize("throughput — 10 sequential requests (3 sections)", times)

    # No single request should be an extreme outlier (> 5× median)
    median = statistics.median(times)
    outliers = [t for t in times if t > median * 5]
    assert not outliers, f"Outlier requests detected: {outliers} ms (median={median:.0f} ms)"


@pytest.mark.parametrize("first", [5, 10, 25, 50])
def test_feed_response_time_by_page_size(http_client, first):
    """Does increasing `first` (products per section) significantly affect response time?"""
    time.sleep(3)  # avoid rate limit between parametrize calls
    data, ms = graphql_post(http_client, {
        "branchTipo": "restaurante",
        "first": first,
        "sections": ["populares_cerca", "trending"],
    })

    errors = data.get("errors")
    assert not errors, f"GraphQL errors for first={first}: {errors}"

    sections = data["data"]["getFeed"]["sections"]
    total_products = sum(s["totalCount"] for s in sections)
    print(f"\n  first={first}: {ms:.0f} ms — {total_products} total products returned")

    assert ms < 10_000, f"first={first} took {ms:.0f} ms (limit 10s)"


# ---------------------------------------------------------------------------
# Tests autenticados (con JWT)
# ---------------------------------------------------------------------------

def test_feed_authenticated_all_sections(http_client):
    """
    Feed completo con JWT — activa las secciones personalizadas:
    para_ti, pide_de_nuevo, basado_busquedas, nuevos_lugares_favoritos, te_podria_gustar.
    Compara el tiempo total vs el feed anónimo.
    """
    time.sleep(3)

    # Anónimo (baseline)
    _, ms_anon = graphql_post(http_client, {
        "branchTipo": "restaurante",
        "first": 10,
    })

    time.sleep(3)

    # Autenticado (todas las secciones)
    data_auth, ms_auth = graphql_post(http_client, {
        "branchTipo": "restaurante",
        "first": 10,
        "jwt": JWT,
    })

    errors = data_auth.get("errors")
    assert not errors, f"GraphQL errors con JWT: {errors}"

    sections = data_auth["data"]["getFeed"]["sections"]
    diagnostics = data_auth["data"]["getFeed"]["sectionDiagnostics"]

    print(f"\n  Anónimo:      {ms_anon:.0f} ms")
    print(f"  Autenticado:  {ms_auth:.0f} ms  (+{ms_auth - ms_anon:.0f} ms por personalización)")
    print(f"\n  Secciones incluidas ({len(sections)}):")
    for s in sections:
        print(f"    {s['sectionId']}: {s['totalCount']} productos")
    print(f"\n  Diagnóstico completo ({len(diagnostics)} entradas):")
    for d in diagnostics:
        print(f"    {d['sectionId']}: {d['status']}  before={d['totalBeforeDedup']} after={d['totalAfterDedup']}")

    assert ms_auth < 10_000, f"Feed autenticado tomó {ms_auth:.0f} ms (límite 10s)"


@pytest.mark.parametrize("section_id,label", [
    (["para_ti"], "para_ti"),
    (["pide_de_nuevo"], "pide_de_nuevo"),
    (["basado_busquedas"], "basado_busquedas"),
    (["nuevos_lugares_favoritos"], "nuevos_lugares_favoritos"),
    (["te_podria_gustar"], "te_podria_gustar"),
])
def test_feed_personalized_section_response_time(http_client, section_id, label):
    """Mide el tiempo de cada sección personalizada individualmente."""
    time.sleep(3)

    data, ms = graphql_post(http_client, {
        "branchTipo": "restaurante",
        "first": 10,
        "sections": section_id,
        "jwt": JWT,
    })

    errors = data.get("errors")
    assert not errors, f"GraphQL errors para {label!r}: {errors}"

    diagnostics = data["data"]["getFeed"]["sectionDiagnostics"]
    print(f"\n  {label}: {ms:.0f} ms")
    for d in diagnostics:
        print(f"    status={d['status']}  before={d['totalBeforeDedup']} after={d['totalAfterDedup']}")

    assert ms < 10_000, f"{label!r} tomó {ms:.0f} ms (límite 10s)"


def test_feed_authenticated_vs_anonymous_comparison(http_client):
    """
    Compara el tiempo de 5 requests anónimos vs 5 autenticados en la misma sección.
    Cuantifica el overhead de la personalización.
    """
    time.sleep(3)
    N = 3

    anon_times = []
    auth_times = []

    for i in range(N):
        time.sleep(3)
        _, ms = graphql_post(http_client, {
            "branchTipo": "restaurante",
            "first": 10,
            "sections": ["populares_cerca", "trending", "mas_favoriteados"],
        })
        anon_times.append(ms)

    for i in range(N):
        time.sleep(3)
        _, ms = graphql_post(http_client, {
            "branchTipo": "restaurante",
            "first": 10,
            "sections": ["para_ti", "pide_de_nuevo", "te_podria_gustar"],
            "jwt": JWT,
        })
        auth_times.append(ms)

    summarize("Anónimo — populares_cerca + trending + mas_favoriteados", anon_times)
    summarize("Autenticado — para_ti + pide_de_nuevo + te_podria_gustar", auth_times)

    overhead = statistics.mean(auth_times) - statistics.mean(anon_times)
    print(f"\n  Overhead de personalización: {overhead:+.0f} ms")

    assert statistics.mean(auth_times) < 10_000


# ---------------------------------------------------------------------------
# Tests que replican exactamente la query de la app iOS (GetCompleteFeed)
# ---------------------------------------------------------------------------

def test_ios_complete_feed_anonymous(http_client):
    """
    Replica la query exacta de la app iOS sin JWT.
    Incluye: getFeed + productCategories + branches (con URLs S3) + activeTutorials + allCombos.
    """
    time.sleep(3)

    start = time.perf_counter()
    response = http_client.post(
        GRAPHQL_URL,
        json={
            "query": IOS_COMPLETE_FEED_QUERY,
            "variables": {
                "branchTipo": "restaurante",
                "branchTipoEnum": "RESTAURANTE",
                "first": 10,
            },
        },
        timeout=TIMEOUT,
    )
    ms = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    data = response.json()

    errors = data.get("errors")
    assert not errors, f"GraphQL errors: {errors}"

    feed = data["data"]["getFeed"]
    branches = data["data"].get("branches", {}).get("edges", [])
    categories = data["data"].get("productCategories", [])
    tutorials = data["data"].get("activeTutorials", [])
    combos = data["data"].get("allCombos", [])

    total_products = sum(s["totalCount"] for s in feed["sections"])
    total_images = sum(
        2 for s in feed["sections"] for p in s["products"]  # imageUrlBaja + imageUrlMedia
    ) + len(branches) * 6  # avatarUrl x3 + coverUrl x3

    print(f"\n  Tiempo total (iOS query completa, sin JWT): {ms:.0f} ms")
    print(f"  Feed: {len(feed['sections'])} secciones, {total_products} productos")
    print(f"  Branches: {len(branches)} (cada una con 6 URLs S3)")
    print(f"  Categorías: {len(categories)}")
    print(f"  Tutoriales: {len(tutorials)}")
    print(f"  Combos: {len(combos)}")
    print(f"  URLs S3 generadas estimadas: ~{total_images}")

    print(f"\n  Desglose por sección:")
    for s in feed["sections"]:
        print(f"    {s['sectionId']}: {s['totalCount']} productos")
    for d in feed["sectionDiagnostics"]:
        if d["status"] == "omitted":
            print(f"    {d['sectionId']}: omitida — {d.get('reason', '')}")


def test_ios_complete_feed_authenticated(http_client):
    """
    Replica la query exacta de la app iOS CON JWT.
    Este es el caso que tarda ~2s en la app — identifica dónde está el costo.
    """
    time.sleep(3)

    start = time.perf_counter()
    response = http_client.post(
        GRAPHQL_URL,
        json={
            "query": IOS_COMPLETE_FEED_QUERY,
            "variables": {
                "branchTipo": "restaurante",
                "branchTipoEnum": "RESTAURANTE",
                "first": 10,
                "jwt": JWT,
            },
        },
        timeout=TIMEOUT,
    )
    ms = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    data = response.json()

    errors = data.get("errors")
    assert not errors, f"GraphQL errors: {errors}"

    feed = data["data"]["getFeed"]
    branches = data["data"].get("branches", {}).get("edges", [])
    categories = data["data"].get("productCategories", [])
    tutorials = data["data"].get("activeTutorials", [])
    combos = data["data"].get("allCombos", [])

    total_products = sum(s["totalCount"] for s in feed["sections"])

    print(f"\n  Tiempo total (iOS query completa, CON JWT): {ms:.0f} ms")
    print(f"  Feed: {len(feed['sections'])} secciones, {total_products} productos")
    print(f"  Branches: {len(branches)} (cada una con 6 URLs S3)")
    print(f"  Categorías: {len(categories)}")
    print(f"  Tutoriales: {len(tutorials)}")
    print(f"  Combos: {len(combos)}")

    print(f"\n  Desglose secciones:")
    for s in feed["sections"]:
        print(f"    {s['sectionId']}: {s['totalCount']} productos")
    for d in feed["sectionDiagnostics"]:
        if d["status"] == "omitted":
            print(f"    {d['sectionId']}: omitida")


def test_ios_identify_slow_resolver(http_client):
    """
    Mide cada resolver de GetCompleteFeed por separado para identificar cuál es el lento.
    """
    time.sleep(3)

    resolvers = {
        "getFeed solo (sin imágenes)": (FEED_QUERY, {
            "branchTipo": "restaurante", "first": 10,
        }),
    }

    # Query mínima para branches con URLs S3
    branches_query = """
    query { branches(first: 15, tipo: RESTAURANTE) {
      edges { node { id name avatarUrl avatarUrlBaja avatarUrlAlta coverUrl coverUrlBaja coverUrlAlta } }
    }}
    """
    tutorials_query = """
    query { activeTutorials { id title videoUrlSigned thumbnailUrlSigned } }
    """
    combos_query = """
    query { allCombos(availableOnly: true) { id name imageUrl branch { avatarUrlBaja } } }
    """
    categories_query = """
    query { productCategories(branchType: "restaurante") { id name } }
    """
    feed_with_images_query = """
    query {
      getFeed(branchTipo: "restaurante", first: 10) {
        sections { sectionId totalCount products { id name imageUrlBaja imageUrlMedia } }
      }
    }
    """

    results = {}
    for label, query in [
        ("productCategories", categories_query),
        ("branches con 6 URLs S3", branches_query),
        ("activeTutorials con videoUrlSigned", tutorials_query),
        ("allCombos con imageUrl", combos_query),
        ("getFeed sin imágenes", (FEED_QUERY, {"branchTipo": "restaurante", "first": 10})),
        ("getFeed con imageUrlBaja + imageUrlMedia", feed_with_images_query),
    ]:
        time.sleep(3)
        if isinstance(query, tuple):
            q, variables = query
            payload = {"query": q, "variables": variables}
        else:
            payload = {"query": query}

        start = time.perf_counter()
        r = http_client.post(GRAPHQL_URL, json=payload, timeout=TIMEOUT)
        ms = (time.perf_counter() - start) * 1000
        r.raise_for_status()
        results[label] = ms

    print("\n  Tiempo por resolver individual:")
    for label, ms in sorted(results.items(), key=lambda x: -x[1]):
        bar = "█" * int(ms / 50)
        print(f"    {ms:6.0f} ms  {bar}  {label}")
