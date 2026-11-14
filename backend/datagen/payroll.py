"""PayrollInput aggregation: one row per active employee per pay period.
Only approved source rows count (see docs/decisions.md)."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

import config
from datagen.ids import IdGenerator
from datagen.pay_items import _active
from datagen.time_entries import _working_days, effective_time_entries

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(x):
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def counted_time_entries(time_entries, force_unapproved=frozenset()):
    """(employee_id, work_date) -> entry that counts. Normally the approved
    effective entry. For (employee_id, pay_period_id) keys in force_unapproved,
    non-approved originals are also counted: this simulates the injected
    'unapproved time exported' defect."""
    counted = dict(effective_time_entries(time_entries))
    for e in time_entries:
        if (e["entry_type"] == "original" and e["approval_status"] != "approved"
                and (e["employee_id"], e["pay_period_id"]) in force_unapproved):
            counted.setdefault((e["employee_id"], e["work_date"]), e)
    return counted


def aggregate_payroll_inputs(employees, time_entries, allowances, deductions,
                             force_unapproved=frozenset()):
    counted = counted_time_entries(time_entries, force_unapproved)
    entries = defaultdict(list)
    for e in counted.values():
        entries[(e["employee_id"], e["pay_period_id"])].append(e)

    allow, ded = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for a in allowances:
        if a["approval_status"] == "approved":
            allow[(a["employee_id"], a["pay_period_id"])] += a["amount"]
    for d in deductions:
        if d["approval_status"] == "approved":
            ded[(d["employee_id"], d["pay_period_id"])] += d["amount"]

    rows = []
    for period in config.PAY_PERIODS:
        working = _working_days(period)
        month = period.start_date.month
        for emp in sorted(employees, key=lambda e: e["employee_id"]):
            if not _active(emp, period):
                continue
            eid = emp["employee_id"]
            key = (eid, period.pay_period_id)
            group = config.PAY_GROUP_BY_ID[emp["pay_group_id"]]
            rows_in = entries.get(key, [])
            unapproved = sum(1 for e in rows_in if e["approval_status"] != "approved")

            reg = ot = ZERO
            if emp["pay_type"] == "hourly":
                for e in rows_in:
                    h = e["hours_worked"]
                    r = min(h, group.standard_hours_per_day)
                    reg += r
                    ot += h - r
                base = money(reg * emp["hourly_rate"])
                overtime = money(ot * emp["hourly_rate"] * group.overtime_multiplier)
            else:
                last = emp["termination_date"] or period.end_date
                days = sum(1 for d in working if emp["hire_date"] <= d <= last)
                base = money(emp["monthly_salary"] * days / period.working_days)
                overtime = ZERO

            allowance_total = money(allow.get(key, ZERO))
            deduction_total = money(ded.get(key, ZERO))
            gross = base + overtime + allowance_total
            rows.append({
                "payroll_input_id": IdGenerator.payroll_input_id(eid, month),
                "employee_id": eid,
                "pay_period_id": period.pay_period_id,
                "pay_group_id": emp["pay_group_id"],
                "pay_type": emp["pay_type"],
                "regular_hours": reg,
                "overtime_hours": ot,
                "base_pay": base,
                "overtime_pay": overtime,
                "allowance_total": allowance_total,
                "deduction_total": deduction_total,
                "gross_pay": gross,
                "net_pay": gross - deduction_total,
                "unapproved_source_count": unapproved,
                "status": "draft",
                "aggregated_at": datetime.combine(period.end_date + timedelta(days=8),
                                                  time(9, 0)),
            })
    return rows