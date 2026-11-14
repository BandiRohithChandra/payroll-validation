# Data Dictionary

All data is synthetic, including identities and bank and tax details. IDs are immutable and zero-padded. Timestamps are UTC ISO 8601, dates are YYYY-MM-DD, and money is in INR with 2 decimals.

## Employee
Master table. One row per employee. Pay group changes and other history are kept as events in later tables, so this row holds the current state only.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| employee_id | string | yes | EMP-000001 | PK | matches ^EMP-\d{6}$, immutable |
| first_name | string | yes | synthetic name list | no | non-empty |
| last_name | string | yes | synthetic name list | no | non-empty |
| email | string | yes | synthetic, @example.com | yes | valid format, lowercase |
| role | enum | yes | employee, manager, hr_partner | no | one of the allowed values |
| manager_id | string | optional | existing EMP- id | no | FK to Employee (self); null for top-level managers; cannot be the employee's own id |
| pay_group_id | string | yes | existing PG- id | no | FK to PayGroup |
| pay_type | enum | yes | hourly, salaried | no | one of the allowed values |
| hourly_rate | decimal(10,2) | optional | INR per hour | no | required and greater than 0 when pay_type is hourly, null otherwise |
| monthly_salary | decimal(12,2) | optional | INR per month | no | required and greater than 0 when pay_type is salaried, null otherwise |
| hire_date | date | yes | YYYY-MM-DD | no | before the first pay period start for staff hired before the data begins |
| termination_date | date | optional | YYYY-MM-DD | no | null for active staff; after hire_date when set |
| status | enum | yes | active, terminated | no | terminated if and only if termination_date is set |
| bank_account_number | string | optional | synthetic, 12 digits | no | required before a payroll export; a missing value is a planted validation case |
| bank_ifsc | string | optional | synthetic, 4 letters + 0 + 6 digits | no | required together with bank_account_number |
| tax_id | string | optional | synthetic, TIN- + 8 digits | yes | required before a payroll export; a missing value is a planted validation case |

Notes:
- Bank and tax fields are optional on purpose. The workflow checks for them before export, so a baseline row can lack them only when a ground-truth label says so.
- manager_id gives the approval chain, because an employee's time and leave are approved by their manager and payroll inputs by an hr_partner.
- Bank accounts and tax IDs use fictional formats, so no real person or account can match them.


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
| status | enum | yes | open, validating, approved, exported | no | one of the allowed values; moves forward only |

Lifecycle: open -> validating -> approved -> exported. A period can only be exported after it is approved. Each move is recorded as an Approval or PayrollExport row, so the history is never overwritten and status only shows the current state.

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
| hours_worked | decimal(4,2) | yes | hours | no | greater than 0 and at most 24 |
| entry_type | enum | yes | original, correction, duplicate_submission | no | one of the allowed values |
| related_entry_id | string | optional | existing TIME- id | no | FK to TimeEntry (self); required for correction and duplicate_submission and null for original; must point to an original entry of the same employee and work_date |
| submitted_at | timestamp | yes | UTC | no | on or after work_date; a submission after the period's submission_deadline is late |
| approval_status | enum | yes | approved, pending, rejected | no | one of the allowed values; set when the row is created |
| approved_by | string | optional | existing EMP- id | no | FK to Employee; required when approved or rejected; must be the employee's manager_id |
| approved_at | timestamp | optional | UTC | no | required when approved_by is set; on or after submitted_at |

Uniqueness rules beyond the primary key:
- At most one original entry per (employee_id, work_date).
- At most one correction per original entry.

Effective hours for an employee on a day: the correction if it is approved, otherwise the original if it is approved. A duplicate_submission never counts toward hours. Duplicates are expected in the baseline data and are caught by the duplicate-hours validation rule. Overtime is calculated during aggregation, never stored here.


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
| entry_type | enum | yes | original, correction | no | one of the allowed values |
| related_allowance_id | string | optional | existing ALW- id | no | FK to Allowance (self); required for correction and null for original; must point to an original of the same employee, period and type |
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
- At most one correction per original.

Effective allowance: the correction if approved, otherwise the original if approved. Pending and rejected rows never count toward payroll.


## PayrollInput
Derived table. One row per employee per pay period, aggregated from the effective approved source records. No value is generated independently, and every amount can be recomputed from the source tables.

| Field | Type | Required | Allowed / format | Unique | Validation |
|---|---|---|---|---|---|
| payroll_input_id | string | yes | PIN-EMP-000001-2026-01 | PK | matches ^PIN-EMP-\d{6}-\d{4}-\d{2}$; must equal PIN-<employee_id>-<year>-<month of the period>; immutable |
| employee_id | string | yes | existing EMP- id | no | FK to Employee; unique together with pay_period_id |
| pay_period_id | string | yes | existing PP- id | no | FK to PayPeriod |
| pay_group_id | string | yes | existing PG- id | no | FK to PayGroup; the employee's pay group for this period |
| pay_type | enum | yes | hourly, salaried | no | equals the employee's pay_type |
| regular_hours | decimal(6,2) | yes | hours | no | sum over effective approved time entries of min(hours, standard_hours_per_day) per day; 0 for salaried |
| overtime_hours | decimal(6,2) | yes | hours | no | sum of hours above standard_hours_per_day per day; 0 for salaried |
| total_hours | decimal(6,2) | yes | hours | no | equals regular_hours + overtime_hours; flagged when above the pay group's max_hours_per_period |
| base_pay | decimal(12,2) | yes | INR | no | hourly: regular_hours x hourly_rate; salaried: monthly_salary |
| overtime_pay | decimal(12,2) | yes | INR | no | overtime_hours x hourly_rate x overtime_multiplier; 0 for salaried |
| allowances_total | decimal(12,2) | yes | INR | no | sum of effective approved Allowance amounts |
| deductions_total | decimal(12,2) | yes | INR | no | sum of effective approved Deduction amounts |
| gross_pay | decimal(12,2) | yes | INR | no | equals base_pay + overtime_pay + allowances_total |
| net_pay | decimal(12,2) | yes | INR | no | equals gross_pay - deductions_total; must not be negative |
| unpaid_leave_days | decimal(5,2) | yes | days | no | sum of days of effective approved unpaid leave; for information, not subtracted again |
| time_entry_count | integer | yes | count | no | number of effective approved time entries used |
| allowance_count | integer | yes | count | no | number of effective approved allowances used |
| deduction_count | integer | yes | count | no | number of effective approved deductions used |
| status | enum | yes | calculated, flagged, approved, exported | no | one of the allowed values; moves forward only, except that flagged returns to calculated when its exceptions are resolved |
| calculated_at | timestamp | yes | UTC | no | on or after the pay period's end_date |

Lifecycle: calculated -> flagged (one or more open Exceptions) -> calculated (resolved) -> approved (HR partner Approval) -> exported (PayrollExport). A row can only become approved when it has no open exceptions and every source record it used is approved. Each transition is stored as an Approval or PayrollExport row.

Reconciliation rules (checked by validate.py):
- Every amount and count equals a fresh recomputation from the source tables.
- For each pay period, the sum of net_pay over exported rows equals the total of its PayrollExport.
- Source records that are pending, rejected, or superseded by a correction never contribute to any total.

