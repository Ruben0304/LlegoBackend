"""Override diario de horario ("solo hoy") de una sucursal.

`setBranchDailyOverride` (app de negocios, BranchStatusChip) guarda
`schedule.temporaryStatus` con `date` = hoy. Antes el backend aplicaba
temporallyClosed/temporallyOpen sin mirar la fecha ni las horas: un "cerrado
hoy" cerraba la tienda para siempre y un "abierto hoy" la abría 24 h todos los
días. Estos tests fijan la regla nueva (services/branch_hours.py):
solo aplica el día de su fecha en hora de Cuba y respeta openTime/closeTime.

Decisión de producto posterior: "Abierto hoy" sin horas (temporallyOpen sin
openTime/closeTime) significa el horario normal, no abierto todo el día.
"""

import asyncio
import os
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import schema.branches.mutations as branch_mutations
import schema.branches.utils as branch_utils
from domain.models import BranchSchedule, DaySchedule, TemporaryStatus, TimeRange
from services.branch_hours import (
    normalize_daily_override_input,
    override_day_ranges,
    temporary_status_applies_on,
)
from services.orders_service import OrderService

HAVANA = ZoneInfo("America/Havana")
TODAY = date(2026, 10, 1)  # jueves
YESTERDAY = date(2026, 9, 30)
TOMORROW = date(2026, 10, 2)


def _at(day: date, hhmm: str) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=HAVANA)


def _schedule(open_="09:00", close="18:00", temporary_status=None) -> BranchSchedule:
    return BranchSchedule(
        days=[
            DaySchedule(day=d, isOpen=True, hours=[TimeRange(open=open_, close=close)])
            for d in range(7)
        ],
        temporaryStatus=temporary_status,
    )


def _override(**kwargs) -> TemporaryStatus:
    return TemporaryStatus(**kwargs)


def _open_now(schedule, when: datetime) -> bool:
    return OrderService._is_branch_open_now(schedule, when)


# ---------------------------------------------------------------------------
# Reglas puras (services/branch_hours.py)
# ---------------------------------------------------------------------------


def test_dated_override_applies_only_on_its_day():
    ts = _override(temporallyClosed=True, date=TODAY.isoformat())
    assert temporary_status_applies_on(ts, TODAY)
    assert not temporary_status_applies_on(ts, YESTERDAY)
    assert not temporary_status_applies_on(ts, TOMORROW)


def test_undated_legacy_override_applies_unless_excluded():
    ts = _override(temporallyOpen=True)
    assert temporary_status_applies_on(ts, TODAY)
    assert not temporary_status_applies_on(ts, TODAY, include_undated=False)


def test_unreadable_date_never_applies():
    ts = {"temporallyClosed": True, "date": "1/10/2026"}
    assert not temporary_status_applies_on(ts, TODAY)


def test_override_day_ranges():
    assert override_day_ranges(_override(temporallyClosed=True, openTime="10:00", closeTime="12:00")) == []
    assert override_day_ranges(_override(temporallyOpen=True, openTime="10:00", closeTime="12:00")) == [(600, 720)]
    # "Abierto hoy" sin horas no decide: manda el horario semanal.
    assert override_day_ranges(_override(temporallyOpen=True)) is None
    assert override_day_ranges(_override(openTime="20:00", closeTime="02:00")) == [(1200, 120)]
    assert override_day_ranges(_override(reason="sin flags")) is None


def test_normalize_daily_override_input():
    assert normalize_daily_override_input("2026-10-01", "9:00", "22:30") == (
        "2026-10-01",
        "09:00",
        "22:30",
    )
    assert normalize_daily_override_input("2026-10-01", None, "") == ("2026-10-01", None, None)
    for bad in [
        ("01/10/2026", None, None),
        ("2026-13-01", None, None),
        ("2026-10-01", "09:00", None),
        ("2026-10-01", "9h", "22:00"),
        ("2026-10-01", "10:00", "10:00"),
    ]:
        with pytest.raises(ValueError):
            normalize_daily_override_input(*bad)
    # Cerrar el día nunca falla por unas horas a medio escribir: se descartan.
    assert normalize_daily_override_input(
        "2026-10-01", "09:00", None, temporally_closed=True
    ) == ("2026-10-01", None, None)
    with pytest.raises(ValueError):
        normalize_daily_override_input("bad", None, None, temporally_closed=True)


# ---------------------------------------------------------------------------
# ¿Abierta ahora? (OrderService._is_branch_open_now)
# ---------------------------------------------------------------------------


def test_closed_today_closes_within_weekly_hours():
    schedule = _schedule(temporary_status=_override(temporallyClosed=True, date=TODAY.isoformat()))
    assert not _open_now(schedule, _at(TODAY, "12:00"))


def test_closed_yesterday_does_not_close_today():
    schedule = _schedule(temporary_status=_override(temporallyClosed=True, date=YESTERDAY.isoformat()))
    assert _open_now(schedule, _at(TODAY, "12:00"))
    assert not _open_now(schedule, _at(TODAY, "20:00"))  # fuera del horario semanal


def test_closed_today_also_cuts_last_nights_overnight_tail():
    schedule = _schedule(
        open_="22:00",
        close="02:00",
        temporary_status=_override(temporallyClosed=True, date=TODAY.isoformat()),
    )
    assert not _open_now(schedule, _at(TODAY, "01:00"))
    # Sin override, la cola nocturna de ayer sí cuenta.
    assert _open_now(_schedule(open_="22:00", close="02:00"), _at(TODAY, "01:00"))


def test_open_today_without_hours_follows_weekly_schedule():
    """El switch "Abierto hoy" de la app de negocios (BranchStatusChip) manda
    temporallyOpen=true sin horas al deshacer un "Cerrado hoy": la tienda
    vuelve a su horario normal, no queda abierta las 24 h."""
    schedule = _schedule(temporary_status=_override(temporallyOpen=True, date=TODAY.isoformat()))
    assert _open_now(schedule, _at(TODAY, "12:00"))
    assert not _open_now(schedule, _at(TODAY, "23:00"))
    assert not _open_now(schedule, _at(TODAY, "03:00"))


def test_open_yesterday_does_not_open_today_outside_hours():
    schedule = _schedule(temporary_status=_override(temporallyOpen=True, date=YESTERDAY.isoformat()))
    assert not _open_now(schedule, _at(TODAY, "23:00"))


def test_special_hours_today_replace_weekly_hours():
    schedule = _schedule(
        temporary_status=_override(
            temporallyOpen=True, date=TODAY.isoformat(), openTime="13:00", closeTime="23:00"
        )
    )
    assert not _open_now(schedule, _at(TODAY, "10:00"))  # semanal abierto, especial no
    assert _open_now(schedule, _at(TODAY, "22:00"))  # semanal cerrado, especial sí
    assert not _open_now(schedule, _at(TODAY, "23:00"))
    # Al día siguiente vuelve el horario semanal.
    assert _open_now(schedule, _at(TOMORROW, "10:00"))
    assert not _open_now(schedule, _at(TOMORROW, "22:00"))


def test_special_overnight_hours_yesterday_cover_early_morning():
    schedule = _schedule(
        temporary_status=_override(
            temporallyOpen=True, date=YESTERDAY.isoformat(), openTime="20:00", closeTime="02:00"
        )
    )
    assert _open_now(schedule, _at(TODAY, "01:30"))
    assert not _open_now(schedule, _at(TODAY, "02:30"))


def test_legacy_undated_override_still_applies():
    closed = _schedule(temporary_status=_override(temporallyClosed=True))
    assert not _open_now(closed, _at(TODAY, "12:00"))
    special = _schedule(temporary_status=_override(openTime="00:00", closeTime="24:00"))
    assert _open_now(special, _at(TODAY, "03:00"))


def test_legacy_undated_open_without_hours_follows_weekly_schedule():
    # Misma regla con o sin fecha (seed de la tienda demo: su horario semanal
    # ya es 00:00-23:59, así que sigue abierta).
    opened = _schedule(temporary_status=_override(temporallyOpen=True, reason="Demo store"))
    assert not _open_now(opened, _at(TODAY, "03:00"))
    assert _open_now(opened, _at(TODAY, "12:00"))


def test_raw_mongo_dict_schedule_is_supported():
    schedule = _schedule(
        temporary_status=_override(temporallyClosed=True, date=YESTERDAY.isoformat())
    ).model_dump()
    assert _open_now(schedule, _at(TODAY, "12:00"))
    schedule["temporaryStatus"]["date"] = TODAY.isoformat()
    assert not _open_now(schedule, _at(TODAY, "12:00"))


# ---------------------------------------------------------------------------
# Pedidos programados (OrderService._is_branch_open_at)
# ---------------------------------------------------------------------------


def test_scheduled_order_respects_override_of_its_day_only():
    schedule = _schedule(temporary_status=_override(temporallyClosed=True, date=TODAY.isoformat()))
    assert not OrderService._is_branch_open_at(schedule, _at(TODAY, "15:00"))
    assert OrderService._is_branch_open_at(schedule, _at(TOMORROW, "15:00"))


def test_scheduled_order_respects_special_hours():
    schedule = _schedule(
        temporary_status=_override(
            temporallyOpen=True, date=TODAY.isoformat(), openTime="13:00", closeTime="23:00"
        )
    )
    assert not OrderService._is_branch_open_at(schedule, _at(TODAY, "10:00"))
    assert OrderService._is_branch_open_at(schedule, _at(TODAY, "22:00"))


def test_scheduled_order_with_open_today_without_hours_uses_weekly_schedule():
    schedule = _schedule(temporary_status=_override(temporallyOpen=True, date=TODAY.isoformat()))
    assert OrderService._is_branch_open_at(schedule, _at(TODAY, "15:00"))
    assert not OrderService._is_branch_open_at(schedule, _at(TODAY, "22:00"))
    msg = OrderService._format_schedule_for_day(schedule, TODAY.weekday(), local_date=TODAY)
    assert msg == "09:00-18:00"


def test_scheduled_order_ignores_legacy_undated_override_as_before():
    schedule = _schedule(temporary_status=_override(temporallyClosed=True))
    assert OrderService._is_branch_open_at(schedule, _at(TOMORROW, "15:00"))


def test_closed_message_shows_special_hours_of_the_day():
    schedule = _schedule(
        temporary_status=_override(
            temporallyOpen=True, date=TODAY.isoformat(), openTime="13:00", closeTime="23:00"
        )
    )
    msg = OrderService._format_schedule_for_day(schedule, TODAY.weekday(), local_date=TODAY)
    assert msg == "13:00-23:00 (horario especial del día)"
    assert OrderService._format_schedule_for_day(schedule, TOMORROW.weekday(), local_date=TOMORROW) == "09:00-18:00"


# ---------------------------------------------------------------------------
# Lo que se expone a los clientes (schema/branches/utils.schedule_to_type)
# ---------------------------------------------------------------------------


@pytest.fixture
def havana_today(monkeypatch):
    monkeypatch.setattr(branch_utils, "branch_local_now", lambda: _at(TODAY, "12:00"))


def test_exposes_todays_override(havana_today):
    ts = _override(temporallyClosed=True, date=TODAY.isoformat(), reason="Inventario")
    result = branch_utils.schedule_to_type(_schedule(temporary_status=ts))
    assert result.temporaryStatus is not None
    assert result.temporaryStatus.temporallyClosed is True
    assert result.temporaryStatus.date == TODAY.isoformat()


def test_hides_stale_or_future_dated_override(havana_today):
    for other_day in (YESTERDAY, TOMORROW):
        ts = _override(temporallyClosed=True, date=other_day.isoformat())
        assert branch_utils.schedule_to_type(_schedule(temporary_status=ts)).temporaryStatus is None


def test_still_exposes_legacy_undated_override(havana_today):
    ts = _override(temporallyClosed=True, reason="Inventario")
    result = branch_utils.schedule_to_type(_schedule(temporary_status=ts).model_dump())
    assert result.temporaryStatus is not None
    assert result.temporaryStatus.temporallyClosed is True


@pytest.mark.parametrize("as_dict", [False, True])
def test_open_without_hours_is_exposed_as_not_open(havana_today, as_dict):
    """iOS/Android pintan "Abierto" con temporallyOpen sin mirar horas; como sin
    horas ya no decide nada, se expone false y las apps usan el horario semanal."""
    for ts in (
        _override(temporallyOpen=True, date=TODAY.isoformat(), reason="Abierto hoy"),
        _override(temporallyOpen=True, reason="Demo store - always open"),
    ):
        schedule = _schedule(temporary_status=ts)
        result = branch_utils.schedule_to_type(schedule.model_dump() if as_dict else schedule)
        assert result.temporaryStatus is not None
        assert result.temporaryStatus.temporallyOpen is False
        assert result.temporaryStatus.reason == ts.reason


def test_open_with_special_hours_is_still_exposed_as_open(havana_today):
    ts = _override(temporallyOpen=True, date=TODAY.isoformat(), openTime="13:00", closeTime="23:00")
    result = branch_utils.schedule_to_type(_schedule(temporary_status=ts))
    assert result.temporaryStatus.temporallyOpen is True
    assert result.temporaryStatus.openTime == "13:00"


# ---------------------------------------------------------------------------
# setBranchDailyOverride valida y normaliza la entrada
# ---------------------------------------------------------------------------


def _patch_mutation(monkeypatch, branch):
    def _auth(jwt, info):
        info.context["user_id"] = "user-1"

    monkeypatch.setattr(branch_mutations, "apply_optional_jwt", _auth)
    monkeypatch.setattr(
        branch_mutations.access_checker, "require_branch_access", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(branch_mutations.branches_repo, "get_by_id", AsyncMock(return_value=branch))
    update = AsyncMock(return_value=None)
    monkeypatch.setattr(branch_mutations.branches_repo, "update", update)
    return update


def test_set_daily_override_rejects_bad_date_before_writing(monkeypatch):
    update = _patch_mutation(monkeypatch, SimpleNamespace(schedule=_schedule()))
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        asyncio.run(
            branch_mutations.BranchMutation().set_branch_daily_override(
                info=SimpleNamespace(context={}),
                branch_id="b1",
                date="1/10/2026",
                temporally_closed=True,
            )
        )
    update.assert_not_awaited()


def test_set_daily_override_stores_normalized_hours(monkeypatch):
    update = _patch_mutation(monkeypatch, SimpleNamespace(schedule=_schedule()))
    # update devuelve None → la mutación lanza "Error al actualizar", pero ya
    # podemos inspeccionar lo que intentó guardar.
    with pytest.raises(Exception, match="Error al actualizar"):
        asyncio.run(
            branch_mutations.BranchMutation().set_branch_daily_override(
                info=SimpleNamespace(context={}),
                branch_id="b1",
                date="2026-10-01",
                temporally_open=True,
                open_time="9:00",
                close_time="22:00",
            )
        )
    saved = update.await_args.args[1]["schedule"]["temporaryStatus"]
    assert saved["date"] == "2026-10-01"
    assert saved["openTime"] == "09:00"
    assert saved["closeTime"] == "22:00"
    assert saved["temporallyOpen"] is True
