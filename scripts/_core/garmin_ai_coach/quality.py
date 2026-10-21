"""Metric-specific eligibility. Source values remain unchanged."""

from __future__ import annotations

POLICY_VERSION = "m11-metric-policy-v1"
METRICS = ("distance_m", "timer_s", "moving_s", "elapsed_s", "pace_s_per_km",
           "avg_hr_bpm", "max_hr_bpm", "avg_power_w", "speed_m_per_s")


def refresh_metric_quality(conn, activity_ids=None):
    ids = set(activity_ids) if activity_ids is not None else None
    for row in conn.execute("SELECT * FROM activity").fetchall():
        if ids is not None and row["id"] not in ids:
            continue
        codes = {r[0] for r in conn.execute(
            "SELECT code FROM data_quality_issue WHERE activity_id=? AND status='open'",
            (row["id"],))}
        duration_conflict = any(row[a] is not None and row[b] is not None and row[a] > row[b] + 1
                                for a, b in (("timer_s", "elapsed_s"), ("moving_s", "elapsed_s")))
        identity_hold = any(code.startswith("ambiguous_") or "identity" in code for code in codes)
        # M1 held the whole row for duration_order. M1.1 keeps reliable distance eligible.
        if row["count_status"] == "hold_review" and codes and codes <= {"duration_order", "csv_duration_order", "hr_order"}:
            conn.execute("UPDATE activity SET count_status='counted' WHERE id=?", (row["id"],))
        elif row["count_status"] == "hold_review":
            identity_hold = True
        hr_conflict = (row["avg_hr_bpm"] is not None and row["max_hr_bpm"] is not None
                       and row["avg_hr_bpm"] > row["max_hr_bpm"])
        for metric in METRICS:
            value = row[metric]
            if identity_hold:
                status, reason = "pending", "activity_identity_or_reliability_hold"
            elif value is None:
                status, reason = "missing", "source_value_missing"
            elif value < 0:
                status, reason = "excluded", "negative_source_value"
            elif duration_conflict and metric in {"timer_s", "moving_s", "elapsed_s", "pace_s_per_km", "speed_m_per_s"}:
                status, reason = "pending", "duration_order_conflict"
            elif hr_conflict and metric in {"avg_hr_bpm", "max_hr_bpm"}:
                status, reason = "excluded", "average_hr_exceeds_maximum_hr"
            else:
                status, reason = "included", "source_field_eligible"
            conn.execute(
                "INSERT INTO activity_metric_quality(activity_id,metric,status,reason,policy_version) "
                "VALUES (?,?,?,?,?) ON CONFLICT(activity_id,metric) DO UPDATE SET "
                "status=excluded.status,reason=excluded.reason,policy_version=excluded.policy_version "
                "WHERE status<>excluded.status OR reason<>excluded.reason OR policy_version<>excluded.policy_version",
                (row["id"], metric, status, reason, POLICY_VERSION),
            )


def metric_eligible(conn, activity_id, metric):
    row = conn.execute("SELECT status FROM activity_metric_quality WHERE activity_id=? AND metric=?",
                       (activity_id, metric)).fetchone()
    return row is None or row[0] == "included"
