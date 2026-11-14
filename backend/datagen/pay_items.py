"""Allowance and Deduction generation (see docs/data_dictionary.md and docs/decisions.md)."""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

import config
from datagen.leave import effective_leave_records
from datagen.time_entries import _decision, effective_time_entries

CENT = Decimal("0.01")
D = Decimal
CORPORATE = config.PAY_GROUPS[0].pay_group_id
OPERATIONS = config.PAY_GROUPS[1].pay_group_id


def _money(x):
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _active(emp, period):
    return (emp["hire_date"] <= period.end_date
            and (emp["termination_date"] is None
                 or emp["termination_date"] >= period.start_date))


def _created_at(rng, period):
    return (datetime.combine(period.end_date + timedelta(days=1), time(9, 0))
            + timedelta(minutes=rng.randrange(2 * 24 * 60)))


def _auto_approved(rng, created, approver_id):
    return {"submitted": created, "status": "approved", "by": approver_id,
            "at": created + timedelta(hours=rng.randint(1, 72))}


def _hr_ids(employees):
    return sorted(e["employee_id"] for e in employees if e["role"] == "hr_partner")


def generate_allowances(rng, ids, employees, time_entries):
    effective = effective_time_entries(time_entries)
    days = Counter((e["employee_id"], e["pay_period_id"]) for e in effective.values())
    hr_ids = _hr_ids(employees)

    rows = []
    for period in config.PAY_PERIODS:
        for emp in sorted(employees, key=lambda e: e["employee_id"]):
            if not _active(emp, period):
                continue
            worked = days[(emp["employee_id"], period.pay_period_id)]
            wanted = [("transport", 1)]
            if emp["pay_type"] == "hourly":
                if worked:
                    wanted.append(("meal", worked))
                    if emp["pay_group_id"] == OPERATIONS:
                        wanted.append(("shift", worked))
            elif emp["pay_group_id"] == CORPORATE:
                wanted.append(("remote_work", 1))

            for a_type, units in wanted:
                created = _created_at(rng, period)
                approver = emp["manager_id"] or rng.choice(hr_ids)  # group heads have no manager
                d = _decision(rng, created, approver)
                rate = config.ALLOWANCE_RATES[a_type]
                rows.append({
                    "allowance_id": ids.next("allowance"),
                    "employee_id": emp["employee_id"],
                    "pay_period_id": period.pay_period_id,
                    "allowance_type": a_type,
                    "units": units,
                    "unit_amount": rate,
                    "amount": _money(rate * units),
                    "entry_type": "original",
                    "related_allowance_id": None,
                    "created_at": created,
                    "approval_status": d["status"],
                    "approved_by": d["by"],
                    "approved_at": d["at"],
                })
    return rows


def generate_deductions(rng, ids, employees, leaves):
    ordered = sorted(employees, key=lambda e: e["employee_id"])
    hr_ids = _hr_ids(employees)

    k = round(len(ordered) * config.LOAN_SHARE)
    loans = {e["employee_id"]: rng.choice(config.LOAN_INSTALLMENTS)
             for e in rng.sample(ordered, k)}

    unpaid = defaultdict(list)  # (employee_id, pay_period_id) -> effective unpaid leave
    for r in effective_leave_records(leaves).values():
        if r["leave_type"] == "unpaid":
            unpaid[(r["employee_id"], r["pay_period_id"])].append(r)

    rows = []
    for period in config.PAY_PERIODS:
        for emp in ordered:
            if not _active(emp, period):
                continue
            eid = emp["employee_id"]
            items = []  # (type, leave_id, units, unit_amount, always_approved)
            if emp["pay_type"] == "salaried":
                working_days = [
                    period.start_date + timedelta(days=i)
                    for i in range((period.end_date - period.start_date).days + 1)
                    if (period.start_date + timedelta(days=i)).weekday() < 5
                ]

                last = emp["termination_date"] or period.end_date
                active_days = sum(
                    1 for day in working_days
                    if emp["hire_date"] <= day <= last
                )

                prorated_salary = (
                    emp["monthly_salary"] * active_days / period.working_days
                )

                items.append((
                    "provident_fund", None, D("1.00"),
                    _money(prorated_salary * config.PROVIDENT_FUND_RATE), True
                ))
            items.append(("professional_tax", None, D("1.00"), config.PROFESSIONAL_TAX, True))
            if eid in loans:
                items.append(("loan_recovery", None, D("1.00"), D(loans[eid]).quantize(CENT), False))
            for r in sorted(unpaid.get((eid, period.pay_period_id), []),
                            key=lambda r: r["leave_id"]):
                daily = _money(emp["monthly_salary"] / period.working_days)
                items.append(("unpaid_leave", r["leave_id"], D(r["days"]).quantize(CENT), daily, True))

            for d_type, leave_id, units, unit_amount, auto in items:
                created = _created_at(rng, period)
                approver = rng.choice(hr_ids)
                d = (_auto_approved(rng, created, approver) if auto
                     else _decision(rng, created, approver))
                rows.append({
                    "deduction_id": ids.next("deduction"),
                    "employee_id": eid,
                    "pay_period_id": period.pay_period_id,
                    "deduction_type": d_type,
                    "leave_id": leave_id,
                    "units": units,
                    "unit_amount": unit_amount,
                    "amount": _money(units * unit_amount),
                    "entry_type": "original",
                    "related_deduction_id": None,
                    "created_at": created,
                    "approval_status": d["status"],
                    "approved_by": d["by"],
                    "approved_at": d["at"],
                })
    return rows