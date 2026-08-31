from dataclasses import dataclass

from app.models.process_state import ProcessState
from app.monitoring.operating_mode import OperatingModeLimit, OperatingModeProfile
from app.monitoring.parameter_snapshot import PARAMETER_DEFINITIONS


@dataclass
class DeviationResult:
    status: str
    parameter: str | None = None
    value: str | None = None
    level: str = "Норма"
    message: str = "Отклонений не обнаружено"
    recommendation: str = "Действия не требуются"

    @property
    def has_deviation(self) -> bool:
        return self.status in ("предупреждение", "авария")

    @property
    def is_emergency(self) -> bool:
        return self.status == "авария"


class DeviationAnalyzer:
    """
    Подсистема анализа отклонений технологического процесса.

    Задачи:
    - сравнение текущих параметров с допустимыми пределами;
    - выявление предупреждений;
    - выявление аварийных состояний;
    - формирование рекомендаций для оператора или технолога.
    """

    TEMPERATURE_WARNING_MAX = 430.0
    TEMPERATURE_CRITICAL_MAX = 450.0

    PRESSURE_WARNING_MAX = 200.0
    PRESSURE_CRITICAL_MAX = 210.0

    HYDROGEN_WARNING_MIN = 1800.0
    HYDROGEN_CRITICAL_MIN = 1500.0
    MODE_CRITICAL_MARGIN = 0.15

    PARAMETER_DEFINITIONS_BY_CODE = {
        definition.code: definition for definition in PARAMETER_DEFINITIONS
    }

    def analyze(
        self,
        state: ProcessState,
        operating_mode_profile: OperatingModeProfile | None = None,
    ) -> DeviationResult:
        emergency_result = self._check_emergency(state)
        if emergency_result is not None:
            return emergency_result

        if operating_mode_profile is not None:
            mode_result = self._check_operating_mode_limits(
                state=state,
                operating_mode_profile=operating_mode_profile,
            )
            if mode_result is not None:
                return mode_result

            return DeviationResult(status="норма")

        warning_result = self._check_warning(state)
        if warning_result is not None:
            return warning_result

        return DeviationResult(status="норма")

    def _check_operating_mode_limits(
        self,
        state: ProcessState,
        operating_mode_profile: OperatingModeProfile,
    ) -> DeviationResult | None:
        for parameter_code, limit in operating_mode_profile.limits.items():
            definition = self.PARAMETER_DEFINITIONS_BY_CODE.get(parameter_code)
            if definition is None:
                continue

            value = float(getattr(state, definition.state_attribute))
            if limit.min_value <= value <= limit.max_value:
                continue

            is_critical = self._is_critical_mode_deviation(value, limit)
            status = "авария" if is_critical else "предупреждение"
            level = "Авария" if is_critical else "Предупреждение"
            direction = "ниже" if value < limit.min_value else "выше"

            return DeviationResult(
                status=status,
                parameter=definition.title,
                value=f"{value:.1f} {limit.measurement_unit}",
                level=level,
                message=(
                    f"{definition.title} {direction} уставки режима "
                    f"'{operating_mode_profile.mode.title}'"
                ),
                recommendation=(
                    "Проверить технологический режим, уставки и стабильность "
                    "подачи сырья/водорода"
                ),
            )

        return None

    def _is_critical_mode_deviation(
        self,
        value: float,
        limit: OperatingModeLimit,
    ) -> bool:
        span = max(abs(limit.max_value - limit.min_value), 1.0)
        margin = span * self.MODE_CRITICAL_MARGIN

        return value < limit.min_value - margin or value > limit.max_value + margin

    def _check_emergency(self, state: ProcessState) -> DeviationResult | None:
        if state.temperature >= self.TEMPERATURE_CRITICAL_MAX:
            return DeviationResult(
                status="авария",
                parameter="Температура",
                value=f"{state.temperature:.1f} °C",
                level="Авария",
                message="Критическое превышение температуры реактора",
                recommendation=(
                    "Снизить подачу сырья, увеличить охлаждение "
                    "и проверить состояние теплообменника"
                ),
            )

        if state.pressure >= self.PRESSURE_CRITICAL_MAX:
            return DeviationResult(
                status="авария",
                parameter="Давление",
                value=f"{state.pressure:.1f} атм",
                level="Авария",
                message="Критическое превышение давления в системе",
                recommendation=(
                    "Открыть клапан сброса давления, снизить подачу сырья "
                    "и проверить регулирующую арматуру"
                ),
            )

        if state.hydrogen_flow <= self.HYDROGEN_CRITICAL_MIN:
            return DeviationResult(
                status="авария",
                parameter="Расход водорода",
                value=f"{state.hydrogen_flow:.1f} нм³/ч",
                level="Авария",
                message="Критическое снижение расхода водорода",
                recommendation=(
                    "Проверить компрессор подачи водорода, снизить расход сырья "
                    "и перевести установку в безопасный режим"
                ),
            )

        return None

    def _check_warning(self, state: ProcessState) -> DeviationResult | None:
        if state.temperature >= self.TEMPERATURE_WARNING_MAX:
            return DeviationResult(
                status="предупреждение",
                parameter="Температура",
                value=f"{state.temperature:.1f} °C",
                level="Предупреждение",
                message="Температура реактора выше нормы",
                recommendation="Проверить режим охлаждения и нагрузку на реактор",
            )

        if state.pressure >= self.PRESSURE_WARNING_MAX:
            return DeviationResult(
                status="предупреждение",
                parameter="Давление",
                value=f"{state.pressure:.1f} атм",
                level="Предупреждение",
                message="Давление приближается к критическому значению",
                recommendation="Проверить клапан регулирования давления",
            )

        if state.hydrogen_flow <= self.HYDROGEN_WARNING_MIN:
            return DeviationResult(
                status="предупреждение",
                parameter="Расход водорода",
                value=f"{state.hydrogen_flow:.1f} нм³/ч",
                level="Предупреждение",
                message="Расход водорода ниже нормы",
                recommendation="Проверить подачу водорода и состояние компрессора",
            )

        return None
