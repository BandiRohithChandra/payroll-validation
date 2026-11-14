"""One function that builds the whole dataset in memory, in dependency order."""
import random

import config
from datagen.anomalies import inject_input_anomalies, inject_source_anomalies
from datagen.evaluate import evaluate
from datagen.ids import IdGenerator
from datagen.leave import generate_leave_records
from datagen.master import generate_employees, generate_pay_groups, generate_pay_periods
from datagen.pay_items import generate_allowances, generate_deductions
from datagen.payroll import aggregate_payroll_inputs
from datagen.rules import RULES, run_validation
from datagen.time_entries import generate_time_entries
from datagen.workflow import run_workflow, summarize


def build_dataset(scale_name="starter", seed=config.SEED):
    scale = config.SCALES[scale_name]
    rng, ids = random.Random(seed), IdGenerator()

    employees, p_emp = generate_employees(rng, ids, scale)
    time_entries, p_time = generate_time_entries(rng, employees)
    leaves = generate_leave_records(rng, ids, employees)
    allowances = generate_allowances(rng, ids, employees, time_entries)
    deductions = generate_deductions(rng, ids, employees, leaves)

    src_truth, forced, used = inject_source_anomalies(
        rng, ids, scale, employees, time_entries, allowances, deductions)
    payroll_inputs = aggregate_payroll_inputs(employees, time_entries, allowances,
                                              deductions, forced)
    in_truth = inject_input_anomalies(rng, scale, payroll_inputs, used)

    truth = p_emp + p_time + src_truth + in_truth
    findings = run_validation(employees, time_entries, allowances, deductions, payroll_inputs)

    pay_groups, pay_periods = generate_pay_groups(), generate_pay_periods()
    flow = run_workflow(rng, ids, employees, time_entries, allowances, deductions,
                        payroll_inputs, pay_periods, findings)
    return {
        "pay_groups": pay_groups, "pay_periods": pay_periods,
        "employees": employees, "time_entries": time_entries, "leaves": leaves,
        "allowances": allowances, "deductions": deductions,
        "payroll_inputs": payroll_inputs, "validation_rules": RULES,
        "findings": findings, "truth": truth, **flow,
    }


if __name__ == "__main__":
    import sys
    data = build_dataset(sys.argv[1] if len(sys.argv) > 1 else "starter")
    print({k: len(v) for k, v in data.items()})
    for row in evaluate(data["findings"], data["truth"]):
        print(row)
    print(summarize(data["payroll_inputs"], data["exceptions"], data["payroll_exports"]))
    exported = [r for r in data["payroll_inputs"] if r["status"] == "exported"]
    print("exported with unapproved source rows:",
          sum(r["unapproved_source_count"] > 0 for r in exported))