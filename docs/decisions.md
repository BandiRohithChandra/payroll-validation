# Decisions and Assumptions

Each item fills a gap in the problem statement or fixes a rule. Code, validation and metrics must follow this file. The problem statement is paraphrased here, not copied.

**## 1. Architecture (backend-only)**
- Database: SQLite (data/payroll.db) holds all entities. CSV, JSON and SQL exports are written beside it.
- Backend: Python generators, validation rules, payroll calculations and workflow logic. The CLI supports dataset generation, validation and reproducibility verification. FastAPI provides the API layer where applicable.
- No frontend is required. The solution is focused on backend data generation, payroll validation, approvals, reconciliation and controlled exports.
- Generic scaffolding (ID counters, exporter and manifest, validator framework) is reused from my own earlier project, cart-recovery-datagen. All payroll domain logic is new.

## 2. Reproducibility
- Fixed seed 20261022 through a single random.Random instance. No wall-clock time is used during generation.
- Scale is parameterized (starter and full share one generator).
- Rows are exported sorted by primary key, with a manifest of row counts and SHA-256 checksums. reproduce.py generates twice and compares.
- Money uses Decimal with ROUND_HALF_UP to 2 decimals, so totals reconcile exactly.

## 3. Data period and calendar
- Three monthly pay periods: PP-2026-01, PP-2026-02, PP-2026-03 (January to March 2026), shared by all pay groups.
- working_days counts Monday to Friday. There is no holiday calendar.
- submission_deadline is 5 days after the period end. Anything submitted later is late.

## 4. Volumes (full dataset)
- 3,000 employees in 3 pay groups: Corporate, Operations, Contract (PG-001 to PG-003).
- About 38% hourly and 62% salaried. Only hourly staff have time entries, only salaried staff have leave.
- The statement asks for about 100,000 time, allowance and deduction records over three months. Volume follows from the rules (one time entry per hourly employee per working day, plus allowances and deductions) and is tuned by the hourly share to land within 10% of 100,000. The exact counts are reported in the validation summary.
- Starter dataset: 300 employees, same rules.

## 5. Employees
- All identities, emails (@example.com), bank accounts (12 digits, IFSC-style) and tax IDs (TIN- plus 8 digits) are fictional.
- About 2% of employees are hired or terminated during the period, so some periods are partial.
- manager_id forms the approval chain for source records. HR partners (about 1% of staff) approve payroll inputs and exceptions.
- Managers and HR partners are salaried. HR partners are all in the Corporate pay group. The first manager of each pay group is its head and has no manager; heads take no leave, because it would have no approver. Every other employee has a manager from their own pay group.
- Missing bank and tax fields are planted with fixed counts (at least 2 each), not by chance, and labelled in the ground truth with the rule expected to catch them (VR-001, VR-002).

## 6. Source records and approval
- Time, leave, allowance and deduction rows carry their own approval fields, set when the row is created. Payroll-level decisions (payroll inputs, exceptions, period) live in Approval.
- About 93% of source rows are approved, 5% pending and 2% rejected. Pending and rejected rows never count toward payroll.
- Corrections and duplicate submissions are new rows pointing to the original. Effective value = the approved correction if there is one, otherwise the approved original. A duplicate_submission never counts toward hours.
- Baseline: about 2% of time entries get a correction and about 1% get a duplicate submission.
- Hours are quarter-hour values. About 4% of working days have no entry (absence). A submission is late when its date is after the period's submission_deadline. Corrections are made only for approved, on-time, non-outlier originals; duplicate submissions copy the original's hours and never count. Rows are conservatively capped so no baseline employee exceeds the pay group maximum; exceeding it happens only through the labelled injection.
- Leave: only salaried employees who have a manager (group heads take none). At most one unpaid and one paid block per employee per period, placed with at least 2 free working days between blocks so records never overlap and a correction of plus or minus one day never collides. Leave is never submitted late. Effective leave is the approved correction, otherwise the approved original.

- Allowances and deductions have no corrections in the baseline, because their units and amounts are fully derived. Allowances are approved by the employee's manager; the three group heads have no manager, so an HR partner approves theirs. Deductions are approved by an HR partner. Provident fund, professional tax and unpaid-leave deductions are always approved (they are automatic); only loan_recovery follows the 93/5/2 approval split.
- An allowance or deduction is created on the first or second day after the period ends. An employee is active in a period if their hire date is on or before the period end date and their termination date is either empty or on or after the period start date.

## 7. Pay calculation (all derived)
- Overtime is hours above the pay group's standard_hours_per_day on each day, paid at hourly_rate x overtime_multiplier.
- Hourly base_pay = regular_hours x hourly_rate. Salaried base_pay = monthly_salary prorated by active working days in the pay period.
- Unpaid leave (salaried only) reduces pay only through its Deduction row: units = leave days, unit_amount = monthly_salary / working_days.
- Allowance rules: transport (all active, INR 2,000 per period), meal (hourly, INR 100 per day worked), remote_work (salaried in Corporate, INR 1,500 per period), shift (hourly in Operations, INR 250 per day worked).
- Deduction rules: provident_fund (salaried, 12% of prorated monthly salary), professional_tax (all active, INR 200), loan_recovery (about 8% of employees, a fixed installment), unpaid_leave (one per effective unpaid leave record).
- gross_pay = base_pay + overtime_pay + allowances_total. net_pay = gross_pay - deductions_total and must not be negative.

## 8. Validation rules (stored in ValidationRule)
- 12 rules, VR-001 to VR-012 (see the data dictionary for the catalogue). Blocking rules keep the payroll input in flagged status. Warning rules are recorded and reviewed.
- Thresholds: daily hours outlier 14 hours, reconciliation tolerance 0.01 INR, net pay below 0.
- Validation rules run after payroll aggregation. The export workflow separately checks approval status and open blocking exceptions before allowing payroll inputs to be exported. Reconciliation checks verify payroll totals and exported amounts.

## 9. Exceptions, approvals and export
- Each finding becomes one Exception row. About 85% of blocking exceptions get resolved through a correction or rejection, and their payroll inputs are recalculated. The rest stay open, so their inputs are held back from export.
- Warning exceptions are waived by an HR partner or left open. They do not block export.
- An HR partner approves clean payroll inputs, never their own. A period is approved when no input remains in calculated status.
- Export happens in batches. Only approved inputs with no open blocking exception are exported, each in at most one batch.

## 10. Outcomes and labels
- Every outcome (flags, approvals, resolutions, export inclusion) comes from the rules above and fixed probabilities that depend on the record, never from independent random assignment.
- Baseline-planted validation cases (missing bank or tax field, duplicate hours, late submission, daily outliers) are generated first, flagged by the rules, and labelled in the ground truth.

## 11. Labelled anomalies (injected after the valid baseline)
1. hours_exceed_period_max: an employee's total hours go above the pay group maximum.
2. duplicate_allowance: a second original allowance of the same type for one employee and period.
3. unapproved_time_exported: an export line whose payroll input used an unapproved time entry.
4. leave_deduction_twice: a second unpaid_leave deduction for the same leave record.
5\. totals_fail_to_reconcile: a payroll input whose stored totals differ from the recomputed totals.
- Counts: 3 per type in the starter set and 40 per type in the full set. Each injection touches only its target rows and is recorded in ground_truth with the rule expected to catch it.
- ground_truth is a separate output and is never read by any generator, rule or feature step. validate_dataset.py runs dataset integrity checks, while evaluate.py compares validation findings with ground-truth labels afterwards.

## 12. ID conventions
- Given: EMP-000001, PP-2026-01, TIME-<employee-id>-<date>, PIN-<employee-id>-2026-01, PEX-2026-000001.
- Added by us: PG-001, LV-, ALW-, DED-, VR-, EXC-, APR-, PXL-.
- TimeEntry corrections and duplicates add the suffix -C1 or -D1 to the original ID.
- Counters are zero-padded and IDs are immutable.

## 13. Deviations and additions
- Added the supporting table PayrollExportLine so every exported amount is traceable.
- No bridge table: Exception links rules to the records they flag.
- ValidationRule changes are new rows with a later effective_from. Old rows are never edited.

## 14. Provenance and lawful use
- No external or real data. Everything is generated. Names come from a short built-in list.
- Prompts to AI tools are kept in ai-prompts/prompt-history.md.