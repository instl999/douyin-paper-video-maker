"""AFP quota: a local ledger of paid calls, and pacing of the monthly budget (spec §8.6).

The plan's daily cap is half the monthly quota, so spending "up to the daily cap" empties the month in two
days. Instead, what is left of the month is spread evenly over the days left in the cycle.
"""
from __future__ import annotations

import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .config import get_settings
from .util import PvmError, data_dir, ensure_dir, now_iso

MODES = (  # (minimum remaining fraction, mode) — spec §8.6
    (0.30, "normal"),
    (0.10, "single-candidate"),
    (0.0, "approved-only"),
)


def ledger_path():
    return data_dir("cache") / "afp_ledger.jsonl"


def record(afp: int, *, kind: str, project: str | None = None, model: str | None = None,
           note: str | None = None) -> None:
    """Append one paid call to the ledger (append-only JSON lines survive crashes mid-run)."""
    path = ledger_path()
    ensure_dir(path.parent)
    entry = {"at": now_iso(), "afp": int(afp), "kind": kind, "project": project, "model": model}
    if note:
        entry["note"] = note
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def entries() -> list[dict]:
    path = ledger_path()
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn last line from a crash must not break budgeting
    return out


def project_spend(slug: str) -> dict:
    """AFP a project has used, from the ledger: total, and amount and calls per kind (image, voice, text)."""
    by_kind: dict[str, int] = {}
    calls: dict[str, int] = {}
    for e in entries():
        if e.get("project") == slug:
            kind = e.get("kind") or "other"
            by_kind[kind] = by_kind.get(kind, 0) + int(e.get("afp") or 0)
            calls[kind] = calls.get(kind, 0) + 1
    return {"total": sum(by_kind.values()), "by_kind": by_kind, "calls": calls}


def _day(entry: dict) -> date | None:
    try:
        return datetime.fromisoformat(entry["at"]).date()
    except (KeyError, TypeError, ValueError):
        return None


def used_between(start: date, end: date, items: list[dict] | None = None) -> int:
    total = 0
    for e in entries() if items is None else items:
        d = _day(e)
        if d is not None and start <= d <= end:
            total += int(e.get("afp") or 0)
    return total


def _add_months(d: date, months: int) -> date:
    years, month0 = divmod(d.month - 1 + months, 12)
    year = d.year + years
    return date(year, month0 + 1, min(d.day, monthrange(year, month0 + 1)[1]))


def plan_start(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise PvmError(f"PVM_PLAN_START must be the plan's purchase date, like 2026-10-07 (got '{raw}')") from None


def cycle_bounds(today: date, start: date | None = None) -> tuple[date, date]:
    """First and last day of the quota month that contains today.

    The Agent Plan's month starts on the day of purchase and its monthly quota resets on that day (docs, 2026-09-29),
    so with the purchase date the cycle runs from that day of the month to the day before it in the next month
    (days 29-31 clamp to shorter months). Without it, the calendar month.
    """
    if start is None:
        return today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1])
    months = (today.year - start.year) * 12 + today.month - start.month
    if _add_months(start, months) > today:
        months -= 1
    return _add_months(start, months), _add_months(start, months + 1) - timedelta(days=1)


def daily_allowance(monthly_budget: int, used_before_today: int, used_today: int, days_left: int,
                    daily_cap: int, override: int | None = None) -> int:
    """AFP that may still be spent today.

    Today's budget is fixed at the start of the day: what was left of the month, divided by the days left
    (today included). It never exceeds the plan's daily cap or what is left of the month.
    """
    remaining_at_start = max(0, monthly_budget - used_before_today)
    budget = override if override is not None else remaining_at_start // max(1, days_left)
    budget = min(budget, daily_cap, remaining_at_start)
    return max(0, budget - used_today)


@dataclass
class QuotaStatus:
    tier: str
    monthly_budget: int
    daily_cap: int
    used_cycle: int
    used_today: int
    days_left: int
    allowance_today: int
    cycle: tuple[date, date]
    cycle_known: bool  # False: PVM_PLAN_START is not set, so the calendar month stands in

    @property
    def remaining(self) -> int:
        return max(0, self.monthly_budget - self.used_cycle)

    @property
    def remaining_fraction(self) -> float:
        return self.remaining / self.monthly_budget if self.monthly_budget else 0.0

    @property
    def mode(self) -> str:
        for floor, mode in MODES:
            if self.remaining_fraction > floor:
                return mode
        return MODES[-1][1]


def status(today: date | None = None) -> QuotaStatus:
    s = get_settings()
    today = today or date.today()
    purchased = plan_start(s.plan_start)
    start, end = cycle_bounds(today, purchased)
    items = entries()
    used_cycle = used_between(start, end, items)
    used_today = used_between(today, today, items)
    days_left = (end - today).days + 1
    cap = s.tier_limits["daily"]
    return QuotaStatus(
        tier=s.plan_tier,
        monthly_budget=s.afp_monthly_budget,
        daily_cap=cap,
        used_cycle=used_cycle,
        used_today=used_today,
        days_left=days_left,
        allowance_today=daily_allowance(s.afp_monthly_budget, used_cycle - used_today, used_today, days_left,
                                        cap, s.afp_daily_budget),
        cycle=(start, end),
        cycle_known=purchased is not None,
    )
