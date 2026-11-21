"""Roles are ordered: each one can do everything the roles below it can.

viewer      read only: telemetry, history, alarm list, alarm limits
operator    + acknowledge alarms, move rods within the envelope, scram
supervisor  + change alarm limits, reset after a scram, read the audit log
"""

from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"

    @property
    def rank(self) -> int:
        return _RANK[self]

    def allows(self, required: "Role") -> bool:
        return self.rank >= required.rank


_RANK = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.SUPERVISOR: 2}
