"""Central configuration. All rules and volumes live here (see docs/decisions.md)."""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

SEED = 20261022
YEAR = 2026
MONTHS = (1, 2, 3)
SUBMISSION_GRACE_DAYS = 5  # a submission after period end + 5 days is late


@dataclass(frozen=True)
class PayPeriodDef:
    pay_period_id: str
    start_date: date
    end_date: date
    working_days: int          # Monday to Friday, no holiday calendar
    submission_deadline: date


def _build_periods():
    periods = []
    for month in MONTHS:
        last_day = calendar.monthrange(YEAR, month)[1]
        start, end = date(YEAR, month, 1), date(YEAR, month, last_day)
        working = sum(1 for d in range(last_day)
                      if (start + timedelta(days=d)).weekday() < 5)
        periods.append(PayPeriodDef(
            pay_period_id=f"PP-{YEAR}-{month:02d}",
            start_date=start,
            end_date=end,
            working_days=working,
            submission_deadline=end + timedelta(days=SUBMISSION_GRACE_DAYS),
        ))
    return tuple(periods)


PAY_PERIODS = _build_periods()
PERIOD_START = PAY_PERIODS[0].start_date
PERIOD_END = PAY_PERIODS[-1].end_date


@dataclass(frozen=True)
class PayGroupDef:
    pay_group_id: str
    name: str
    share: float                  # share of all employees
    hourly_share: float           # share of this group paid hourly
    standard_hours_per_day: Decimal
    max_hours_per_period: Decimal
    overtime_multiplier: Decimal
    payday_day: int               # day of the month after the period ends


PAY_GROUPS = (
    PayGroupDef("PG-001", "Corporate", 0.40, 0.10, Decimal("8.00"), Decimal("210.00"), Decimal("1.50"), 5),
    PayGroupDef("PG-002", "Operations", 0.40, 0.62, Decimal("8.00"), Decimal("230.00"), Decimal("2.00"), 7),
    PayGroupDef("PG-003", "Contract", 0.20, 0.45, Decimal("8.00"), Decimal("200.00"), Decimal("1.25"), 10),
)
PAY_GROUP_BY_ID = {g.pay_group_id: g for g in PAY_GROUPS}


@dataclass(frozen=True)
class Scale:
    name: str
    n_employees: int
    anomalies_per_type: int


SCALES = {
    "starter": Scale("starter", n_employees=300, anomalies_per_type=3),
    "full": Scale("full", n_employees=3000, anomalies_per_type=40),
}

# ---------------------------------------------------------------- employees
HOURLY_RATE_RANGE = (150, 600)         # INR per hour
MONTHLY_SALARY_RANGE = (25000, 150000)  # INR per month
ROLE_SHARES = {"hr_partner": 0.01, "manager": 0.08}  # the rest are employees
PARTIAL_PERIOD_SHARE = 0.02            # hired or terminated during the period
MISSING_BANK_RATE = 0.01               # planted validation cases, labelled
MISSING_TAX_RATE = 0.01

# ------------------------------------------------------ source records
APPROVAL_SHARES = (("approved", 0.93), ("pending", 0.05), ("rejected", 0.02))
CORRECTION_RATE = 0.02                 # share of time entries with a correction
DUPLICATE_RATE = 0.01                  # share of time entries with a duplicate submission
LATE_SUBMISSION_RATE = 0.03
OVERTIME_DAY_RATE = 0.12               # share of days with hours above standard
DAILY_OUTLIER_RATE = 0.002             # days with hours above the outlier threshold

# ---------------------------------------------------------------- leave
UNPAID_LEAVE_RATE = 0.06               # salaried employees with unpaid leave per period
PAID_LEAVE_RATE = 0.18                 # salaried employees with annual or sick leave per period

# ------------------------------------------------- allowances and deductions
ALLOWANCE_RATES = {
    "transport": Decimal("2000.00"),    # all active, 1 unit per period
    "meal": Decimal("100.00"),          # hourly, per day worked
    "remote_work": Decimal("1500.00"),  # salaried in Corporate, 1 unit per period
    "shift": Decimal("250.00"),         # hourly in Operations, per day worked
}
PROVIDENT_FUND_RATE = Decimal("0.12")   # salaried, of monthly_salary
PROFESSIONAL_TAX = Decimal("200.00")    # all active
LOAN_SHARE = 0.08                       # employees with a loan installment
LOAN_INSTALLMENTS = (1000, 2000, 3000, 5000)

# ------------------------------------------------------------- validation
DAILY_HOURS_OUTLIER = Decimal("14.00")
RECONCILIATION_TOLERANCE = Decimal("0.01")
MIN_NET_PAY = Decimal("0.00")

# ------------------------------------------------- exceptions and export
BLOCKING_RESOLVE_RATE = 0.85           # blocking exceptions fixed by a correction or rejection
WARNING_WAIVE_RATE = 0.50              # warning exceptions waived by an HR partner


# ------------------------------------------------------------- time entries
ABSENCE_RATE = 0.04                    # working days an hourly employee has no entry