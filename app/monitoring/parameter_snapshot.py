from dataclasses import dataclass

from app.models.process_state import ProcessState


@dataclass(frozen=True)
class ParameterDefinition:
    code: str
    title: str
    state_attribute: str
    measurement_unit: str
    normal_min: float
    normal_max: float


@dataclass(frozen=True)
class ParameterSnapshot:
    code: str
    title: str
    value: float
    measurement_unit: str
    normal_min: float
    normal_max: float
    status: str

    @property
    def normal_range(self) -> str:
        return f"{self.normal_min:g} - {self.normal_max:g}"

    @property
    def formatted_value(self) -> str:
        if self.code == "catalyst_consumption":
            return f"{self.value:.2f}"

        return f"{self.value:.1f}"


PARAMETER_DEFINITIONS: tuple[ParameterDefinition, ...] = (
    ParameterDefinition(
        code="reactor_temperature",
        title="Температура реактора",
        state_attribute="temperature",
        measurement_unit="°C",
        normal_min=360.0,
        normal_max=430.0,
    ),
    ParameterDefinition(
        code="reactor_pressure",
        title="Давление реактора",
        state_attribute="pressure",
        measurement_unit="атм",
        normal_min=120.0,
        normal_max=180.0,
    ),
    ParameterDefinition(
        code="feed_flow",
        title="Расход сырья",
        state_attribute="feed_flow",
        measurement_unit="т/ч",
        normal_min=60.0,
        normal_max=100.0,
    ),
    ParameterDefinition(
        code="hydrogen_flow",
        title="Расход водорода",
        state_attribute="hydrogen_flow",
        measurement_unit="нм³/ч",
        normal_min=2200.0,
        normal_max=3800.0,
    ),
    ParameterDefinition(
        code="energy_consumption",
        title="Потребление энергии",
        state_attribute="energy",
        measurement_unit="кВт⋅ч",
        normal_min=750.0,
        normal_max=1200.0,
    ),
    ParameterDefinition(
        code="cooling_water_flow",
        title="Расход охлаждающей воды",
        state_attribute="water_consumption",
        measurement_unit="м³/ч",
        normal_min=25.0,
        normal_max=50.0,
    ),
    ParameterDefinition(
        code="catalyst_consumption",
        title="Расход катализатора",
        state_attribute="catalyst_consumption",
        measurement_unit="кг/ч",
        normal_min=0.8,
        normal_max=2.5,
    ),
    ParameterDefinition(
        code="product_yield",
        title="Выход продукции",
        state_attribute="product_yield",
        measurement_unit="%",
        normal_min=75.0,
        normal_max=90.0,
    ),
)


def build_parameter_snapshots(state: ProcessState) -> tuple[ParameterSnapshot, ...]:
    return tuple(
        ParameterSnapshot(
            code=definition.code,
            title=definition.title,
            value=float(getattr(state, definition.state_attribute)),
            measurement_unit=definition.measurement_unit,
            normal_min=definition.normal_min,
            normal_max=definition.normal_max,
            status=classify_parameter_status(
                value=float(getattr(state, definition.state_attribute)),
                normal_min=definition.normal_min,
                normal_max=definition.normal_max,
            ),
        )
        for definition in PARAMETER_DEFINITIONS
    )


def classify_parameter_status(
    value: float,
    normal_min: float,
    normal_max: float,
) -> str:
    if normal_min <= value <= normal_max:
        return "норма"

    return "отклонение"
