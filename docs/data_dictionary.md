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