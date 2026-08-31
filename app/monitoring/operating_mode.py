from dataclasses import dataclass


@dataclass(frozen=True)
class OperatingMode:
    code: str
    title: str
    feedstock_type: str
    goal: str
    is_active: bool


@dataclass(frozen=True)
class OperatingModeLimit:
    mode_code: str
    parameter_code: str
    parameter_title: str
    min_value: float
    max_value: float
    measurement_unit: str

    @property
    def normal_range(self) -> str:
        return f"{self.min_value:g} - {self.max_value:g}"


@dataclass(frozen=True)
class OperatingModeProfile:
    mode: OperatingMode
    limits: dict[str, OperatingModeLimit]

    def get_limit(self, parameter_code: str) -> OperatingModeLimit | None:
        return self.limits.get(parameter_code)
