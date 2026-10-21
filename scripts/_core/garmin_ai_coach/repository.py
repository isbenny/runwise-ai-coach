"""Idempotent activity and lap writes; no Garmin business writes."""

from __future__ import annotations

from datetime import datetime
import sqlite3

from .storage import utc_now


ACTIVITY_FIELDS = (
    "kind", "type_key", "started_at_raw", "started_at_utc", "started_at_local",
    "local_date", "timezone_basis", "distance_m", "timer_s", "moving_s",
    "elapsed_s", "pace_s_per_km", "avg_hr_bpm", "max_hr_bpm", "avg_power_w",
    "avg_cadence_spm",
    "speed_m_per_s",
)
LAP_FIELDS = (
    "lap_type", "distance_m", "timer_s", "moving_s", "elapsed_s",
    "avg_hr_bpm", "max_hr_bpm", "avg_power_w", "avg_cadence_spm",
)


def issue(conn: sqlite3.Connection, code: str, note: str, *, activity_id: int | None = None,
          source_id: int | None = None, severity: str = "warning") -> None:
    existing = conn.execute(
        "SELECT id FROM data_quality_issue WHERE activity_id IS ? AND source_id IS ? "
        "AND code=? AND note=? AND status='open'",
        (activity_id, source_id, code, note),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO data_quality_issue(activity_id,source_id,code,severity,note,created_at_utc) "
            "VALUES (?,?,?,?,?,?)",
            (activity_id, source_id, code, severity, note, utc_now()),
        )


def _match_candidates(conn: sqlite3.Connection, activity: dict, provider: str) -> list[int]:
    """Only match by type, precise UTC time, distance and timer; never title/date alone."""
    if not all(activity.get(k) is not None for k in ("started_at_utc", "distance_m", "timer_s")):
        return []
    try:
        wanted_time = datetime.fromisoformat(activity["started_at_utc"])
    except ValueError:
        return []
    rows = conn.execute(
        "SELECT id,started_at_utc,distance_m,timer_s FROM activity "
        "WHERE provider=? AND kind=? AND started_at_utc IS NOT NULL",
        (provider, activity["kind"]),
    )
    matches = []
    for row in rows:
        if row["distance_m"] is None or row["timer_s"] is None:
            continue
        delta = abs((wanted_time - datetime.fromisoformat(row["started_at_utc"])).total_seconds())
        distance_gap = abs(activity["distance_m"] - row["distance_m"])
        timer_gap = abs(activity["timer_s"] - row["timer_s"])
        if (delta <= 120
                and distance_gap <= max(50, 0.005 * max(activity["distance_m"], row["distance_m"]))
                and timer_gap <= max(30, 0.01 * max(activity["timer_s"], row["timer_s"]))):
            matches.append(row["id"])
    return matches


def _insert_activity(conn: sqlite3.Connection, activity: dict, *, count_status: str = "counted") -> int:
    now = utc_now()
    columns = ("provider", "region", "provider_activity_id") + ACTIVITY_FIELDS + (
        "count_status", "first_seen_at_utc", "updated_at_utc"
    )
    values = [activity.get(column) for column in columns[:-3]] + [count_status, now, now]
    placeholders = ",".join("?" for _ in columns)
    cursor = conn.execute(
        f"INSERT INTO activity({','.join(columns)}) VALUES ({placeholders})", values
    )
    return cursor.lastrowid


def _update_activity(conn: sqlite3.Connection, activity_id: int, activity: dict) -> bool:
    old = conn.execute("SELECT * FROM activity WHERE id=?", (activity_id,)).fetchone()
    changes = {}
    for key in ACTIVITY_FIELDS:
        new = activity.get(key)
        if new is None or new == "missing":
            continue
        if key == "kind" and new == "other" and old[key] in {"running", "track_running", "cycling"}:
            continue
        if old[key] != new:
            changes[key] = new
    if not changes:
        return False
    assignments = ",".join(f"{key}=?" for key in changes)
    conn.execute(
        f"UPDATE activity SET {assignments},revision=revision+1,updated_at_utc=? WHERE id=?",
        (*changes.values(), utc_now(), activity_id),
    )
    return True


def _source(conn: sqlite3.Connection, activity_id: int, kind: str, region: str,
            key: str, *, file_hash: str | None = None, line: int | None = None,
            label: str | None = None) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO activity_source(activity_id,source_kind,region,source_key,"
        "file_sha256,file_line,source_label,imported_at_utc) VALUES (?,?,?,?,?,?,?,?)",
        (activity_id, kind, region, key, file_hash, line, label, utc_now()),
    )
    row = conn.execute(
        "SELECT id FROM activity_source WHERE source_kind=? AND region=? AND source_key=?",
        (kind, region, key),
    ).fetchone()
    return row["id"]


def upsert_api_activity(conn: sqlite3.Connection, activity: dict,
                        issues: list[tuple[str, str]] = ()) -> tuple[int, str]:
    key = activity["provider_activity_id"]
    existing = conn.execute(
        "SELECT id FROM activity WHERE provider='garmin' AND region='garmin.cn' "
        "AND provider_activity_id=?", (key,)
    ).fetchone()
    if existing:
        activity_id = existing["id"]
        status = "updated" if _update_activity(conn, activity_id, activity) else "unchanged"
    else:
        matches = _match_candidates(conn, activity, "csv")
        if len(matches) == 1:
            activity_id = matches[0]
            conn.execute(
                "UPDATE activity SET provider='garmin',region='garmin.cn',"
                "provider_activity_id=?,updated_at_utc=?,revision=revision+1 WHERE id=?",
                (key, utc_now(), activity_id),
            )
            _update_activity(conn, activity_id, activity)
            status = "linked"
        else:
            activity_id = _insert_activity(conn, activity)
            status = "inserted"
            if len(matches) > 1:
                for candidate in matches:
                    conn.execute("UPDATE activity SET count_status='hold_review' WHERE id=?", (candidate,))
                    issue(conn, "ambiguous_csv_api_match", "Multiple CSV candidates match one Garmin activity",
                          activity_id=candidate)
    source_id = _source(conn, activity_id, "garmin", "garmin.cn", key)
    if any(code in {"negative_distance", "negative_timer", "duration_order"}
           for code, _ in issues):
        conn.execute("UPDATE activity SET count_status='hold_review' WHERE id=?", (activity_id,))
    for code, note in issues:
        issue(conn, code, note, activity_id=activity_id, source_id=source_id)
    from .quality import refresh_metric_quality
    refresh_metric_quality(conn, [activity_id])
    return activity_id, status


def upsert_csv_activity(conn: sqlite3.Connection, activity: dict, record_key: str,
                        file_hash: str, line: int, label: str,
                        issues: list[tuple[str, str]] = ()) -> tuple[int, str]:
    previous = conn.execute(
        "SELECT activity_id FROM activity_source WHERE source_kind='csv' AND region='local' "
        "AND source_key=?", (record_key,)
    ).fetchone()
    if previous:
        return previous["activity_id"], "unchanged"
    matches = _match_candidates(conn, activity, "garmin")
    if len(matches) == 1:
        activity_id = matches[0]
        status = "linked"
    else:
        activity_id = _insert_activity(conn, activity, count_status="hold_review" if len(matches) > 1 else "counted")
        status = "held_for_review" if len(matches) > 1 else "inserted"
        if len(matches) > 1:
            issue(conn, "ambiguous_csv_api_match", "CSV record matches multiple Garmin activities",
                  activity_id=activity_id)
    source_id = _source(conn, activity_id, "csv", "local", record_key,
                        file_hash=file_hash, line=line, label=label)
    if any(code in {"csv_negative_value", "csv_duration_order"} for code, _ in issues):
        conn.execute("UPDATE activity SET count_status='hold_review' WHERE id=?", (activity_id,))
    for code, note in issues:
        issue(conn, code, note, activity_id=activity_id, source_id=source_id)
    return activity_id, status


def upsert_laps(conn: sqlite3.Connection, activity_id: int, laps: list[dict],
                issues: list[tuple[str, str]] = ()) -> tuple[int, str, dict[str, int]]:
    change_counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    old_count = conn.execute(
        "SELECT count(*) FROM activity_lap WHERE activity_id=? AND source_kind='garmin_laps'",
        (activity_id,),
    ).fetchone()[0]
    if not laps:
        if old_count == 0:
            conn.execute("UPDATE activity SET lap_status='temporarily_unavailable' WHERE id=?", (activity_id,))
        issue(conn, "laps_unavailable", "No lap records returned", activity_id=activity_id)
        return 0, "temporarily_unavailable", change_counts
    for lap in laps:
        existing = conn.execute(
            "SELECT * FROM activity_lap WHERE activity_id=? AND lap_no=? AND source_kind='garmin_laps'",
            (activity_id, lap["lap_no"]),
        ).fetchone()
        if existing:
            changes = {k: lap.get(k) for k in LAP_FIELDS if lap.get(k) is not None and existing[k] != lap.get(k)}
            if changes:
                assignments = ",".join(f"{k}=?" for k in changes)
                conn.execute(f"UPDATE activity_lap SET {assignments},verified_at_utc=? WHERE id=?",
                             (*changes.values(), utc_now(), existing["id"]))
                change_counts["updated"] += 1
            else:
                change_counts["unchanged"] += 1
        else:
            columns = ("activity_id", "lap_no") + LAP_FIELDS + ("source_kind", "verified_at_utc")
            values = [activity_id, lap["lap_no"]] + [lap.get(k) for k in LAP_FIELDS] + ["garmin_laps", utc_now()]
            conn.execute(f"INSERT INTO activity_lap({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
            change_counts["inserted"] += 1
    if old_count and old_count != len(laps):
        issue(conn, "lap_count_changed", "Returned lap count changed; old laps retained for review",
              activity_id=activity_id)
    for code, note in issues:
        issue(conn, code, note, activity_id=activity_id)
    complete = all(lap.get("distance_m") is not None and lap.get("timer_s") is not None for lap in laps)
    status = "verified" if complete and not issues and (not old_count or old_count == len(laps)) else "partial"
    conn.execute("UPDATE activity SET lap_status=? WHERE id=?", (status, activity_id))
    return len(laps), status, change_counts
