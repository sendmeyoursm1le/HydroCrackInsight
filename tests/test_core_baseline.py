import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.database.database_service import DatabaseService
from app.diagnostics import DiagnosticService
from app.domain import PROJECT_NAME, get_domain_terms, get_subsystems
from app.equipment.emergency_service import EmergencyService
from app.forecasting import ForecastScenario, ProcessForecastService
from app.models.equipment import create_default_equipment
from app.models.process_state import ProcessState
from app.monitoring.deviation_analyzer import DeviationAnalyzer
from app.monitoring.parameter_snapshot import (
    PARAMETER_DEFINITIONS,
    build_parameter_snapshots,
    classify_parameter_status,
)
from app.monitoring.process_data_importer import ProcessDataImporter
from app.reports import ReportService
from app.simulation.sensor_simulator import SensorSimulator
from app.users import (
    BACKUP_DATABASE,
    CHANGE_OPERATING_MODE,
    CREATE_SHIFT_ENTRY,
    CREATE_SHIFT_HANDOVER,
    DEMO_USERS,
    IMPORT_PROCESS_DATA,
    SIMULATE_EMERGENCY,
    VIEW_DATABASE_STATISTICS,
    VIEW_DIAGNOSTICS,
    VIEW_FORECASTING,
    VIEW_RESOURCES,
    VIEW_SHIFT_JOURNAL,
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

    def test_mode_limits_create_warning_before_hardcoded_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            profile = database.get_operating_mode_profile("balanced")

            result = DeviationAnalyzer().analyze(
                ProcessState(temperature=420.0),
                operating_mode_profile=profile,
            )

            self.assertEqual(result.status, "предупреждение")
            self.assertEqual(result.parameter, "Температура реактора")
            self.assertIn("Нормальный режим", result.message)

    def test_mode_limits_create_critical_deviation_by_margin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            profile = database.get_operating_mode_profile("balanced")

            result = DeviationAnalyzer().analyze(
                ProcessState(feed_flow=60.0),
                operating_mode_profile=profile,
            )

            self.assertEqual(result.status, "авария")
            self.assertEqual(result.parameter, "Расход сырья")

    def test_mode_limits_override_legacy_warning_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            profile = database.get_operating_mode_profile("deep_hydrocracking")

            result = DeviationAnalyzer().analyze(
                ProcessState(temperature=432.0),
                operating_mode_profile=profile,
            )

            self.assertEqual(result.status, "норма")


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

    def test_emergency_shutdown_pauses_product_yield(self) -> None:
        simulator = SensorSimulator()
        simulator.start()
        simulator.scenario = "pressure_spike"
        simulator.current_state.pressure = 212.0

        state = simulator.generate_next_state()

        self.assertEqual(state.status, "авария")
        self.assertEqual(state.mode, "аварийная остановка")
        self.assertEqual(state.product_yield, 0.0)
        self.assertLess(state.feed_flow, 80.0)


class ProcessForecastServiceTest(unittest.TestCase):
    def test_forecaster_calculates_normal_product_yield(self) -> None:
        forecast_service = ProcessForecastService()

        product_yield = forecast_service.calculate_product_yield(ProcessState())

        self.assertAlmostEqual(product_yield, 84.0)

    def test_forecaster_pauses_yield_for_emergency_state(self) -> None:
        forecast_service = ProcessForecastService()
        state = ProcessState(status="авария")

        self.assertEqual(forecast_service.calculate_product_yield(state), 0.0)

    def test_hydrogen_support_scenario_improves_low_hydrogen_forecast(self) -> None:
        forecast_service = ProcessForecastService()
        state = ProcessState(hydrogen_flow=1800.0)

        result = forecast_service.evaluate_scenarios(
            state,
            scenarios=(
                ForecastScenario(
                    code="increase_hydrogen",
                    title="Увеличить подачу водорода",
                    hydrogen_flow_delta=300.0,
                ),
            ),
        )[0]

        self.assertGreater(result.forecast_yield, result.current_yield)
        self.assertIn("Рекомендуется", result.recommendation)


class MonitoringParameterTest(unittest.TestCase):
    def test_parameter_snapshots_include_status_and_ranges(self) -> None:
        snapshots = build_parameter_snapshots(ProcessState(temperature=460.0))
        snapshot_by_code = {snapshot.code: snapshot for snapshot in snapshots}

        self.assertEqual(len(snapshots), len(PARAMETER_DEFINITIONS))
        self.assertEqual(snapshot_by_code["reactor_temperature"].status, "отклонение")
        self.assertEqual(snapshot_by_code["reactor_pressure"].status, "норма")
        self.assertEqual(classify_parameter_status(10.0, 20.0, 30.0), "отклонение")

    def test_parameter_snapshots_use_operating_mode_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            profile = database.get_operating_mode_profile("energy_saving")

            snapshots = build_parameter_snapshots(
                ProcessState(temperature=400.0),
                operating_mode_profile=profile,
            )
            snapshot_by_code = {snapshot.code: snapshot for snapshot in snapshots}

            self.assertEqual(snapshot_by_code["reactor_temperature"].normal_max, 390.0)
            self.assertEqual(snapshot_by_code["reactor_temperature"].status, "отклонение")


class ProcessDataImporterTest(unittest.TestCase):
    def test_importer_reads_csv_with_process_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "process.csv"
            csv_path.write_text(
                (
                    "timestamp,temperature,pressure,feed_flow,hydrogen_flow,"
                    "energy,water_consumption,catalyst_consumption,product_yield\n"
                    "01.01.2026 00:00:00,390,150,80,3000,900,35,1.5,82\n"
                    "01.01.2026 00:00:01,395,151,81,3050,910,36,1.6,83\n"
                ),
                encoding="utf-8",
            )

            result = ProcessDataImporter().import_file(str(csv_path))

            self.assertEqual(result.imported_count, 2)
            self.assertEqual(result.last_state.temperature, 395.0)
            self.assertEqual(result.timestamps[0], "01.01.2026 00:00:00")

    def test_importer_reads_excel_with_process_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx_path = Path(temp_dir) / "process.xlsx"
            pd.DataFrame(
                [
                    {
                        "timestamp": "01.01.2026 00:00:00",
                        "temperature": 390.0,
                        "pressure": 150.0,
                        "feed_flow": 80.0,
                        "hydrogen_flow": 3000.0,
                    }
                ]
            ).to_excel(xlsx_path, index=False)

            result = ProcessDataImporter().import_file(str(xlsx_path))

            self.assertEqual(result.imported_count, 1)
            self.assertEqual(result.last_state.hydrogen_flow, 3000.0)


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

    def test_database_manages_active_operating_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            self.assertEqual(database.get_active_operating_mode_code(), "balanced")

            database.set_active_operating_mode("energy_saving")
            profile = database.get_active_operating_mode_profile()

            self.assertEqual(profile.mode.code, "energy_saving")
            self.assertEqual(
                profile.limits["reactor_temperature"].max_value,
                390.0,
            )

            with self.assertRaises(ValueError):
                database.set_active_operating_mode("missing_mode")

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

    def test_database_reads_recent_sensor_data_by_sensor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            for index in range(3):
                database.save_process_state(
                    f"01.01.2026 00:00:0{index}",
                    ProcessState(temperature=390.0 + index),
                )

            records = database.get_recent_sensor_data(
                sensor_codes=("reactor_temperature", "reactor_pressure"),
                limit_per_sensor=2,
            )

            temperatures = [
                record.value
                for record in records
                if record.sensor_code == "reactor_temperature"
            ]
            pressures = [
                record.value
                for record in records
                if record.sensor_code == "reactor_pressure"
            ]

            self.assertEqual(temperatures, [391.0, 392.0])
            self.assertEqual(pressures, [150.0, 150.0])

    def test_database_saves_sensor_status_by_active_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            database.set_active_operating_mode("energy_saving")
            profile = database.get_active_operating_mode_profile()

            database.save_process_state(
                "01.01.2026 00:00:00",
                ProcessState(temperature=400.0),
                operating_mode_profile=profile,
            )
            records = database.get_recent_sensor_data(
                sensor_codes=("reactor_temperature",),
                limit_per_sensor=1,
            )

            self.assertEqual(records[0].status, "отклонение")
            self.assertEqual(records[0].mode, "Энергосберегающий режим")

    def test_database_saves_shift_journal_and_handover(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            database.save_shift_journal_entry(
                timestamp="01.01.2026 08:00:00",
                shift_code="Смена A",
                author_username="operator",
                level="ACTION",
                message="Проверить насос после отклонения расхода",
                equipment_name=None,
                action_required=True,
            )
            handover_id = database.create_shift_handover(
                timestamp="01.01.2026 20:00:00",
                from_user="operator",
                to_user="technologist",
                shift_code="Смена A",
                summary="Установка работает стабильно",
                open_actions="Проконтролировать расход водорода",
                checklist_items=(
                    ("parameters_checked", "Параметры проверены", True, ""),
                    ("resources_checked", "Ресурсы проверены", False, ""),
                ),
            )

            counts = database.get_counts()
            journal_records = database.get_recent_shift_journal_entries()
            handover_records = database.get_recent_shift_handovers()

            self.assertGreater(handover_id, 0)
            self.assertEqual(counts["shift_journal_entries"], 1)
            self.assertEqual(counts["shift_handovers"], 1)
            self.assertEqual(counts["shift_handover_items"], 2)
            self.assertTrue(journal_records[0].action_required)
            self.assertEqual(handover_records[0].checked_items, 1)
            self.assertEqual(handover_records[0].total_items, 2)

    def test_database_builds_resource_usage_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            database.save_process_state(
                "01.01.2026 00:00:00",
                ProcessState(hydrogen_flow=3000.0),
            )
            database.save_process_state(
                "01.01.2026 01:00:00",
                ProcessState(hydrogen_flow=3600.0),
            )

            summaries = database.get_resource_usage_summary(
                current_time=datetime(2026, 1, 1, 1, 30, 0),
            )
            summary_by_code = {
                summary.resource_code: summary
                for summary in summaries
            }

            self.assertAlmostEqual(summary_by_code["hydrogen"].shift_total, 3060.0)
            self.assertEqual(summary_by_code["hydrogen"].shift_status, "норма")
            self.assertEqual(summary_by_code["hydrogen"].measurement_unit, "нм³")

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

    def test_database_saves_report_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()

            database.save_report(
                report_type="daily",
                period_start="01.01.2026 00:00:00",
                period_end="01.01.2026 23:59:59",
                title="Суточный отчет",
                file_path=str(Path(temp_dir) / "daily.pdf"),
                created_at="01.01.2026 23:59:59",
                created_by="operator",
            )

            reports = database.get_recent_reports()

            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].report_type, "daily")
            self.assertEqual(reports[0].created_by, "operator")

    def test_database_backup_creates_readable_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            backup_path = Path(temp_dir) / "backup.db"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            database.save_process_state("01.01.2026 00:00:00", ProcessState())

            result_path = database.backup_database(backup_path)
            backup_database = DatabaseService(str(result_path))

            self.assertTrue(result_path.exists())
            self.assertEqual(backup_database.get_counts()["process_values"], 1)

    def test_role_permissions_limit_actions_and_tabs(self) -> None:
        self.assertTrue(has_permission("operator", SIMULATE_EMERGENCY))
        self.assertFalse(has_permission("manager", SIMULATE_EMERGENCY))
        self.assertTrue(has_permission("manager", VIEW_DATABASE_STATISTICS))
        self.assertFalse(has_permission("operator", VIEW_DATABASE_STATISTICS))
        self.assertTrue(has_permission("technologist", IMPORT_PROCESS_DATA))
        self.assertFalse(has_permission("manager", IMPORT_PROCESS_DATA))
        self.assertTrue(has_permission("technologist", CHANGE_OPERATING_MODE))
        self.assertFalse(has_permission("operator", CHANGE_OPERATING_MODE))
        self.assertTrue(has_permission("operator", CREATE_SHIFT_ENTRY))
        self.assertTrue(has_permission("operator", CREATE_SHIFT_HANDOVER))
        self.assertFalse(has_permission("manager", CREATE_SHIFT_HANDOVER))
        self.assertTrue(has_permission("manager", VIEW_RESOURCES))
        self.assertTrue(has_permission("manager", VIEW_SHIFT_JOURNAL))
        self.assertTrue(has_permission("technologist", VIEW_FORECASTING))
        self.assertTrue(has_permission("manager", VIEW_FORECASTING))
        self.assertFalse(has_permission("operator", VIEW_FORECASTING))
        self.assertTrue(has_permission("instrumentation_engineer", VIEW_DIAGNOSTICS))
        self.assertFalse(has_permission("operator", VIEW_DIAGNOSTICS))
        self.assertTrue(has_permission("administrator", BACKUP_DATABASE))
        self.assertFalse(has_permission("manager", BACKUP_DATABASE))
        self.assertIn("resources", get_accessible_tabs("manager"))
        self.assertIn("forecasting", get_accessible_tabs("technologist"))
        self.assertIn("diagnostics", get_accessible_tabs("instrumentation_engineer"))
        self.assertIn("shift_journal", get_accessible_tabs("operator"))
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
        self.assertIn("diagnostics", subsystems)

    def test_terms_and_roles_are_defined_for_tz5_scope(self) -> None:
        term_codes = {item.code for item in get_domain_terms()}
        role_codes = {item.code for item in get_role_definitions()}

        self.assertIn("operating_mode", term_codes)
        self.assertIn("shift_journal", term_codes)
        self.assertIn("operator", role_codes)
        self.assertIn("technologist", role_codes)
        self.assertIn("instrumentation_engineer", role_codes)


class ReportServiceTest(unittest.TestCase):
    def test_report_service_generates_pdf_csv_and_database_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            output_dir = Path(temp_dir) / "generated"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            database.save_process_state("01.01.2026 00:00:00", ProcessState())
            database.save_process_state(
                "01.01.2026 01:00:00",
                ProcessState(temperature=452.0, status="авария"),
            )
            database.save_event("01.01.2026 01:00:01", "CRITICAL", "Аварийная остановка")
            database.save_deviation(
                timestamp="01.01.2026 01:00:01",
                parameter="Температура",
                value="452.0 °C",
                level="Авария",
                message="Критическое превышение температуры",
                recommendation="Снизить подачу сырья",
            )
            database.save_shift_journal_entry(
                timestamp="01.01.2026 07:50:00",
                shift_code="Смена A",
                author_username="operator",
                level="ACTION",
                message="Контроль после аварийной остановки",
                action_required=True,
            )

            service = ReportService(database, output_dir=output_dir)
            results = (
                service.generate_daily_report("operator"),
                service.generate_resources_report("operator"),
                service.generate_emergency_report("operator"),
                service.generate_shift_report("operator"),
            )

            for result in results:
                self.assertTrue(result.pdf_path.exists())
                self.assertTrue(result.csv_path.exists())
                self.assertGreater(result.pdf_path.stat().st_size, 0)
                self.assertGreater(result.csv_path.stat().st_size, 0)

            self.assertEqual(len(database.get_recent_reports()), 4)


class DiagnosticServiceTest(unittest.TestCase):
    def test_diagnostic_service_builds_snapshot_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hydrocrack.db"
            backup_dir = Path(temp_dir) / "backups"
            database = DatabaseService(str(database_path))
            database.initialize_database()
            database.save_process_state("01.01.2026 00:00:00", ProcessState())

            service = DiagnosticService(database)
            snapshot = service.build_snapshot(
                simulator_is_running=True,
                simulator_mode="мониторинг",
                simulator_status="норма",
            )
            backup_result = service.backup_database(backup_dir)

            item_names = {item.name for item in snapshot.items}

            self.assertIn(snapshot.overall_status, {"ok", "warning"})
            self.assertIn("База данных", item_names)
            self.assertIn("Последнее измерение", item_names)
            self.assertTrue(backup_result.path.exists())
            self.assertGreater(backup_result.size_bytes, 0)


if __name__ == "__main__":
    unittest.main()
