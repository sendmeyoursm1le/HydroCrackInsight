import tempfile
import unittest
from pathlib import Path

from app.database.database_service import DatabaseService
from app.domain import PROJECT_NAME, get_domain_terms, get_subsystems
from app.equipment.emergency_service import EmergencyService
from app.models.equipment import create_default_equipment
from app.models.process_state import ProcessState
from app.monitoring.deviation_analyzer import DeviationAnalyzer
from app.simulation.sensor_simulator import SensorSimulator
from app.users import get_role_definitions


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
    def test_database_initializes_tz5_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            expected_tables = set(DatabaseService.COUNTED_TABLES) | {"database_meta"}

            self.assertTrue(expected_tables.issubset(database.get_table_names()))

    def test_database_seeds_reference_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            counts = database.get_counts()

            self.assertEqual(counts["roles"], len(get_role_definitions()))
            self.assertEqual(counts["users"], 1)
            self.assertEqual(counts["units"], 1)
            self.assertEqual(counts["equipment_catalog"], len(create_default_equipment()))
            self.assertEqual(counts["sensors"], len(DatabaseService.SENSOR_DEFINITIONS))
            self.assertEqual(counts["operating_modes"], len(DatabaseService.OPERATING_MODES))
            self.assertEqual(counts["operating_mode_limits"], 20)

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
            self.assertEqual(counts["sensor_data"], len(DatabaseService.PROCESS_SENSOR_FIELDS))
            self.assertEqual(counts["resource_usage"], len(DatabaseService.RESOURCE_FIELDS))

    def test_database_restores_last_process_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            self.assertIsNone(database.get_last_process_state())

            state = ProcessState(
                temperature=401.5,
                pressure=151.2,
                feed_flow=79.4,
                hydrogen_flow=3100.0,
                energy=910.0,
                water_consumption=36.5,
                catalyst_consumption=1.65,
                product_yield=83.4,
                mode="мониторинг",
                status="предупреждение",
            )

            database.save_process_state("01.01.2026 00:00:00", ProcessState())
            database.save_process_state("01.01.2026 00:00:01", state)

            restored_database = DatabaseService(str(database_path))
            restored_database.initialize_database()

            self.assertEqual(restored_database.get_last_process_state(), state)

    def test_database_saves_deviation_as_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            database.save_deviation(
                timestamp="01.01.2026 00:00:00",
                parameter="Температура",
                value="460.0 °C",
                level="critical",
                message="Перегрев реактора",
                recommendation="Снизить тепловую нагрузку",
            )

            counts = database.get_counts()

            self.assertEqual(counts["deviations"], 1)
            self.assertEqual(counts["recommendations"], 1)


class ProjectStructureTest(unittest.TestCase):
    def test_domain_registry_contains_project_subsystems(self) -> None:
        subsystems = {item.code: item for item in get_subsystems()}

        self.assertEqual(PROJECT_NAME, "HydroCrack Insight")
        self.assertIn("monitoring", subsystems)
        self.assertIn("equipment", subsystems)
        self.assertIn("reports", subsystems)
        self.assertIn("users", subsystems)

    def test_terms_and_roles_are_defined_for_tz5_scope(self) -> None:
        term_codes = {item.code for item in get_domain_terms()}
        role_codes = {item.code for item in get_role_definitions()}

        self.assertIn("operating_mode", term_codes)
        self.assertIn("shift_journal", term_codes)
        self.assertIn("operator", role_codes)
        self.assertIn("technologist", role_codes)
        self.assertIn("instrumentation_engineer", role_codes)


if __name__ == "__main__":
    unittest.main()
