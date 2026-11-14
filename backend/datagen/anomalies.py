"""Labelled edge cases injected into the valid baseline (see docs/decisions.md).
Source-level cases are injected before aggregation, input-level cases after.
Each case gets its own employee-period, so one label explains one defect."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

import config
from datagen.ids import IdGenerator
from datagen.time_entries import effective_time_entries

D = Decimal
HOURS_FILL = D("12.00")


def _truth(issue, table, record_id, rule, note):
    return {"issue_type": issue, "table_name": table, "record_id": record_id,
            "expected_rule": rule, "injected": True, "note": note}


def _pin(employee_id, period_id):
    return IdGenerator.payroll_input_id(employee_id, int(period_id[-2:]))


def _pick(rng, candidates, n, used, key_of):
    """Random choice of up to n candidates whose (employee, period) key is unused."""
    chosen = []
    for c in rng.sample(candidates, len(candidates)):
        k = key_of(c)
        if k in used:
            continue
        used.add(k)
        chosen.append(c)
        if len(chosen) == n:
            break
    return chosen


def _duplicate(rng, row, id_field, related_field, new_id):
    dup = dict(row)
    dup[id_field] = new_id
    dup["entry_type"] = "duplicate_submission"
    dup[related_field] = row[id_field]
    dup["created_at"] = row["created_at"] + timedelta(hours=rng.randint(1, 5))
    dup["approved_at"] = dup["created_at"] + timedelta(hours=rng.randint(1, 72))
    return dup


def inject_source_anomalies(rng, ids, scale, employees, time_entries, allowances, deductions):
    """Edits and appends to the lists in place.
    Returns (ground_truth, force_unapproved, used_keys)."""
    n = scale.anomalies_per_type
    truth, used = [], set()
    emp_by_id = {e["employee_id"]: e for e in employees}
    max_hours = lambda eid: config.PAY_GROUP_BY_ID[emp_by_id[eid]["pay_group_id"]].max_hours_per_period

    by_key = defaultdict(list)  # (employee, period) -> effective entries
    for e in effective_time_entries(time_entries).values():
        by_key[(e["employee_id"], e["pay_period_id"])].append(e)

    # 1. hours exceed the period maximum -> VR-004 on the payroll input
    over = sorted(k for k, rows in by_key.items()
                  if len(rows) * HOURS_FILL > max_hours(k[0])
                  and all(r["hours_worked"] <= HOURS_FILL for r in rows))
    for k in _pick(rng, over, n, used, lambda k: k):
        for r in by_key[k]:
            r["hours_worked"] = HOURS_FILL
        truth.append(_truth("hours_exceed_period_max", "payroll_inputs", _pin(*k), "VR-004",
                            "effective approved entries raised to 12h; total above group maximum"))

    # 2. unapproved time exported -> VR-007, and totals no longer reconcile -> VR-009
    pending = defaultdict(D)
    for e in time_entries:
        if e["entry_type"] == "original" and e["approval_status"] != "approved":
            pending[(e["employee_id"], e["pay_period_id"])] += e["hours_worked"]
    fits = sorted(k for k, h in pending.items()
                  if sum((r["hours_worked"] for r in by_key.get(k, [])), D("0")) + h <= max_hours(k[0]))
    forced = set()
    for k in _pick(rng, fits, n, used, lambda k: k):
        forced.add(k)
        for rule in ("VR-007", "VR-009"):
            truth.append(_truth("unapproved_time_exported", "payroll_inputs", _pin(*k), rule,
                                "non-approved time counted in the payroll input"))

    # 3. same allowance duplicated -> VR-006 on the duplicate row
    approved = sorted((a for a in allowances if a["approval_status"] == "approved"),
                      key=lambda a: a["allowance_id"])
    for a in _pick(rng, approved, n, used, lambda a: (a["employee_id"], a["pay_period_id"])):
        dup = _duplicate(rng, a, "allowance_id", "related_allowance_id", ids.next("allowance"))
        allowances.append(dup)
        truth.append(_truth("duplicate_allowance", "allowances", dup["allowance_id"], "VR-006",
                            f"copy of {a['allowance_id']}"))

    # 4. leave deduction applied twice -> VR-008 on the duplicate row
    unpaid = sorted((d for d in deductions
                     if d["deduction_type"] == "unpaid_leave" and d["approval_status"] == "approved"),
                    key=lambda d: d["deduction_id"])
    for d in _pick(rng, unpaid, n, used, lambda d: (d["employee_id"], d["pay_period_id"])):
        dup = _duplicate(rng, d, "deduction_id", "related_deduction_id", ids.next("deduction"))
        deductions.append(dup)
        truth.append(_truth("leave_deduction_twice", "deductions", dup["deduction_id"], "VR-008",
                            f"copy of {d['deduction_id']} for {d['leave_id']}"))
    return truth, frozenset(forced), used


def inject_input_anomalies(rng, scale, payroll_inputs, used):
    """5. payroll totals fail to reconcile -> VR-009. Edits net_pay in place."""
    truth = []
    candidates = sorted(r["payroll_input_id"] for r in payroll_inputs
                        if (r["employee_id"], r["pay_period_id"]) not in used)
    by_id = {r["payroll_input_id"]: r for r in payroll_inputs}
    for pid in sorted(rng.sample(candidates, min(scale.anomalies_per_type, len(candidates)))):
        delta = D(rng.choice([-2500, -1200, -350, 125, 480, 1750, 3000])) + D(rng.randrange(1, 100)) / 100
        by_id[pid]["net_pay"] += delta
        truth.append(_truth("totals_fail_to_reconcile", "payroll_inputs", pid, "VR-009",
                            f"net_pay shifted by {delta}"))
    return truth