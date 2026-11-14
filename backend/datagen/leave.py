"""LeaveRecord generation (see docs/data_dictionary.md and docs/decisions.md)."""
from datetime import datetime, time, timedelta

import config
from datagen.time_entries import _decision, _working_days

PAID_TYPES = ("annual", "sick")
LENGTHS = {
    "annual": ((1, 0.35), (2, 0.25), (3, 0.20), (4, 0.10), (5, 0.10)),
    "sick": ((1, 0.60), (2, 0.30), (3, 0.10)),
    "unpaid": ((1, 0.30), (2, 0.30), (3, 0.20), (4, 0.10), (5, 0.10)),
}
MIN_GAP = 2  # working days kept free between two blocks, so a correction can add a day


def _try_add(rng, n, leave_type, blocks):
    """Places a block of working days inside 0..n-1 without touching other blocks.
    Skips silently after 20 failed attempts."""
    lengths = [x for x, _ in LENGTHS[leave_type]]
    weights = [w for _, w in LENGTHS[leave_type]]
    length = rng.choices(lengths, weights)[0]
    if n - length < 1:
        return
    for _ in range(20):
        start = rng.randrange(0, n - length)  # leaves room for a +1 day correction
        if all(not (start < s + l + MIN_GAP and s < start + length + MIN_GAP)
               for s, l, _ in blocks):
            blocks.append((start, length, leave_type))
            return


def _row(ids, emp, period, leave_type, elig, start, length, entry_type, related_id, d):
    return {
        "leave_id": ids.next("leave"),
        "employee_id": emp["employee_id"],
        "pay_period_id": period.pay_period_id,
        "leave_type": leave_type,
        "start_date": elig[start],
        "end_date": elig[start + length - 1],
        "days": length,
        "entry_type": entry_type,
        "related_leave_id": related_id,
        "submitted_at": d["submitted"],
        "approval_status": d["status"],
        "approved_by": d["by"],
        "approved_at": d["at"],
    }


def generate_leave_records(rng, ids, employees):
    rows = []
    eligible = sorted((e for e in employees
                       if e["pay_type"] == "salaried" and e["manager_id"] is not None),
                      key=lambda e: e["employee_id"])
    for period in config.PAY_PERIODS:
        working = _working_days(period)
        for emp in eligible:
            last_ok = emp["termination_date"] or config.PERIOD_END
            elig = [d for d in working if emp["hire_date"] <= d <= last_ok]
            n = len(elig)
            if n < 6:
                continue

            blocks = []  # (start index, length, leave_type)
            if rng.random() < config.UNPAID_LEAVE_RATE:
                _try_add(rng, n, "unpaid", blocks)
            if rng.random() < config.PAID_LEAVE_RATE:
                _try_add(rng, n, rng.choice(PAID_TYPES), blocks)

            for start, length, leave_type in sorted(blocks):
                submitted = (datetime.combine(elig[start], time(9, 0))
                             - timedelta(days=rng.randint(1, 10))
                             + timedelta(minutes=rng.randrange(480)))
                submitted = max(submitted, datetime.combine(emp["hire_date"], time(9, 0)))
                d = _decision(rng, submitted, emp["manager_id"])
                original = _row(ids, emp, period, leave_type, elig, start, length,
                                "original", None, d)
                rows.append(original)

                if d["status"] == "approved" and rng.random() < config.LEAVE_CORRECTION_RATE:
                    new_len = length + (1 if length == 1 or rng.random() < 0.5 else -1)
                    c_submitted = submitted + timedelta(hours=rng.randint(24, 120))
                    cd = _decision(rng, c_submitted, emp["manager_id"])
                    rows.append(_row(ids, emp, period, leave_type, elig, start, new_len,
                                     "correction", original["leave_id"], cd))
    return rows


def effective_leave_records(leaves):
    """original leave_id -> the record that counts: the approved correction if there
    is one, otherwise the approved original. Pending and rejected rows never count."""
    originals, corrections = {}, {}
    for r in leaves:
        if r["entry_type"] == "original":
            originals[r["leave_id"]] = r
        else:
            corrections[r["related_leave_id"]] = r
    result = {}
    for leave_id, original in originals.items():
        corr = corrections.get(leave_id)
        if corr and corr["approval_status"] == "approved":
            result[leave_id] = corr
        elif original["approval_status"] == "approved":
            result[leave_id] = original
    return result