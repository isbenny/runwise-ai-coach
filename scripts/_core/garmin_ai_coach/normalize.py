"""Whitelist Garmin summaries and laps into explicit SI units."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def number(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def first_number(record: dict, *names: str) -> float | None:
    for name in names:
        value = number(record.get(name))
        if value is not None:
            return value
    return None


def parse_time(value: object, default_zone: ZoneInfo | timezone) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_zone)
    return parsed


def normalize_type(raw: object) -> tuple[str, str | None]:
    if isinstance(raw, dict):
        key = raw.get("typeKey")
    else:
        key = raw
    key = str(key).strip().lower().replace(" ", "_") if key is not None else None
    if key in {"running", "treadmill_running", "trail_running", "virtual_run", "indoor_running"}:
        return "running", key
    if key in {"track_running", "track_run"}:
        return "track_running", key
    if key and ("cycling" in key or key == "biking"):
        return "cycling", key
    return "other", key


def normalize_api_activity(record: dict) -> tuple[dict, list[tuple[str, str]]]:
    if not isinstance(record, dict):
        raise ValueError("activity summary is not an object")
    activity_id = record.get("activityId")
    if activity_id is None or not str(activity_id).isdigit() or int(activity_id) <= 0:
        raise ValueError("activity summary has no valid Garmin ID")
    kind, type_key = normalize_type(record.get("activityType"))
    raw_time = record.get("startTimeGMT") or record.get("startTimeLocal")
    gmt = parse_time(record.get("startTimeGMT"), timezone.utc)
    local_source = parse_time(record.get("startTimeLocal"), SHANGHAI)
    timestamp = gmt or local_source
    issues: list[tuple[str, str]] = []
    if timestamp is None:
        issues.append(("missing_start_time", "No parseable activity start time"))
    utc = timestamp.astimezone(timezone.utc) if timestamp else None
    local = timestamp.astimezone(SHANGHAI) if timestamp else None
    distance = first_number(record, "distance")
    timer = first_number(record, "duration")
    moving = first_number(record, "movingDuration")
    elapsed = first_number(record, "elapsedDuration")
    avg_hr = first_number(record, "averageHR")
    max_hr = first_number(record, "maxHR")
    if distance is not None and distance < 0:
        issues.append(("negative_distance", "Negative distance retained for review"))
    if timer is not None and timer < 0:
        issues.append(("negative_timer", "Negative timer duration retained for review"))
    if avg_hr is not None and max_hr is not None and avg_hr > max_hr:
        issues.append(("hr_order", "Average HR exceeds maximum HR"))
    if timer is not None and elapsed is not None and timer > elapsed + 1:
        issues.append(("duration_order", "Timer duration exceeds elapsed duration"))
    if moving is not None and elapsed is not None and moving > elapsed + 1:
        issues.append(("duration_order", "Moving duration exceeds elapsed duration"))
    pace = 1000 * timer / distance if distance and distance > 0 and timer is not None and timer >= 0 and kind in {"running", "track_running"} else None
    return {
        "provider": "garmin",
        "region": "garmin.cn",
        "provider_activity_id": str(activity_id),
        "kind": kind,
        "type_key": type_key,
        "started_at_raw": str(raw_time) if raw_time is not None else None,
        "started_at_utc": utc.isoformat() if utc else None,
        "started_at_local": local.isoformat() if local else None,
        "local_date": local.date().isoformat() if local else None,
        "timezone_basis": "garmin_utc" if gmt else "assumed_Asia/Shanghai" if local_source else "missing",
        "distance_m": distance,
        "timer_s": timer,
        "moving_s": moving,
        "elapsed_s": elapsed,
        "pace_s_per_km": pace,
        "avg_hr_bpm": avg_hr,
        "max_hr_bpm": max_hr,
        "avg_power_w": first_number(record, "averagePower", "avgPower"),
        "avg_cadence_spm": first_number(record, "averageRunningCadenceInStepsPerMinute"),
    }, issues


def normalize_api_laps(response: object) -> tuple[list[dict], list[tuple[str, str]]]:
    if isinstance(response, dict):
        raw_laps = response.get("lapDTOs")
    elif isinstance(response, list):
        raw_laps = response
    else:
        raw_laps = None
    if raw_laps is None:
        raise ValueError("lap response has no lapDTOs")
    if not isinstance(raw_laps, list):
        raise ValueError("lapDTOs is not a list")
    laps: list[dict] = []
    issues: list[tuple[str, str]] = []
    for position, raw in enumerate(raw_laps, 1):
        if not isinstance(raw, dict):
            issues.append(("invalid_lap", f"Lap {position} is not an object"))
            continue
        raw_type = raw.get("intensityType") or raw.get("lapType") or raw.get("type")
        if isinstance(raw_type, dict):
            raw_type = raw_type.get("typeKey")
        distance = first_number(raw, "distance")
        timer = first_number(raw, "duration")
        if distance is None or timer is None:
            issues.append(("incomplete_lap", f"Lap {position} lacks distance or timer duration"))
        if distance is not None and distance < 0 or timer is not None and timer < 0:
            issues.append(("negative_lap_value", f"Lap {position} has a negative value"))
        laps.append({
            "lap_no": position,
            "lap_type": str(raw_type).lower() if raw_type is not None else None,
            "distance_m": distance,
            "timer_s": timer,
            "moving_s": first_number(raw, "movingDuration"),
            "elapsed_s": first_number(raw, "elapsedDuration"),
            "avg_hr_bpm": first_number(raw, "averageHR"),
            "max_hr_bpm": first_number(raw, "maxHR"),
            "avg_power_w": first_number(raw, "averagePower"),
            "avg_cadence_spm": first_number(raw, "averageRunningCadenceInStepsPerMinute"),
            "source_kind": "garmin_laps",
        })
    return laps, issues
