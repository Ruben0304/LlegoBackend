"""
Utilidad para generar códigos de invitación seguros y únicos.
Usa el módulo secrets para garantizar seguridad criptográfica.
"""
import secrets
import string


# Configuración del formato del código
CODE_PREFIX = "INV"
SEGMENT_LENGTH = 6
SEGMENTS = 2

# Set de caracteres excluyendo ambiguos (0, O, I, 1)
CHARSET = string.ascii_uppercase + string.digits
CHARSET = CHARSET.replace('O', '').replace('I', '').replace('0', '').replace('1', '')


def generate_invitation_code() -> str:
    """
    Genera un código de invitación seguro.

    Formato: INV-XXXXXX-XXXXXX (12 caracteres aleatorios)
    Usa caracteres alfanuméricos en mayúsculas, excluyendo 0/O/1/I para evitar confusión.

    Returns:
        str: Código de invitación generado

    Examples:
        >>> code = generate_invitation_code()
        >>> code  # "INV-A7B3C2-D9E4F6"
    """
    segments = []
    for _ in range(SEGMENTS):
        segment = ''.join(secrets.choice(CHARSET) for _ in range(SEGMENT_LENGTH))
        segments.append(segment)

    return f"{CODE_PREFIX}-{'-'.join(segments)}"


async def generate_unique_code() -> str:
    """
    Genera un código único verificando que no exista en la base de datos.

    Realiza hasta 10 intentos de generar un código único.
    Con el espacio de ~30^12 combinaciones, las colisiones son extremadamente raras.

    Returns:
        str: Código de invitación único

    Raises:
        Exception: Si no se puede generar un código único después de 10 intentos
    """
    from repositories import branch_invitations_repo

    max_attempts = 10
    for attempt in range(max_attempts):
        code = generate_invitation_code()

        # Verificar si el código ya existe
        existing = await branch_invitations_repo.get_by_code(code)
        if not existing:
            return code

    # Esto es extremadamente improbable con ~30^12 combinaciones
    raise Exception(
        f"No se pudo generar un código único después de {max_attempts} intentos. "
        "Por favor, intente nuevamente."
    )
