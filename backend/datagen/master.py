"""Master data: PayGroup, PayPeriod and Employee (see docs/data_dictionary.md)."""
import string
from datetime import date, timedelta
from decimal import Decimal

import config

CENT = Decimal("0.01")
HIRE_FLOOR = date(2018, 1, 1)
HIRE_SPAN = (date(2025, 12, 31) - HIRE_FLOOR).days

FIRST_NAMES = (
    "Aarav", "Vivaan", "Ananya", "Diya", "Rohan", "Priya", "Karan", "Sneha",
    "Arjun", "Kavya", "Rahul", "Meera", "Imran", "Fatima", "Suresh", "Lakshmi",
    "Vikram", "Anjali", "Manoj", "Pooja", "Harsha", "Divya", "Nikhil", "Swati",
)
LAST_NAMES = (
    "Sharma", "Reddy", "Rao", "Khan", "Patel", "Nair", "Iyer", "Gupta",
    "Singh", "Das", "Mehta", "Verma", "Joshi", "Menon", "Naidu", "Kapoor",
)


def generate_pay_groups():
    return [{
        "pay_group_id": g.pay_group_id,
        "name": g.name,
        "pay_frequency": "monthly",
        "standard_hours_per_day": g.standard_hours_per_day,
        "max_hours_per_period": g.max_hours_per_period,
        "overtime_multiplier": g.overtime_multiplier,
        "payday_day": g.payday_day,
        "effective_from": config.PERIOD_START,
        "status": "active",
    } for g in config.PAY_GROUPS]


def generate_pay_periods():
    return [{
        "pay_period_id": p.pay_period_id,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "working_days": p.working_days,
        "submission_deadline": p.submission_deadline,
        "status": "open",  # moved forward later by Approval and PayrollExport events
    } for p in config.PAY_PERIODS]


def generate_employees(rng, ids, scale):
    """Returns (employees, planted). planted lists the deliberate missing bank
    and tax cases, to be turned into ground truth later."""
    n = scale.n_employees
    emp_ids = [ids.next("employee") for _ in range(n)]

    # pay groups, shuffled so ids do not line up with groups
    counts = [round(n * g.share) for g in config.PAY_GROUPS]
    counts[-1] = n - sum(counts[:-1])
    group_of = [g.pay_group_id for g, c in zip(config.PAY_GROUPS, counts) for _ in range(c)]
    rng.shuffle(group_of)
    members = {g.pay_group_id: [i for i in range(n) if group_of[i] == g.pay_group_id]
               for g in config.PAY_GROUPS}

    # roles: managers in every group, HR partners in the first group (Corporate)
    role = ["employee"] * n
    managers = {}
    for gid, idxs in members.items():
        k = max(2, round(len(idxs) * config.ROLE_SHARES["manager"]))
        managers[gid] = sorted(rng.sample(idxs, k))
        for i in managers[gid]:
            role[i] = "manager"
    pool = [i for i in members[config.PAY_GROUPS[0].pay_group_id] if role[i] == "employee"]
    for i in sorted(rng.sample(pool, max(2, round(n * config.ROLE_SHARES["hr_partner"])))):
        role[i] = "hr_partner"

    # employees who start or leave during the period (never managers or HR partners)
    candidates = [i for i in range(n) if role[i] == "employee"]
    k = round(n * config.PARTIAL_PERIOD_SHARE)
    partial = rng.sample(candidates, k)
    hired_in_period = set(partial[: k // 2])
    terminated = set(partial[k // 2:])

    # deliberate missing fields (labelled later); fixed counts, at least 2 each
    no_bank = set(rng.sample(range(n), max(2, round(n * config.MISSING_BANK_RATE))))
    no_tax = set(rng.sample(range(n), max(2, round(n * config.MISSING_TAX_RATE))))
    tax_numbers = rng.sample(range(10_000_000, 100_000_000), n)
    accounts = rng.sample(range(10 ** 11, 10 ** 12), n)

    employees, planted = [], []
    for i in range(n):
        gid = group_of[i]
        group = config.PAY_GROUP_BY_ID[gid]
        eid = emp_ids[i]

        if role[i] != "employee" or rng.random() >= group.hourly_share:
            pay_type = "salaried"
        else:
            pay_type = "hourly"

        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)

        if role[i] == "manager":
            head = managers[gid][0]
            manager_id = None if i == head else emp_ids[head]
        else:
            manager_id = emp_ids[rng.choice(managers[gid])]

        if i in hired_in_period:
            hire = config.PERIOD_START + timedelta(days=rng.randrange(5, 50))
            term = None
        else:
            hire = HIRE_FLOOR + timedelta(days=rng.randrange(HIRE_SPAN))
            term = None
            if i in terminated:
                term = config.PERIOD_START + timedelta(days=rng.randrange(35, 80))

        if i in no_bank:
            bank = ifsc = None
            planted.append({"issue_type": "missing_bank_details", "table_name": "employees",
                            "record_id": eid, "expected_rule": "VR-001"})
        else:
            bank = str(accounts[i])
            ifsc = ("".join(rng.choices(string.ascii_uppercase, k=4))
                    + "0" + f"{rng.randrange(10 ** 6):06d}")

        if i in no_tax:
            tax_id = None
            planted.append({"issue_type": "missing_tax_id", "table_name": "employees",
                            "record_id": eid, "expected_rule": "VR-002"})
        else:
            tax_id = f"TIN-{tax_numbers[i]}"

        low, high = config.HOURLY_RATE_RANGE, config.MONTHLY_SALARY_RANGE
        employees.append({
            "employee_id": eid,
            "first_name": first,
            "last_name": last,
            "email": f"{first.lower()}.{last.lower()}.{i + 1:06d}@example.com",
            "role": role[i],
            "manager_id": manager_id,
            "pay_group_id": gid,
            "pay_type": pay_type,
            "hourly_rate": (Decimal(rng.randint(*low)).quantize(CENT)
                            if pay_type == "hourly" else None),
            "monthly_salary": (Decimal(rng.randrange(high[0], high[1] + 1, 500)).quantize(CENT)
                               if pay_type == "salaried" else None),
            "hire_date": hire,
            "termination_date": term,
            "status": "terminated" if term else "active",
            "bank_account_number": bank,
            "bank_ifsc": ifsc,
            "tax_id": tax_id,
        })
    return employees, planted