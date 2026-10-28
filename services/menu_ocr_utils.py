"""Utilidades puras para búsqueda en cartas por OCR: normalización, tokenización, búsqueda de spans, métricas de calidad."""

import math
import re
import statistics
import unicodedata
from typing import Any

import numpy as np
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

# Umbrales PROVISIONALES (a calibrar con fotos reales)
MIN_TOKEN_LENGTH = 3
MIN_QUERY_FOR_FUZZY = 4
# Similitud mínima (0-100) de Levenshtein entre consulta y palabra: una errata en
# una palabra de 5+ letras ("piza"/"pizza", "cofee"/"coffee") pasa; fragmentos no.
FUZZY_MIN_SIMILARITY = 80

_WORD_RE = re.compile(r"[a-z0-9]+")

# Vocabulario para métricas de OCR
VOCAB = [
    "pizza",
    "pasta",
    "carta",
    "menu",
    "cerveza",
    "refresco",
    "ensalada",
    "queso",
    "jamon",
    "carne",
    "bebidas",
    "postre",
    "pollo",
    "arroz",
    "sandwich",
    "cafe",
    "jugo",
]

# Mensajes de calidad en español
QUALITY_MESSAGES_ES = {
    "no_text": "No pudimos leer la carta: toma otra foto de frente y con buena luz.",
    "many_doubtful_lines": "Muchas líneas dudosas: intenta enfocar mejor.",
    "low_confidence": "Confianza OCR baja: toma otra foto de frente y con buena luz.",
    "noisy_text": "Texto con ruido: toma otra foto más clara.",
    "dark": "Hay poca luz: busca un lugar más iluminado.",
    "blurry": "Foto borrosa: mantén el teléfono firme y enfoca.",
    "slightly_blurry": "Algo desenfocada: intenta enfocar mejor.",
    "glare": "Hay reflejos: evita el flash directo.",
    "low_resolution": "La imagen es muy pequeña: acércate a la carta.",
    "tilted": "Coloca el teléfono de frente a la carta.",
}


def normalize_text(text: str) -> str:
    """Normaliza a minúsculas sin diacríticos, conservando la longitud.

    Cada carácter se normaliza independientemente para que los índices
    sean válidos sobre el texto original.
    """
    out = []
    for c in text:
        # Descompone en NFD y elimina marcas diacríticas (categoría Mn)
        d = "".join(x for x in unicodedata.normalize("NFD", c.lower()) if unicodedata.category(x) != "Mn")
        # Si la normalización cambió la longitud, usa solo el carácter en minúsculas
        out.append(d if len(d) == 1 else c.lower())
    return "".join(out)


def tokenize(text: str) -> list[str]:
    """Extrae secuencias alfanuméricas de longitud >= 3 que contengan al menos una letra.

    Devuelve los tokens en orden y con repetidos.
    """
    normalized = normalize_text(text)
    tokens = []
    for match in re.finditer(r"[a-z0-9]+", normalized):
        token = match.group()
        # Mantener solo si tiene longitud >= 3 y contiene al menos una letra
        if len(token) >= MIN_TOKEN_LENGTH and any(c.isalpha() for c in token):
            tokens.append(token)
    return tokens


def trigrams_of(word: str) -> set[str]:
    """Devuelve trigramas de caracteres de una palabra (normalizada)."""
    if len(word) < 3:
        return set()
    return {word[i : i + 3] for i in range(len(word) - 2)}


def build_index_fields(lines: list[dict], max_tokens: int = 2000, max_trigrams: int = 6000) -> dict:
    """Construye índice de tokens y trigramas a partir de líneas OCR.

    Args:
        lines: Lista de dicts con clave 'text'
        max_tokens: Máximo número de tokens únicos a incluir
        max_trigrams: Máximo número de trigramas únicos a incluir

    Returns:
        Dict con claves 'tokens' (lista ordenada) y 'trigrams' (lista ordenada)
    """
    all_tokens = []
    all_trigrams = set()

    for line in lines:
        text = line.get("text", "")
        line_tokens = tokenize(text)
        all_tokens.extend(line_tokens)
        for token in line_tokens:
            all_trigrams.update(trigrams_of(token))

    # Remover duplicados y ordenar
    unique_tokens = sorted(list(set(all_tokens)))
    unique_trigrams = sorted(list(all_trigrams))

    # Respetar topes
    unique_tokens = unique_tokens[:max_tokens]
    unique_trigrams = unique_trigrams[:max_trigrams]

    return {"tokens": unique_tokens, "trigrams": unique_trigrams}


def query_terms(query: str) -> dict:
    """Extrae términos de búsqueda de una consulta.

    Returns:
        Dict con 'tokens' (lista única y sin repetidos) y 'trigrams' (lista única)
    """
    tokens = tokenize(query)
    unique_tokens = sorted(list(set(tokens)))

    # Calcular trigramas de todos los tokens
    all_trigrams = set()
    for token in unique_tokens:
        all_trigrams.update(trigrams_of(token))

    trigrams_list = sorted(list(all_trigrams))

    # Si la consulta normalizada tiene < 3 caracteres alfanuméricos, devolver vacío
    normalized_query = normalize_text(query)
    alnum_chars = [c for c in normalized_query if c.isalnum()]
    if len(alnum_chars) < 3:
        return {"tokens": [], "trigrams": []}

    return {"tokens": unique_tokens, "trigrams": trigrams_list}


def find_spans(text: str, query: str) -> list[tuple[int, int]]:
    """Encuentra posiciones donde aparece la consulta en el texto.

    Primero busca ocurrencias exactas. Si no hay y query_norm >= 4 caracteres,
    intenta búsqueda difusa con rapidfuzz.

    Args:
        text: Texto original
        query: Consulta (sin normalizar)

    Returns:
        Lista de tuplas (start, end) sobre el texto original
    """
    normalized_text = normalize_text(text)
    normalized_query = normalize_text(query).strip()

    # Consulta vacía devuelve lista vacía
    if not normalized_query:
        return []

    # Buscar ocurrencias exactas
    spans = [(m.start(), m.end()) for m in re.finditer(re.escape(normalized_query), normalized_text)]
    if spans:
        return spans

    # Sin coincidencias exactas: tolerar erratas, pero comparando PALABRAS COMPLETAS.
    # `partial_ratio_alignment` aceptaba fragmentos cortos de cualquier palabra
    # ("Chse" por "cheeze", "SALE" por "salad", "fres" de "fresh" por "fries").
    if len(normalized_query) >= MIN_QUERY_FOR_FUZZY:
        return _fuzzy_word_spans(normalized_text, normalized_query)

    return []


def _fuzzy_word_spans(normalized_text: str, normalized_query: str) -> list[tuple[int, int]]:
    """Ventanas de palabras del texto que se parecen a la consulta (similitud Levenshtein).

    La similitud de Levenshtein penaliza la diferencia de longitud, así que un
    prefijo o fragmento de otra palabra no pasa. Las palabras pegadas por el OCR
    ("downsviewmilk") solo se encuentran por la vía exacta.
    """
    query_words = _WORD_RE.findall(normalized_query)
    if not query_words:
        return []
    joined_query = " ".join(query_words)
    size = len(query_words)
    words = list(_WORD_RE.finditer(normalized_text))

    spans = []
    for i in range(len(words) - size + 1):
        window = words[i : i + size]
        candidate = " ".join(w.group() for w in window)
        similarity = Levenshtein.normalized_similarity(joined_query, candidate)
        if similarity * 100 >= FUZZY_MIN_SIMILARITY - 1e-9:
            spans.append((window[0].start(), window[-1].end()))
    return spans


def word_polygon(box: list, text: str, start: int, end: int) -> list[list[float]]:
    """Calcula el polígono de la palabra dentro de la línea.

    Interpola proporcionalmente sobre los bordes superior e inferior de la caja.

    Args:
        box: Lista de 4 puntos [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]
             donde tl, tr, br, bl son top-left, top-right, bottom-right, bottom-left
        text: Texto completo de la línea
        start: Índice de inicio de la palabra
        end: Índice de fin de la palabra

    Returns:
        Lista de 4 puntos [p_top_a, p_top_b, p_bottom_b, p_bottom_a]
    """
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = box  # tl, tr, br, bl

    n = max(len(text), 1)
    a = start / n
    b = end / n

    def lerp(p: tuple, q: tuple, f: float) -> tuple:
        """Interpolación lineal entre dos puntos."""
        return (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)

    p_top_a = lerp((x0, y0), (x1, y1), a)
    p_top_b = lerp((x0, y0), (x1, y1), b)
    p_bottom_b = lerp((x3, y3), (x2, y2), b)
    p_bottom_a = lerp((x3, y3), (x2, y2), a)

    # Redondear a 4 decimales
    return [
        [round(p[0], 4), round(p[1], 4)] for p in [p_top_a, p_top_b, p_bottom_b, p_bottom_a]
    ]


def search_lines(
    lines: list[dict], query: str, max_matches: int = 50
) -> list[dict]:
    """Busca la consulta en las líneas y devuelve spans con polígonos.

    Args:
        lines: Lista de dicts con 'text' y 'box'
        query: Consulta
        max_matches: Máximo número de resultados

    Returns:
        Lista de dicts con lineIndex, start, end, text, polygon
    """
    results = []

    for i, line in enumerate(lines):
        text = line.get("text", "")
        box = line.get("box")
        if not box:
            continue

        spans = find_spans(text, query)
        for start, end in spans:
            if len(results) >= max_matches:
                break
            results.append(
                {
                    "lineIndex": i,
                    "start": start,
                    "end": end,
                    "text": text[start:end],
                    "polygon": word_polygon(box, text, start, end),
                }
            )

        if len(results) >= max_matches:
            break

    return results


def limit_lines(lines: list[dict], max_lines: int = 400) -> list[dict]:
    """Limita el número de líneas, conservando las de mayor confianza.

    Mantiene el orden original.
    """
    if len(lines) <= max_lines:
        return lines

    # Crear lista de (índice original, line) ordenada por confianza descendente
    indexed_lines = [(i, line) for i, line in enumerate(lines)]
    sorted_by_conf = sorted(indexed_lines, key=lambda x: x[1].get("conf", 0), reverse=True)[
        :max_lines
    ]

    # Devolver en orden original
    return [line for _, line in sorted(sorted_by_conf, key=lambda x: x[0])]


def normalize_box(box: list, width: int, height: int) -> list[list[float]]:
    """Normaliza coordenadas de caja dividiéndolas por dimensiones de imagen.

    Args:
        box: Lista de puntos [[x0, y0], [x1, y1], ...]
        width: Ancho de la imagen
        height: Altura de la imagen

    Returns:
        Lista de puntos normalizados (valores entre 0 y 1)
    """
    normalized = []
    for point in box:
        x, y = point
        normalized.append([round(x / width, 4), round(y / height, 4)])
    return normalized


def skew_degrees(lines: list[dict]) -> float:
    """Calcula la inclinación mediana del borde superior de las líneas.

    Args:
        lines: Lista de dicts con 'box' (4 puntos)

    Returns:
        Ángulo en grados (0.0 si no hay líneas)
    """
    angles = []
    for line in lines:
        box = line.get("box")
        if not box or len(box) < 2:
            continue
        (x0, y0), (x1, y1) = box[0], box[1]
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        angles.append(angle)

    if not angles:
        return 0.0

    return float(statistics.median(angles))


def ocr_metrics(lines: list[dict]) -> dict:
    """Calcula métricas de calidad del OCR.

    Args:
        lines: Lista de dicts con 'conf' (confianza) y 'text'

    Returns:
        Dict con lineas, conf, baja_pct, basura_pct, vocab, inclin
    """
    if not lines:
        return {
            "lineas": 0,
            "conf": 0,
            "baja_pct": 100,
            "basura_pct": 100,
            "vocab": 0,
            "inclin": 0,
        }

    confs = [line.get("conf", 0) for line in lines]
    tokens = [t for line in lines for t in line.get("text", "").split()]

    # Detectar basura: tokens que parecen ruido
    price_pattern = re.compile(r"^\$?\d+([.,:]\d{1,2})?$")
    junk = []
    for token in tokens:
        if not price_pattern.match(token):
            # Contar caracteres no alfanuméricos
            non_alnum = sum(1 for c in token if not c.isalnum())
            has_digit = any(c.isdigit() for c in token)
            has_alpha = any(c.isalpha() for c in token)
            if non_alnum / len(token) > 0.3 or (has_digit and has_alpha):
                junk.append(token)

    # Contar vocabulario: palabras > 3 caracteres que coinciden con vocabulario conocido
    vocab_count = 0
    for token in tokens:
        if len(token) > 3:
            best_ratio = max((fuzz.ratio(normalize_text(token), v) for v in VOCAB), default=0)
            if best_ratio >= 80:
                vocab_count += 1

    return {
        "lineas": len(lines),
        "conf": float(statistics.mean(confs)) if confs else 0,
        "baja_pct": 100 * sum(1 for c in confs if c < 0.6) / len(confs) if confs else 0,
        "basura_pct": 100 * len(junk) / max(len(tokens), 1),
        "vocab": vocab_count,
        "inclin": skew_degrees(lines),
    }


def glare_pct(rgb: np.ndarray, tile: int = 24) -> float:
    """Porcentaje de zonas quemadas (reflejos) en la imagen.

    Detecta áreas blancas puras sobre papel de color, indicando reflejos.

    Args:
        rgb: Imagen como ndarray HxWx3 uint8
        tile: Tamaño del tile para análisis de varianza

    Returns:
        Porcentaje de área quemada (0.0 a 100.0)
    """
    h, w, _ = rgb.shape
    th, tw = h // tile, w // tile

    # Escala grises y canal mínimo dentro de los límites de tiles
    gray = rgb.astype(np.float32).mean(axis=2)[: th * tile, : tw * tile]
    chmin = rgb.min(axis=2)[: th * tile, : tw * tile]

    # Reorganizar en tiles y calcular media y desv. estándar
    t = gray.reshape(th, tile, tw, tile)
    mean, std = t.mean(axis=(1, 3)), t.std(axis=(1, 3))

    # Detectar tiles de papel (brillo > 150)
    paper = mean > 150
    if paper.sum() < 10:
        return 0.0

    # Tiles quemados y sin quemar
    tmin = chmin.reshape(th, tile, tw, tile).min(axis=(1, 3))
    burnt = paper & (tmin >= 250) & (std < 4)
    blank_ok = paper & (tmin < 250) & (std < 4)

    # Si no hay contraste suficiente, no es reflejo
    if burnt.sum() == 0 or blank_ok.sum() / (burnt.sum() + blank_ok.sum()) < 0.15:
        return 0.0

    return float(100 * burnt.sum() / paper.sum())


def photo_metrics(rgb: np.ndarray) -> dict:
    """Calcula métricas de calidad de la foto.

    Args:
        rgb: Imagen como ndarray HxWx3 uint8

    Returns:
        Dict con nitidez, brillo, contraste, lado_corto, reflejo_pct
    """
    import cv2

    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = g.shape

    # Redimensionar para normalizar análisis (máximo 1000 px de ancho)
    if w > 1000:
        g1 = cv2.resize(g, (1000, int(h * 1000 / w)), interpolation=cv2.INTER_AREA)
    else:
        g1 = g  # nunca agrandar (evita falsos positivos en nitidez)

    # Estirar contraste antes de medir nitidez
    lo, hi = np.percentile(g1, [2, 98])
    gs = np.clip((g1.astype(np.float32) - lo) / max(hi - lo, 1) * 255, 0, 255).astype(
        np.uint8
    )

    return {
        "nitidez": float(cv2.Laplacian(gs, cv2.CV_64F).var()),
        "brillo": float(g.mean()),
        "contraste": float(g.std()),
        "lado_corto": min(h, w),
        "reflejo_pct": glare_pct(rgb),
    }


def assess_quality(photo: dict, ocr: dict) -> dict:
    """Evalúa la calidad de la carta basándose en OCR y foto.

    El veredicto está dominado por OCR; la foto solo aporta consejos.

    Args:
        photo: Dict con métricas de foto (photo_metrics)
        ocr: Dict con métricas de OCR (ocr_metrics)

    Returns:
        Dict con 'verdict' (good|fair|bad), 'reasons' y 'tips'
    """
    # Umbrales PROVISIONALES (a calibrar)
    ocr_bad = (
        ocr.get("lineas", 0) < 5
        or ocr.get("baja_pct", 0) > 30
        or ocr.get("conf", 0) < 0.60
        or ocr.get("basura_pct", 0) > 50
    )

    ocr_warn = (
        ocr.get("conf", 0) < 0.70
        or ocr.get("baja_pct", 0) > 15
        or ocr.get("basura_pct", 0) > 15
    )

    reasons = []
    tips = []

    # Determinar veredicto por OCR
    if ocr.get("lineas", 0) < 5:
        reasons.append("no_text")
    if ocr.get("baja_pct", 0) > 15:
        reasons.append("many_doubtful_lines")
    if ocr.get("conf", 0) < 0.70:
        reasons.append("low_confidence")
    if ocr.get("basura_pct", 0) > 15:
        reasons.append("noisy_text")

    # Consejos de foto (pero no anulan good, salvo si ocr_bad)
    brillo = photo.get("brillo", 0)
    nitidez = photo.get("nitidez", 0)
    reflejo = photo.get("reflejo_pct", 0)
    lado_corto = photo.get("lado_corto", 0)
    inclin = abs(ocr.get("inclin", 0))

    if brillo < 70:
        tips.append("dark")
    if nitidez < 40:
        tips.append("blurry")
    elif nitidez < 500:
        tips.append("slightly_blurry")
    if reflejo > 4:
        tips.append("glare")
    if lado_corto < 600:
        tips.append("low_resolution")
    if inclin > 12:
        tips.append("tilted")

    # Determinar veredicto final
    if ocr_bad:
        verdict = "bad"
    elif ocr_warn or tips:
        verdict = "fair"
    else:
        verdict = "good"

    return {"verdict": verdict, "reasons": reasons, "tips": tips}
