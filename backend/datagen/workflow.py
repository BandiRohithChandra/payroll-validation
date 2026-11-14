"""Exceptions, approvals and export. Every state change is also written as an
event row, so history is never lost (see docs/decisions.md)."""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

import config
from datagen.ids import IdGenerator
from datagen.payroll import aggregate_payroll_inputs
from datagen.rules import RECON_FIELDS

SYSTEM = "SYSTEM"
APPROVAL_OUTCOMES = (("approved", 0.95), ("rejected", 0.02), ("pending", 0.03))
# Blocking rules that a correction can fix by recomputing the input. VR-001, VR-002
# and VR-004 need new source data, so those inputs stay held.
RESOLVABLE = frozenset({"VR-006", "VR-007", "VR-008", "VR-009"})
CORRECTED_FIELDS = RECON_FIELDS + ("unapproved_source_count",)
ZERO = Decimal("0.00")


def _pin(employee_id, period_id):
    return IdGenerator.payroll_input_id(employee_id, int(period_id[-2:]))


def _at(day, minutes=0):
    return datetime.combine(day, time(9, 0)) + timedelta(minutes=minutes)


def run_workflow(rng, ids, employees, time_entries, allowances, deductions,
                 payroll_inputs, pay_periods, findings):
    """Edits payroll_inputs and pay_periods in place (status, corrected values).
    Returns exceptions, approvals, exports, export_lines and events."""
    events = []

    def event(entity_type, entity_id, frm, to, at, actor, note=""):
        events.append({"event_id": ids.next("event"), "entity_type": entity_type,
                       "entity_id": entity_id, "from_status": frm, "to_status": to,
                       "event_at": at, "actor_id": actor, "note": note})

    period_by_id = {p.pay_period_id: p for p in config.PAY_PERIODS}
    emp_by_id = {e["employee_id"]: e for e in employees}
    hr_ids = sorted(e["employee_id"] for e in employees if e["role"] == "hr_partner")
    by_input = {r["payroll_input_id"]: r for r in payroll_inputs}

    # 1. every input starts as draft and is validated
    for r in payroll_inputs:
        pid = r["payroll_input_id"]
        event("payroll_input", pid, None, "draft", r["aggregated_at"], SYSTEM)
        event("payroll_input", pid, "draft", "validated",
              r["aggregated_at"] + timedelta(hours=1), SYSTEM)
        r["status"] = "validated"

    # 2. one exception per finding; warnings may be waived, some blocking ones corrected
    exceptions, resolve_draw = [], {}
    excluded_rows, corrected = set(), {}
    first_detect = config.PAY_PERIODS[0].end_date + timedelta(days=9)
    for f in sorted(findings, key=lambda f: (f["rule_id"], f["record_id"])):
        period_id = f["pay_period_id"]
        pin = _pin(f["employee_id"], period_id) if period_id else None
        day = (period_by_id[period_id].end_date + timedelta(days=9)) if period_id else first_detect
        detected = _at(day, rng.randrange(180))
        exc = {"exception_id": ids.next("exception"), "rule_id": f["rule_id"],
               "severity": f["severity"], "table_name": f["table_name"],
               "record_id": f["record_id"], "employee_id": f["employee_id"],
               "pay_period_id": period_id, "payroll_input_id": pin, "detail": f["detail"],
               "status": "open", "resolution": None, "detected_at": detected,
               "resolved_at": None, "resolved_by": None}
        event("exception", exc["exception_id"], None, "open", detected, SYSTEM, f["rule_id"])

        status = resolution = None
        if f["severity"] == "warning":
            if rng.random() < config.WARNING_WAIVE_RATE:
                status, resolution = "waived", "waived"
        elif f["rule_id"] in RESOLVABLE:
            if pin not in resolve_draw:  # one decision per input, so its defects clear together
                resolve_draw[pin] = rng.random() < config.BLOCKING_RESOLVE_RATE
            if resolve_draw[pin]:
                status, resolution = "resolved", "corrected"
        if status:
            exc.update(status=status, resolution=resolution, resolved_by=rng.choice(hr_ids),
                       resolved_at=detected + timedelta(hours=rng.randint(1, 48)))
            event("exception", exc["exception_id"], "open", status, exc["resolved_at"],
                  exc["resolved_by"], resolution)
            if resolution == "corrected":
                corrected[pin] = (exc["resolved_by"], exc["resolved_at"])
                if f["rule_id"] in ("VR-006", "VR-008"):
                    excluded_rows.add(f["record_id"])
        exceptions.append(exc)

    # 3. apply corrections: recompute the input without the duplicate rows
    if corrected:
        clean = {r["payroll_input_id"]: r for r in aggregate_payroll_inputs(
            employees, time_entries, allowances, deductions,
            frozenset(), frozenset(excluded_rows))}
        for pin in sorted(corrected):
            row, new = by_input[pin], clean[pin]
            note = f"net_pay {row['net_pay']} -> {new['net_pay']}"
            for k in CORRECTED_FIELDS:
                row[k] = new[k]
            actor, at = corrected[pin]
            event("payroll_input", pin, "validated", "validated", at, actor, note)

    # 4. open blocking exceptions hold an input; the rest go to HR approval
    blockers = defaultdict(list)  # payroll_input_id, or employee_id for employee-level
    for x in exceptions:
        if x["severity"] == "blocking" and x["status"] == "open":
            blockers[x["payroll_input_id"] or x["employee_id"]].append(x["rule_id"])
    approvals = []
    outcomes = [o for o, _ in APPROVAL_OUTCOMES]
    weights = [w for _, w in APPROVAL_OUTCOMES]
    for r in sorted(payroll_inputs, key=lambda r: r["payroll_input_id"]):
        pid = r["payroll_input_id"]
        rules = blockers.get(pid, []) + blockers.get(r["employee_id"], [])
        if rules:
            r["status"] = "held"
            event("payroll_input", pid, "validated", "held",
                  r["aggregated_at"] + timedelta(days=1), SYSTEM, ",".join(sorted(set(rules))))
            continue
        outcome = rng.choices(outcomes, weights)[0]
        if outcome == "pending":
            continue  # still waiting for HR; never exported
        approver = rng.choice(hr_ids)
        decided = r["aggregated_at"] + timedelta(days=1, minutes=rng.randrange(36 * 60))
        approvals.append({"approval_id": ids.next("approval"), "entity_type": "payroll_input",
                          "entity_id": pid, "approver_id": approver, "decision": outcome,
                          "decided_at": decided, "comment": ""})
        r["status"] = outcome
        event("payroll_input", pid, "validated", outcome, decided, approver)

    # 5. export only approved inputs, one export per period
    exports, lines = [], []
    pay_period_rows = {p["pay_period_id"]: p for p in pay_periods}
    for period in config.PAY_PERIODS:
        rows = sorted((r for r in payroll_inputs
                       if r["pay_period_id"] == period.pay_period_id and r["status"] == "approved"),
                      key=lambda r: r["payroll_input_id"])
        generated = _at(period.end_date + timedelta(days=12), rng.randrange(120))
        export_id = ids.next("export")
        line_gross = line_net = ZERO
        for r in rows:
            e = emp_by_id[r["employee_id"]]
            lines.append({"export_line_id": ids.next("export_line"), "export_id": export_id,
                          "payroll_input_id": r["payroll_input_id"],
                          "employee_id": r["employee_id"],
                          "bank_account_number": e["bank_account_number"],
                          "bank_ifsc": e["bank_ifsc"],
                          "gross_pay": r["gross_pay"], "net_pay": r["net_pay"]})
            line_gross += r["gross_pay"]
            line_net += r["net_pay"]
            r["status"] = "exported"
            event("payroll_input", r["payroll_input_id"], "approved", "exported",
                  generated, SYSTEM, export_id)
        total_gross = sum((r["gross_pay"] for r in rows), ZERO)
        total_net = sum((r["net_pay"] for r in rows), ZERO)
        exports.append({"export_id": export_id, "pay_period_id": period.pay_period_id,
                        "status": "generated", "record_count": len(rows),
                        "total_gross": total_gross, "total_net": total_net,
                        "reconciliation_status": ("reconciled" if (line_gross, line_net) ==
                                                  (total_gross, total_net) else "mismatch"),
                        "generated_at": generated, "generated_by": SYSTEM})
        pay_period_rows[period.pay_period_id]["status"] = "exported"
        event("pay_period", period.pay_period_id, "open", "exported", generated, SYSTEM, export_id)

    return {"exceptions": exceptions, "approvals": approvals, "payroll_exports": exports,
            "payroll_export_lines": lines, "status_events": events}


def summarize(payroll_inputs, exceptions, exports):
    return {
        "input_status": dict(Counter(r["status"] for r in payroll_inputs)),
        "exceptions": dict(Counter(f"{x['severity']}/{x['status']}" for x in exceptions)),
        "exports": [(e["export_id"], e["record_count"], str(e["total_net"])) for e in exports],
    }