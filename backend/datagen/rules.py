"""ValidationRule table and the validation engine."""
from collections import defaultdict

import config
from datagen.payroll import aggregate_payroll_inputs


def _rule(rule_id, name, severity, table, description):
    return {"rule_id": rule_id, "name": name, "severity": severity, "target_table": table,
            "description": description, "status": "active",
            "effective_from": config.PERIOD_START}


RULES = [
    _rule("VR-001", "Missing bank details", "blocking", "employees",
          "Bank account number or IFSC is empty."),
    _rule("VR-002", "Missing tax id", "blocking", "employees", "Tax id is empty."),
    _rule("VR-003", "Duplicate time submission", "warning", "time_entries",
          "More than one non-correction entry for the same employee and date; the later one is flagged."),
    _rule("VR-004", "Hours exceed period maximum", "blocking", "payroll_inputs",
          "Regular plus overtime hours are above the pay group maximum."),
    _rule("VR-005", "Daily hours outlier", "warning", "time_entries",
          "An original entry has more hours than the daily outlier threshold."),
    _rule("VR-006", "Duplicate allowance", "blocking", "allowances",
          "More than one approved allowance of the same type for an employee and period."),
    _rule("VR-007", "Unapproved source in payroll input", "blocking", "payroll_inputs",
          "The input counts source rows that are not approved."),
    _rule("VR-008", "Leave deduction applied twice", "blocking", "deductions",
          "More than one approved unpaid_leave deduction for the same leave record."),
    _rule("VR-009", "Payroll totals do not reconcile", "blocking", "payroll_inputs",
          "Stored totals differ from a recomputation from approved source rows, or net is not gross minus deductions."),
    _rule("VR-010", "Late time submission", "warning", "time_entries",
          "Entry submitted after the pay period submission deadline."),
]
SEVERITY = {r["rule_id"]: r["severity"] for r in RULES}
RECON_FIELDS = ("regular_hours", "overtime_hours", "base_pay", "overtime_pay",
                "allowance_total", "deduction_total", "gross_pay", "net_pay")


def run_validation(employees, time_entries, allowances, deductions, payroll_inputs):
    findings = []
    tol = config.RECONCILIATION_TOLERANCE
    period_by_id = {p.pay_period_id: p for p in config.PAY_PERIODS}

    def flag(rule, table, record_id, employee_id, period_id, detail):
        findings.append({"rule_id": rule, "severity": SEVERITY[rule], "table_name": table,
                         "record_id": record_id, "employee_id": employee_id,
                         "pay_period_id": period_id, "detail": detail})

    for e in employees:
        eid = e["employee_id"]
        if not e["bank_account_number"] or not e["bank_ifsc"]:
            flag("VR-001", "employees", eid, eid, None, "bank account or IFSC missing")
        if not e["tax_id"]:
            flag("VR-002", "employees", eid, eid, None, "tax id missing")

    same_day = defaultdict(list)
    for t in time_entries:
        if t["entry_type"] != "correction":
            same_day[(t["employee_id"], t["work_date"])].append(t)
        if t["entry_type"] == "original":
            if t["hours_worked"] > config.DAILY_HOURS_OUTLIER:
                flag("VR-005", "time_entries", t["time_entry_id"], t["employee_id"],
                     t["pay_period_id"], f"{t['hours_worked']} hours in one day")
            if t["submitted_at"].date() > period_by_id[t["pay_period_id"]].submission_deadline:
                flag("VR-010", "time_entries", t["time_entry_id"], t["employee_id"],
                     t["pay_period_id"], "submitted after the deadline")
    for rows in same_day.values():
        if len(rows) > 1:
            rows.sort(key=lambda r: (r["submitted_at"], r["time_entry_id"]))
            for r in rows[1:]:
                flag("VR-003", "time_entries", r["time_entry_id"], r["employee_id"],
                     r["pay_period_id"], f"same day as {rows[0]['time_entry_id']}")

    allowance_groups = defaultdict(list)
    for a in allowances:
        if a["approval_status"] == "approved":
            allowance_groups[(a["employee_id"], a["pay_period_id"], a["allowance_type"])].append(a)
    for rows in allowance_groups.values():
        rows.sort(key=lambda r: r["allowance_id"])
        for r in rows[1:]:
            flag("VR-006", "allowances", r["allowance_id"], r["employee_id"],
                 r["pay_period_id"], f"{r['allowance_type']} already counted in {rows[0]['allowance_id']}")

    leave_groups = defaultdict(list)
    for d in deductions:
        if d["deduction_type"] == "unpaid_leave" and d["approval_status"] == "approved":
            leave_groups[d["leave_id"]].append(d)
    for rows in leave_groups.values():
        rows.sort(key=lambda r: r["deduction_id"])
        for r in rows[1:]:
            flag("VR-008", "deductions", r["deduction_id"], r["employee_id"],
                 r["pay_period_id"], f"leave {r['leave_id']} already deducted in {rows[0]['deduction_id']}")

    expected = {r["payroll_input_id"]: r
                for r in aggregate_payroll_inputs(employees, time_entries, allowances, deductions)}
    for r in payroll_inputs:
        pid, eid, per = r["payroll_input_id"], r["employee_id"], r["pay_period_id"]
        hours = r["regular_hours"] + r["overtime_hours"]
        limit = config.PAY_GROUP_BY_ID[r["pay_group_id"]].max_hours_per_period
        if hours > limit:
            flag("VR-004", "payroll_inputs", pid, eid, per, f"{hours} hours, maximum {limit}")
        if r["unapproved_source_count"] > 0:
            flag("VR-007", "payroll_inputs", pid, eid, per,
                 f"{r['unapproved_source_count']} unapproved source rows counted")
        exp = expected.get(pid)
        bad = exp is None or any(abs(r[k] - exp[k]) > tol for k in RECON_FIELDS)
        bad = bad or abs(r["gross_pay"] - r["deduction_total"] - r["net_pay"]) > tol
        if bad:
            flag("VR-009", "payroll_inputs", pid, eid, per, "stored totals differ from recomputation")
    return findings