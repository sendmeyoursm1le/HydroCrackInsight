from dataclasses import dataclass

from app.models.process_state import ProcessState


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

    def analyze(self, state: ProcessState) -> DeviationResult:
        emergency_result = self._check_emergency(state)
        if emergency_result is not None:
            return emergency_result

        warning_result = self._check_warning(state)
        if warning_result is not None:
            return warning_result

        return DeviationResult(status="норма")

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