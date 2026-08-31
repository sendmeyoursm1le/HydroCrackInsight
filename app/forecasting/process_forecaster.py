from dataclasses import dataclass

from app.models.process_state import ProcessState


@dataclass(frozen=True)
class ForecastScenario:
    code: str
    title: str
    temperature_delta: float = 0.0
    pressure_delta: float = 0.0
    feed_flow_delta: float = 0.0
    hydrogen_flow_delta: float = 0.0


@dataclass(frozen=True)
class ForecastResult:
    scenario_code: str
    scenario_title: str
    current_yield: float
    forecast_yield: float
    yield_delta: float
    forecast_temperature: float
    forecast_pressure: float
    forecast_feed_flow: float
    forecast_hydrogen_flow: float
    recommendation: str


FORECAST_SCENARIOS = (
    ForecastScenario(
        code="cool_reactor",
        title="Снизить температуру реактора",
        temperature_delta=-10.0,
    ),
    ForecastScenario(
        code="lower_pressure",
        title="Снизить давление",
        pressure_delta=-15.0,
    ),
    ForecastScenario(
        code="increase_hydrogen",
        title="Увеличить подачу водорода",
        hydrogen_flow_delta=300.0,
    ),
    ForecastScenario(
        code="reduce_feed",
        title="Снизить подачу сырья",
        feed_flow_delta=-10.0,
    ),
    ForecastScenario(
        code="balanced_optimization",
        title="Сбалансированная оптимизация",
        temperature_delta=-5.0,
        pressure_delta=-5.0,
        feed_flow_delta=-3.0,
        hydrogen_flow_delta=150.0,
    ),
)


class ProcessForecastService:
    """
    Расчетный модуль для оценки выхода продукта и простых сценариев оптимизации.
    """

    def calculate_product_yield(
        self,
        state: ProcessState,
        random_noise: float = 0.0,
    ) -> float:
        if self.is_shutdown_state(state):
            return 0.0

        temperature_penalty = abs(state.temperature - 390.0) * 0.05
        pressure_penalty = abs(state.pressure - 150.0) * 0.03

        hydrogen_penalty = 0.0
        if state.hydrogen_flow < 2200.0:
            hydrogen_penalty = (2200.0 - state.hydrogen_flow) * 0.004

        feed_penalty = 0.0
        if state.feed_flow < 60.0:
            feed_penalty = (60.0 - state.feed_flow) * 0.15

        calculated_yield = (
            84.0
            - temperature_penalty
            - pressure_penalty
            - hydrogen_penalty
            - feed_penalty
            + random_noise
        )

        return self._clamp(calculated_yield, 0.0, 95.0)

    def evaluate_scenarios(
        self,
        state: ProcessState,
        scenarios: tuple[ForecastScenario, ...] = FORECAST_SCENARIOS,
    ) -> tuple[ForecastResult, ...]:
        current_yield = self.calculate_product_yield(state)

        return tuple(
            self._evaluate_scenario(
                state=state,
                current_yield=current_yield,
                scenario=scenario,
            )
            for scenario in scenarios
        )

    def apply_scenario(
        self,
        state: ProcessState,
        scenario: ForecastScenario,
    ) -> ProcessState:
        return ProcessState(
            temperature=self._clamp(state.temperature + scenario.temperature_delta, 0.0, 520.0),
            pressure=self._clamp(state.pressure + scenario.pressure_delta, 0.0, 260.0),
            feed_flow=self._clamp(state.feed_flow + scenario.feed_flow_delta, 0.0, 130.0),
            hydrogen_flow=self._clamp(state.hydrogen_flow + scenario.hydrogen_flow_delta, 0.0, 4500.0),
            energy=state.energy,
            water_consumption=state.water_consumption,
            catalyst_consumption=state.catalyst_consumption,
            product_yield=state.product_yield,
            mode="прогноз",
            status=state.status,
        )

    def is_shutdown_state(self, state: ProcessState) -> bool:
        return (
            state.status == "авария"
            or state.mode == "аварийная остановка"
            or state.feed_flow <= 1.0
        )

    def _evaluate_scenario(
        self,
        state: ProcessState,
        current_yield: float,
        scenario: ForecastScenario,
    ) -> ForecastResult:
        forecast_state = self.apply_scenario(state, scenario)
        forecast_yield = self.calculate_product_yield(forecast_state)
        yield_delta = forecast_yield - current_yield

        return ForecastResult(
            scenario_code=scenario.code,
            scenario_title=scenario.title,
            current_yield=current_yield,
            forecast_yield=forecast_yield,
            yield_delta=yield_delta,
            forecast_temperature=forecast_state.temperature,
            forecast_pressure=forecast_state.pressure,
            forecast_feed_flow=forecast_state.feed_flow,
            forecast_hydrogen_flow=forecast_state.hydrogen_flow,
            recommendation=self._build_recommendation(scenario, yield_delta),
        )

    def _build_recommendation(
        self,
        scenario: ForecastScenario,
        yield_delta: float,
    ) -> str:
        if yield_delta > 1.0:
            return f"Рекомендуется рассмотреть сценарий: {scenario.title}"

        if yield_delta < -1.0:
            return "Сценарий ухудшает расчетный выход, применять только при ограничениях безопасности"

        return "Сценарий существенно не меняет расчетный выход"

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(value, max_value))
