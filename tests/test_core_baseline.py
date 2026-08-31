import tempfile
import unittest
from pathlib import Path

from app.core.deviation_analyzer import DeviationAnalyzer
from app.core.emergency_service import EmergencyService
from app.database.database_service import DatabaseService
from app.models.equipment import create_default_equipment
from app.models.process_state import ProcessState
from app.simulation.sensor_simulator import SensorSimulator


class DeviationAnalyzerTest(unittest.TestCase):
    def test_normal_state_has_no_deviation(self) -> None:
        analyzer = DeviationAnalyzer()
        result = analyzer.analyze(ProcessState())

        self.assertEqual(result.status, "норма")
        self.assertFalse(result.has_deviation)

    def test_critical_temperature_is_emergency(self) -> None:
        analyzer = DeviationAnalyzer()
        state = ProcessState(temperature=460.0)

        result = analyzer.analyze(state)

        self.assertEqual(result.status, "авария")
        self.assertEqual(result.parameter, "Температура")
        self.assertTrue(result.is_emergency)


class EmergencyServiceTest(unittest.TestCase):
    def test_temperature_emergency_updates_equipment_statuses(self) -> None:
        analyzer = DeviationAnalyzer()
        emergency_service = EmergencyService()
        equipment = create_default_equipment()
        deviation = analyzer.analyze(ProcessState(temperature=460.0))

        response = emergency_service.process_emergency(deviation, equipment)

        statuses = {item.name: item.status for item in equipment}
        self.assertTrue(response.is_required)
        self.assertEqual(statuses["Реактор R-101"], "Авария")
        self.assertEqual(statuses["Теплообменник H-501"], "Требуется проверка")


class SensorSimulatorTest(unittest.TestCase):
    def test_started_simulator_generates_process_state(self) -> None:
        simulator = SensorSimulator()
        simulator.start()

        state = simulator.generate_next_state()

        self.assertEqual(state.mode, "мониторинг")
        self.assertGreater(state.temperature, 0)
        self.assertGreater(state.product_yield, 0)


class DatabaseServiceTest(unittest.TestCase):
    def test_database_saves_baseline_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            state = ProcessState()
            equipment = create_default_equipment()
            database.save_process_state("01.01.2026 00:00:00", state)
            database.save_event("01.01.2026 00:00:01", "INFO", "test")
            database.save_equipment_statuses("01.01.2026 00:00:02", equipment)

            counts = database.get_counts()

            self.assertEqual(counts["process_values"], 1)
            self.assertEqual(counts["events"], 1)
            self.assertEqual(counts["equipment_statuses"], len(equipment))


if __name__ == "__main__":
    unittest.main()
