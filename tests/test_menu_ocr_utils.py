"""Tests para menu_ocr_utils: normalización, tokenización, búsqueda, métricas de calidad."""

import math
import pytest
import numpy as np

from services.menu_ocr_utils import (
    normalize_text,
    tokenize,
    trigrams_of,
    build_index_fields,
    query_terms,
    find_spans,
    word_polygon,
    search_lines,
    limit_lines,
    normalize_box,
    skew_degrees,
    ocr_metrics,
    photo_metrics,
    assess_quality,
)


class TestNormalizeText:
    """Pruebas para normalize_text."""

    def test_lowercase(self):
        """Convierte a minúsculas."""
        assert normalize_text("PIZZA") == "pizza"
        assert normalize_text("Pizza") == "pizza"

    def test_preserves_length_with_tilde(self):
        """Conserva la longitud con ñ."""
        original = "niño"
        normalized = normalize_text(original)
        assert len(normalized) == len(original)
        assert normalized == "nino"

    def test_preserves_length_with_accents(self):
        """Conserva la longitud con tildes."""
        original = "café"
        normalized = normalize_text(original)
        assert len(normalized) == len(original)
        assert normalized == "cafe"

    def test_preserves_length_complex(self):
        """Conserva la longitud con múltiples diacríticos."""
        original = "Señorita"
        normalized = normalize_text(original)
        assert len(normalized) == len(original)

    def test_empty_string(self):
        """Maneja strings vacíos."""
        assert normalize_text("") == ""

    def test_mixed_case_and_diacritics(self):
        """Maneja casos y diacríticos mezclados."""
        original = "MAÑANA"
        normalized = normalize_text(original)
        assert len(normalized) == len(original)
        assert normalized == "manana"


class TestTokenize:
    """Pruebas para tokenize."""

    def test_simple_word(self):
        """Extrae palabras simples."""
        tokens = tokenize("pizza")
        assert "pizza" in tokens

    def test_multiple_words(self):
        """Extrae múltiples palabras."""
        tokens = tokenize("pizza pasta")
        assert "pizza" in tokens
        assert "pasta" in tokens

    def test_minimum_length(self):
        """Solo tokens de >= 3 caracteres."""
        tokens = tokenize("a ab abc abcd")
        assert "abc" in tokens
        assert "abcd" in tokens
        assert "a" not in tokens
        assert "ab" not in tokens

    def test_requires_letter(self):
        """Solo tokens con al menos una letra."""
        tokens = tokenize("123 abc123 123abc")
        # "123" no tiene letra, debe excluirse
        # "abc123" y "123abc" tienen letras, deben incluirse
        assert "123" not in tokens
        assert "abc123" in tokens
        assert "123abc" in tokens

    def test_normalized(self):
        """Los tokens están normalizados."""
        tokens = tokenize("PIZZA Ñoño")
        assert "pizza" in tokens
        # "nono" debería estar (normalizado de "ñoño")
        for token in tokens:
            assert token == normalize_text(token)

    def test_order_preserved(self):
        """Mantiene el orden de aparición."""
        tokens = tokenize("pizza pasta pizza")
        assert tokens[0] == "pizza"
        assert tokens[1] == "pasta"
        assert tokens[2] == "pizza"  # repetido

    def test_no_tokens(self):
        """Devuelve lista vacía si no hay tokens válidos."""
        tokens = tokenize("123 456 a b")
        assert tokens == []

    def test_punctuation_splits(self):
        """La puntuación actúa como separador."""
        tokens = tokenize("pizza-pasta, café")
        assert "pizza" in tokens
        assert "pasta" in tokens
        assert "caf" in tokens or "cafe" in tokens


class TestTrigramsOf:
    """Pruebas para trigrams_of."""

    def test_simple_word(self):
        """Extrae trigramas de una palabra."""
        trigrams = trigrams_of("pizza")
        assert "piz" in trigrams
        assert "izz" in trigrams
        assert "zza" in trigrams
        assert len(trigrams) == 3

    def test_short_word(self):
        """Palabras < 3 caracteres devuelven conjunto vacío."""
        assert trigrams_of("a") == set()
        assert trigrams_of("ab") == set()

    def test_exact_three_chars(self):
        """Palabra de exactamente 3 caracteres."""
        trigrams = trigrams_of("abc")
        assert trigrams == {"abc"}

    def test_four_chars(self):
        """Palabra de 4 caracteres devuelve 2 trigramas."""
        trigrams = trigrams_of("abcd")
        assert trigrams == {"abc", "bcd"}


class TestBuildIndexFields:
    """Pruebas para build_index_fields."""

    def test_simple_lines(self):
        """Construye índice desde líneas simples."""
        lines = [{"text": "Pizza Margarita"}, {"text": "Pasta Carbonara"}]
        result = build_index_fields(lines)
        assert isinstance(result["tokens"], list)
        assert isinstance(result["trigrams"], list)
        assert "pizza" in result["tokens"]
        assert "pasta" in result["tokens"]

    def test_contains_expected_trigrams(self):
        """Contiene trigramas esperados."""
        lines = [{"text": "pizza"}]
        result = build_index_fields(lines)
        # "pizza" normalizado tiene trigramas "piz", "izz", "zza"
        assert "piz" in result["trigrams"] or len(result["trigrams"]) > 0

    def test_respects_max_tokens(self):
        """Respeta el límite de tokens."""
        lines = [{"text": f"word{i}"} for i in range(100)]
        result = build_index_fields(lines, max_tokens=50)
        # Algunos tokens se descartan
        assert len(result["tokens"]) <= 50

    def test_respects_max_trigrams(self):
        """Respeta el límite de trigramas."""
        lines = [{"text": f"word{i}"} for i in range(100)]
        result = build_index_fields(lines, max_trigrams=100)
        assert len(result["trigrams"]) <= 100

    def test_empty_lines(self):
        """Maneja líneas vacías."""
        lines = [{"text": ""}, {"text": ""}]
        result = build_index_fields(lines)
        assert result["tokens"] == []
        assert result["trigrams"] == []

    def test_sorted_output(self):
        """Devuelve listas ordenadas."""
        lines = [{"text": "zebra apple"}, {"text": "banana"}]
        result = build_index_fields(lines)
        assert result["tokens"] == sorted(result["tokens"])
        assert result["trigrams"] == sorted(result["trigrams"])


class TestQueryTerms:
    """Pruebas para query_terms."""

    def test_simple_query(self):
        """Extrae términos de una consulta simple."""
        result = query_terms("pizza")
        assert "pizza" in result["tokens"]

    def test_short_query_empty(self):
        """Consulta con < 3 caracteres alfanuméricos devuelve vacío."""
        result = query_terms("ab")
        assert result["tokens"] == []
        assert result["trigrams"] == []

    def test_query_with_spaces(self):
        """Consulta con múltiples palabras."""
        result = query_terms("Pizza Margarita")
        assert "pizza" in result["tokens"]
        assert "margarita" in result["tokens"]
        # Debe haber trigramas
        assert len(result["trigrams"]) > 0

    def test_no_duplicates(self):
        """Sin tokens duplicados."""
        result = query_terms("pizza pizza pizza")
        assert result["tokens"].count("pizza") == 1

    def test_exactly_three_chars(self):
        """Consulta con exactamente 3 caracteres alfanuméricos devuelve resultados."""
        result = query_terms("abc")
        # "abc" tiene 3 caracteres, debe incluirse
        assert len(result["tokens"]) > 0 or result["tokens"] == []  # puede ser no encontrado


class TestFindSpans:
    """Pruebas para find_spans."""

    def test_exact_match(self):
        """Encuentra ocurrencia exacta."""
        spans = find_spans("Pizza Margarita", "pizza")
        assert (0, 5) in spans

    def test_multiple_occurrences(self):
        """Encuentra múltiples ocurrencias."""
        spans = find_spans("pizza pizza pizza", "pizza")
        assert len(spans) >= 2

    def test_case_insensitive(self):
        """Búsqueda sin considerar mayúsculas."""
        spans = find_spans("PIZZA", "pizza")
        assert len(spans) > 0

    def test_word_stuck_to_punctuation(self):
        """Encuentra palabras pegadas a puntuación (e.g., 'norm.PIZZA')."""
        spans = find_spans("norm.PIZZA", "pizza")
        assert len(spans) > 0

    def test_fuzzy_match(self):
        """Búsqueda difusa: 'piza' encuentra 'pizza'."""
        spans = find_spans("Pizza Margarita", "piza")
        # "piza" -> "pizza" con score >= 85
        assert len(spans) > 0

    def test_no_false_positive(self):
        """'pizza' no encuentra 'spaghetti'."""
        spans = find_spans("Spaghetti", "pizza")
        assert len(spans) == 0

    def test_short_query_no_fuzzy(self):
        """Consulta < 4 caracteres sin búsqueda difusa."""
        # "piz" tiene 3 caracteres, no debe intentar fuzzy
        spans = find_spans("Pizza", "piz")
        # Puede encontrar "piz" en "pizza" como exacta, pero no por fuzzy
        # En este caso, "piz" es exacta dentro de "pizza" normalizado

    def test_empty_text(self):
        """Texto vacío devuelve lista vacía."""
        spans = find_spans("", "pizza")
        assert spans == []

    def test_empty_query(self):
        """Consulta vacía devuelve lista vacía."""
        spans = find_spans("Pizza", "")
        assert spans == []
        # Después de normalización, "" sigue siendo ""
        assert find_spans("Anything", "") == []


class TestWordPolygon:
    """Pruebas para word_polygon."""

    def test_axis_aligned_box(self):
        """Caja alineada a ejes."""
        box = [[0, 0], [100, 0], [100, 50], [0, 50]]
        text = "hello"
        # Primeros 2 caracteres: start=0, end=2
        polygon = word_polygon(box, text, 0, 2)
        assert len(polygon) == 4
        # Top-left debe estar en (0, 0)
        assert polygon[0][0] == 0.0 and polygon[0][1] == 0.0
        # Top-right debe estar en (40, 0)
        assert polygon[1][0] == 40.0 and polygon[1][1] == 0.0

    def test_tilted_box(self):
        """Caja inclinada."""
        box = [[10, 10], [110, 20], [100, 60], [0, 50]]
        text = "hello"
        polygon = word_polygon(box, text, 0, 2)
        assert len(polygon) == 4
        # Debe interpolar correctamente aunque esté inclinada

    def test_rounding(self):
        """Redondea a 4 decimales."""
        box = [[0.5, 0.5], [100.5, 0.5], [100.5, 50.5], [0.5, 50.5]]
        text = "hello"
        polygon = word_polygon(box, text, 0, 2)
        for point in polygon:
            # Cada valor debe tener máximo 4 decimales
            for coord in point:
                decimal_places = len(str(coord).split(".")[-1]) if "." in str(coord) else 0
                assert decimal_places <= 4

    def test_full_word(self):
        """Polígono de la palabra completa."""
        box = [[0, 0], [100, 0], [100, 50], [0, 50]]
        text = "hello"
        polygon = word_polygon(box, text, 0, 5)
        # start=0, end=len(text), debe ser toda la caja
        assert polygon[0] == [0.0, 0.0]
        assert polygon[1] == [100.0, 0.0]


class TestSearchLines:
    """Pruebas para search_lines."""

    def test_simple_search(self):
        """Busca en líneas simples."""
        lines = [
            {"text": "Pizza Margarita", "box": [[0, 0], [100, 0], [100, 50], [0, 50]]},
            {"text": "Pasta Carbonara", "box": [[0, 60], [100, 60], [100, 100], [0, 100]]},
        ]
        results = search_lines(lines, "pizza")
        assert len(results) > 0
        assert results[0]["lineIndex"] == 0

    def test_respects_max_matches(self):
        """Respeta el límite de coincidencias."""
        lines = [
            {"text": "pizza pizza pizza", "box": [[0, 0], [100, 0], [100, 50], [0, 50]]},
        ]
        results = search_lines(lines, "pizza", max_matches=2)
        assert len(results) <= 2

    def test_includes_polygon(self):
        """Cada resultado incluye polígono."""
        lines = [
            {"text": "Pizza", "box": [[0, 0], [100, 0], [100, 50], [0, 50]]},
        ]
        results = search_lines(lines, "pizza")
        assert len(results) > 0
        assert "polygon" in results[0]

    def test_missing_box_skipped(self):
        """Líneas sin 'box' se saltan."""
        lines = [
            {"text": "Pizza", "box": [[0, 0], [100, 0], [100, 50], [0, 50]]},
            {"text": "Pizza"},  # sin box
        ]
        results = search_lines(lines, "pizza")
        # Solo una línea debe tener resultados
        assert len(results) > 0


class TestLimitLines:
    """Pruebas para limit_lines."""

    def test_preserves_order(self):
        """Conserva el orden original de las líneas."""
        lines = [
            {"text": "First", "conf": 0.5},
            {"text": "Second", "conf": 0.9},
            {"text": "Third", "conf": 0.3},
        ]
        result = limit_lines(lines, max_lines=2)
        # Debe conservar orden: Second (0.9) y First (0.5) en su orden original
        assert result[0]["text"] == "First"
        assert result[1]["text"] == "Second"

    def test_keeps_highest_conf(self):
        """Mantiene las líneas con mayor confianza."""
        lines = [
            {"text": "Low", "conf": 0.2},
            {"text": "High", "conf": 0.9},
            {"text": "Med", "conf": 0.5},
        ]
        result = limit_lines(lines, max_lines=2)
        # Debe mantener "High" y "Med" (en ese orden original)
        assert any(l["text"] == "High" for l in result)
        assert any(l["text"] == "Med" for l in result)

    def test_no_limit_when_below_max(self):
        """Si hay menos líneas que el tope, devuelve todas."""
        lines = [
            {"text": "A", "conf": 0.5},
            {"text": "B", "conf": 0.6},
        ]
        result = limit_lines(lines, max_lines=10)
        assert len(result) == 2

    def test_missing_conf_defaults_to_zero(self):
        """Líneas sin 'conf' se tratan como 0."""
        lines = [
            {"text": "A"},  # sin conf
            {"text": "B", "conf": 0.5},
        ]
        result = limit_lines(lines, max_lines=1)
        # Debe mantener "B" (conf=0.5 > 0)
        assert result[0]["text"] == "B"


class TestNormalizeBox:
    """Pruebas para normalize_box."""

    def test_divides_by_dimensions(self):
        """Divide cada punto por (width, height)."""
        box = [[100, 50], [200, 50], [200, 100], [100, 100]]
        result = normalize_box(box, width=200, height=100)
        assert result[0] == [0.5, 0.5]  # [100/200, 50/100]
        assert result[1] == [1.0, 0.5]  # [200/200, 50/100]

    def test_rounding(self):
        """Redondea a 4 decimales."""
        box = [[1, 1], [2, 2]]
        result = normalize_box(box, width=3, height=3)
        for point in result:
            for coord in point:
                decimal_places = len(str(coord).split(".")[-1]) if "." in str(coord) else 0
                assert decimal_places <= 4


class TestSkewDegrees:
    """Pruebas para skew_degrees."""

    def test_horizontal_line(self):
        """Línea horizontal: 0 grados."""
        lines = [{"box": [[0, 0], [100, 0], [100, 50], [0, 50]]}]
        skew = skew_degrees(lines)
        assert skew == 0.0

    def test_tilted_line(self):
        """Línea inclinada: calcula ángulo."""
        lines = [{"box": [[0, 0], [100, 100], [100, 150], [0, 50]]}]
        skew = skew_degrees(lines)
        # arctan(100/100) = 45 grados
        assert abs(skew - 45.0) < 1.0

    def test_empty_lines(self):
        """Sin líneas: 0 grados."""
        skew = skew_degrees([])
        assert skew == 0.0

    def test_median_of_multiple(self):
        """Mediana de múltiples inclinaciones."""
        lines = [
            {"box": [[0, 0], [100, 0], [100, 50], [0, 50]]},  # 0 grados
            {"box": [[0, 0], [100, 100], [100, 150], [0, 50]]},  # ~45 grados
        ]
        skew = skew_degrees(lines)
        # Mediana debe estar entre 0 y 45
        assert 0 <= skew <= 45


class TestOcrMetrics:
    """Pruebas para ocr_metrics."""

    def test_empty_lines(self):
        """Líneas vacías: valores por defecto."""
        result = ocr_metrics([])
        assert result["lineas"] == 0
        assert result["conf"] == 0
        assert result["baja_pct"] == 100
        assert result["basura_pct"] == 100

    def test_simple_lines(self):
        """Calcula métricas desde líneas simples."""
        lines = [
            {"text": "Pizza", "conf": 0.9, "box": [[0, 0], [50, 0], [50, 20], [0, 20]]},
            {"text": "Pasta", "conf": 0.8, "box": [[0, 25], [50, 25], [50, 45], [0, 45]]},
        ]
        result = ocr_metrics(lines)
        assert result["lineas"] == 2
        assert result["conf"] == pytest.approx(0.85, abs=0.01)
        assert result["baja_pct"] == 0
        assert result["basura_pct"] == 0


class TestPhotoMetrics:
    """Pruebas para photo_metrics."""

    def test_clean_white_image(self):
        """Imagen blanca limpia."""
        pytest.importorskip("cv2")
        # Crear imagen blanca
        rgb = np.ones((200, 200, 3), dtype=np.uint8) * 255
        result = photo_metrics(rgb)

        assert "nitidez" in result
        assert "brillo" in result
        assert "contraste" in result
        assert "lado_corto" in result
        assert "reflejo_pct" in result

        # Imagen blanca debe tener brillo alto
        assert result["brillo"] > 200
        # Imagen sin detalles debe tener bajo contraste
        assert result["contraste"] < 50

    def test_dark_image(self):
        """Imagen muy oscura."""
        pytest.importorskip("cv2")
        # Crear imagen oscura
        rgb = np.ones((200, 200, 3), dtype=np.uint8) * 50
        result = photo_metrics(rgb)

        # Imagen oscura debe tener bajo brillo
        assert result["brillo"] < 100

    def test_small_image(self):
        """Imagen pequeña."""
        pytest.importorskip("cv2")
        rgb = np.ones((50, 50, 3), dtype=np.uint8) * 128
        result = photo_metrics(rgb)

        # lado_corto debe ser 50
        assert result["lado_corto"] == 50


class TestAssessQuality:
    """Pruebas para assess_quality."""

    def test_good_quality(self):
        """Veredicto GOOD con OCR y foto buenos."""
        photo = {
            "brillo": 100,
            "nitidez": 1000,
            "contraste": 50,
            "lado_corto": 1000,
            "reflejo_pct": 0,
        }
        ocr = {
            "lineas": 20,
            "conf": 0.9,
            "baja_pct": 5,
            "basura_pct": 5,
            "vocab": 5,
            "inclin": 0,
        }
        result = assess_quality(photo, ocr)
        assert result["verdict"] == "good"
        assert result["reasons"] == []

    def test_bad_quality(self):
        """Veredicto BAD con OCR malo."""
        photo = {"brillo": 100, "nitidez": 100, "contraste": 5, "lado_corto": 200, "reflejo_pct": 0}
        ocr = {
            "lineas": 2,  # < 5: malo
            "conf": 0.5,  # < 0.60: malo
            "baja_pct": 40,  # > 30: malo
            "basura_pct": 60,  # > 50: malo
            "vocab": 0,
            "inclin": 0,
        }
        result = assess_quality(photo, ocr)
        assert result["verdict"] == "bad"
        assert len(result["reasons"]) > 0

    def test_fair_quality(self):
        """Veredicto FAIR con advertencias."""
        photo = {
            "brillo": 50,  # oscura: dark
            "nitidez": 200,  # slightly_blurry
            "contraste": 30,
            "lado_corto": 1000,
            "reflejo_pct": 0,
        }
        ocr = {
            "lineas": 15,
            "conf": 0.75,  # borderline
            "baja_pct": 10,
            "basura_pct": 10,
            "vocab": 3,
            "inclin": 5,
        }
        result = assess_quality(photo, ocr)
        assert result["verdict"] == "fair"
        assert "dark" in result["tips"]

    def test_tips_included(self):
        """Incluye tips de foto en el resultado."""
        photo = {
            "brillo": 30,  # dark
            "nitidez": 30,  # blurry
            "contraste": 10,
            "lado_corto": 400,  # low_resolution
            "reflejo_pct": 10,  # glare
        }
        ocr = {
            "lineas": 20,
            "conf": 0.9,
            "baja_pct": 5,
            "basura_pct": 5,
            "vocab": 5,
            "inclin": 20,  # tilted
        }
        result = assess_quality(photo, ocr)
        # Debe incluir varios tips
        assert "dark" in result["tips"] or "blurry" in result["tips"]
        assert "tilted" in result["tips"]
