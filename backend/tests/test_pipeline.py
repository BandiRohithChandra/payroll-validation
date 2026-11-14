import sqlite3
import pytest

from datagen.evaluate import evaluate
from datagen.pipeline import build_dataset
from datagen.validate_dataset import run_checks
from datagen.rules import run_validation
from decimal import Decimal
from datagen.writer import write_all


@pytest.fixture(scope="module")
def data():
    return build_dataset("starter")


def test_all_dataset_checks_pass(data):
    failed = [c for c in run_checks(data) if not c["passed"]]
    assert not failed, failed


def test_rules_find_every_planted_error_and_nothing_else(data):
    for row in evaluate(data["findings"], data["truth"]):
        assert row["fn"] == 0 and row["fp"] == 0, row


def test_required_edge_cases_are_present(data):
    issues = {t["issue_type"] for t in data["truth"]}
    assert {"hours_exceed_period_max", "duplicate_allowance", "unapproved_time_exported",
            "leave_deduction_twice", "totals_fail_to_reconcile"} <= issues


def test_only_approved_inputs_are_exported(data):
    approved = {a["entity_id"] for a in data["approvals"] if a["decision"] == "approved"}
    exported = [r for r in data["payroll_inputs"] if r["status"] == "exported"]
    assert exported
    for r in exported:
        assert r["payroll_input_id"] in approved
        assert r["unapproved_source_count"] == 0


def test_corrections_are_auditable(data):
    fixes = [e for e in data["status_events"] if e["entity_type"] == "payroll_input"
             and e["from_status"] == "validated" and e["to_status"] == "validated"]
    assert fixes and all(e["note"].startswith("net_pay") for e in fixes)


def test_ground_truth_is_not_in_input_tables(data):
    leaked = {"issue_type", "expected_rule", "expected_decision", "injected", "ground_truth"}
    for key in ("employees", "time_entries", "leaves", "allowances", "deductions", "payroll_inputs"):
        assert not leaked & set(data[key][0])


def test_same_seed_gives_same_row_counts_and_checksums(data, tmp_path):
    a = write_all(data, tmp_path / "a", "starter", 20261022)["files"]
    b = write_all(build_dataset("starter"), tmp_path / "b", "starter", 20261022)["files"]
    assert a == b


def test_sql_seed_loads_with_foreign_keys_enforced(data, tmp_path):
    write_all(data, tmp_path, "starter", 20261022, ("sql",))
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((tmp_path / "sql" / "schema.sql").read_text(encoding="utf-8"))
    conn.executescript((tmp_path / "sql" / "seed.sql").read_text(encoding="utf-8"))
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == len(data["employees"])


def test_vr011_detects_negative_net_pay(data):
    inputs = [r.copy() for r in data["payroll_inputs"]]
    inputs[0]["net_pay"] = Decimal("-1.00")

    findings = run_validation(
        data["employees"], data["time_entries"],
        data["allowances"], data["deductions"], inputs
    )

    assert any(
        f["rule_id"] == "VR-011"
        and f["record_id"] == inputs[0]["payroll_input_id"]
        for f in findings
    )


def test_vr012_detects_ineligible_allowance(data):
    hourly_input = next(
        r for r in data["payroll_inputs"] if r["pay_type"] == "hourly"
    )

    invalid = data["allowances"][0].copy()
    invalid.update({
        "allowance_id": "AL-TEST-000001",
        "employee_id": hourly_input["employee_id"],
        "pay_period_id": hourly_input["pay_period_id"],
        "allowance_type": "remote_work",
        "approval_status": "pending",
        "approved_by": None,
        "approved_at": None,
    })

    findings = run_validation(
        data["employees"], data["time_entries"],
        data["allowances"] + [invalid],
        data["deductions"], data["payroll_inputs"]
    )

    assert any(
        f["rule_id"] == "VR-012"
        and f["record_id"] == invalid["allowance_id"]
        for f in findings
    )