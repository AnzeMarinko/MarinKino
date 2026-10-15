"""Private fitness journal, validation and descriptive statistics."""

import json
import math
import os
import re
import sqlite3
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from fitness_workouts import EQUIPMENT, GENERAL_ADVICE, STYLES, SUGGESTIONS

LOCAL_ZONE = ZoneInfo("Europe/Ljubljana")
DEFAULT_DATABASE = (
    Path(__file__).resolve().parents[1] / "data/fitness-development.sqlite3"
)
COLLECTIONS = ("measurements", "activities", "templates", "plan", "schedule")
KINDS = {
    "cycling": "Kolesarjenje",
    "running": "Tek",
    "cardio": "Kardio vaje",
    "strength": "Vaje za moč",
}
STARTERS = (
    (
        "cycling",
        "Kolesarjenje",
        30,
        "moderate",
        "Izberi svojo traso. V opis dodaj pot in želeno intenzivnost.",
    ),
    (
        "running",
        "Tek",
        20,
        "moderate",
        "V opis dodaj traso; tempo in trajanje prilagodi pripravljenosti.",
    ),
    (
        "cardio",
        "Kardio",
        20,
        "moderate",
        "Dopiši znane vaje, kroge, odmore in povezavo do prikaza tehnike.",
    ),
    (
        "strength",
        "Vaje za moč",
        30,
        "moderate",
        "Dopiši vaje za glavne mišične skupine, ponovitve, serije in odmore.",
    ),
)


class ValidationError(ValueError):
    """Invalid journal input, safe to display to the user."""


def now_local():
    return datetime.now(LOCAL_ZONE)


def number(value, label, minimum, maximum):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        result = float(str(value).replace(",", "."))
        if not math.isfinite(result) or not minimum <= result <= maximum:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError(
            f"{label}: vnesi število med {minimum} in {maximum}."
        ) from None
    return result


def text(value, label, maximum=5000):
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum:
        raise ValidationError(f"{label}: največ {maximum} znakov.")
    return value.strip()


def timestamp(value=None):
    if value is None or value == "":
        result = now_local()
    else:
        try:
            result = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            raise ValidationError("Datum in ura nista veljavna.") from None
        if result.tzinfo is None:
            result = result.replace(tzinfo=LOCAL_ZONE)
    if result > now_local() + timedelta(minutes=2):
        raise ValidationError(
            "Meritev ali izvedba ne more biti v prihodnosti."
        )
    return result.astimezone(timezone.utc).isoformat(timespec="seconds")


def calendar_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        raise ValidationError("Izberi veljaven datum.") from None


def duration_seconds(data):
    """Normalize an exact clock time, seconds, or legacy decimal minutes."""
    elapsed = text(data.get("elapsed_time"), "Čas", 20)
    if elapsed:
        match = re.fullmatch(r"(\d{1,5}):([0-5]\d)(?::([0-5]\d))?", elapsed)
        if not match:
            raise ValidationError("Čas: uporabi m:ss ali h:mm:ss, npr. 27:30.")
        first, second, third = match.groups()
        seconds = (
            int(first) * 3600 + int(second) * 60 + int(third)
            if third is not None
            else int(first) * 60 + int(second)
        )
    elif data.get("duration_seconds") not in (None, ""):
        seconds = number(data["duration_seconds"], "Čas v sekundah", 1, 86400)
    else:
        minutes = number(data.get("duration_min"), "Minute", 1 / 60, 1440)
        seconds = round(minutes * 60) if minutes is not None else None
    if seconds is not None:
        seconds = number(seconds, "Čas v sekundah", 1, 86400)
        if seconds != int(seconds):
            raise ValidationError("Čas v sekundah mora biti celo število.")
        return int(seconds)
    return None


def validate(collection, data):
    if not isinstance(data, dict):
        raise ValidationError("Pričakovan je zapis s podatki.")
    if collection == "measurements":
        result = {
            "timestamp": timestamp(data.get("timestamp")),
            "weight_kg": number(data.get("weight_kg"), "Teža", 1, 600),
            "waist_cm": number(data.get("waist_cm"), "Pas", 1, 400),
            "notes": text(data.get("notes"), "Opomba"),
        }
        for key in ("fasting", "morning", "after_bowel"):
            value = data.get(key)
            if value is not None and type(value) is not bool:
                raise ValidationError(
                    "Pogoji meritve: izberi da, ne ali ne vem."
                )
            result[key] = value
        return result
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValidationError("Izberi vrsto aktivnosti.")
    intensity = data.get("intensity") or None
    if intensity not in (None, "light", "moderate", "vigorous"):
        raise ValidationError("Izberi veljavno intenzivnost.")
    tutorial = text(data.get("tutorial_url"), "Povezava", 2000)
    try:
        parts = urlsplit(tutorial)
        valid_url = parts.scheme in ("https", "http") and parts.hostname
    except ValueError:
        valid_url = False
    if tutorial and (not valid_url or any(c.isspace() for c in tutorial)):
        raise ValidationError(
            "Povezava mora biti veljaven naslov https ali http."
        )
    style = data.get("training_style")
    equipment = data.get("equipment")
    if style == "":
        style = None
    if equipment == "":
        equipment = None
    if style is not None and (
        not isinstance(style, str) or style not in STYLES
    ):
        raise ValidationError("Izberi veljavno obliko vadbe.")
    if equipment is not None and (
        not isinstance(equipment, str) or equipment not in EQUIPMENT
    ):
        raise ValidationError("Izberi veljavno opremo.")
    seconds = duration_seconds(data)
    result = {
        "kind": kind,
        "title": text(data.get("title"), "Naslov", 160) or KINDS[kind],
        "duration_seconds": seconds,
        "duration_min": seconds / 60 if seconds is not None else None,
        "intensity": intensity,
        "distance_km": number(data.get("distance_km"), "Razdalja", 0, 2000),
        "description": text(data.get("description"), "Opis"),
        "tutorial_url": tutorial,
        "training_style": style,
        "equipment": equipment,
        "cadence_rpm": number(data.get("cadence_rpm"), "Kadenca", 20, 220)
        if kind == "cycling"
        else None,
        "advice": text(data.get("advice"), "Nasvet"),
    }
    if collection == "activities":
        result["timestamp"] = timestamp(data.get("timestamp"))
    elif collection == "plan":
        result["date"] = calendar_date(data.get("date"))
        status = data.get("status", "planned")
        if status not in ("planned", "skipped"):
            raise ValidationError("Izberi status načrtovano ali preskočeno.")
        result["status"] = status
    elif collection == "schedule":
        parity = data.get("parity")
        if parity not in ("odd", "even"):
            raise ValidationError("Izberi lihe ali sode tedne.")
        weekday = number(data.get("weekday"), "Dan v tednu", 0, 6)
        if weekday is None or weekday != int(weekday):
            raise ValidationError("Izberi dan v tednu.")
        result.update(parity=parity, weekday=int(weekday))
    return result


def validate_profile(data):
    if not isinstance(data, dict):
        raise ValidationError("Pričakovane so nastavitve.")
    result = {
        "height_cm": number(data.get("height_cm"), "Višina", 50, 260),
        "target_weight_kg": number(
            data.get("target_weight_kg"), "Ciljna teža", 1, 600
        ),
        "target_waist_cm": number(
            data.get("target_waist_cm"), "Ciljni obseg pasu", 1, 400
        ),
        "aerobic_goal": number(
            data.get("aerobic_goal"), "Tedenski aerobni cilj", 1, 3000
        )
        or 150,
        "strength_goal": number(
            data.get("strength_goal"), "Cilj dni za moč", 1, 7
        )
        or 2,
    }
    if result["strength_goal"] != int(result["strength_goal"]):
        raise ValidationError("Cilj dni za moč mora biti celo število.")
    return result


@contextmanager
def database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS fitness_profiles "
            "(user_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS fitness_entries "
            "(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, "
            "collection TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS fitness_owner "
            "ON fitness_entries(user_id, collection)"
        )
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def insert(connection, user_id, collection, payload):
    entry_id = uuid4().hex
    connection.execute(
        "INSERT INTO fitness_entries VALUES (?, ?, ?, ?)",
        (entry_id, user_id, collection, json.dumps(payload)),
    )
    return {**payload, "id": entry_id}


def get_entry(connection, user_id, collection, entry_id):
    row = connection.execute(
        "SELECT payload FROM fitness_entries "
        "WHERE user_id = ? AND collection = ? AND id = ?",
        (user_id, collection, entry_id),
    ).fetchone()
    return json.loads(row["payload"]) if row else None


def update(connection, user_id, collection, entry_id, payload):
    connection.execute(
        "UPDATE fitness_entries SET payload = ? "
        "WHERE user_id = ? AND collection = ? AND id = ?",
        (json.dumps(payload), user_id, collection, entry_id),
    )


def week_parity(day):
    """Use ISO week numbers, including week 53 and ISO year boundaries."""
    return "odd" if day.isocalendar().week % 2 else "even"


def schedule_matches(schedule, day):
    return (
        day.isoformat() >= schedule["starts_on"]
        and day.weekday() == schedule["weekday"]
        and week_parity(day) == schedule["parity"]
    )


def sync_schedule(connection, user_id, schedule_id, schedule=None):
    """Change pending occurrences; completed workouts retain their history."""
    cutoff = week_start(now_local().date()).isoformat()
    for row in connection.execute(
        "SELECT id, payload FROM fitness_entries "
        "WHERE user_id = ? AND collection = 'plan'",
        (user_id,),
    ).fetchall():
        plan = json.loads(row["payload"])
        if (
            plan.get("schedule_id") != schedule_id
            or plan.get("activity_id")
            or plan["date"] < cutoff
        ):
            continue
        if schedule and schedule_matches(
            schedule, date.fromisoformat(plan["scheduled_date"])
        ):
            # An individually edited or cancelled occurrence stays edited.
            if not plan.get("customized") and not plan.get("cancelled"):
                workout = validate("templates", schedule)
                update(
                    connection,
                    user_id,
                    "plan",
                    row["id"],
                    {
                        **plan,
                        **workout,
                    },
                )
        else:
            connection.execute(
                "DELETE FROM fitness_entries WHERE id = ? AND user_id = ?",
                (row["id"], user_id),
            )


def materialize_schedule(connection, user_id, start=None):
    """Create dated copies once, without duplicating edited occurrences."""
    schedules = [
        {**json.loads(row["payload"]), "id": row["id"]}
        for row in connection.execute(
            "SELECT id, payload FROM fitness_entries "
            "WHERE user_id = ? AND collection = 'schedule'",
            (user_id,),
        )
    ]
    if not schedules:
        return
    existing = set()
    for row in connection.execute(
        "SELECT payload FROM fitness_entries "
        "WHERE user_id = ? AND collection = 'plan'",
        (user_id,),
    ):
        plan = json.loads(row["payload"])
        if plan.get("schedule_id"):
            existing.add((plan["schedule_id"], plan["scheduled_date"]))
    today = now_local().date()
    days = {today + timedelta(days=offset) for offset in range(-6, 14)}
    if start is not None:
        days.update(start + timedelta(days=offset) for offset in range(14))
    for schedule in schedules:
        workout = validate("templates", schedule)
        for day in sorted(days):
            key = (schedule["id"], day.isoformat())
            if key not in existing and schedule_matches(schedule, day):
                insert(
                    connection,
                    user_id,
                    "plan",
                    {
                        **workout,
                        "date": day.isoformat(),
                        "status": "planned",
                        "schedule_id": schedule["id"],
                        "scheduled_date": day.isoformat(),
                    },
                )
                existing.add(key)


def plan_progress(state):
    """Count linked executions independently of the scheduled weekday."""
    today = now_local().date()
    today_iso = today.isoformat()
    first = week_start(today).isoformat()
    last = (week_start(today) + timedelta(days=6)).isoformat()
    activities = {row["id"]: row for row in state["activities"]}

    def completed(plan):
        actual = activities.get(plan.get("activity_id"))
        return bool(actual and actual.get("plan_id") == plan["id"])

    week = [row for row in state["plan"] if first <= row["date"] <= last]
    # Unlocking requires an actual execution this week, including a pending
    # workout moved from a different planned day or week.
    week_completed = [
        row
        for row in state["plan"]
        if completed(row)
        and first
        <= local_date(activities[row["activity_id"]]).isoformat()
        <= today_iso
    ]
    recent_start = (today - timedelta(days=6)).isoformat()
    recent = [
        row
        for row in state["plan"]
        if recent_start <= row["date"] <= today_iso
    ]
    due_start = (today - timedelta(days=2)).isoformat()
    due = [
        row
        for row in state["plan"]
        if due_start <= row["date"] <= today_iso
        and not completed(row)
        and row["status"] == "planned"
    ]
    return {
        "allowed": bool(week_completed),
        "week_start": first,
        "week_end": last,
        "iso_week": today.isocalendar().week,
        "parity": week_parity(today),
        "week_completed": len(week_completed),
        "week_total": len(week),
        "recent_start": recent_start,
        "recent_end": today_iso,
        "recent_completed": sum(completed(row) for row in recent),
        "recent_total": len(recent),
        "due": sorted(due, key=lambda row: row["date"]),
        "upcoming": sorted(
            [row for row in week if row["status"] == "planned"],
            key=lambda row: row["date"],
        ),
    }


def read_state(connection, user_id, plan_start=None):
    profile = connection.execute(
        "SELECT payload FROM fitness_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    if profile is None:
        defaults = {"height_cm": None, "aerobic_goal": 150, "strength_goal": 2}
        connection.execute(
            "INSERT INTO fitness_profiles VALUES (?, ?)",
            (user_id, json.dumps(defaults)),
        )
        for kind, title, minutes, intensity, description in STARTERS:
            insert(
                connection,
                user_id,
                "templates",
                validate(
                    "templates",
                    {
                        "kind": kind,
                        "title": title,
                        "duration_min": minutes,
                        "intensity": intensity,
                        "description": description,
                    },
                ),
            )
        profile = defaults
    else:
        profile = json.loads(profile["payload"])
    profile = {
        "target_weight_kg": None,
        "target_waist_cm": None,
        **profile,
    }
    materialize_schedule(connection, user_id, plan_start)
    state = {"profile": profile, **{key: [] for key in COLLECTIONS}}
    for row in connection.execute(
        "SELECT * FROM fitness_entries WHERE user_id = ?", (user_id,)
    ):
        payload = json.loads(row["payload"])
        if not payload.get("cancelled"):
            state[row["collection"]].append({**payload, "id": row["id"]})
    for key in COLLECTIONS:
        state[key].sort(
            key=lambda row: row.get(
                "timestamp", row.get("date", row.get("title", ""))
            )
        )
    state["weighing_status"] = weighing_status(state["measurements"])
    state["plan_progress"] = plan_progress(state)
    return enrich(state)


def local_date(entry):
    return (
        datetime.fromisoformat(entry["timestamp"])
        .astimezone(LOCAL_ZONE)
        .date()
    )


def date_months_before(day, months):
    month_index = day.year * 12 + day.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def weighing_status(measurements, today=None):
    weighings = [
        row for row in measurements if row.get("weight_kg") is not None
    ]
    if not weighings:
        return {
            "last_date": None,
            "days": None,
            "reminder": True,
            "orange": False,
            "red": False,
            "locked": False,
        }
    latest = max(weighings, key=lambda row: row["timestamp"])
    last_date = local_date(latest)
    today = today or now_local().date()
    days = max(0, (today - last_date).days)
    return {
        "last_date": last_date.isoformat(),
        "days": days,
        "reminder": days > 7,
        "orange": days > 14 and last_date >= date_months_before(today, 1),
        "red": last_date < date_months_before(today, 1),
        "locked": last_date < date_months_before(today, 2),
    }


def week_start(day):
    return day - timedelta(days=day.weekday())


def session_statistics(row):
    seconds = row.get("duration_seconds")
    if seconds is None and row.get("duration_min") is not None:
        seconds = round(row["duration_min"] * 60)
    distance = row.get("distance_km")
    timed = seconds is not None and seconds > 0 and distance is not None
    positive_distance = timed and distance > 0
    return {
        "duration_seconds": seconds,
        "average_speed_kmh": distance * 3600 / seconds
        if positive_distance
        else None,
        "pace_seconds_per_km": seconds / distance
        if positive_distance and row["kind"] == "running"
        else None,
    }


def activity_totals(entries):
    strength_days = set()
    recorded_strength_days = set()
    result = {
        "minutes": 0,
        "aerobic_equivalent": 0,
        "strength_days": 0,
        "sessions": len(entries),
        "missing_duration": 0,
        "unknown_intensity": 0,
        "unknown_strength_intensity": 0,
        "recorded_strength_days": 0,
        "by_kind": dict.fromkeys(KINDS, 0),
        "distance_by_kind": dict.fromkeys(KINDS, 0),
        "sessions_by_kind": dict.fromkeys(KINDS, 0),
        "seconds_by_kind": dict.fromkeys(KINDS, 0),
        "missing_distance_by_kind": dict.fromkeys(KINDS, 0),
        "timed_distance_by_kind": dict.fromkeys(KINDS, 0),
        "timed_seconds_by_kind": dict.fromkeys(KINDS, 0),
    }
    for row in entries:
        kind = row["kind"]
        result["sessions_by_kind"][kind] += 1
        seconds = session_statistics(row)["duration_seconds"]
        distance = row.get("distance_km")
        if seconds is not None:
            result["seconds_by_kind"][kind] += seconds
        if distance is None:
            result["missing_distance_by_kind"][kind] += 1
        else:
            result["distance_by_kind"][kind] += distance
            if distance > 0 and seconds is not None and seconds > 0:
                result["timed_distance_by_kind"][kind] += distance
                result["timed_seconds_by_kind"][kind] += seconds
        duration = row["duration_min"]
        if duration is None:
            result["missing_duration"] += 1
        else:
            result["minutes"] += duration
            result["by_kind"][row["kind"]] += duration
        if row["kind"] == "strength":
            recorded_strength_days.add(local_date(row))
            if row["intensity"] in ("moderate", "vigorous"):
                strength_days.add(local_date(row))
            elif row["intensity"] is None:
                result["unknown_strength_intensity"] += 1
        elif duration is not None:
            multiplier = {"moderate": 1, "vigorous": 2}.get(
                row["intensity"], 0
            )
            result["aerobic_equivalent"] += duration * multiplier
        if row["intensity"] is None and row["kind"] != "strength":
            result["unknown_intensity"] += 1
    result["strength_days"] = len(strength_days)
    result["recorded_strength_days"] = len(recorded_strength_days)
    return result


def enrich(state):
    height = state["profile"]["height_cm"]
    for row in state["measurements"]:
        row["bmi"] = (
            row["weight_kg"] / (height / 100) ** 2
            if height and row["weight_kg"] is not None
            else None
        )
        row["waist_height_ratio"] = (
            row["waist_cm"] / height
            if height and row["waist_cm"] is not None
            else None
        )
    today = now_local().date()
    for collection in ("activities", "templates", "plan"):
        for row in state[collection]:
            row.update(session_statistics(row))
            for key, default in (
                ("training_style", None),
                ("equipment", None),
                ("cadence_rpm", None),
                ("advice", ""),
            ):
                row.setdefault(key, default)
    state["suggestions"] = [
        {**validate("templates", suggestion), "id": suggestion["id"]}
        for suggestion in SUGGESTIONS
    ]
    state["general_advice"] = GENERAL_ADVICE
    state["styles"] = STYLES
    state["equipment"] = EQUIPMENT
    state["activity_totals"] = activity_totals(state["activities"])
    current_week = week_start(today)
    weekly = []
    for offset in range(11, -1, -1):
        start = current_week - timedelta(weeks=offset)
        rows = [
            row
            for row in state["activities"]
            if start <= local_date(row) < start + timedelta(days=7)
        ]
        weekly.append({"date": start.isoformat(), **activity_totals(rows)})
    state["weekly"] = weekly
    state["current_week"] = weekly[-1]
    state["today"] = today.isoformat()
    state["timezone"] = "Europe/Ljubljana"
    return state
