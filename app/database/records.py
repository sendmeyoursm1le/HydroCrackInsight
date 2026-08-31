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


@dataclass(frozen=True)
class SensorDataRecord:
    timestamp: str
    sensor_code: str
    parameter_name: str
    value: float
    measurement_unit: str
    status: str
    mode: str


@dataclass(frozen=True)
class ShiftJournalRecord:
    timestamp: str
    shift_code: str
    author_username: str
    level: str
    message: str
    equipment_name: str
    action_required: bool


@dataclass(frozen=True)
class ShiftHandoverRecord:
    timestamp: str
    shift_code: str
    from_user: str
    to_user: str
    status: str
    summary: str
    open_actions: str
    checked_items: int
    total_items: int
