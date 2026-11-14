# Data Dictionary

All data is synthetic, including identities and bank and tax details. IDs are immutable and zero-padded. Timestamps are UTC, written as `YYYY-MM-DD HH:MM:SS`, dates are `YYYY-MM-DD`, and money is in INR with 2 decimals.

## Employee
Master table. One row per employee. Pay group changes and other history are kept as events in later tables, so this row holds the current state only.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| employee_id | string | yes | EMP-000001 | PK | matches ^EMP-\d{6}$, immutable |
| first_name | string | yes | synthetic name list | no | non-empty |
| last_name | string | yes | synthetic name list | no | non-empty |
| email | string | yes | synthetic, @example.com | yes | valid format, lowercase |
| role | enum | yes | employee, manager, hr_partner | no | one of the allowed values |
| manager_id | string | optional | existing EMP- id | no | FK to Employee (self); null only for the head manager of each pay group (3 rows); cannot be the employee's own id |
| pay_group_id | string | yes | existing PG- id | no | FK to PayGroup |
| pay_type | enum | yes | hourly, salaried | no | one of the allowed values |
| hourly_rate | decimal(10,2) | optional | INR per hour | no | required and greater than 0 when pay_type is hourly, null otherwise |
| monthly_salary | decimal(12,2) | optional | INR per month | no | required and greater than 0 when pay_type is salaried, null otherwise |
| hire_date | date | yes | YYYY-MM-DD | no | between 2018-01-01 and 2025-12-31 for most staff; about 1% are hired during the first two months of the data, and those have no time or pay before their hire date |
| termination_date | date | optional | YYYY-MM-DD | no | null for active staff; after hire_date when set |
| status | enum | yes | active, terminated | no | terminated if and only if termination_date is set |
| bank_account_number | string | optional | synthetic, 12 digits | no | required before a payroll export; a missing value is a planted validation case |
| bank_ifsc | string | optional | synthetic, 4 letters + 0 + 6 digits | no | required together with bank_account_number |
| tax_id | string | optional | synthetic, TIN- + 8 digits | yes | required before a payroll export; a missing value is a planted validation case |

Notes:
- Bank and tax fields are optional on purpose. The workflow checks for them before export, so a baseline row can lack them only when a ground-truth label says so.
- manager_id gives the approval chain, because an employee's time and leave are approved by their manager and payroll inputs by an hr_partner.
- Bank accounts and tax IDs use fictional formats, so no real person or account can match them.
- HR partners all belong to the Corporate pay group. About 1% of employees are terminated during the data period (their termination_date falls between 5 Feb and 21 Mar 2026), and they have no payroll input after the month they leave.


## PayGroup
Master table. A pay group defines the pay rules shared by its employees. Employee.pay_group_id points here (1:N from PayGroup to Employee).

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| pay_group_id | string | yes | PG-001 | PK | matches ^PG-\d{3}$, immutable |
| name | string | yes | e.g. Corporate, Operations, Contract | yes | non-empty |
| pay_frequency | enum | yes | monthly | no | one of the allowed values |
| standard_hours_per_day | decimal(4,2) | yes | hours | no | greater than 0 and at most 12 |
| max_hours_per_period | decimal(6,2) | yes | hours per pay period | no | greater than 0; hours above this are flagged as exceeding the period maximum |
| overtime_multiplier | decimal(3,2) | yes | multiple of the hourly rate | no | at least 1.00 |
| payday_day | integer | yes | 1 to 28 | no | day of the month after the period ends on which pay is released |
| effective_from | date | yes | YYYY-MM-DD | no | on or before the first pay period start |
| status | enum | yes | active, inactive | no | one of the allowed values |

Notes:
- All three pay groups are active for the whole data period. Pay rule changes would be new rows with a later effective_from, never edits to an old row.
- Whether an employee is paid hourly or a fixed salary is on Employee (pay_type), not here, so each group can mix both.



## PayPeriod
Master table. One shared monthly calendar for all pay groups (3 rows: 2026-01, 2026-02, 2026-03). Each period is a parent of the time, leave, allowance, deduction, payroll input and export records for that month.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| pay_period_id | string | yes | PP-2026-01 | PK | matches ^PP-\d{4}-\d{2}$, immutable |
| start_date | date | yes | YYYY-MM-DD | yes | first day of the month |
| end_date | date | yes | YYYY-MM-DD | yes | last day of the month; after start_date |
| working_days | integer | yes | days | no | Monday to Friday days in the period; greater than 0 |
| submission_deadline | date | yes | YYYY-MM-DD | no | after end_date; time and leave entered after this are late |
| status | enum | yes | open, exported | no | one of the allowed values; moves forward only |; moves forward only |

Lifecycle: open -> exported. A period becomes exported when its PayrollExport batch is generated. Validation, correction and approval steps are tracked per payroll input in `status_events`, so nothing is overwritten.

Notes:
- Periods must not overlap and must follow each other without gaps.
- Overtime and hour limits are per pay group (max_hours_per_period on PayGroup), not per period.


## TimeEntry
Transaction table. One row per hours submission by an hourly employee. Rows are never edited: a correction or a duplicate submission is a new row that points to the original. History is preserved in full.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| time_entry_id | string | yes | TIME-EMP-000001-2026-01-05, with -C1 (correction) or -D1 (duplicate) suffix | PK | matches ^TIME-EMP-\d{6}-\d{4}-\d{2}-\d{2}(-[CD]\d)?$; the prefix must equal the employee_id and work_date; immutable |
| employee_id | string | yes | existing EMP- id | no | FK to Employee; the employee's pay_type must be hourly |
| pay_period_id | string | yes | existing PP- id | no | FK to PayPeriod; work_date must fall inside the period |
| work_date | date | yes | YYYY-MM-DD | no | on or after hire_date and not after termination_date |
| hours_worked | decimal(4,2) | yes | hours | no | greater than 0 and at most 24; baseline entries are between 5 and 12 hours, planted daily outliers are 14.25 to 18.00 |


| related_entry_id | string | optional | existing TIME- id | no | FK to TimeEntry (self); required for correction and duplicate_submission and null for original; must point to an original entry of the same employee and work_date |
| submitted_at | timestamp | yes | UTC | no | 1 to 10 days before start_date for originals, so it can fall before the period starts; leave submissions are not checked by a validation rule |


| approval_status | enum | yes | approved, pending, rejected | no | one of the allowed values; set when the row is created |
| approved_by | string | optional | existing EMP- id | no | FK to Employee; required when approved or rejected; must be the employee's manager_id |
| approved_at | timestamp | optional | UTC | no | required when approved_by is set; on or after submitted_at |

Uniqueness rules beyond the primary key:
- At most one original entry per (employee_id, work_date).
- At most one correction per original entry.

Effective hours for an employee on a day: the correction if it is approved, otherwise the original if it is approved. A duplicate_submission never counts toward hours. Duplicates are expected in the baseline data and are caught by the duplicate-hours validation rule. Overtime is calculated during aggregation, never stored here.

Injected anomaly: for the "hours exceed period maximum" cases, the generator sets `hours_worked` to 12.00 on the effective rows of the chosen employee-period before payroll inputs are built. This is a labelled edit made at generation time (ground truth lists the payroll input), not a later overwrite.


## LeaveRecord
Transaction table. One row per leave request for a salaried employee, always inside a single pay period. Rows are never edited: a change is a new correction row that points to the original.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| leave_id | string | yes | LV-000001 | PK | matches ^LV-\d{6}$, immutable |
| employee_id | string | yes | existing EMP- id | no | FK to Employee; the employee's pay_type must be salaried |
| pay_period_id | string | yes | existing PP- id | no | FK to PayPeriod; start_date and end_date must both fall inside the period |
| leave_type | enum | yes | annual, sick, unpaid | no | one of the allowed values |
| start_date | date | yes | YYYY-MM-DD | no | on or after hire_date and not after termination_date |
| end_date | date | yes | YYYY-MM-DD | no | on or after start_date |
| days | integer | yes | working days (Monday to Friday) | no | equals the number of working days from start_date to end_date inclusive; at least 1 |
| entry_type | enum | yes | original, correction | no | one of the allowed values |
| related_leave_id | string | optional | existing LV- id | no | FK to LeaveRecord (self); required for correction and null for original; must point to an original record of the same employee |
| submitted_at | timestamp | yes | UTC | no | a late submission is one after the period's submission_deadline |
| approval_status | enum | yes | approved, pending, rejected | no | one of the allowed values; set when the row is created |
| approved_by | string | optional | existing EMP- id | no | FK to Employee; required when approved or rejected; must be the employee's manager_id |
| approved_at | timestamp | optional | UTC | no | required when approved_by is set; on or after submitted_at |

Rules:
- Approved leave records of one employee must not overlap in dates, apart from a correction replacing its original.
- Effective leave is the correction if approved, otherwise the original if approved. Pending and rejected rows never count.
- Only effective unpaid leave produces a deduction. Each effective unpaid leave record has exactly one unpaid_leave Deduction, linked by leave_id. A second one is the "leave deduction applied twice" anomaly.
- Paid leave (annual, sick) reduces no pay.


## Allowance
Transaction table. One row per allowance granted to an employee for a pay period. Rows are never edited: a change is a new correction row that points to the original.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| allowance_id | string | yes | ALW-000001 | PK | matches ^ALW-\d{6}$, immutable |
| employee_id | string | yes | existing EMP- id | no | FK to Employee; must be eligible for the allowance type (see rules) |
| pay_period_id | string | yes | existing PP- id | no | FK to PayPeriod |
| allowance_type | enum | yes | transport, meal, remote_work, shift | no | one of the allowed values |
| units | integer | yes | count (days or 1) | no | at least 1; for meal and shift equals the days with effective time entries in the period |
| unit_amount | decimal(10,2) | yes | INR per unit | no | equals the configured rate for the allowance type |
| amount | decimal(12,2) | yes | INR | no | equals units x unit_amount |
| entry_type | enum | yes | original, correction, duplicate_submission | no | one of the allowed values |
| related_allowance_id | string | optional | existing ALW- id | no | FK to Allowance (self); required for correction and duplicate_submission, null for original; must point to an original of the same employee, period and type |
required for correction and null for original; must point to an original of the same employee, period and type |
| created_at | timestamp | yes | UTC | no | on or after the pay period start |
| approval_status | enum | yes | approved, pending, rejected | no | one of the allowed values; set when the row is created |
| approved_by | string | optional | existing EMP- id | no | FK to Employee; required when approved or rejected; must be the employee's manager_id |
| approved_at | timestamp | optional | UTC | no | required when approved_by is set; on or after created_at |

Eligibility rules (defined in config.py and decisions.md, checked by a validation rule):
- transport: all active employees, 1 unit per period, INR 2,000.
- meal: hourly employees only, 1 unit per day worked, INR 100.
- remote_work: salaried employees in the Corporate pay group, 1 unit per period, INR 1,500.
- shift: hourly employees in the Operations pay group, 1 unit per day worked, INR 250.

Uniqueness rules beyond the primary key:
- At most one original per (employee_id, pay_period_id, allowance_type). A second original is the "same allowance duplicated" anomaly.
- Only one approved row per (employee_id, pay_period_id, allowance_type) should count. A second approved row is a `duplicate_submission` and is the "same allowance duplicated" anomaly, caught by VR-006.

Effective allowance: the correction if approved, otherwise the original if approved. Pending and rejected rows never count toward payroll.

For the group heads, who have no manager, approved_by is an hr_partner.

## Deduction
Transaction table. One row per deduction applied to an employee for a pay period. Rows are never edited: a duplicate is a new row that points to the original.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| deduction_id | string | yes | DED-000001 | PK | matches ^DED-\d{6}$, immutable |
| employee_id | string | yes | existing EMP- id | no | FK to Employee |
| pay_period_id | string | yes | existing PP- id | no | FK to PayPeriod |
| deduction_type | enum | yes | professional_tax, provident_fund, loan_recovery, unpaid_leave | no | one of the allowed values |
| leave_id | string | optional | existing LV- id | no | FK to LeaveRecord; required for unpaid_leave, null otherwise |
| units | decimal(5,2) | yes | 1 or leave days | no | 1.00 except unpaid_leave, where it equals the leave record's days |
| unit_amount | decimal(10,2) | yes | INR per unit | no | see eligibility rules |
| amount | decimal(12,2) | yes | INR | no | equals units x unit_amount |
| entry_type | enum | yes | original, correction, duplicate_submission | no | one of the allowed values |
| related_deduction_id | string | optional | existing DED- id | no | FK to Deduction (self); set for duplicate_submission, null for original |
| created_at | timestamp | yes | UTC | no | after the pay period end |
| approval_status | enum | yes | approved, pending, rejected | no | one of the allowed values |
| approved_by | string | optional | existing EMP- id | no | FK to Employee; an hr_partner; null when pending |
| approved_at | timestamp | optional | UTC | no | required when approved_by is set; on or after created_at |

Eligibility rules (defined in config.py):
- professional_tax: all active employees, 1 unit per period, INR 200. Always approved.
- provident_fund: salaried employees, 12% of monthly_salary. Always approved.
- loan_recovery: about 8% of employees, a fixed monthly installment of 1,000, 2,000, 3,000 or 5,000. Goes through the normal approval draw.
- unpaid_leave: one row per effective approved unpaid leave record, units = leave days, unit_amount = monthly_salary / working days in the period. Always approved.

Uniqueness rules beyond the primary key:
- At most one approved unpaid_leave deduction per leave_id. A second one is the "leave deduction applied twice" anomaly, caught by VR-008.

Only approved rows count toward payroll. Pending and rejected rows never count.

## PayrollInput
Derived table. One row per employee per pay period in which the employee was active, aggregated from approved source rows. Amounts are calculated from the source tables, never generated independently.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| payroll_input_id | string | yes | PIN-EMP-000001-2026-01 | PK | matches ^PIN-EMP-\d{6}-\d{4}-\d{2}$; equals PIN-<employee_id>-<year>-<month>; immutable |
| employee_id | string | yes | existing EMP- id | no | FK to Employee; unique together with pay_period_id |
| pay_period_id | string | yes | existing PP- id | no | FK to PayPeriod |
| pay_group_id | string | yes | existing PG- id | no | FK to PayGroup |
| pay_type | enum | yes | hourly, salaried | no | equals the employee's pay_type |
| regular_hours | decimal(6,2) | yes | hours | no | sum over counted time entries of min(hours, standard_hours_per_day) per day; 0 for salaried |
| overtime_hours | decimal(6,2) | yes | hours | no | sum of hours above standard_hours_per_day per day; 0 for salaried |
| base_pay | decimal(12,2) | yes | INR | no | hourly: regular_hours x hourly_rate; salaried: monthly_salary x active working days / period working days |
| overtime_pay | decimal(12,2) | yes | INR | no | overtime_hours x hourly_rate x overtime_multiplier; 0 for salaried |
| allowance_total | decimal(12,2) | yes | INR | no | sum of approved Allowance amounts for the employee and period |
| deduction_total | decimal(12,2) | yes | INR | no | sum of approved Deduction amounts for the employee and period |
| gross_pay | decimal(12,2) | yes | INR | no | equals base_pay + overtime_pay + allowance_total |
| net_pay | decimal(12,2) | yes | INR | no | equals gross_pay - deduction_total |
| unapproved_source_count | integer | yes | count | no | number of counted time entries that are not approved; 0 for a valid input, above 0 triggers VR-007 |
| status | enum | yes | draft, validated, held, approved, rejected, exported | no | one of the allowed values; current state only, see lifecycle |
| aggregated_at | timestamp | yes | UTC | no | after the pay period end_date |

Counted time entries: the approved correction if there is one, otherwise the approved original. Duplicate submissions, pending rows and rejected rows never count. Total hours (regular + overtime) above the pay group's max_hours_per_period trigger VR-004.

Lifecycle: draft -> validated -> held | approved | rejected -> exported.
- validated -> validated: a correction that recomputed the input (the event note stores net pay before and after).
- held: an open blocking exception exists for the input or its employee.
- approved or rejected: decided by an HR partner (an Approval row).
- exported: only from approved, in a PayrollExport batch.
- An input that stays in validated has not been decided yet, and is never exported.
Every transition is a row in `status_events`.

Reconciliation rules (checked by VR-009 and validate_dataset.py):
- Stored amounts and hours equal a fresh recomputation from the approved source rows.
- net_pay equals gross_pay - deduction_total.
- For each export, the sum of its lines equals the export totals.


## ValidationRule
Master table. The catalogue of validation checks run before payroll export. 10 rows. Rows are never edited: a change to a rule would be a new row with a later effective_from.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| rule_id | string | yes | VR-001 | PK | matches ^VR-\d{3}$, immutable |
| name | string | yes | short title | no | non-empty |
| severity | enum | yes | blocking, warning | no | one of the allowed values |
| target_table | enum | yes | employees, time_entries, allowances, deductions, payroll_inputs | no | the table whose rows the rule flags |
| description | string | yes | what the rule checks | no | non-empty |
| status | enum | yes | active | no | one of the allowed values |
| effective_from | date | yes | YYYY-MM-DD | no | on or before the first pay period start |

Severity effect:
- blocking: while the exception is open, the payroll input is held and cannot be approved or exported.
- warning: the exception is recorded but does not stop approval or export.

Catalogue:

| rule_id | name | severity | target_table | What it checks |
|---|---|---|---|---|
| VR-001 | Missing bank details | blocking | employees | bank_account_number or bank_ifsc is empty |
| VR-002 | Missing tax id | blocking | employees | tax_id is empty |
| VR-003 | Duplicate time submission | warning | time_entries | more than one non-correction entry for the same employee and day; the later one is flagged |
| VR-004 | Hours exceed period maximum | blocking | payroll_inputs | regular + overtime hours above the pay group's max_hours_per_period |
| VR-005 | Daily hours outlier | warning | time_entries | an original entry has more than 14 hours in one day |
| VR-006 | Duplicate allowance | blocking | allowances | more than one approved allowance of the same type for an employee and period; the later one is flagged |
| VR-007 | Unapproved source in payroll input | blocking | payroll_inputs | unapproved_source_count is above 0 |
| VR-008 | Leave deduction applied twice | blocking | deductions | more than one approved unpaid_leave deduction for the same leave_id; the later one is flagged |
| VR-009 | Payroll totals do not reconcile | blocking | payroll_inputs | stored amounts differ from a recomputation by more than INR 0.01, or net_pay is not gross_pay - deduction_total |
| VR-010 | Late time submission | warning | time_entries | an original entry was submitted after the period's submission_deadline |

Notes:
- The five required edge cases are detected by VR-004 (hours exceed period maximum), VR-006 (same allowance duplicated), VR-007 (unapproved time exported), VR-008 (leave deduction twice) and VR-009 (totals fail to reconcile).
- The tolerance (0.01), the outlier threshold (14 hours) and the submission grace period (5 days) are in config.py, not stored per rule.


## Exception
Event table. One row per finding raised by a validation rule. The row holds the current status; every status change is also a row in `status_events`, so history is not lost.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| exception_id | string | yes | EXC-000001 | PK | matches ^EXC-\d{6}$, immutable |
| rule_id | string | yes | existing VR- id | no | FK to ValidationRule |
| severity | enum | yes | blocking, warning | no | copied from the rule |
| table_name | enum | yes | employees, time_entries, allowances, deductions, payroll_inputs | no | equals the rule's target_table |
| record_id | string | yes | id of the flagged record | no | exists in table_name |
| employee_id | string | yes | existing EMP- id | no | FK to Employee |
| pay_period_id | string | optional | existing PP- id | no | FK to PayPeriod; null for employee-level findings (VR-001, VR-002) |
| payroll_input_id | string | optional | existing PIN- id | no | FK to PayrollInput; null for employee-level findings, which block every input of that employee |
| detail | string | yes | one sentence with the values that triggered the rule | no | non-empty |
| status | enum | yes | open, resolved, waived | no | one of the allowed values |
| resolution | enum | optional | corrected, waived | no | null while open; corrected when status is resolved, waived when status is waived |
| detected_at | timestamp | yes | UTC | no | after the payroll input's aggregated_at |
| resolved_at | timestamp | optional | UTC | no | required when status is not open; on or after detected_at |
| resolved_by | string | optional | existing EMP- id | no | FK to Employee; an hr_partner; required when status is not open |

Lifecycle: open -> resolved, or open -> waived.
- resolved (resolution corrected): only for blocking rules VR-006, VR-007, VR-008 and VR-009. The payroll input is recomputed without the duplicate row (VR-006, VR-008) or from approved rows only (VR-007, VR-009). The before and after net pay are stored in a `validated -> validated` event in `status_events`.
- waived: only for warning rules. A blocking exception is never waived.
- open: VR-001, VR-002 and VR-004 need new source data, so they stay open and the input stays held. Warnings that are not waived also stay open and do not block anything.

Effect on payroll:
- A payroll input with an open blocking exception (its own, or an employee-level one) has status held and is not exported.
- One decision is made per payroll input, so all its correctable defects are cleared together.


## Approval
Event table, append-only. One row per HR decision on a payroll input. Approvals of source records (time, leave, allowance, deduction) are stored on those rows. Exception resolutions are stored on the exception and in `status_events`, not here. Rows are never edited or deleted.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| approval_id | string | yes | APR-000001 | PK | matches ^APR-\d{6}$, immutable |
| entity_type | enum | yes | payroll_input | no | one of the allowed values |
| entity_id | string | yes | existing PIN- id | no | FK to PayrollInput (entity_type says which table) |
| approver_id | string | yes | existing EMP- id | no | FK to Employee; an hr_partner |
| decision | enum | yes | approved, rejected | no | one of the allowed values |
| decided_at | timestamp | yes | UTC | no | after the input's aggregated_at |
| comment | string | optional | free text | no | empty in generated data |

Rules:
- An input gets an Approval row only when it has no open blocking exception. Held inputs never get one.
- About 3% of eligible inputs have no decision yet. They stay in status validated and are never exported.
- An input can be exported only if it has exactly one approved decision (checked by `exported_only_if_approved_once`).
- Each decision moves the input to approved or rejected, and the move is a row in `status_events`.



## PayrollExport
Event table. One row per export for a pay period (3 rows). Only approved payroll inputs without open blocking exceptions are included. Rows are never edited.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| export_id | string | yes | PEX-2026-000001 | PK | matches ^PEX-\d{4}-\d{6}$; the counter increases across periods; immutable |
| pay_period_id | string | yes | existing PP- id | yes | FK to PayPeriod; one export per period |
| status | enum | yes | generated | no | one of the allowed values |
| record_count | integer | yes | count | no | equals the number of export lines with this export_id |
| total_gross | decimal(14,2) | yes | INR | no | equals the sum of gross_pay of its lines |
| total_net | decimal(14,2) | yes | INR | no | equals the sum of net_pay of its lines |
| reconciliation_status | enum | yes | reconciled | no | the generator computes the line sums against the totals; a mismatch would fail the allowed-values check |
| generated_at | timestamp | yes | UTC | no | after the latest approval of the inputs it contains |
| generated_by | string | yes | SYSTEM | no | the export is a system step, so this is not an Employee id and has no foreign key |

Rules:
- An input is exported only when its status is approved: it has exactly one approved Approval row, no open blocking exception of its own or on its employee, and `unapproved_source_count` of 0.
- Held, rejected and undecided inputs are never exported. The pipeline excludes them by construction, and `validate_dataset.py` checks the result afterwards (checks `exported_only_if_approved_once`, `no_export_with_open_blocking_exception` and `exported_inputs_reconcile_to_source`).
- The injected defects are caught by VR-004, VR-006 to VR-009 before export. Those that are corrected are recomputed first, so exported figures are correct. Those that are not corrected stay held.
- Exporting moves each input from approved to exported and the period from open to exported. Both moves are rows in `status_events`.

## PayrollExportLine
Supporting table. One row per exported payroll input. It makes every exported amount traceable and lets the export totals be reconciled.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| export_line_id | string | yes | PXL-000001 | PK | matches ^PXL-\d{6}$, immutable |
| export_id | string | yes | existing PEX- id | no | FK to PayrollExport |
| payroll_input_id | string | yes | existing PIN- id | yes | FK to PayrollInput; an input appears in at most one line, and only when its status is exported |
| employee_id | string | yes | existing EMP- id | no | FK to Employee; equals the input's employee |
| bank_account_number | string | yes | 12 digits | no | copied from Employee at export time; never empty |
| bank_ifsc | string | yes | 4 letters + 0 + 6 digits | no | copied from Employee at export time; never empty |
| gross_pay | decimal(12,2) | yes | INR | no | equals the payroll input's gross_pay |
| net_pay | decimal(12,2) | yes | INR | no | equals the payroll input's net_pay |

The employee's tax_id must also be present for every line (checked by `export_lines_have_bank_and_tax`).

## status_events
Event table, append-only. Every state change of a payroll input, an exception and a pay period is a row here, so history is never overwritten. The current status on the entity row is always equal to the last event.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| event_id | string | yes | EVT-000001 | PK | matches ^EVT-\d{6}$, immutable |
| entity_type | enum | yes | payroll_input, exception, pay_period | no | one of the allowed values |
| entity_id | string | yes | PIN-, EXC- or PP- id | no | must exist in the entity's table (not a database foreign key, because the table depends on entity_type) |
| from_status | string | optional | status value | no | null for the first event of an entity; otherwise equals the previous event's to_status |
| to_status | string | yes | status value | no | the transition must be in the allowed list below |
| event_at | timestamp | yes | UTC | no | not before the previous event of the same entity |
| actor_id | string | yes | EMP- id or SYSTEM | no | an hr_partner for corrections, approvals and waivers; SYSTEM for automatic steps |
| note | string | optional | free text | no | rule ids for held, net_pay before and after for corrections, export id for exported |

Allowed transitions:
- payroll_input: (none) -> draft, draft -> validated, validated -> validated (a correction), validated -> held, validated -> approved, validated -> rejected, approved -> exported.
- exception: (none) -> open, open -> resolved, open -> waived.
- pay_period: open -> exported.

Checked by `lifecycle_transitions_and_event_order`.

## Relationships and cardinality

| Relationship | Cardinality | Optional? | Notes |
|---|---|---|---|
| PayGroup to Employee | 1:N | no | every employee has one pay group |
| Employee to Employee (manager_id) | 1:N | yes | null only for each pay group's head manager |
| Employee to TimeEntry, LeaveRecord, Allowance, Deduction | 1:N | yes | time entries only for hourly staff, leave only for salaried staff |
| PayPeriod to TimeEntry, LeaveRecord, Allowance, Deduction | 1:N | no | |
| Employee and PayPeriod to PayrollInput | N:M, resolved by PayrollInput (bridge) | no | one input per employee per period in which the employee was active |
| TimeEntry to TimeEntry (related_entry_id) | 1:0..1 correction, 1:0..1 duplicate | yes | corrections and duplicates point to the original |
| LeaveRecord to Deduction (leave_id) | 1:0..1 expected | yes | one unpaid_leave deduction per effective unpaid leave record; a second one is the injected anomaly |
| ValidationRule to Exception | 1:N | no | |
| PayrollInput to Exception | 1:N | yes | null for employee-level findings (VR-001, VR-002) |
| PayrollInput to Approval | 1:0..1 | yes | held and undecided inputs have none |
| PayrollExport to PayrollExportLine | 1:N | no | |
| PayrollInput to PayrollExportLine | 1:0..1 | yes | only exported inputs have a line, so the line is the link between an input and an export |
| PayPeriod to PayrollExport | 1:1 | no | |

Effective dates: PayGroup, ValidationRule and the pay period calendar carry `effective_from` or start and end dates. A rule or pay group change would be a new row with a later date, never an edit.

## Ground truth (file, not a table)
`data/<scale>/ground_truth/ground_truth.csv` and `.json`. One row per (record, rule). It is generated beside the data and never joined into any input table.

| Field | Type | Meaning |
|---|---|---|
| issue_type | string | e.g. duplicate_allowance, hours_exceed_period_max, missing_bank_details |
| table_name | string | table of the labelled record |
| record_id | string | id of the labelled record (a payroll input id for aggregate-level cases) |
| expected_rule | string | the VR- rule that must flag the record |
| expected_decision | enum | block_export for blocking rules, warn for warnings |
| injected | boolean | true for the five injected edge cases, false for natural baseline cases |
| note | string | short explanation |