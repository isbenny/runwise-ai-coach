"""Local activity, lap and calendar-period queries."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import sqlite3
from zoneinfo import ZoneInfo
from collections import Counter


SHANGHAI = ZoneInfo("Asia/Shanghai")


def today_local() -> date:
    return datetime.now(SHANGHAI).date()


def recent_activities(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    rows = conn.execute(
        "SELECT id,provider,region,provider_activity_id,kind,type_key,local_date,"
        "started_at_local,distance_m,timer_s,moving_s,elapsed_s,pace_s_per_km,speed_m_per_s,avg_hr_bpm,lap_status,"
        "count_status FROM activity ORDER BY started_at_utc DESC,id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def laps_for_activity(conn: sqlite3.Connection, activity_id: int) -> dict:
    activity = conn.execute(
        "SELECT id,provider,region,provider_activity_id,local_date,kind,lap_status "
        "FROM activity WHERE id=?", (activity_id,),
    ).fetchone()
    if activity is None:
        raise ValueError("activity not found")
    laps = conn.execute(
        "SELECT lap_no,lap_type,distance_m,timer_s,moving_s,elapsed_s,avg_hr_bpm,"
        "max_hr_bpm,avg_power_w,avg_cadence_spm,source_kind,verified_at_utc "
        "FROM activity_lap WHERE activity_id=? ORDER BY lap_no", (activity_id,),
    ).fetchall()
    return {"activity": dict(activity), "laps": [dict(lap) for lap in laps]}


def period_stats(conn: sqlite3.Connection, start: date, end: date) -> dict:
    if start > end:
        raise ValueError("start must be on or before end")
    rows = conn.execute("SELECT * FROM activity WHERE count_status='counted' "
                        "AND kind IN ('running','track_running') AND local_date BETWEEN ? AND ?",
                        (start.isoformat(), end.isoformat())).fetchall()
    policies = {(r["activity_id"], r["metric"]): r["status"] for r in conn.execute("SELECT * FROM activity_metric_quality")}
    result = {"activity_count": len(rows), "running_days": len({r["local_date"] for r in rows}),
              "start": start.isoformat(), "end": end.isoformat(), "metric_counts": {}}
    values_by_metric = {}
    for metric in ("distance_m", "timer_s", "moving_s", "elapsed_s", "avg_hr_bpm"):
        values, counts = [], Counter()
        for row in rows:
            status = policies.get((row["id"], metric), "included" if row[metric] is not None else "missing")
            counts[status] += 1
            if status == "included" and row[metric] is not None:
                values.append(row[metric])
        result["metric_counts"][metric] = dict(counts)
        values_by_metric[metric] = values
        if metric != "avg_hr_bpm":
            result[metric] = sum(values) if values else 0 if not rows else None
    result["longest_distance_m"] = max(values_by_metric["distance_m"], default=None)
    result["avg_hr_usable_count"] = len(values_by_metric["avg_hr_bpm"])
    result["avg_hr_coverage"] = len(values_by_metric["avg_hr_bpm"]) / len(rows) if rows else None
    result["distance_km"] = (round(result["distance_m"] / 1000, 3)
                             if result["distance_m"] is not None else None)
    return result


def rolling_stats(conn: sqlite3.Connection, days: int, *, as_of: date | None = None) -> dict:
    if days not in {7, 28, 30}:
        raise ValueError("rolling days must be 7, 28 or 30")
    end = as_of or today_local()
    return period_stats(conn, end - timedelta(days=days - 1), end)


def complete_weeks(conn: sqlite3.Connection, count: int = 6,
                   *, as_of: date | None = None) -> list[dict]:
    if not 1 <= count <= 52:
        raise ValueError("count must be between 1 and 52")
    current = as_of or today_local()
    current_monday = current - timedelta(days=current.weekday())
    result = []
    for weeks_back in range(count, 0, -1):
        start = current_monday - timedelta(weeks=weeks_back)
        end = start + timedelta(days=6)
        result.append(period_stats(conn, start, end))
    return result


def sync_status(conn: sqlite3.Connection) -> dict:
    progress = conn.execute(
        "SELECT mode,range_start,range_end,next_offset,completed,last_attempt_at_utc,"
        "last_success_at_utc,last_error_type FROM sync_progress ORDER BY id DESC LIMIT 20"
    ).fetchall()
    batches = conn.execute(
        "SELECT kind,label,started_at_utc,ended_at_utc,status,records_seen,inserted,"
        "updated,linked,unchanged,held_for_review,failed "
        "FROM import_batch ORDER BY id DESC LIMIT 20"
    ).fetchall()
    counts = conn.execute(
        "SELECT count(*) AS activities,"
        "coalesce(sum(CASE WHEN provider='garmin' THEN 1 ELSE 0 END),0) AS garmin_activities,"
        "coalesce(sum(CASE WHEN provider='csv' THEN 1 ELSE 0 END),0) AS csv_only_activities,"
        "coalesce(sum(CASE WHEN count_status='hold_review' THEN 1 ELSE 0 END),0) AS held_for_review "
        "FROM activity"
    ).fetchone()
    return {"counts": dict(counts), "progress": [dict(x) for x in progress],
            "batches": [dict(x) for x in batches],
            "source_records": [dict(x) for x in conn.execute("SELECT status,count(*) AS count FROM source_record GROUP BY status")]}


def quality_report(conn: sqlite3.Connection, limit: int = 50) -> dict:
    counts = conn.execute(
        "SELECT code,severity,count(*) AS count FROM data_quality_issue WHERE status='open' "
        "GROUP BY code,severity ORDER BY count DESC,code"
    ).fetchall()
    issues = conn.execute(
        "SELECT activity_id,code,severity,note,created_at_utc FROM data_quality_issue "
        "WHERE status='open' ORDER BY id DESC LIMIT ?", (limit,),
    ).fetchall()
    lap_counts = conn.execute(
        "SELECT lap_status,count(*) AS count FROM activity GROUP BY lap_status"
    ).fetchall()
    return {"issue_counts": [dict(x) for x in counts],
            "recent_issues": [dict(x) for x in issues],
            "lap_status_counts": [dict(x) for x in lap_counts],
            "metric_eligibility": [dict(x) for x in conn.execute(
                "SELECT metric,status,reason,count(*) AS count FROM activity_metric_quality GROUP BY metric,status,reason")],
            "source_status": [dict(x) for x in conn.execute("SELECT status,count(*) AS count FROM source_record GROUP BY status")]}
