"""Lógica pura del override diario de horario de una sucursal (`temporaryStatus`).

Sin Mongo ni Strawberry, para poder testearla aislada (mismo criterio que
`services/orders_utils.py`). La usan `OrderService` (¿está abierta la sucursal
ahora / a la hora programada?) y `schema/branches/utils.py` (qué override se
expone a los clientes).

Reglas del override (`BranchSchedule.temporaryStatus`, ver `domain/models.py`):

- Con `date` (YYYY-MM-DD, lo que escribe `setBranchDailyOverride` desde la app
  de negocios): aplica **solo ese día en hora de Cuba**. Cualquier otro día se
  ignora y manda el horario semanal.
- Sin `date` (legacy: seeds, `updateBranch` con `schedule.temporaryStatus`):
  se mantiene el comportamiento antiguo, aplica indefinidamente.
- Cuando aplica, decide así (en este orden):
  1. `temporallyClosed` → cerrada todo el día.
  2. `openTime` y `closeTime` válidos → abierta solo en ese rango ese día
     (si `closeTime < openTime`, el rango cruza la medianoche).
  3. Nada de lo anterior → no decide; manda el horario semanal. Incluye
     `temporallyOpen` sin horas: "Abierto hoy" significa el horario normal, no
     abierto todo el día (decisión de producto; antes abría las 24 h y el
     switch de la app de negocios, al deshacer un "Cerrado hoy", dejaba la
     tienda abierta de madrugada).
"""

import re
from datetime import date, datetime
from typing import Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

# Todas las sucursales están en Cuba: "hoy" y las horas del horario se
# interpretan siempre en esta zona, nunca en la del servidor (UTC en Railway).
BRANCH_TIMEZONE = "America/Havana"

MINUTES_PER_DAY = 24 * 60

DayRange = Tuple[int, int]


def branch_local_now() -> datetime:
    """Hora actual en la zona horaria de las sucursales (aware)."""
    try:
        return datetime.now(ZoneInfo(BRANCH_TIMEZONE))
    except Exception:
        return datetime.now()


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Lee un campo de un modelo Pydantic o de un dict crudo de Mongo."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def parse_time_to_minutes(time_value: Any) -> Optional[int]:
    """'HH:MM' 24h → minutos desde medianoche. '24:00' vale 1440. None si es inválida."""
    raw = str(time_value or "").strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", raw):
        return None

    hour_str, minute_str = raw.split(":")
    hour = int(hour_str)
    minute = int(minute_str)

    if hour == 24 and minute == 0:
        return MINUTES_PER_DAY
    if hour < 0 or hour > 23:
        return None
    if minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def parse_override_date(value: Any) -> Optional[date]:
    """'YYYY-MM-DD' → date. None si falta o no se puede leer."""
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def get_temporary_status(schedule: Any) -> Any:
    return _field(schedule, "temporaryStatus")


def is_dated_override(temporary_status: Any) -> bool:
    return bool(str(_field(temporary_status, "date") or "").strip())


def temporary_status_applies_on(
    temporary_status: Any, local_date: date, include_undated: bool = True
) -> bool:
    """¿El override aplica en `local_date` (fecha local de Cuba)?

    Un override con fecha ilegible no aplica nunca: es preferible ignorarlo a
    dejar la tienda cerrada (o abierta) indefinidamente.
    """
    if not temporary_status:
        return False
    if not is_dated_override(temporary_status):
        return include_undated
    return parse_override_date(_field(temporary_status, "date")) == local_date


def override_day_ranges(temporary_status: Any) -> Optional[List[DayRange]]:
    """Rangos de apertura que impone el override para su día.

    - `[]` → cerrada todo el día.
    - `[(inicio, fin)]` → horario especial de ese día.
    - `None` → el override no decide; usar el horario semanal (también
      `temporallyOpen` sin horas, ver la regla 3 del módulo).

    No mira la fecha: el llamante decide antes si el override aplica.
    """
    if not temporary_status:
        return None
    if _field(temporary_status, "temporallyClosed", False):
        return []

    hours = _override_hours(temporary_status)
    if hours is not None:
        return [hours]
    return None


def _override_hours(temporary_status: Any) -> Optional[DayRange]:
    start = parse_time_to_minutes(_field(temporary_status, "openTime"))
    end = parse_time_to_minutes(_field(temporary_status, "closeTime"))
    if start is None or end is None:
        return None
    return (start, end)


def exposed_temporally_open(temporary_status: Any) -> bool:
    """`temporallyOpen` que se expone a las apps.

    iOS y Android muestran "Abierto" con `temporallyOpen` sin mirar las horas.
    Sin horario especial el flag ya no decide nada (manda el horario semanal),
    así que se expone `false` para que las apps calculen el estado con el
    horario semanal igual que el backend.
    """
    if not temporary_status or not _field(temporary_status, "temporallyOpen", False):
        return False
    return _override_hours(temporary_status) is not None


def _format_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _normalize_override_hours(
    open_time: Optional[str], close_time: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    has_open = bool(str(open_time or "").strip())
    has_close = bool(str(close_time or "").strip())
    if has_open != has_close:
        raise ValueError("Indica la hora de apertura y la de cierre del horario especial")
    if not has_open:
        return None, None

    start = parse_time_to_minutes(open_time)
    end = parse_time_to_minutes(close_time)
    if start is None or end is None:
        raise ValueError("Las horas del horario especial deben tener formato HH:MM (24 h)")
    if start == end:
        raise ValueError("La hora de apertura y la de cierre no pueden ser iguales")
    return _format_minutes(start), _format_minutes(end)


def normalize_daily_override_input(
    date_value: str,
    open_time: Optional[str],
    close_time: Optional[str],
    temporally_closed: bool = False,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Valida y normaliza lo que recibe `setBranchDailyOverride`.

    Devuelve `(fecha 'YYYY-MM-DD', apertura 'HH:MM' | None, cierre 'HH:MM' | None)`.
    Lanza ValueError con un mensaje en español que la app muestra tal cual.

    Si se cierra el día (`temporally_closed`), las horas no cuentan: unas horas
    incompletas o ilegibles se descartan en vez de impedir el cierre.
    """
    parsed_date = parse_override_date(date_value)
    if parsed_date is None:
        raise ValueError("La fecha del horario especial debe tener formato YYYY-MM-DD")

    try:
        open_norm, close_norm = _normalize_override_hours(open_time, close_time)
    except ValueError:
        if temporally_closed:
            return parsed_date.isoformat(), None, None
        raise
    return parsed_date.isoformat(), open_norm, close_norm
