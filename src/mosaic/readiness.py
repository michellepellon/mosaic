"""Readiness scoring and daily performance brief computation."""
# ABOUTME: Computes a composite readiness score from HRV, RHR, sleep, SpO2,
# ABOUTME: and training load data. Powers the Daily Action Brief.

import duckdb


def _factor_score(current: float | None, baseline: float | None, *, invert: bool = False) -> float:
    """Score a single factor 0-100 based on deviation from baseline.

    At baseline = 75. 10%+ above = 100. 10%+ below = 50. 20%+ below = 25.
    If invert=True (for metrics where lower is better like RHR), the logic flips.
    """
    if current is None or baseline is None or baseline == 0:
        return 75.0  # neutral when data is missing

    if invert:
        # For RHR: being below baseline is good
        ratio = baseline / current
    else:
        ratio = current / baseline

    if ratio >= 1.1:
        return 100.0
    if ratio >= 1.0:
        # Linear interpolation from 75 to 100 as ratio goes 1.0 to 1.1
        return 75.0 + (ratio - 1.0) / 0.1 * 25.0
    if ratio >= 0.9:
        # Linear interpolation from 50 to 75 as ratio goes 0.9 to 1.0
        return 50.0 + (ratio - 0.9) / 0.1 * 25.0
    if ratio >= 0.8:
        # Linear interpolation from 25 to 50 as ratio goes 0.8 to 0.9
        return 25.0 + (ratio - 0.8) / 0.1 * 25.0
    return 25.0


def _target_score(current: float | None, target: float, floor: float) -> float:
    """Score a factor based on distance from a fixed target.

    At target = 100. At floor = 25. Linear interpolation between.
    """
    if current is None:
        return 75.0
    if current >= target:
        return 100.0
    if current <= floor:
        return 25.0
    return 25.0 + (current - floor) / (target - floor) * 75.0


def compute_readiness(conn: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Compute today's readiness score and performance brief.

    Returns a dict with: score, status, prescription, factors, alerts.
    """
    # Get last night's data and 30-day baselines
    hrv_row = conn.sql("""
        SELECT v, r30 FROM dashboard_hrv
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    hrv_current = hrv_row[0] if hrv_row else None
    hrv_baseline = hrv_row[1] if hrv_row else None

    rhr_row = conn.sql("""
        SELECT v FROM dashboard_rhr
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    rhr_current = rhr_row[0] if rhr_row else None
    rhr_baseline_row = conn.sql("""
        SELECT AVG(v) FROM (
            SELECT v FROM dashboard_rhr ORDER BY date DESC LIMIT 30
        )
    """).fetchone()
    rhr_baseline = rhr_baseline_row[0] if rhr_baseline_row else None

    sleep_row = conn.sql("""
        SELECT total, deep, rem FROM dashboard_sleep
        WHERE total > 0.5
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    sleep_total = sleep_row[0] if sleep_row else None
    sleep_deep = sleep_row[1] if sleep_row else None
    sleep_rem = sleep_row[2] if sleep_row else None
    sleep_quality = (sleep_deep or 0) + (sleep_rem or 0)

    sleep_quality_baseline_row = conn.sql("""
        SELECT AVG(deep + rem) FROM (
            SELECT deep, rem FROM dashboard_sleep
            WHERE total > 0.5
            ORDER BY date DESC LIMIT 30
        )
    """).fetchone()
    sleep_quality_baseline = sleep_quality_baseline_row[0] if sleep_quality_baseline_row else None

    spo2_row = conn.sql("""
        SELECT min FROM dashboard_spo2
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    spo2_min = spo2_row[0] if spo2_row else None

    exercise_row = conn.sql("""
        SELECT v FROM dashboard_exercise
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    exercise_current = exercise_row[0] if exercise_row else None
    exercise_baseline_row = conn.sql("""
        SELECT AVG(v) FROM (
            SELECT v FROM dashboard_exercise ORDER BY date DESC LIMIT 4
        )
    """).fetchone()
    exercise_baseline = exercise_baseline_row[0] if exercise_baseline_row else None

    # Compute factor scores
    f_hrv = _factor_score(hrv_current, hrv_baseline)
    f_rhr = _factor_score(rhr_current, rhr_baseline, invert=True)
    f_sleep_total = _target_score(sleep_total, target=7.5, floor=5.0)
    f_sleep_quality = _factor_score(sleep_quality, sleep_quality_baseline)
    f_spo2 = _target_score(spo2_min, target=90.0, floor=82.0)
    f_training = _factor_score(exercise_current, exercise_baseline, invert=True)

    # Weighted composite
    score = round(
        f_hrv * 0.30
        + f_rhr * 0.20
        + f_sleep_total * 0.20
        + f_sleep_quality * 0.15
        + f_spo2 * 0.10
        + f_training * 0.05,
        1,
    )

    # Status and prescription
    if score >= 85:
        status = "peak"
        prescription = (
            "High-intensity intervals, heavy strength, or long endurance. "
            "Your best training day."
        )
    elif score >= 70:
        status = "ready"
        prescription = "Zone 2 aerobic base, moderate strength. Solid training day."
    elif score >= 50:
        status = "moderate"
        prescription = "Light Zone 2, mobility work, yoga. Don't push today."
    else:
        status = "recover"
        prescription = "Walk only. Prioritize sleep tonight. Watch for illness."

    # Watch list alerts
    alerts: list[dict[str, str]] = []

    # HRV trending down 3+ days
    hrv_recent = conn.sql("""
        SELECT v FROM dashboard_hrv ORDER BY date DESC LIMIT 4
    """).fetchall()
    if len(hrv_recent) >= 4:
        vals = [r[0] for r in hrv_recent if r[0] is not None]
        if len(vals) >= 4 and all(vals[i] < vals[i + 1] for i in range(3)):
            alerts.append({
                "level": "warning",
                "message": "HRV trending down 3+ consecutive days",
            })

    # Deep sleep < 1hr for 3+ nights
    deep_recent = conn.sql("""
        SELECT deep FROM dashboard_sleep
        WHERE total > 0.5
        ORDER BY date DESC LIMIT 3
    """).fetchall()
    if len(deep_recent) >= 3:
        if all(r[0] is not None and r[0] < 1.0 for r in deep_recent):
            alerts.append({
                "level": "warning",
                "message": "Deep sleep under 1 hour for 3+ nights",
            })

    # SpO2 below 88% last night
    if spo2_min is not None and spo2_min < 88:
        alerts.append({
            "level": "critical",
            "message": f"SpO2 dropped to {spo2_min:.0f}% last night — consider a sleep study",
        })

    # RHR rising while training stable
    rhr_7d = conn.sql("""
        SELECT AVG(v) FROM (SELECT v FROM dashboard_rhr ORDER BY date DESC LIMIT 7)
    """).fetchone()
    rhr_prior_7d = conn.sql("""
        SELECT AVG(v) FROM (
            SELECT v FROM dashboard_rhr ORDER BY date DESC LIMIT 14 OFFSET 7
        )
    """).fetchone()
    if (
        rhr_7d and rhr_prior_7d and rhr_7d[0] and rhr_prior_7d[0]
        and rhr_7d[0] > rhr_prior_7d[0] * 1.05
    ):
        if exercise_current and exercise_baseline and exercise_current >= exercise_baseline * 0.9:
            alerts.append({
                "level": "warning",
                "message": (
                    "Resting HR rising while training volume is stable "
                    "— possible overreaching"
                ),
            })

    # No Zone 2 this week
    z2_row = conn.sql("""
        SELECT z2 FROM dashboard_hrzones ORDER BY date DESC LIMIT 1
    """).fetchone()
    if z2_row is None or (z2_row[0] is not None and z2_row[0] < 5):
        alerts.append({
            "level": "info",
            "message": "No significant Zone 2 training this week",
        })

    # Training load spike
    if (
        exercise_current and exercise_baseline
        and exercise_current > exercise_baseline * 1.5
    ):
        alerts.append({
            "level": "warning",
            "message": "Training load spike — this week is 50%+ above your 4-week average",
        })

    return {
        "score": score,
        "status": status,
        "prescription": prescription,
        "factors": {
            "hrv": {
                "score": round(f_hrv, 1),
                "current": hrv_current,
                "baseline": hrv_baseline,
            },
            "rhr": {
                "score": round(f_rhr, 1),
                "current": rhr_current,
                "baseline": rhr_baseline,
            },
            "sleep_total": {
                "score": round(f_sleep_total, 1),
                "current": sleep_total,
                "target": 7.5,
            },
            "sleep_quality": {
                "score": round(f_sleep_quality, 1),
                "current": sleep_quality,
                "baseline": sleep_quality_baseline,
            },
            "spo2": {
                "score": round(f_spo2, 1),
                "current": spo2_min,
                "target": 90.0,
            },
            "training_load": {
                "score": round(f_training, 1),
                "current": exercise_current,
                "baseline": exercise_baseline,
            },
        },
        "alerts": alerts,
    }
