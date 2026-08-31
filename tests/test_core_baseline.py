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
from app.users import (
    DEMO_USERS,
    SIMULATE_EMERGENCY,
    VIEW_DATABASE_STATISTICS,
    get_accessible_tabs,
    get_role_definitions,
    has_permission,
)


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
            self.assertEqual(counts["users"], len(DEMO_USERS))
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

    def test_database_reads_shared_events_and_deviations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            database.save_event("01.01.2026 00:00:00", "INFO", "first")
            database.save_event("01.01.2026 00:00:01", "WARNING", "second")
            database.save_deviation(
                timestamp="01.01.2026 00:00:02",
                parameter="Температура",
                value="460.0 °C",
                level="critical",
                message="Перегрев реактора",
                recommendation="Снизить тепловую нагрузку",
            )

            recent_events = database.get_recent_events(limit=1)
            recent_deviations = database.get_recent_deviations()

            self.assertEqual(len(recent_events), 1)
            self.assertEqual(recent_events[0].message, "second")
            self.assertEqual(recent_deviations[0].parameter, "Температура")

    def test_database_restores_latest_equipment_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            equipment = create_default_equipment()
            equipment[0].status = "Авария"
            equipment[0].description = "Температурное отклонение"

            database.save_equipment_statuses("01.01.2026 00:00:00", equipment)
            restored_equipment = database.get_equipment_catalog()

            statuses = {item.name: item.status for item in restored_equipment}
            descriptions = {item.name: item.description for item in restored_equipment}

            self.assertEqual(statuses["Реактор R-101"], "Авария")
            self.assertEqual(descriptions["Реактор R-101"], "Температурное отклонение")

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

    def test_database_authenticates_demo_users(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            operator_session = database.authenticate_user("operator", "demo")
            technologist_session = database.authenticate_user("technologist", "demo")

            self.assertIsNotNone(operator_session)
            self.assertIsNotNone(technologist_session)
            self.assertEqual(operator_session.role_code, "operator")
            self.assertEqual(technologist_session.role_code, "technologist")
            self.assertIsNone(database.authenticate_user("operator", "wrong"))

    def test_database_saves_audit_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            database.save_audit_event(
                timestamp="01.01.2026 00:00:00",
                username="operator",
                role_code="operator",
                action="login",
                details="Вход в систему",
            )

            counts = database.get_counts()

            self.assertEqual(counts["audit_log"], 1)
            self.assertEqual(database.get_recent_audit_events()[0].action, "login")

    def test_role_permissions_limit_actions_and_tabs(self) -> None:
        self.assertTrue(has_permission("operator", SIMULATE_EMERGENCY))
        self.assertFalse(has_permission("manager", SIMULATE_EMERGENCY))
        self.assertTrue(has_permission("manager", VIEW_DATABASE_STATISTICS))
        self.assertFalse(has_permission("operator", VIEW_DATABASE_STATISTICS))
        self.assertIn("users", get_accessible_tabs("administrator"))
        self.assertNotIn("users", get_accessible_tabs("operator"))


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
