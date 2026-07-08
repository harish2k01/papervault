from collections.abc import Iterable

from sqlalchemy import CheckConstraint


def check_values(column_name: str, values: Iterable[str], name: str) -> CheckConstraint:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column_name} IN ({quoted_values})", name=name)
