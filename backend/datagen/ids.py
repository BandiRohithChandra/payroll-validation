"""Deterministic ID generation (see docs/decisions.md section 12)."""
import re
from datetime import date

YEAR = 2026

# kind -> (format string, validation regex)
_FORMATS = {
    "employee": ("EMP-{n:06d}", r"^EMP-\d{6}$"),
    "pay_group": ("PG-{n:03d}", r"^PG-\d{3}$"),
    "leave": ("LV-{n:06d}", r"^LV-\d{6}$"),
    "allowance": ("ALW-{n:06d}", r"^ALW-\d{6}$"),
    "deduction": ("DED-{n:06d}", r"^DED-\d{6}$"),
    "rule": ("VR-{n:03d}", r"^VR-\d{3}$"),
    "exception": ("EXC-{n:06d}", r"^EXC-\d{6}$"),
    "approval": ("APR-{n:06d}", r"^APR-\d{6}$"),
    "export": (f"PEX-{YEAR}-{{n:06d}}", r"^PEX-\d{4}-\d{6}$"),
    "export_line": ("PXL-{n:06d}", r"^PXL-\d{6}$"),
}

# kinds built from other ids, not from a counter
_COMPOSED = {
    "pay_period": r"^PP-\d{4}-\d{2}$",
    "time_entry": r"^TIME-EMP-\d{6}-\d{4}-\d{2}-\d{2}(-[CD]\d)?$",
    "payroll_input": r"^PIN-EMP-\d{6}-\d{4}-\d{2}$",
}


class IdGenerator:
    """One counter per entity type. Counters only go up."""

    def __init__(self):
        self._counters = {key: 0 for key in _FORMATS}

    def next(self, kind: str) -> str:
        self._counters[kind] += 1
        return _FORMATS[kind][0].format(n=self._counters[kind])

    @staticmethod
    def period_id(month: int) -> str:
        """PP-2026-01"""
        return f"PP-{YEAR}-{month:02d}"

    @staticmethod
    def time_entry_id(employee_id: str, work_date: date, suffix: str = None) -> str:
        """TIME-<employee-id>-<date>; suffix 'C1' (correction) or 'D1' (duplicate)."""
        base = f"TIME-{employee_id}-{work_date.isoformat()}"
        return f"{base}-{suffix}" if suffix else base

    @staticmethod
    def payroll_input_id(employee_id: str, month: int) -> str:
        """PIN-<employee-id>-2026-01"""
        return f"PIN-{employee_id}-{YEAR}-{month:02d}"


def is_valid(kind: str, value: str) -> bool:
    pattern = _FORMATS[kind][1] if kind in _FORMATS else _COMPOSED[kind]
    return re.match(pattern, value) is not None