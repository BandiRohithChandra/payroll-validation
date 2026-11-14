"""Dataset validation: keys, joins, enums, dates, arithmetic, lifecycle and export rules."""
from collections import Counter, defaultdict
from decimal import Decimal

import config
from datagen.ids import is_valid
from datagen.payroll import aggregate_payroll_inputs
from datagen.rules import RECON_FIELDS, allowance_is_eligible
from datagen.schema import ENUMS, FKS, ID_KIND, PK, TABLE_OF_KEY

ZERO = Decimal("0.00")
TOL = config.RECONCILIATION_TOLERANCE
ALLOWED = {
    "payroll_input": {(None, "draft"), ("draft", "validated"), ("validated", "validated"),
                      ("validated", "held"), ("validated", "approved"),
                      ("validated", "rejected"), ("approved", "exported")},
    "exception": {(None, "open"), ("open", "resolved"), ("open", "waived")},
    "pay_period": {("open", "exported")},
}
STATUS_TABLE = {"payroll_input": "payroll_inputs", "exception": "exceptions",
                "pay_period": "pay_periods"}
DATE_PAIRS = [
    ("employees", "hire_date", "termination_date"),
    ("pay_periods", "start_date", "end_date"),
    ("pay_periods", "end_date", "submission_deadline"),
    ("leave_records", "start_date", "end_date"),
    ("time_entries", "submitted_at", "approved_at"),
    ("leave_records", "submitted_at", "approved_at"),
    ("allowances", "created_at", "approved_at"),
    ("deductions", "created_at", "approved_at"),
    ("exceptions", "detected_at", "resolved_at"),
]


def run_checks(data):
    t = {TABLE_OF_KEY[k]: data[k] for k in TABLE_OF_KEY}
    results = []

    def record(name, failures):
        results.append({"check": name, "passed": not failures, "failures": len(failures),
                        "examples": [str(f) for f in failures[:3]]})

    # keys and joins
    bad = []
    for table, rows in t.items():
        seen = set()
        for r in rows:
            v = r[PK[table]]
            if v is None or v in seen:
                bad.append((table, v))
            seen.add(v)
    record("primary_keys_unique_and_not_null", bad)
    record("id_formats", [(tb, r[PK[tb]]) for tb, rows in t.items() for r in rows
                          if not is_valid(ID_KIND[tb], r[PK[tb]])])
    keys = {tb: {r[PK[tb]] for r in rows} for tb, rows in t.items()}
    record("foreign_keys_resolve",
           [(tb, col, r[col]) for tb, col, rt, _ in FKS for r in t[tb]
            if r[col] is not None and r[col] not in keys[rt]])
    record("allowed_enum_values",
           [(tb, col, r[col]) for (tb, col), ok in ENUMS.items() for r in t[tb]
            if r[col] is not None and r[col] not in ok])

    # dates and approval fields
    periods = {p["pay_period_id"]: p for p in t["pay_periods"]}
    employees_by_id = {e["employee_id"]: e for e in t["employees"]}
    bad = []
    for tb, a, b in DATE_PAIRS:
        bad += [(tb, r[PK[tb]], a, b) for r in t[tb]
                if r[a] is not None and r[b] is not None and r[a] > r[b]]
    bad += [("time_entries", r["time_entry_id"]) for r in t["time_entries"]
            if not periods[r["pay_period_id"]]["start_date"] <= r["work_date"]
            <= periods[r["pay_period_id"]]["end_date"]]
    bad += [("leave_records", r["leave_id"]) for r in t["leave_records"]
            if r["start_date"] < periods[r["pay_period_id"]]["start_date"]
            or r["end_date"] > periods[r["pay_period_id"]]["end_date"]]
    record("date_ordering", bad)
    record("pending_rows_have_no_approver",
           [(tb, r[PK[tb]]) for tb in ("time_entries", "leave_records", "allowances", "deductions")
            for r in t[tb]
            if (r["approval_status"] == "pending") != (r["approved_by"] is None)])

    # arithmetic on source and derived rows
    record("allowance_deduction_amounts",
           [(tb, r[PK[tb]]) for tb in ("allowances", "deductions") for r in t[tb]
            if r["amount"] != r["units"] * r["unit_amount"]])

    record("allowances_match_employee_eligibility",
           [a["allowance_id"] for a in t["allowances"]
            if not allowance_is_eligible(a, employees_by_id, periods)])

    record("payroll_inputs_meet_minimum_net_pay",
           [r["payroll_input_id"] for r in t["payroll_inputs"]
            if r["net_pay"] < config.MIN_NET_PAY])
    inputs = {r["payroll_input_id"]: r for r in t["payroll_inputs"]}
    record("payroll_input_gross_arithmetic",
           [pid for pid, r in inputs.items()
            if abs(r["gross_pay"] - (r["base_pay"] + r["overtime_pay"] + r["allowance_total"])) > TOL])
    exported = {pid for pid, r in inputs.items() if r["status"] == "exported"}
    record("exported_input_net_arithmetic",
           [pid for pid in exported
            if abs(inputs[pid]["gross_pay"] - inputs[pid]["deduction_total"]
                   - inputs[pid]["net_pay"]) > TOL])

    # duplicates and labels
    originals = Counter((r["employee_id"], r["work_date"]) for r in t["time_entries"]
                        if r["entry_type"] == "original")
    record("one_original_time_entry_per_day", [k for k, n in originals.items() if n > 1])
    labelled = {(x["table_name"], x["record_id"]) for x in data["truth"]}
    record("every_duplicate_row_is_labelled",
           [(tb, r[PK[tb]]) for tb in ("time_entries", "allowances", "deductions")
            for r in t[tb] if r["entry_type"] == "duplicate_submission"
            and (tb, r[PK[tb]]) not in labelled])
    record("ground_truth_records_exist",
           [(x["table_name"], x["record_id"]) for x in data["truth"]
            if x["record_id"] not in keys[x["table_name"]]])

    # lifecycle
    history = defaultdict(list)
    for e in sorted(t["status_events"], key=lambda e: e["event_id"]):
        history[(e["entity_type"], e["entity_id"])].append(e)
    current = {et: {r[PK[tb]]: r["status"] for r in t[tb]} for et, tb in STATUS_TABLE.items()}
    bad = []
    for (et, eid), evs in history.items():
        prev, last_at = ("open" if et == "pay_period" else None), None
        for e in evs:
            if (e["from_status"] != prev or (e["from_status"], e["to_status"]) not in ALLOWED[et]
                    or (last_at is not None and e["event_at"] < last_at)):
                bad.append((et, eid, e["event_id"]))
            prev, last_at = e["to_status"], e["event_at"]
        if current[et].get(eid) != prev:
            bad.append((et, eid, "final status differs from last event"))
    bad += [(et, eid, "no history") for et, ids_ in current.items() for eid in ids_
            if (et, eid) not in history]
    record("lifecycle_transitions_and_event_order", bad)

    # approvals and export
    approved = Counter(a["entity_id"] for a in t["approvals"] if a["decision"] == "approved")
    record("exported_only_if_approved_once", [pid for pid in exported if approved[pid] != 1])
    blocking_open = {x["payroll_input_id"] or x["employee_id"] for x in t["exceptions"]
                     if x["severity"] == "blocking" and x["status"] == "open"}
    record("no_export_with_open_blocking_exception",
           [pid for pid in exported
            if pid in blocking_open or inputs[pid]["employee_id"] in blocking_open])
    lines = t["payroll_export_lines"]
    counts = Counter(l["payroll_input_id"] for l in lines)
    record("export_lines_match_exported_inputs",
           [pid for pid in exported | set(counts) if (pid in exported) != (counts[pid] == 1)])
    emps = {e["employee_id"]: e for e in t["employees"]}
    record("export_lines_have_bank_and_tax",
           [l["export_line_id"] for l in lines
            if not l["bank_account_number"] or not l["bank_ifsc"]
            or not emps[l["employee_id"]]["tax_id"]])
    bad = []
    for ex in t["payroll_exports"]:
        mine = [l for l in lines if l["export_id"] == ex["export_id"]]
        if (len(mine) != ex["record_count"]
                or sum((l["gross_pay"] for l in mine), ZERO) != ex["total_gross"]
                or sum((l["net_pay"] for l in mine), ZERO) != ex["total_net"]
                or any(inputs[l["payroll_input_id"]]["pay_period_id"] != ex["pay_period_id"]
                       or inputs[l["payroll_input_id"]]["net_pay"] != l["net_pay"]
                       or inputs[l["payroll_input_id"]]["gross_pay"] != l["gross_pay"]
                       for l in mine)):
            bad.append(ex["export_id"])
    record("export_totals_and_lines_reconcile", bad)

    # exported inputs reconcile to approved source rows (duplicates fixed by a correction are excluded)
    fixed = frozenset(x["record_id"] for x in t["exceptions"]
                      if x["rule_id"] in ("VR-006", "VR-008") and x["resolution"] == "corrected")
    expected = {r["payroll_input_id"]: r for r in aggregate_payroll_inputs(
        t["employees"], t["time_entries"], t["allowances"], t["deductions"],
        frozenset(), fixed)}
    record("exported_inputs_reconcile_to_source",
           [pid for pid in exported
            if inputs[pid]["unapproved_source_count"] > 0
            or any(abs(inputs[pid][k] - expected[pid][k]) > TOL for k in RECON_FIELDS)])
    return results