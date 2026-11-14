"""TimeEntry generation (see docs/data_dictionary.md and docs/decisions.md section 6)."""
from datetime import datetime, time, timedelta
from decimal import Decimal

import config
from datagen.ids import IdGenerator

D = Decimal
OVERTIME_EXTRA = (D("1.00"), D("1.50"), D("2.00"), D("2.50"), D("3.00"))
SHORT_DAY_CHANGE = (D("-1.00"), D("-0.50"), D("-0.25"), D("0.00"),
                    D("0.00"), D("0.00"), D("0.00"), D("0.00"))
CORRECTION_DELTA = (D("-2.00"), D("-1.00"), D("-0.50"), D("0.50"), D("1.00"), D("2.00"))
MIN_HOURS, MAX_HOURS = D("1.00"), D("12.00")
QUARTER = D("0.25")
STATUSES = [s for s, _ in config.APPROVAL_SHARES]
STATUS_WEIGHTS = [w for _, w in config.APPROVAL_SHARES]


def _working_days(period):
    span = (period.end_date - period.start_date).days + 1
    days = [period.start_date + timedelta(days=i) for i in range(span)]
    return [d for d in days if d.weekday() < 5]


def _decision(rng, submitted, manager_id):
    """Approval fields for a new row, decided when it is created."""
    status = rng.choices(STATUSES, STATUS_WEIGHTS)[0]
    if status == "pending":
        return {"submitted": submitted, "status": status, "by": None, "at": None}
    return {"submitted": submitted, "status": status, "by": manager_id,
            "at": submitted + timedelta(hours=rng.randint(1, 72))}


def _plan_day(rng, emp, standard, period, work_date):
    if rng.random() < config.OVERTIME_DAY_RATE:
        hours = standard + rng.choice(OVERTIME_EXTRA)
    else:
        hours = standard + rng.choice(SHORT_DAY_CHANGE)
    outlier = rng.random() < config.DAILY_OUTLIER_RATE
    if outlier:
        hours = D(rng.randrange(57, 73)) * QUARTER  # 14.25 to 18.00
    late = rng.random() < config.LATE_SUBMISSION_RATE
    if late:
        submitted = (datetime.combine(period.submission_deadline, time(9, 0))
                     + timedelta(days=rng.randint(1, 4), minutes=rng.randrange(600)))
    else:
        submitted = (datetime.combine(work_date, time(18, 0))
                     + timedelta(minutes=rng.randrange(2 * 24 * 60)))

    day = {"work_date": work_date, "hours": hours, "outlier": outlier,
           "late": late, "corr": None, "dup": None,
           **_decision(rng, submitted, emp["manager_id"])}

    if (day["status"] == "approved" and not outlier and not late
            and rng.random() < config.CORRECTION_RATE):
        new = max(MIN_HOURS, min(MAX_HOURS, hours + rng.choice(CORRECTION_DELTA)))
        if new == hours:
            new = hours + D("0.50") if hours + D("0.50") <= MAX_HOURS else hours - D("0.50")
        c_submitted = submitted + timedelta(hours=rng.randint(6, 48))
        day["corr"] = {"hours": new, **_decision(rng, c_submitted, emp["manager_id"])}

    if not late and rng.random() < config.DUPLICATE_RATE:
        d_submitted = submitted + timedelta(minutes=rng.randint(1, 600))
        day["dup"] = _decision(rng, d_submitted, emp["manager_id"])
    return day


def _cap_hours(days, standard, cap):
    """Keeps the baseline under the pay group maximum: the biggest days are reset to
    standard hours until the period total (counting every correction) fits."""
    def effective(d):
        return d["corr"]["hours"] if d["corr"] else d["hours"]

    if sum(effective(d) for d in days) <= cap:
        return
    for d in sorted(days, key=effective, reverse=True):
        d["hours"], d["corr"], d["outlier"] = standard, None, False
        if sum(effective(x) for x in days) <= cap:
            return


def _row(entry_id, emp, period, work_date, hours, entry_type, related_id, d):
    return {
        "time_entry_id": entry_id,
        "employee_id": emp["employee_id"],
        "pay_period_id": period.pay_period_id,
        "work_date": work_date,
        "hours_worked": hours,
        "entry_type": entry_type,
        "related_entry_id": related_id,
        "submitted_at": d["submitted"],
        "approval_status": d["status"],
        "approved_by": d["by"],
        "approved_at": d["at"],
    }


def generate_time_entries(rng, employees):
    """Returns (time_entries, planted). planted lists the deliberate baseline
    validation cases (duplicates, outliers, late submissions) for ground truth."""
    entries, planted = [], []
    hourly = sorted((e for e in employees if e["pay_type"] == "hourly"),
                    key=lambda e: e["employee_id"])

    def plant(issue, record_id, rule):
        planted.append({"issue_type": issue, "table_name": "time_entries",
                        "record_id": record_id, "expected_rule": rule})

    for period in config.PAY_PERIODS:
        working = _working_days(period)
        for emp in hourly:
            group = config.PAY_GROUP_BY_ID[emp["pay_group_id"]]
            standard = group.standard_hours_per_day
            last_ok = emp["termination_date"] or config.PERIOD_END

            days = []
            for work_date in working:
                if work_date < emp["hire_date"] or work_date > last_ok:
                    continue
                if rng.random() < config.ABSENCE_RATE:
                    continue
                days.append(_plan_day(rng, emp, standard, period, work_date))
            _cap_hours(days, standard, group.max_hours_per_period)

            for d in days:
                wd = d["work_date"]
                original_id = IdGenerator.time_entry_id(emp["employee_id"], wd)
                entries.append(_row(original_id, emp, period, wd, d["hours"],
                                    "original", None, d))
                if d["outlier"]:
                    plant("daily_hours_outlier", original_id, "VR-005")
                if d["late"]:
                    plant("late_submission", original_id, "VR-010")
                if d["corr"]:
                    entries.append(_row(
                        IdGenerator.time_entry_id(emp["employee_id"], wd, "C1"),
                        emp, period, wd, d["corr"]["hours"], "correction",
                        original_id, d["corr"]))
                if d["dup"]:
                    dup_id = IdGenerator.time_entry_id(emp["employee_id"], wd, "D1")
                    entries.append(_row(dup_id, emp, period, wd, d["hours"],
                                        "duplicate_submission", original_id, d["dup"]))
                    plant("duplicate_hours", dup_id, "VR-003")
    return entries, planted


def effective_time_entries(time_entries):
    """(employee_id, work_date) -> the entry whose hours count: the approved
    correction if there is one, otherwise the approved original. Duplicates,
    pending and rejected rows never count."""
    originals, corrections = {}, {}
    for e in time_entries:
        key = (e["employee_id"], e["work_date"])
        if e["entry_type"] == "original":
            originals[key] = e
        elif e["entry_type"] == "correction":
            corrections[key] = e
    result = {}
    for key, original in originals.items():
        corr = corrections.get(key)
        if corr and corr["approval_status"] == "approved":
            result[key] = corr
        elif original["approval_status"] == "approved":
            result[key] = original
    return result
