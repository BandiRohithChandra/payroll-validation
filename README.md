# Payroll Validation: synthetic data generator

Validates time, leave, allowances and deductions before payroll export, while keeping reconciliation and approvals intact. The generator builds a valid baseline, plants labelled defects, runs ten validation rules, raises exceptions, records approvals and exports only approved inputs. Every state change is kept as an event row.

Everything is synthetic and deterministic. Fixed seed: **20261022**.

## Quick start (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python generate.py --scale starter --verify    # 300 employees
python generate.py --scale full --formats csv,sql --verify   # 3,000 employees
python -m pytest -q                            # 8 tests
```

`generate.py` options:

| Option | Meaning |
|---|---|
| `--scale starter\|full` | Same generator, different volume (`config.SCALES`) |
| `--seed N` | Defaults to 20261022 |
| `--formats csv,json,sql` | Output formats (default: all three) |
| `--out PATH` | Output root (default: `data/`) |
| `--verify` | Regenerates twice more and compares row counts and SHA-256 checksums |

## What the generator does

1. **Master data:** PayGroup, PayPeriod (PP-2026-01 to PP-2026-03), Employee (3 pay groups, hourly and salaried, managers and HR partners).
2. **Source records:** TimeEntry (with corrections and duplicate submissions), LeaveRecord (paid and unpaid, with corrections), Allowance, Deduction. Every row carries its own approval status and approver.
3. **Labelled edge cases** are injected into the valid baseline (see below).
4. **PayrollInput:** one row per active employee per period, aggregated from **approved** source rows only. Derived values (hours, pay, totals) are calculated from source rows, never generated separately.
5. **Validation:** ten rules produce findings.
6. **Workflow:** each finding becomes an Exception. Warnings may be waived by an HR partner. Blocking exceptions that a correction can fix are corrected, and the input is recomputed. Inputs with open blocking exceptions are held. The rest go to HR approval.
7. **Export:** only approved inputs reach PayrollExport, one export per period, with line items and reconciled totals.

## Project layout

```
backend/
  config.py            all rules, rates and volumes
  generate.py          command line entry point
  datagen/
    ids.py             deterministic ID generation and format checks
    master.py          PayGroup, PayPeriod, Employee
    time_entries.py    TimeEntry
    leave.py           LeaveRecord
    pay_items.py       Allowance, Deduction
    anomalies.py       labelled defect injection
    payroll.py         PayrollInput aggregation
    rules.py           ValidationRule table and validation engine
    workflow.py        Exception, Approval, PayrollExport, event history
    evaluate.py        precision and recall of rules against ground truth
    validate_dataset.py  19 dataset integrity checks
    writer.py          CSV / JSON / SQL / manifest writer
    schema.py          primary keys, foreign keys, enums
    pipeline.py        builds the whole dataset in dependency order
  tests/test_pipeline.py
data/
  starter/  full/      generated output (see below)
docs/                  data dictionary and design decisions
```

## ID conventions

| Entity | Format | Example |
|---|---|---|
| Employee | `EMP-000001` | EMP-000001 |
| PayPeriod | `PP-2026-01` | PP-2026-01 |
| TimeEntry | `TIME-<employee-id>-<date>` (`-C1` correction, `-D1` duplicate) | TIME-EMP-000001-2026-01-05 |
| PayrollInput | `PIN-<employee-id>-2026-01` | PIN-EMP-000001-2026-01 |
| PayrollExport | `PEX-2026-000001` | PEX-2026-000001 |

Other entities use `PG-`, `LV-`, `ALW-`, `DED-`, `VR-`, `EXC-`, `APR-`, `PXL-` (export line) and `EVT-` (event). Counters are zero-padded and only increase, IDs are never reused, and every foreign key is checked.

## Output layout

```
data/<scale>/
  csv/ json/ sql/            14 tables (schema.sql + seed.sql for SQL)
  ground_truth/              ground_truth.csv and .json, kept apart from the input tables
  outputs/validation_findings.csv
  manifest.json              scale, seed, command, row counts, SHA-256 per file
  validation_summary.json    19 check results, rule precision/recall, workflow summary
  reproducibility_check.json
```

The `full` dataset was generated with `--formats csv,sql`. The `starter` dataset has all three formats.

## Entities

Employee, PayGroup, PayPeriod, TimeEntry, LeaveRecord, Allowance, Deduction, PayrollInput, ValidationRule, Exception, Approval, PayrollExport, plus `payroll_export_lines` (export line items) and `status_events` (event history). The data dictionary is in `docs/data_dictionary.md`.

Main relationships: PayGroup 1:N Employee; Employee 1:N TimeEntry / LeaveRecord / Allowance / Deduction; PayPeriod 1:N each of those; Employee and PayPeriod 1:1 PayrollInput per period; PayrollExport 1:N export lines; each export line references exactly one PayrollInput. Corrections and duplicates point to the row they relate to through `related_*_id`, and history is kept (rows are not overwritten).

## Validation rules

| Rule | Severity | Checks |
|---|---|---|
| VR-001 | blocking | Missing bank account or IFSC |
| VR-002 | blocking | Missing tax id |
| VR-003 | warning | Duplicate time submission for the same employee and day |
| VR-004 | blocking | Hours above the pay group maximum for the period |
| VR-005 | warning | Daily hours above 14 (outlier) |
| VR-006 | blocking | Same allowance type counted twice in a period |
| VR-007 | blocking | Payroll input counts source rows that are not approved |
| VR-008 | blocking | Unpaid-leave deduction applied twice for one leave record |
| VR-009 | blocking | Totals do not reconcile with a recomputation from approved source rows, or net is not gross minus deductions |
| VR-010 | warning | Time entry submitted after the period deadline |

## Edge cases and ground truth

Five required edge cases are injected after the valid baseline is generated. Each one gets its own employee-period, so one label explains one defect:

| Issue type | How it is injected | Expected rule |
|---|---|---|
| `hours_exceed_period_max` | Effective approved entries raised to 12 h, so the total is above the group maximum | VR-004 |
| `unapproved_time_exported` | Pending or rejected time is counted in the payroll input | VR-007 and VR-009 |
| `duplicate_allowance` | An approved allowance is copied as a `duplicate_submission` row | VR-006 |
| `leave_deduction_twice` | An approved unpaid-leave deduction is copied | VR-008 |
| `totals_fail_to_reconcile` | `net_pay` of a payroll input is shifted | VR-009 |

The baseline also contains labelled natural cases: missing bank and tax fields, duplicate time submissions, daily outliers and late submissions.

`ground_truth.csv` has one row per (record, rule): `issue_type, table_name, record_id, expected_rule, expected_decision, injected, note`. `expected_decision` is `block_export` for blocking rules and `warn` for warnings. The ground truth is written to its own folder and never joined into input tables (a test checks this).

## Results

| | starter | full |
|---|---|---|
| Employees | 300 | 3,000 |
| Time entries | 7,860 | 65,230 |
| Allowances | 1,797 | 17,486 |
| Deductions | 1,521 | 15,885 |
| Time + allowance + deduction records | 11,178 | **98,601** |
| Leave records | 136 | 1,463 |
| Payroll inputs | 898 | 8,974 |
| Exceptions | 333 | 2,892 |
| Approvals | 844 | 8,476 |
| Exported inputs | 820 | 8,303 |
| Dataset checks passed | 19 / 19 | 19 / 19 |
| Reproducible (2 extra runs, same row counts and SHA-256) | yes | yes |

Rule performance at full scale (against ground truth): every rule has **precision 1.0 and recall 1.0**. Expected counts: VR-001 30, VR-002 30, VR-003 607, VR-004 40, VR-005 130, VR-006 40, VR-007 40, VR-008 40, VR-009 80, VR-010 1,855. Starter scale also gives precision and recall of 1.0 on every rule.

Full-scale workflow: 8,303 inputs exported, 239 held by open blocking exceptions, 173 rejected, 259 still waiting for approval. Exceptions: 171 blocking resolved by correction, 129 blocking still open, 1,296 warnings waived, 1,296 warnings open.

Exports: PEX-2026-000001 (2,782 inputs), PEX-2026-000002 (2,767), PEX-2026-000003 (2,754).

## Acceptance criteria

- **Aggregates reconcile to source inputs:** check `exported_inputs_reconcile_to_source`, plus export totals against line items.
- **Validation flags planted errors:** all ten rules have precision and recall of 1.0 against ground truth.
- **Corrections are auditable:** a corrected input has a `validated -> validated` event with the actor, the time and the before and after net pay.
- **Only approved inputs export:** checks `exported_only_if_approved_once`, `no_export_with_open_blocking_exception` and `export_lines_match_exported_inputs`.

## Dataset checks (19)

Primary key uniqueness, ID formats, foreign key integrity, allowed enum values, date ordering, approval field consistency, allowance and deduction arithmetic, payroll input arithmetic, one original time entry per day, duplicates labelled, ground truth records exist, lifecycle transitions and event order, export approval rules, export line and total reconciliation. The SQL seed is also loaded into SQLite with foreign keys enforced (in the tests).

## Reproducibility

```powershell
python generate.py --scale full --formats csv,sql --verify
```

`--verify` regenerates twice and compares row counts and SHA-256 checksums with the first run. Results are in `reproducibility_check.json`. All randomness comes from one `random.Random(seed)`.

## Provenance and lawful use

No external data is used. Names come from short fixed lists in `datagen/master.py`. Bank accounts, IFSC codes and tax ids are random and fake. Amounts are in INR.

## Assumptions and limitations

- Working days are Monday to Friday with no holiday calendar.
- VR-009 recomputes inputs with the same aggregation function the generator uses. It detects tampering and stale totals, but it is not an independent second implementation.
- Corrections of allowances and deductions are not generated in the baseline. Time entries and leave records have corrections.
- Corrections fix VR-006, VR-007, VR-008 and VR-009 exceptions. VR-001, VR-002 and VR-004 need new source data, so those inputs stay held.
- There is no negative-net-pay rule, because a few terminated hourly staff with a loan would trigger unlabelled findings.
- The volume is 98,601 time, allowance and deduction records at full scale (100,064 with leave records).