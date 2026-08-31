from dataclasses import dataclass


@dataclass(frozen=True)
class EventRecord:
    timestamp: str
    level: str
    message: str


@dataclass(frozen=True)
class DeviationRecord:
    timestamp: str
    parameter: str
    value: str
    level: str
    message: str
    recommendation: str


@dataclass(frozen=True)
class AuditRecord:
    timestamp: str
    username: str
    role_code: str
    action: str
    details: str
    level: str
