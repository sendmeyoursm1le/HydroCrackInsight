import random

from app.models.process_state import ProcessState


class SensorSimulator:
    """
    Симулятор технологических параметров установки гидрокрекинга.

    В реальной промышленной системе данные поступали бы от SCADA/DCS.
    В рамках курсового проекта эти данные генерируются программно.
    """

    def __init__(self) -> None:
        self.current_state = ProcessState()
        self.is_running = False
        self.scenario = "normal"
        self._ticks_in_scenario = 0

    def start(self) -> None:
        self.is_running = True
        self.current_state.mode = "мониторинг"

    def stop(self) -> None:
        self.is_running = False
        self.current_state.mode = "остановлен"

    def simulate_emergency(self) -> str:
        self.scenario = random.choice(
            [
                "overheat",
                "pressure_spike",
                "hydrogen_drop",
            ]
        )
        self._ticks_in_scenario = 0
        self.current_state.mode = "аварийный сценарий"

        scenario_names = {
            "overheat": "перегрев реактора",
            "pressure_spike": "рост давления",
            "hydrogen_drop": "снижение расхода водорода",
        }

        return scenario_names[self.scenario]

    def generate_next_state(self) -> ProcessState:
        if not self.is_running:
            return self.current_state

        self._ticks_in_scenario += 1

        if self.scenario == "normal":
            self._generate_normal_state()
        elif self.scenario == "overheat":
            self._generate_overheat_state()
        elif self.scenario == "pressure_spike":
            self._generate_pressure_spike_state()
        elif self.scenario == "hydrogen_drop":
            self._generate_hydrogen_drop_state()

        self._calculate_product_yield()
        return self.current_state

    def _generate_normal_state(self) -> None:
        self.current_state.mode = "мониторинг"

        self.current_state.temperature = self._move_to_target(
            self.current_state.temperature,
            target=390.0,
            speed=0.15,
            noise=3.0,
        )

        self.current_state.pressure = self._move_to_target(
            self.current_state.pressure,
            target=150.0,
            speed=0.15,
            noise=2.0,
        )

        self.current_state.feed_flow = self._move_to_target(
            self.current_state.feed_flow,
            target=80.0,
            speed=0.12,
            noise=1.5,
        )

        self.current_state.hydrogen_flow = self._move_to_target(
            self.current_state.hydrogen_flow,
            target=3000.0,
            speed=0.12,
            noise=80.0,
        )

        self.current_state.energy = self._move_to_target(
            self.current_state.energy,
            target=900.0,
            speed=0.12,
            noise=20.0,
        )

        self.current_state.water_consumption = self._move_to_target(
            self.current_state.water_consumption,
            target=35.0,
            speed=0.12,
            noise=2.0,
        )

        self.current_state.catalyst_consumption = self._move_to_target(
            self.current_state.catalyst_consumption,
            target=1.5,
            speed=0.12,
            noise=0.1,
        )

    def _generate_overheat_state(self) -> None:
        self.current_state.mode = "анализ отклонений"

        self.current_state.temperature = self._move_to_target(
            self.current_state.temperature,
            target=465.0,
            speed=0.18,
            noise=2.0,
        )

        self.current_state.pressure = self._move_to_target(
            self.current_state.pressure,
            target=165.0,
            speed=0.08,
            noise=1.5,
        )

        self.current_state.feed_flow = self._move_to_target(
            self.current_state.feed_flow,
            target=86.0,
            speed=0.08,
            noise=1.0,
        )

        self.current_state.hydrogen_flow = self._move_to_target(
            self.current_state.hydrogen_flow,
            target=3100.0,
            speed=0.08,
            noise=60.0,
        )

        self.current_state.energy = self._move_to_target(
            self.current_state.energy,
            target=1150.0,
            speed=0.12,
            noise=25.0,
        )

    def _generate_pressure_spike_state(self) -> None:
        self.current_state.mode = "анализ отклонений"

        self.current_state.temperature = self._move_to_target(
            self.current_state.temperature,
            target=405.0,
            speed=0.08,
            noise=2.0,
        )

        self.current_state.pressure = self._move_to_target(
            self.current_state.pressure,
            target=220.0,
            speed=0.18,
            noise=2.0,
        )

        self.current_state.feed_flow = self._move_to_target(
            self.current_state.feed_flow,
            target=95.0,
            speed=0.10,
            noise=1.0,
        )

        self.current_state.hydrogen_flow = self._move_to_target(
            self.current_state.hydrogen_flow,
            target=3200.0,
            speed=0.08,
            noise=70.0,
        )

        self.current_state.energy = self._move_to_target(
            self.current_state.energy,
            target=1050.0,
            speed=0.10,
            noise=25.0,
        )

    def _generate_hydrogen_drop_state(self) -> None:
        self.current_state.mode = "анализ отклонений"

        self.current_state.temperature = self._move_to_target(
            self.current_state.temperature,
            target=410.0,
            speed=0.08,
            noise=2.0,
        )

        self.current_state.pressure = self._move_to_target(
            self.current_state.pressure,
            target=145.0,
            speed=0.08,
            noise=2.0,
        )

        self.current_state.feed_flow = self._move_to_target(
            self.current_state.feed_flow,
            target=82.0,
            speed=0.08,
            noise=1.0,
        )

        self.current_state.hydrogen_flow = self._move_to_target(
            self.current_state.hydrogen_flow,
            target=1200.0,
            speed=0.18,
            noise=60.0,
        )

        self.current_state.energy = self._move_to_target(
            self.current_state.energy,
            target=980.0,
            speed=0.10,
            noise=20.0,
        )

    def _calculate_product_yield(self) -> None:
        temperature_penalty = abs(self.current_state.temperature - 390.0) * 0.05
        pressure_penalty = abs(self.current_state.pressure - 150.0) * 0.03

        hydrogen_penalty = 0.0
        if self.current_state.hydrogen_flow < 2200:
            hydrogen_penalty = (2200 - self.current_state.hydrogen_flow) * 0.004

        calculated_yield = (
            84.0
            - temperature_penalty
            - pressure_penalty
            - hydrogen_penalty
            + random.uniform(-1.0, 1.0)
        )

        self.current_state.product_yield = self._clamp(calculated_yield, 50.0, 95.0)

    @staticmethod
    def _move_to_target(
        current: float,
        target: float,
        speed: float,
        noise: float,
    ) -> float:
        value = current + (target - current) * speed + random.uniform(-noise, noise)
        return round(value, 2)

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(value, max_value))