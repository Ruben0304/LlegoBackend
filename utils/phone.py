"""Normalización de teléfonos cubanos para comparar números escritos en formatos distintos.

Los teléfonos llegan sin formato común: el perfil del usuario es texto libre (la app iOS
guarda "+53XXXXXXXX", versiones viejas y Android lo que escribió el usuario) y el SMS de
Transfermóvil que registran los Atajos trae "5XXXXXXX". Comparar el texto tal cual hace
que el mismo número no coincida consigo mismo.
"""

import re
from typing import List, Optional

CUBA_COUNTRY_CODE = "53"
CUBA_NATIONAL_LENGTH = 8

# Separadores que la gente escribe dentro de un número: "+53 (5) 555-5555", "5555.5555"
_SEPARATORS = r"[\s\-().]*"


def cuban_national_number(value: Optional[str]) -> Optional[str]:
    """Devuelve los 8 dígitos nacionales de un teléfono cubano, o None si no lo es.

    Acepta "5XXXXXXX", "535XXXXXXX", "+53 5XXX XXXX", "00535XXXXXXX" y "0XXXXXXXX"
    (prefijo nacional). Un número con otro código de país ("+1...") devuelve None.
    """
    raw = (value or "").strip()
    digits = re.sub(r"\D", "", raw)
    has_country_code = raw.startswith("+")
    if not has_country_code and digits.startswith("00"):
        has_country_code = True
        digits = digits[2:]

    if has_country_code:
        if not digits.startswith(CUBA_COUNTRY_CODE):
            return None
        digits = digits[len(CUBA_COUNTRY_CODE):]
    elif len(digits) == len(CUBA_COUNTRY_CODE) + CUBA_NATIONAL_LENGTH and digits.startswith(
        CUBA_COUNTRY_CODE
    ):
        digits = digits[len(CUBA_COUNTRY_CODE):]
    elif len(digits) == CUBA_NATIONAL_LENGTH + 1 and digits.startswith("0"):
        digits = digits[1:]

    return digits if len(digits) == CUBA_NATIONAL_LENGTH else None


def cuban_phone_variants(value: Optional[str]) -> List[str]:
    """Formatos compactos en que puede estar guardado un teléfono cubano (para `$in`)."""
    national = cuban_national_number(value)
    if not national:
        return []
    return [national, f"{CUBA_COUNTRY_CODE}{national}", f"+{CUBA_COUNTRY_CODE}{national}"]


def cuban_phone_regex(value: Optional[str]) -> Optional[str]:
    """Regex anclada que casa el número en cualquier formato habitual, con o sin separadores.

    Para campos de texto libre (perfil de usuario) donde `cuban_phone_variants` no basta
    porque el número puede estar guardado como "+53 5555 5555" o "5555-5555".
    """
    national = cuban_national_number(value)
    if not national:
        return None
    body = _SEPARATORS.join(national)
    return rf"^{_SEPARATORS}(\+|00)?{_SEPARATORS}(53)?{_SEPARATORS}0?{_SEPARATORS}{body}{_SEPARATORS}$"


# E.164: el número internacional completo (código de país incluido) tiene como
# mucho 15 dígitos. 8 es un mínimo prudente para no aceptar basura como "+1 23".
_INTERNATIONAL_MIN_DIGITS = 8
_INTERNATIONAL_MAX_DIGITS = 15
# Lo único que se acepta al escribir un teléfono: "+" inicial, dígitos y separadores.
_PHONE_CHARS = re.compile(r"^\+?[\d\s\-().]+$")


def normalize_phone(value: Optional[str]) -> Optional[str]:
    """Teléfono en formato internacional compacto ("+<código><número>"), o None si no vale.

    - Un número cubano en cualquiera de los formatos de `cuban_national_number`
      ("5XXXXXXX", "+53 5XXX XXXX", "00535XXXXXXX"...) queda "+53XXXXXXXX": sin código
      de país se asume Cuba.
    - Con otro código de país ("+1 305 555 1234", "0034 600 000 000") se respeta tal
      cual, solo sin separadores.
    - Sin "+"/"00" y sin ser un número cubano de 8 dígitos, o con "+53" y una longitud
      que no es la de Cuba, devuelve None.
    """
    raw = (value or "").strip()
    if not raw or not _PHONE_CHARS.match(raw):
        return None

    national = cuban_national_number(raw)
    if national:
        return f"+{CUBA_COUNTRY_CODE}{national}"

    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        international = digits
    elif digits.startswith("00"):
        international = digits[2:]
    else:
        return None

    if international.startswith(CUBA_COUNTRY_CODE) or international.startswith("0"):
        # "+53" con una longitud que no es la cubana, o un código de país imposible.
        return None
    if not _INTERNATIONAL_MIN_DIGITS <= len(international) <= _INTERNATIONAL_MAX_DIGITS:
        return None
    return f"+{international}"
