CREATE TABLE pay_groups (
  pay_group_id TEXT NOT NULL PRIMARY KEY,
  name TEXT,
  pay_frequency TEXT,
  standard_hours_per_day NUMERIC(14,2),
  max_hours_per_period NUMERIC(14,2),
  overtime_multiplier NUMERIC(14,2),
  payday_day INTEGER,
  effective_from DATE,
  status TEXT
);

CREATE TABLE pay_periods (
  pay_period_id TEXT NOT NULL PRIMARY KEY,
  start_date DATE,
  end_date DATE,
  working_days INTEGER,
  submission_deadline DATE,
  status TEXT
);

CREATE TABLE employees (
  employee_id TEXT NOT NULL PRIMARY KEY,
  first_name TEXT,
  last_name TEXT,
  email TEXT,
  role TEXT,
  manager_id TEXT,
  pay_group_id TEXT,
  pay_type TEXT,
  hourly_rate NUMERIC(14,2),
  monthly_salary NUMERIC(14,2),
  hire_date DATE,
  termination_date DATE,
  status TEXT,
  bank_account_number TEXT,
  bank_ifsc TEXT,
  tax_id TEXT,
  FOREIGN KEY (manager_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_group_id) REFERENCES pay_groups (pay_group_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE leave_records (
  leave_id TEXT NOT NULL PRIMARY KEY,
  employee_id TEXT,
  pay_period_id TEXT,
  leave_type TEXT,
  start_date DATE,
  end_date DATE,
  days INTEGER,
  entry_type TEXT,
  related_leave_id TEXT,
  submitted_at TIMESTAMP,
  approval_status TEXT,
  approved_by TEXT,
  approved_at TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_period_id) REFERENCES pay_periods (pay_period_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (related_leave_id) REFERENCES leave_records (leave_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (approved_by) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE time_entries (
  time_entry_id TEXT NOT NULL PRIMARY KEY,
  employee_id TEXT,
  pay_period_id TEXT,
  work_date DATE,
  hours_worked NUMERIC(14,2),
  entry_type TEXT,
  related_entry_id TEXT,
  submitted_at TIMESTAMP,
  approval_status TEXT,
  approved_by TEXT,
  approved_at TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_period_id) REFERENCES pay_periods (pay_period_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (related_entry_id) REFERENCES time_entries (time_entry_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (approved_by) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE allowances (
  allowance_id TEXT NOT NULL PRIMARY KEY,
  employee_id TEXT,
  pay_period_id TEXT,
  allowance_type TEXT,
  units INTEGER,
  unit_amount NUMERIC(14,2),
  amount NUMERIC(14,2),
  entry_type TEXT,
  related_allowance_id TEXT,
  created_at TIMESTAMP,
  approval_status TEXT,
  approved_by TEXT,
  approved_at TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_period_id) REFERENCES pay_periods (pay_period_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (related_allowance_id) REFERENCES allowances (allowance_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (approved_by) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE deductions (
  deduction_id TEXT NOT NULL PRIMARY KEY,
  employee_id TEXT,
  pay_period_id TEXT,
  deduction_type TEXT,
  leave_id TEXT,
  units NUMERIC(14,2),
  unit_amount NUMERIC(14,2),
  amount NUMERIC(14,2),
  entry_type TEXT,
  related_deduction_id TEXT,
  created_at TIMESTAMP,
  approval_status TEXT,
  approved_by TEXT,
  approved_at TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_period_id) REFERENCES pay_periods (pay_period_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (leave_id) REFERENCES leave_records (leave_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (related_deduction_id) REFERENCES deductions (deduction_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (approved_by) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE payroll_inputs (
  payroll_input_id TEXT NOT NULL PRIMARY KEY,
  employee_id TEXT,
  pay_period_id TEXT,
  pay_group_id TEXT,
  pay_type TEXT,
  regular_hours NUMERIC(14,2),
  overtime_hours NUMERIC(14,2),
  base_pay NUMERIC(14,2),
  overtime_pay NUMERIC(14,2),
  allowance_total NUMERIC(14,2),
  deduction_total NUMERIC(14,2),
  gross_pay NUMERIC(14,2),
  net_pay NUMERIC(14,2),
  unapproved_source_count INTEGER,
  status TEXT,
  aggregated_at TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_period_id) REFERENCES pay_periods (pay_period_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_group_id) REFERENCES pay_groups (pay_group_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE validation_rules (
  rule_id TEXT NOT NULL PRIMARY KEY,
  name TEXT,
  severity TEXT,
  target_table TEXT,
  description TEXT,
  status TEXT,
  effective_from DATE
);

CREATE TABLE exceptions (
  exception_id TEXT NOT NULL PRIMARY KEY,
  rule_id TEXT,
  severity TEXT,
  table_name TEXT,
  record_id TEXT,
  employee_id TEXT,
  pay_period_id TEXT,
  payroll_input_id TEXT,
  detail TEXT,
  status TEXT,
  resolution TEXT,
  detected_at TIMESTAMP,
  resolved_at TIMESTAMP,
  resolved_by TEXT,
  FOREIGN KEY (rule_id) REFERENCES validation_rules (rule_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (employee_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (pay_period_id) REFERENCES pay_periods (pay_period_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (payroll_input_id) REFERENCES payroll_inputs (payroll_input_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (resolved_by) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE approvals (
  approval_id TEXT NOT NULL PRIMARY KEY,
  entity_type TEXT,
  entity_id TEXT,
  approver_id TEXT,
  decision TEXT,
  decided_at TIMESTAMP,
  comment TEXT,
  FOREIGN KEY (approver_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (entity_id) REFERENCES payroll_inputs (payroll_input_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE payroll_exports (
  export_id TEXT NOT NULL PRIMARY KEY,
  pay_period_id TEXT,
  status TEXT,
  record_count INTEGER,
  total_gross NUMERIC(14,2),
  total_net NUMERIC(14,2),
  reconciliation_status TEXT,
  generated_at TIMESTAMP,
  generated_by TEXT,
  FOREIGN KEY (pay_period_id) REFERENCES pay_periods (pay_period_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE payroll_export_lines (
  export_line_id TEXT NOT NULL PRIMARY KEY,
  export_id TEXT,
  payroll_input_id TEXT,
  employee_id TEXT,
  bank_account_number TEXT,
  bank_ifsc TEXT,
  gross_pay NUMERIC(14,2),
  net_pay NUMERIC(14,2),
  FOREIGN KEY (export_id) REFERENCES payroll_exports (export_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (payroll_input_id) REFERENCES payroll_inputs (payroll_input_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (employee_id) REFERENCES employees (employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE status_events (
  event_id TEXT NOT NULL PRIMARY KEY,
  entity_type TEXT,
  entity_id TEXT,
  from_status TEXT,
  to_status TEXT,
  event_at TIMESTAMP,
  actor_id TEXT,
  note TEXT
);
