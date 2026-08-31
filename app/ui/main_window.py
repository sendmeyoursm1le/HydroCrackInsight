from collections.abc import Callable
from datetime import datetime

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QComboBox,
    QHBoxLayout,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.equipment.emergency_service import EmergencyResponse, EmergencyService
from app.database.database_service import DatabaseService
from app.diagnostics import DiagnosticService
from app.forecasting import ProcessForecastService
from app.models.equipment import Equipment
from app.monitoring.deviation_analyzer import DeviationAnalyzer, DeviationResult
from app.monitoring.parameter_snapshot import (
    PARAMETER_DEFINITIONS,
    ParameterSnapshot,
    build_parameter_snapshots,
)
from app.monitoring.process_data_importer import ProcessDataImporter
from app.reports import ReportService
from app.simulation.sensor_simulator import SensorSimulator
from app.users import (
    BACKUP_DATABASE,
    CHANGE_OPERATING_MODE,
    CONTROL_MONITORING,
    CREATE_SHIFT_ENTRY,
    CREATE_SHIFT_HANDOVER,
    IMPORT_PROCESS_DATA,
    RESET_EMERGENCY,
    RESET_EQUIPMENT_STATUSES,
    SIMULATE_EMERGENCY,
    VIEW_DATABASE_STATISTICS,
    VIEW_DIAGNOSTICS,
    VIEW_REPORTS,
    UserSession,
    get_accessible_tabs,
    has_permission,
)


class MainWindow(QMainWindow):
    switch_user_requested = pyqtSignal()

    TREND_SENSOR_CODES = (
        "reactor_temperature",
        "reactor_pressure",
        "feed_flow",
        "hydrogen_flow",
    )
    MAX_TREND_POINTS = 60

    def __init__(
        self,
        database_service: DatabaseService | None = None,
        current_user: UserSession | None = None,
    ) -> None:
        super().__init__()

        self.resize(1200, 750)

        self.simulator = SensorSimulator()
        self.deviation_analyzer = DeviationAnalyzer()
        self.emergency_service = EmergencyService()
        self.process_data_importer = ProcessDataImporter()
        self.forecast_service = ProcessForecastService()

        self.database_service = database_service or DatabaseService()
        self.database_service.initialize_database()
        self.diagnostic_service = DiagnosticService(self.database_service)
        self.report_service = ReportService(self.database_service)
        self.current_user = current_user or self.database_service.get_default_user_session()
        self.accessible_tabs = get_accessible_tabs(self.current_user.role_code)
        self.operating_modes = self.database_service.get_operating_modes()
        self.active_operating_mode_profile = (
            self.database_service.get_active_operating_mode_profile()
        )

        self.setWindowTitle(f"HydroCrack Insight - {self.current_user.role_title}")

        restored_state = self.database_service.get_last_process_state()
        if restored_state is not None:
            self.simulator.current_state = restored_state

        self.equipment_list: list[Equipment] = self.database_service.get_equipment_catalog()
        self.last_status = self.simulator.current_state.status
        self.parameter_definitions_by_code = {
            definition.code: definition for definition in PARAMETER_DEFINITIONS
        }
        self.trend_history: dict[str, list[float]] = {
            sensor_code: [] for sensor_code in self.TREND_SENSOR_CODES
        }

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_process_values)

        self.tabs = QTabWidget()

        self.add_tab_if_allowed("monitoring", "Мониторинг", self.create_monitoring_tab)
        self.add_tab_if_allowed("equipment", "Оборудование", self.create_equipment_tab)
        self.add_tab_if_allowed("deviations", "Отклонения", self.create_deviations_tab)
        self.add_tab_if_allowed("resources", "Ресурсы", self.create_resources_tab)
        self.add_tab_if_allowed("forecasting", "Прогноз", self.create_forecasting_tab)
        self.add_tab_if_allowed("reports", "Отчеты", self.create_reports_tab)
        self.add_tab_if_allowed("diagnostics", "Диагностика", self.create_diagnostics_tab)
        self.add_tab_if_allowed("shift_journal", "Сменный журнал", self.create_shift_journal_tab)
        self.add_tab_if_allowed("logs", "Журнал", self.create_logs_tab)
        self.add_tab_if_allowed("users", "Пользователи", self.create_users_tab)

        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage(
            f"Пользователь: {self.current_user.display_name} | "
            f"Роль: {self.current_user.role_title}"
        )
        self.switch_user_button = QPushButton("Сменить пользователя")
        self.switch_user_button.clicked.connect(self.request_user_switch)
        self.statusBar().addPermanentWidget(self.switch_user_button)

        self.load_persisted_ui_state()

        self.add_log("INFO", "Система HydroCrack Insight запущена")
        self.add_log("INFO", "Главное окно успешно загружено")
        self.add_log("INFO", "База данных инициализирована")
        if restored_state is not None:
            self.add_log("INFO", "Восстановлено последнее сохраненное состояние процесса")
        self.update_process_values()

    def add_tab_if_allowed(
        self,
        tab_code: str,
        title: str,
        factory: Callable[[], QWidget],
    ) -> None:
        if tab_code in self.accessible_tabs:
            self.tabs.addTab(factory(), title)

    def user_can(self, permission: str) -> bool:
        return has_permission(self.current_user.role_code, permission)

    def configure_button_permission(
        self,
        button: QPushButton,
        permission: str,
    ) -> None:
        button.setEnabled(self.user_can(permission))
        if not button.isEnabled():
            button.setToolTip(f"Недоступно для роли: {self.current_user.role_title}")

    def require_permission(self, permission: str, action_name: str) -> bool:
        if self.user_can(permission):
            return True

        message = (
            f"Доступ запрещен для роли '{self.current_user.role_title}': {action_name}"
        )
        self.add_log("WARNING", message)
        self.audit_action(
            action="access_denied",
            details=action_name,
            level="WARNING",
        )
        return False

    def audit_action(self, action: str, details: str, level: str = "INFO") -> None:
        self.database_service.save_audit_event(
            timestamp=self.get_current_time(),
            username=self.current_user.username,
            role_code=self.current_user.role_code,
            action=action,
            details=details,
            level=level,
        )

    def load_persisted_ui_state(self) -> None:
        self.populate_deviations_from_database()
        self.populate_logs_from_database()
        self.populate_audit_from_database()
        self.populate_trends_from_database()
        self.populate_resources_from_database()
        self.populate_forecast_table()
        self.populate_reports_from_database()
        self.populate_diagnostics_from_runtime()
        self.populate_shift_journal_from_database()
        self.populate_shift_handovers_from_database()

    def request_user_switch(self) -> None:
        self.switch_user_requested.emit()

    def prepare_for_session_switch(self) -> None:
        self.timer.stop()

    def populate_deviations_from_database(self) -> None:
        if not hasattr(self, "deviations_table"):
            return

        records = self.database_service.get_recent_deviations()
        self.deviations_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = [
                record.timestamp,
                record.parameter,
                record.value,
                record.level,
                record.message,
                record.recommendation,
            ]

            for col, cell_value in enumerate(values):
                self.deviations_table.setItem(row, col, QTableWidgetItem(cell_value))

        self.deviations_table.resizeColumnsToContents()

    def populate_logs_from_database(self) -> None:
        if not hasattr(self, "logs_text"):
            return

        self.logs_text.clear()
        for record in self.database_service.get_recent_events():
            self.append_log_entry(record.timestamp, record.level, record.message)

    def populate_audit_from_database(self) -> None:
        if not hasattr(self, "audit_table"):
            return

        records = self.database_service.get_recent_audit_events()
        self.audit_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = [
                record.timestamp,
                record.username,
                record.role_code,
                record.action,
                record.details,
                record.level,
            ]

            for col, cell_value in enumerate(values):
                self.audit_table.setItem(row, col, QTableWidgetItem(cell_value))

        self.audit_table.resizeColumnsToContents()

    def populate_trends_from_database(self) -> None:
        if not hasattr(self, "trend_canvas"):
            return

        for sensor_code in self.trend_history:
            self.trend_history[sensor_code] = []

        for record in self.database_service.get_recent_sensor_data(
            sensor_codes=self.TREND_SENSOR_CODES,
            limit_per_sensor=self.MAX_TREND_POINTS,
        ):
            if record.sensor_code in self.trend_history:
                self.trend_history[record.sensor_code].append(record.value)

        self.refresh_trend_chart()

    def populate_resources_from_database(self) -> None:
        if not hasattr(self, "resources_table"):
            return

        records = self.database_service.get_resource_usage_summary()
        self.resources_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = [
                record.resource_name,
                f"{record.shift_total:.2f}",
                f"{record.shift_limit:.2f}",
                record.shift_status,
                f"{record.daily_total:.2f}",
                f"{record.daily_limit:.2f}",
                record.daily_status,
                record.measurement_unit,
            ]

            for col, cell_value in enumerate(values):
                item = QTableWidgetItem(cell_value)
                if col in (3, 6):
                    self.apply_resource_status_style(item, cell_value)
                self.resources_table.setItem(row, col, item)

        self.resources_table.resizeColumnsToContents()

    def populate_shift_journal_from_database(self) -> None:
        if not hasattr(self, "shift_journal_table"):
            return

        records = self.database_service.get_recent_shift_journal_entries()
        self.shift_journal_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = [
                record.timestamp,
                record.shift_code,
                record.author_username,
                record.level,
                record.equipment_name,
                "да" if record.action_required else "нет",
                record.message,
            ]

            for col, cell_value in enumerate(values):
                self.shift_journal_table.setItem(row, col, QTableWidgetItem(cell_value))

        self.shift_journal_table.resizeColumnsToContents()

    def populate_shift_handovers_from_database(self) -> None:
        if not hasattr(self, "shift_handover_table"):
            return

        records = self.database_service.get_recent_shift_handovers()
        self.shift_handover_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = [
                record.timestamp,
                record.shift_code,
                record.from_user,
                record.to_user,
                f"{record.checked_items}/{record.total_items}",
                record.summary,
                record.open_actions,
            ]

            for col, cell_value in enumerate(values):
                self.shift_handover_table.setItem(row, col, QTableWidgetItem(cell_value))

        self.shift_handover_table.resizeColumnsToContents()

    def populate_forecast_table(self) -> None:
        if not hasattr(self, "forecast_table"):
            return

        state = self.simulator.current_state
        current_yield = self.forecast_service.calculate_product_yield(state)
        self.forecast_current_label.setText(
            f"Текущий расчетный выход: {current_yield:.2f} %"
        )

        records = self.forecast_service.evaluate_scenarios(state)
        self.forecast_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = [
                record.scenario_title,
                f"{record.current_yield:.2f} %",
                f"{record.forecast_yield:.2f} %",
                f"{record.yield_delta:+.2f} п.п.",
                f"{record.forecast_temperature:.1f} °C",
                f"{record.forecast_pressure:.1f} атм",
                f"{record.forecast_feed_flow:.1f} т/ч",
                f"{record.forecast_hydrogen_flow:.1f} нм³/ч",
                record.recommendation,
            ]

            for col, cell_value in enumerate(values):
                item = QTableWidgetItem(cell_value)
                if col == 3:
                    self.apply_forecast_delta_style(item, record.yield_delta)
                self.forecast_table.setItem(row, col, item)

        self.forecast_table.resizeColumnsToContents()

    def populate_reports_from_database(self) -> None:
        if not hasattr(self, "reports_table"):
            return

        records = self.database_service.get_recent_reports()
        self.reports_table.setRowCount(len(records))

        for row, record in enumerate(records):
            values = [
                record.created_at,
                record.report_type,
                record.title,
                record.period_start,
                record.period_end,
                record.created_by,
                record.status,
                record.file_path,
            ]

            for col, cell_value in enumerate(values):
                self.reports_table.setItem(row, col, QTableWidgetItem(cell_value))

        self.reports_table.resizeColumnsToContents()

    def populate_diagnostics_from_runtime(self) -> None:
        if not hasattr(self, "diagnostics_table"):
            return

        try:
            snapshot = self.diagnostic_service.build_snapshot(
                simulator_is_running=self.simulator.is_running,
                simulator_mode=self.simulator.current_state.mode,
                simulator_status=self.simulator.current_state.status,
            )
        except Exception as exc:
            self.diagnostics_status_label.setText(f"Диагностика недоступна: {exc}")
            self.diagnostics_table.setRowCount(0)
            return

        status_title = {
            "ok": "норма",
            "warning": "требует внимания",
            "critical": "критично",
        }.get(snapshot.overall_status, snapshot.overall_status)
        self.diagnostics_status_label.setText(
            f"Состояние системы: {status_title} | обновлено: {snapshot.generated_at}"
        )
        self.apply_diagnostic_label_style(snapshot.overall_status)
        self.diagnostics_table.setRowCount(len(snapshot.items))

        for row, item in enumerate(snapshot.items):
            values = [item.name, item.value, item.status]
            for col, cell_value in enumerate(values):
                table_item = QTableWidgetItem(cell_value)
                if col == 2:
                    self.apply_diagnostic_status_style(table_item, item.status)
                self.diagnostics_table.setItem(row, col, table_item)

        self.diagnostics_table.resizeColumnsToContents()

    def create_monitoring_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Панель мониторинга технологического процесса")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        grid = QGridLayout()

        self.temperature_label = QLabel()
        self.pressure_label = QLabel()
        self.feed_flow_label = QLabel()
        self.hydrogen_flow_label = QLabel()
        self.energy_label = QLabel()
        self.water_label = QLabel()
        self.catalyst_label = QLabel()
        self.product_yield_label = QLabel()
        self.mode_label = QLabel()
        self.status_label = QLabel()

        labels = [
            self.temperature_label,
            self.pressure_label,
            self.feed_flow_label,
            self.hydrogen_flow_label,
            self.energy_label,
            self.water_label,
            self.catalyst_label,
            self.product_yield_label,
            self.mode_label,
            self.status_label,
        ]

        for label in labels:
            label.setStyleSheet(
                """
                font-size: 16px;
                padding: 12px;
                border: 1px solid #cccccc;
                border-radius: 6px;
                """
            )

        grid.addWidget(self.temperature_label, 0, 0)
        grid.addWidget(self.pressure_label, 0, 1)
        grid.addWidget(self.feed_flow_label, 1, 0)
        grid.addWidget(self.hydrogen_flow_label, 1, 1)
        grid.addWidget(self.energy_label, 2, 0)
        grid.addWidget(self.water_label, 2, 1)
        grid.addWidget(self.catalyst_label, 3, 0)
        grid.addWidget(self.product_yield_label, 3, 1)
        grid.addWidget(self.mode_label, 4, 0)
        grid.addWidget(self.status_label, 4, 1)

        mode_layout = QHBoxLayout()
        self.operating_mode_label = QLabel("Технологический режим:")
        self.operating_mode_combo = QComboBox()
        for mode in self.operating_modes:
            self.operating_mode_combo.addItem(mode.title, mode.code)

        active_mode_index = self.operating_mode_combo.findData(
            self.active_operating_mode_profile.mode.code
        )
        if active_mode_index >= 0:
            self.operating_mode_combo.setCurrentIndex(active_mode_index)

        self.operating_mode_combo.currentIndexChanged.connect(
            self.change_operating_mode
        )
        self.operating_mode_combo.setEnabled(self.user_can(CHANGE_OPERATING_MODE))
        if not self.operating_mode_combo.isEnabled():
            self.operating_mode_combo.setToolTip(
                f"Недоступно для роли: {self.current_user.role_title}"
            )

        self.operating_mode_goal_label = QLabel(self.active_operating_mode_profile.mode.goal)
        self.operating_mode_goal_label.setWordWrap(True)

        mode_layout.addWidget(self.operating_mode_label)
        mode_layout.addWidget(self.operating_mode_combo)
        mode_layout.addWidget(self.operating_mode_goal_label)

        self.parameters_table = QTableWidget()
        self.parameters_table.setColumnCount(6)
        self.parameters_table.setHorizontalHeaderLabels(
            ["Параметр", "Значение", "Ед.", "Норма", "Статус", "Режим"]
        )
        self.parameters_table.setRowCount(len(PARAMETER_DEFINITIONS))

        self.trend_figure = Figure(figsize=(9, 4), tight_layout=True)
        self.trend_canvas = FigureCanvas(self.trend_figure)
        self.trend_axes = self.trend_figure.subplots(2, 2).flatten()

        buttons_layout = QHBoxLayout()

        self.start_button = QPushButton("Запустить мониторинг")
        self.stop_button = QPushButton("Остановить мониторинг")
        self.emergency_button = QPushButton("Сымитировать аварию")
        self.reset_button = QPushButton("Сбросить аварию")
        self.import_button = QPushButton("Загрузить данные")

        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.emergency_button.clicked.connect(self.simulate_emergency)
        self.reset_button.clicked.connect(self.reset_emergency_state)
        self.import_button.clicked.connect(self.import_process_data)

        self.configure_button_permission(self.start_button, CONTROL_MONITORING)
        self.configure_button_permission(self.stop_button, CONTROL_MONITORING)
        self.configure_button_permission(self.emergency_button, SIMULATE_EMERGENCY)
        self.configure_button_permission(self.reset_button, RESET_EMERGENCY)
        self.configure_button_permission(self.import_button, IMPORT_PROCESS_DATA)

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.emergency_button)
        buttons_layout.addWidget(self.reset_button)
        buttons_layout.addWidget(self.import_button)

        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addLayout(mode_layout)
        layout.addWidget(self.parameters_table)
        layout.addWidget(self.trend_canvas)
        layout.addLayout(buttons_layout)

        widget.setLayout(layout)
        return widget

    def create_equipment_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Состояние оборудования")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.equipment_table = QTableWidget()
        self.equipment_table.setColumnCount(4)
        self.equipment_table.setHorizontalHeaderLabels(
            ["Оборудование", "Тип", "Состояние", "Описание"]
        )

        self.reset_equipment_button = QPushButton("Сбросить статусы оборудования")
        self.reset_equipment_button.clicked.connect(self.reset_equipment_statuses)
        self.configure_button_permission(
            self.reset_equipment_button,
            RESET_EQUIPMENT_STATUSES,
        )

        layout.addWidget(title)
        layout.addWidget(self.equipment_table)
        layout.addWidget(self.reset_equipment_button)

        widget.setLayout(layout)

        self.update_equipment_table()

        return widget

    def create_deviations_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Отклонения и предупреждения")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.deviations_table = QTableWidget()
        self.deviations_table.setColumnCount(6)
        self.deviations_table.setHorizontalHeaderLabels(
            [
                "Время",
                "Параметр",
                "Значение",
                "Уровень",
                "Сообщение",
                "Рекомендация",
            ]
        )

        self.deviations_table.setRowCount(0)
        self.deviations_table.resizeColumnsToContents()

        layout.addWidget(title)
        layout.addWidget(self.deviations_table)

        widget.setLayout(layout)
        return widget

    def create_resources_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Учет расхода ресурсов")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.resources_table = QTableWidget()
        self.resources_table.setColumnCount(8)
        self.resources_table.setHorizontalHeaderLabels(
            [
                "Ресурс",
                "За смену",
                "Лимит смены",
                "Статус смены",
                "За сутки",
                "Лимит суток",
                "Статус суток",
                "Ед.",
            ]
        )

        refresh_button = QPushButton("Обновить ресурсы")
        refresh_button.clicked.connect(self.populate_resources_from_database)

        layout.addWidget(title)
        layout.addWidget(self.resources_table)
        layout.addWidget(refresh_button)

        widget.setLayout(layout)
        return widget

    def create_forecasting_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Прогнозирование и оптимизация")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.forecast_current_label = QLabel()
        self.forecast_current_label.setStyleSheet(
            """
            font-size: 16px;
            padding: 10px;
            border: 1px solid #cccccc;
            border-radius: 6px;
            """
        )

        self.forecast_table = QTableWidget()
        self.forecast_table.setColumnCount(9)
        self.forecast_table.setHorizontalHeaderLabels(
            [
                "Сценарий",
                "Сейчас",
                "Прогноз",
                "Изменение",
                "Температура",
                "Давление",
                "Сырье",
                "Водород",
                "Рекомендация",
            ]
        )

        refresh_button = QPushButton("Рассчитать сценарии")
        refresh_button.clicked.connect(self.calculate_forecast_scenarios)

        layout.addWidget(title)
        layout.addWidget(self.forecast_current_label)
        layout.addWidget(self.forecast_table)
        layout.addWidget(refresh_button)

        widget.setLayout(layout)
        return widget

    def create_shift_journal_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Сменный журнал и итог смены")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.shift_journal_table = QTableWidget()
        self.shift_journal_table.setColumnCount(7)
        self.shift_journal_table.setHorizontalHeaderLabels(
            [
                "Время",
                "Смена",
                "Автор",
                "Уровень",
                "Оборудование",
                "Требует действий",
                "Сообщение",
            ]
        )

        journal_form = QGridLayout()
        self.shift_code_input = QLineEdit("Смена A")
        self.journal_level_combo = QComboBox()
        self.journal_level_combo.addItems(["INFO", "WARNING", "ACTION"])
        self.journal_equipment_combo = QComboBox()
        self.journal_equipment_combo.addItem("Без привязки", "")
        for equipment in self.equipment_list:
            self.journal_equipment_combo.addItem(equipment.name, equipment.name)

        self.action_required_checkbox = QCheckBox("Требуется действие")
        self.journal_message_input = QLineEdit()
        self.journal_message_input.setPlaceholderText("Краткая запись по смене")
        self.add_shift_entry_button = QPushButton("Добавить запись")
        self.add_shift_entry_button.clicked.connect(self.add_shift_journal_entry)
        self.configure_button_permission(
            self.add_shift_entry_button,
            CREATE_SHIFT_ENTRY,
        )

        journal_form.addWidget(QLabel("Смена"), 0, 0)
        journal_form.addWidget(self.shift_code_input, 0, 1)
        journal_form.addWidget(QLabel("Уровень"), 0, 2)
        journal_form.addWidget(self.journal_level_combo, 0, 3)
        journal_form.addWidget(QLabel("Оборудование"), 1, 0)
        journal_form.addWidget(self.journal_equipment_combo, 1, 1)
        journal_form.addWidget(self.action_required_checkbox, 1, 2)
        journal_form.addWidget(self.add_shift_entry_button, 1, 3)
        journal_form.addWidget(QLabel("Сообщение"), 2, 0)
        journal_form.addWidget(self.journal_message_input, 2, 1, 1, 3)

        handover_title = QLabel("Итог смены")
        handover_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handover_title.setStyleSheet("font-size: 18px; font-weight: bold;")

        handover_form = QGridLayout()
        self.handover_to_user_combo = QComboBox()
        for account in self.database_service.get_active_user_accounts():
            self.handover_to_user_combo.addItem(
                f"{account.display_name} ({account.role_title})",
                account.username,
            )

        self.handover_summary_input = QLineEdit()
        self.handover_summary_input.setPlaceholderText("Состояние установки на конец смены")
        self.handover_open_actions_input = QLineEdit()
        self.handover_open_actions_input.setPlaceholderText("Открытые действия или риски")

        checklist_layout = QGridLayout()
        self.handover_checkboxes: list[tuple[str, str, QCheckBox]] = []
        checklist_items = (
            ("parameters_checked", "Параметры процесса проверены"),
            ("deviations_reviewed", "Отклонения и рекомендации просмотрены"),
            ("equipment_checked", "Статусы оборудования актуальны"),
            ("resources_checked", "Расход ресурсов проверен"),
        )
        for row, (item_code, item_title) in enumerate(checklist_items):
            checkbox = QCheckBox(item_title)
            self.handover_checkboxes.append((item_code, item_title, checkbox))
            checklist_layout.addWidget(checkbox, row // 2, row % 2)

        self.create_handover_button = QPushButton("Зафиксировать итог смены")
        self.create_handover_button.clicked.connect(self.create_shift_handover)
        self.configure_button_permission(
            self.create_handover_button,
            CREATE_SHIFT_HANDOVER,
        )

        handover_form.addWidget(QLabel("Ознакомить"), 0, 0)
        handover_form.addWidget(self.handover_to_user_combo, 0, 1)
        handover_form.addWidget(QLabel("Итог смены"), 1, 0)
        handover_form.addWidget(self.handover_summary_input, 1, 1)
        handover_form.addWidget(QLabel("Открытые действия"), 2, 0)
        handover_form.addWidget(self.handover_open_actions_input, 2, 1)
        handover_form.addLayout(checklist_layout, 3, 0, 1, 2)
        handover_form.addWidget(self.create_handover_button, 4, 1)

        self.shift_handover_table = QTableWidget()
        self.shift_handover_table.setColumnCount(7)
        self.shift_handover_table.setHorizontalHeaderLabels(
            [
                "Время",
                "Смена",
                "Ответственный",
                "Ознакомлен",
                "Чек-лист",
                "Итог",
                "Открытые действия",
            ]
        )

        layout.addWidget(title)
        layout.addLayout(journal_form)
        layout.addWidget(self.shift_journal_table)
        layout.addWidget(handover_title)
        layout.addLayout(handover_form)
        layout.addWidget(self.shift_handover_table)

        widget.setLayout(layout)
        return widget

    def create_reports_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Отчетность")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        description = QLabel(
            "Формирование PDF-отчетов по сохраненным данным установки."
        )
        description.setWordWrap(True)

        daily_report_button = QPushButton("Сформировать суточный отчет")
        resources_report_button = QPushButton("Сформировать отчет по ресурсам")
        emergency_report_button = QPushButton("Сформировать отчет по авариям")
        shift_report_button = QPushButton("Сформировать сменный отчет")
        database_stats_button = QPushButton("Показать статистику БД")

        daily_report_button.clicked.connect(self.generate_daily_report)
        resources_report_button.clicked.connect(self.generate_resources_report)
        emergency_report_button.clicked.connect(self.generate_emergency_report)
        shift_report_button.clicked.connect(self.generate_shift_report)
        database_stats_button.clicked.connect(self.show_database_statistics)
        self.configure_button_permission(
            database_stats_button,
            VIEW_DATABASE_STATISTICS,
        )

        self.reports_table = QTableWidget()
        self.reports_table.setColumnCount(8)
        self.reports_table.setHorizontalHeaderLabels(
            [
                "Создан",
                "Тип",
                "Название",
                "Период с",
                "Период по",
                "Автор",
                "Статус",
                "Файл",
            ]
        )

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(daily_report_button)
        buttons_layout.addWidget(resources_report_button)
        buttons_layout.addWidget(emergency_report_button)
        buttons_layout.addWidget(shift_report_button)
        buttons_layout.addWidget(database_stats_button)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addLayout(buttons_layout)
        layout.addWidget(self.reports_table)

        widget.setLayout(layout)
        return widget

    def create_diagnostics_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Диагностика и надежность")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.diagnostics_status_label = QLabel()
        self.diagnostics_status_label.setStyleSheet(
            """
            font-size: 16px;
            padding: 10px;
            border: 1px solid #cccccc;
            border-radius: 6px;
            """
        )

        self.diagnostics_table = QTableWidget()
        self.diagnostics_table.setColumnCount(3)
        self.diagnostics_table.setHorizontalHeaderLabels(
            ["Проверка", "Значение", "Статус"]
        )

        buttons_layout = QHBoxLayout()
        refresh_button = QPushButton("Обновить диагностику")
        self.backup_database_button = QPushButton("Создать резервную копию БД")

        refresh_button.clicked.connect(self.populate_diagnostics_from_runtime)
        self.backup_database_button.clicked.connect(self.create_database_backup)
        self.configure_button_permission(
            self.backup_database_button,
            BACKUP_DATABASE,
        )

        buttons_layout.addWidget(refresh_button)
        buttons_layout.addWidget(self.backup_database_button)

        layout.addWidget(title)
        layout.addWidget(self.diagnostics_status_label)
        layout.addWidget(self.diagnostics_table)
        layout.addLayout(buttons_layout)

        widget.setLayout(layout)
        return widget

    def create_logs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Журнал событий")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)

        layout.addWidget(title)
        layout.addWidget(self.logs_text)

        widget.setLayout(layout)
        return widget

    def create_users_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Пользователи и роли")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.users_table = QTableWidget()
        self.users_table.setColumnCount(5)
        self.users_table.setHorizontalHeaderLabels(
            ["Логин", "Имя", "Роль", "Активен", "Ответственность"]
        )

        user_accounts = self.database_service.get_user_accounts()
        self.users_table.setRowCount(len(user_accounts))

        for row, account in enumerate(user_accounts):
            self.users_table.setItem(row, 0, QTableWidgetItem(account.username))
            self.users_table.setItem(row, 1, QTableWidgetItem(account.display_name))
            self.users_table.setItem(row, 2, QTableWidgetItem(account.role_title))
            self.users_table.setItem(
                row,
                3,
                QTableWidgetItem("Да" if account.is_active else "Нет"),
            )
            self.users_table.setItem(row, 4, QTableWidgetItem(account.responsibility))

        self.users_table.resizeColumnsToContents()

        audit_title = QLabel("Аудит действий")
        audit_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        audit_title.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.audit_table = QTableWidget()
        self.audit_table.setColumnCount(6)
        self.audit_table.setHorizontalHeaderLabels(
            ["Время", "Пользователь", "Роль", "Действие", "Описание", "Уровень"]
        )

        layout.addWidget(title)
        layout.addWidget(self.users_table)
        layout.addWidget(audit_title)
        layout.addWidget(self.audit_table)

        widget.setLayout(layout)
        return widget

    def start_monitoring(self) -> None:
        if not self.require_permission(CONTROL_MONITORING, "запуск мониторинга"):
            return

        self.simulator.reset_to_normal()
        self.simulator.start()
        self.timer.start()
        self.last_status = "норма"
        self.add_log("INFO", "Мониторинг технологического процесса запущен")
        self.audit_action("monitoring_started", "Запуск мониторинга")

    def stop_monitoring(self) -> None:
        if not self.require_permission(CONTROL_MONITORING, "остановка мониторинга"):
            return

        self.simulator.stop()
        self.timer.stop()
        self.update_process_values()
        self.add_log("INFO", "Мониторинг технологического процесса остановлен")
        self.audit_action("monitoring_stopped", "Остановка мониторинга")

    def simulate_emergency(self) -> None:
        if not self.require_permission(SIMULATE_EMERGENCY, "симуляция аварии"):
            return

        self.simulator.start()
        self.timer.start()

        scenario_name = self.simulator.simulate_emergency()
        self.add_log("WARNING", f"Запущен сценарий отклонения: {scenario_name}")
        self.audit_action(
            action="emergency_simulated",
            details=f"Запущен сценарий отклонения: {scenario_name}",
            level="WARNING",
        )

    def reset_emergency_state(self) -> None:
        if not self.require_permission(RESET_EMERGENCY, "сброс аварийного состояния"):
            return

        self.simulator.reset_to_normal()
        self.emergency_service.reset_equipment(self.equipment_list)
        self.update_equipment_table()
        self.last_status = "норма"

        self.database_service.save_equipment_statuses(
            timestamp=self.get_current_time(),
            equipment_list=self.equipment_list,
        )

        self.add_log(
            "INFO",
            "Аварийное состояние сброшено. Оборудование возвращено в рабочий режим.",
        )

        self.update_process_values()
        self.audit_action("emergency_reset", "Сброс аварийного состояния")

    def reset_equipment_statuses(self) -> None:
        if not self.require_permission(
            RESET_EQUIPMENT_STATUSES,
            "сброс статусов оборудования",
        ):
            return

        self.emergency_service.reset_equipment(self.equipment_list)
        self.update_equipment_table()

        self.database_service.save_equipment_statuses(
            timestamp=self.get_current_time(),
            equipment_list=self.equipment_list,
        )

        self.add_log("INFO", "Статусы оборудования сброшены вручную")
        self.audit_action("equipment_statuses_reset", "Сброс статусов оборудования")

    def import_process_data(self) -> None:
        if not self.require_permission(IMPORT_PROCESS_DATA, "импорт данных процесса"):
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт данных процесса",
            "",
            "Табличные файлы (*.csv *.xlsx *.xls);;CSV (*.csv);;Excel (*.xlsx *.xls)",
        )

        if not file_path:
            return

        try:
            import_result = self.process_data_importer.import_file(file_path)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка импорта", str(exc))
            self.add_log("WARNING", f"Ошибка импорта данных: {exc}")
            self.audit_action(
                action="process_data_import_failed",
                details=str(exc),
                level="WARNING",
            )
            return

        self.timer.stop()

        for index, state in enumerate(import_result.states):
            timestamp = import_result.timestamps[index] or self.get_current_time()
            self.database_service.save_process_state(
                timestamp,
                state,
                operating_mode_profile=self.active_operating_mode_profile,
            )

        if import_result.last_state is not None:
            self.simulator.current_state = import_result.last_state
            self.update_process_values(save_state=False)

        self.populate_trends_from_database()
        self.populate_resources_from_database()
        self.add_log(
            "INFO",
            f"Импортировано строк технологических данных: {import_result.imported_count}",
        )
        self.audit_action(
            action="process_data_imported",
            details=f"Импортировано строк: {import_result.imported_count}",
        )

    def change_operating_mode(self, _index: int | None = None) -> None:
        if not hasattr(self, "operating_mode_combo"):
            return

        mode_code = str(self.operating_mode_combo.currentData())
        if mode_code == self.active_operating_mode_profile.mode.code:
            return

        if not self.require_permission(
            CHANGE_OPERATING_MODE,
            "смена технологического режима",
        ):
            active_mode_index = self.operating_mode_combo.findData(
                self.active_operating_mode_profile.mode.code
            )
            if active_mode_index >= 0:
                self.operating_mode_combo.blockSignals(True)
                self.operating_mode_combo.setCurrentIndex(active_mode_index)
                self.operating_mode_combo.blockSignals(False)
            return

        previous_mode_title = self.active_operating_mode_profile.mode.title
        self.database_service.set_active_operating_mode(mode_code)
        self.active_operating_mode_profile = (
            self.database_service.get_active_operating_mode_profile()
        )
        self.operating_mode_goal_label.setText(
            self.active_operating_mode_profile.mode.goal
        )

        self.add_log(
            "INFO",
            (
                f"Технологический режим изменен: {previous_mode_title} -> "
                f"{self.active_operating_mode_profile.mode.title}"
            ),
        )
        self.audit_action(
            action="operating_mode_changed",
            details=(
                f"{previous_mode_title} -> "
                f"{self.active_operating_mode_profile.mode.title}"
            ),
        )
        self.update_process_values(save_state=False)

    def update_parameters_table(
        self,
        parameter_snapshots: tuple[ParameterSnapshot, ...],
        mode_title: str,
    ) -> None:
        if not hasattr(self, "parameters_table"):
            return

        self.parameters_table.setRowCount(len(parameter_snapshots))

        for row, snapshot in enumerate(parameter_snapshots):
            values = [
                snapshot.title,
                snapshot.formatted_value,
                snapshot.measurement_unit,
                snapshot.normal_range,
                snapshot.status,
                mode_title,
            ]

            for col, cell_value in enumerate(values):
                item = QTableWidgetItem(cell_value)
                if col == 4:
                    self.apply_parameter_status_style(item, snapshot.status)
                self.parameters_table.setItem(row, col, item)

        self.parameters_table.resizeColumnsToContents()

    def append_trend_points(
        self,
        parameter_snapshots: tuple[ParameterSnapshot, ...],
    ) -> None:
        if not hasattr(self, "trend_canvas"):
            return

        snapshot_by_code = {
            snapshot.code: snapshot for snapshot in parameter_snapshots
        }

        for sensor_code in self.TREND_SENSOR_CODES:
            snapshot = snapshot_by_code[sensor_code]
            values = self.trend_history[sensor_code]
            values.append(snapshot.value)
            del values[:-self.MAX_TREND_POINTS]

    def refresh_trend_chart(self) -> None:
        if not hasattr(self, "trend_canvas"):
            return

        for axis, sensor_code in zip(self.trend_axes, self.TREND_SENSOR_CODES):
            definition = self.parameter_definitions_by_code[sensor_code]
            mode_limit = self.active_operating_mode_profile.get_limit(sensor_code)
            normal_min = (
                mode_limit.min_value if mode_limit is not None else definition.normal_min
            )
            normal_max = (
                mode_limit.max_value if mode_limit is not None else definition.normal_max
            )
            values = self.trend_history[sensor_code]

            axis.clear()
            axis.set_title(definition.title, fontsize=9)
            axis.set_ylabel(definition.measurement_unit, fontsize=8)
            axis.grid(True, linewidth=0.4, alpha=0.35)

            if values:
                axis.plot(range(1, len(values) + 1), values, color="#2f6fed", linewidth=1.8)
                axis.axhline(normal_min, color="#2b8a3e", linewidth=0.8)
                axis.axhline(normal_max, color="#c92a2a", linewidth=0.8)

        self.trend_canvas.draw_idle()

    def update_process_values(self, save_state: bool = True) -> None:
        state = self.simulator.generate_next_state()

        analysis_result = self.deviation_analyzer.analyze(
            state,
            operating_mode_profile=self.active_operating_mode_profile,
        )
        state.status = analysis_result.status

        self.temperature_label.setText(f"Температура: {state.temperature:.1f} °C")
        self.pressure_label.setText(f"Давление: {state.pressure:.1f} атм")
        self.feed_flow_label.setText(f"Расход сырья: {state.feed_flow:.1f} т/ч")
        self.hydrogen_flow_label.setText(
            f"Расход водорода: {state.hydrogen_flow:.1f} нм³/ч"
        )
        self.energy_label.setText(f"Энергия: {state.energy:.1f} кВт⋅ч")
        self.water_label.setText(f"Вода: {state.water_consumption:.1f} м³/ч")
        self.catalyst_label.setText(
            f"Катализатор: {state.catalyst_consumption:.2f} кг/ч"
        )
        self.product_yield_label.setText(
            f"Выход продукции: {state.product_yield:.1f} %"
        )
        self.mode_label.setText(f"Режим: {state.mode}")
        self.status_label.setText(f"Статус: {state.status}")

        parameter_snapshots = build_parameter_snapshots(
            state,
            operating_mode_profile=self.active_operating_mode_profile,
        )
        self.update_parameters_table(
            parameter_snapshots,
            self.active_operating_mode_profile.mode.title,
        )
        self.populate_forecast_table()
        self.append_trend_points(parameter_snapshots)
        self.refresh_trend_chart()

        self.apply_status_style(state.status)

        current_time = self.get_current_time()
        if save_state:
            self.database_service.save_process_state(
                current_time,
                state,
                operating_mode_profile=self.active_operating_mode_profile,
            )
            self.populate_resources_from_database()
            self.populate_diagnostics_from_runtime()

        if state.status != self.last_status:
            self.handle_analysis_result(analysis_result)

        self.last_status = state.status

    def handle_analysis_result(self, result: DeviationResult) -> None:
        if not result.has_deviation:
            self.add_log("INFO", "Параметры технологического процесса вернулись в норму")
            return

        self.add_deviation(
            parameter=result.parameter or "—",
            value=result.value or "—",
            level=result.level,
            message=result.message,
            recommendation=result.recommendation,
        )

        if result.is_emergency:
            self.add_log("CRITICAL", result.message)

            emergency_response = self.emergency_service.process_emergency(
                deviation=result,
                equipment_list=self.equipment_list,
            )

            self.handle_emergency_response(emergency_response)
        else:
            self.add_log("WARNING", result.message)

    def handle_emergency_response(self, response: EmergencyResponse) -> None:
        if not response.is_required:
            return

        self.add_log("CRITICAL", f"Аварийное реагирование: {response.emergency_type}")
        self.add_log("ACTION", response.operator_message)

        for action in response.actions:
            self.add_log(
                "ACTION",
                (
                    f"{action.equipment_name}: статус изменен на "
                    f"'{action.new_status}'. Действие: {action.action_description}"
                ),
            )

        self.update_equipment_table()

        self.database_service.save_equipment_statuses(
            timestamp=self.get_current_time(),
            equipment_list=self.equipment_list,
        )

    def update_equipment_table(self) -> None:
        if not hasattr(self, "equipment_table"):
            return

        self.equipment_table.setRowCount(len(self.equipment_list))

        for row, equipment in enumerate(self.equipment_list):
            self.equipment_table.setItem(row, 0, QTableWidgetItem(equipment.name))
            self.equipment_table.setItem(
                row,
                1,
                QTableWidgetItem(equipment.equipment_type),
            )
            self.equipment_table.setItem(row, 2, QTableWidgetItem(equipment.status))
            self.equipment_table.setItem(
                row,
                3,
                QTableWidgetItem(equipment.description),
            )

            self.apply_equipment_status_style(row, equipment.status)

        self.equipment_table.resizeColumnsToContents()

    def apply_equipment_status_style(self, row: int, status: str) -> None:
        status_item = self.equipment_table.item(row, 2)

        if status_item is None:
            return

        if status == "Работает":
            status_item.setBackground(Qt.GlobalColor.green)
        elif status in (
            "Требуется проверка",
            "Сниженная нагрузка",
            "Контроль давления",
        ):
            status_item.setBackground(Qt.GlobalColor.yellow)
        elif status in (
            "Авария",
            "Аварийное регулирование",
            "Безопасный режим",
        ):
            status_item.setBackground(Qt.GlobalColor.red)

    @staticmethod
    def apply_parameter_status_style(item: QTableWidgetItem, status: str) -> None:
        if status == "норма":
            item.setBackground(Qt.GlobalColor.green)
        else:
            item.setBackground(Qt.GlobalColor.yellow)

    @staticmethod
    def apply_resource_status_style(item: QTableWidgetItem, status: str) -> None:
        if status == "норма":
            item.setBackground(Qt.GlobalColor.green)
        elif status == "перерасход":
            item.setBackground(Qt.GlobalColor.yellow)
        elif status == "критический перерасход":
            item.setBackground(Qt.GlobalColor.red)

    @staticmethod
    def apply_forecast_delta_style(item: QTableWidgetItem, delta: float) -> None:
        if delta > 1.0:
            item.setBackground(Qt.GlobalColor.green)
        elif delta < -1.0:
            item.setBackground(Qt.GlobalColor.yellow)

    def apply_diagnostic_label_style(self, status: str) -> None:
        base_style = """
            font-size: 16px;
            padding: 10px;
            border: 1px solid #cccccc;
            border-radius: 6px;
            font-weight: bold;
        """
        if status == "ok":
            self.diagnostics_status_label.setStyleSheet(
                base_style + "background-color: #d9fdd3; color: #1f6b2a;"
            )
        elif status == "warning":
            self.diagnostics_status_label.setStyleSheet(
                base_style + "background-color: #fff3cd; color: #8a6d00;"
            )
        elif status == "critical":
            self.diagnostics_status_label.setStyleSheet(
                base_style + "background-color: #f8d7da; color: #842029;"
            )
        else:
            self.diagnostics_status_label.setStyleSheet(base_style)

    @staticmethod
    def apply_diagnostic_status_style(item: QTableWidgetItem, status: str) -> None:
        if status == "ok":
            item.setBackground(Qt.GlobalColor.green)
        elif status == "warning":
            item.setBackground(Qt.GlobalColor.yellow)
        elif status == "critical":
            item.setBackground(Qt.GlobalColor.red)

    def calculate_forecast_scenarios(self) -> None:
        self.populate_forecast_table()
        self.add_log("INFO", "Выполнен расчет прогнозных сценариев")
        self.audit_action(
            action="forecast_scenarios_calculated",
            details="Расчет сценариев прогнозирования и оптимизации",
        )

    def generate_daily_report(self) -> None:
        self.generate_report("daily")

    def generate_resources_report(self) -> None:
        self.generate_report("resources")

    def generate_emergency_report(self) -> None:
        self.generate_report("emergency")

    def generate_shift_report(self) -> None:
        self.generate_report("shift")

    def generate_report(self, report_type: str) -> None:
        if not self.require_permission(VIEW_REPORTS, "формирование отчетов"):
            return

        generators = {
            "daily": self.report_service.generate_daily_report,
            "resources": self.report_service.generate_resources_report,
            "emergency": self.report_service.generate_emergency_report,
            "shift": self.report_service.generate_shift_report,
        }

        generator = generators[report_type]
        try:
            result = generator(self.current_user.username)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка отчета", str(exc))
            self.add_log("WARNING", f"Ошибка формирования отчета: {exc}")
            self.audit_action(
                action="report_generation_failed",
                details=f"{report_type}: {exc}",
                level="WARNING",
            )
            return

        self.populate_reports_from_database()
        self.add_log("INFO", f"Сформирован отчет: {result.title}")
        self.audit_action(
            action="report_generated",
            details=f"{result.title}: {result.pdf_path}",
        )
        QMessageBox.information(
            self,
            "Отчет создан",
            f"PDF: {result.pdf_path}",
        )

    def create_database_backup(self) -> None:
        if not self.require_permission(
            BACKUP_DATABASE,
            "создание резервной копии БД",
        ):
            return

        backup_dir = QFileDialog.getExistingDirectory(
            self,
            "Папка для резервной копии БД",
            "backups",
        )
        if not backup_dir:
            return

        try:
            result = self.diagnostic_service.backup_database(backup_dir)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка резервного копирования", str(exc))
            self.add_log("WARNING", f"Ошибка резервного копирования БД: {exc}")
            self.audit_action(
                action="database_backup_failed",
                details=str(exc),
                level="WARNING",
            )
            return

        self.populate_diagnostics_from_runtime()
        self.add_log("INFO", f"Создана резервная копия БД: {result.path}")
        self.audit_action(
            action="database_backup_created",
            details=str(result.path),
        )
        QMessageBox.information(
            self,
            "Резервная копия создана",
            f"Файл: {result.path}\nРазмер: {result.size_bytes} байт",
        )

    def add_shift_journal_entry(self) -> None:
        if not self.require_permission(
            CREATE_SHIFT_ENTRY,
            "добавление записи в сменный журнал",
        ):
            return

        message = self.journal_message_input.text().strip()
        if not message:
            QMessageBox.warning(self, "Сменный журнал", "Введите текст записи.")
            return

        equipment_name = str(self.journal_equipment_combo.currentData() or "")
        self.database_service.save_shift_journal_entry(
            timestamp=self.get_current_time(),
            shift_code=self.shift_code_input.text().strip() or "Смена A",
            author_username=self.current_user.username,
            level=self.journal_level_combo.currentText(),
            message=message,
            equipment_name=equipment_name or None,
            action_required=self.action_required_checkbox.isChecked(),
        )

        self.journal_message_input.clear()
        self.action_required_checkbox.setChecked(False)
        self.populate_shift_journal_from_database()
        self.add_log("INFO", "Добавлена запись в сменный журнал")
        self.audit_action("shift_journal_entry_created", message)

    def create_shift_handover(self) -> None:
        if not self.require_permission(
            CREATE_SHIFT_HANDOVER,
            "фиксация итога смены",
        ):
            return

        to_user = str(self.handover_to_user_combo.currentData() or "")
        if not to_user:
            QMessageBox.warning(self, "Итог смены", "Выберите пользователя для ознакомления.")
            return

        summary = self.handover_summary_input.text().strip() or "Смена без замечаний"
        open_actions = self.handover_open_actions_input.text().strip() or "Нет"
        checklist_items = tuple(
            (item_code, title, checkbox.isChecked(), "")
            for item_code, title, checkbox in self.handover_checkboxes
        )

        self.database_service.create_shift_handover(
            timestamp=self.get_current_time(),
            from_user=self.current_user.username,
            to_user=to_user,
            shift_code=self.shift_code_input.text().strip() or "Смена A",
            summary=summary,
            open_actions=open_actions,
            checklist_items=checklist_items,
        )

        self.handover_summary_input.clear()
        self.handover_open_actions_input.clear()
        for _item_code, _title, checkbox in self.handover_checkboxes:
            checkbox.setChecked(False)

        self.populate_shift_handovers_from_database()
        self.add_log("ACTION", f"Зафиксирован итог смены: {self.current_user.username} -> {to_user}")
        self.audit_action(
            action="shift_summary_created",
            details=f"{self.current_user.username} -> {to_user}; {summary}",
        )

    def add_deviation(
        self,
        parameter: str,
        value: str,
        level: str,
        message: str,
        recommendation: str,
    ) -> None:
        current_time = self.get_current_time()

        if hasattr(self, "deviations_table"):
            self.deviations_table.insertRow(0)

            values = [
                current_time,
                parameter,
                value,
                level,
                message,
                recommendation,
            ]

            for col, cell_value in enumerate(values):
                self.deviations_table.setItem(0, col, QTableWidgetItem(cell_value))

            self.deviations_table.resizeColumnsToContents()

        self.database_service.save_deviation(
            timestamp=current_time,
            parameter=parameter,
            value=value,
            level=level,
            message=message,
            recommendation=recommendation,
        )

    def add_log(self, level: str, message: str) -> None:
        current_time = self.get_current_time()
        self.append_log_entry(current_time, level, message)

        self.database_service.save_event(
            timestamp=current_time,
            level=level,
            message=message,
        )

    def append_log_entry(self, timestamp: str, level: str, message: str) -> None:
        if hasattr(self, "logs_text"):
            self.logs_text.append(f"[{timestamp}] [{level}] {message}")

    def show_database_statistics(self) -> None:
        if not self.require_permission(
            VIEW_DATABASE_STATISTICS,
            "просмотр статистики БД",
        ):
            return

        counts = self.database_service.get_counts()

        self.add_log(
            "INFO",
            (
                "Статистика БД: "
                f"ролей — {counts['roles']}, "
                f"датчиков — {counts['sensors']}, "
                f"режимов — {counts['operating_modes']}, "
                f"параметров процесса — {counts['process_values']}, "
                f"показаний датчиков — {counts['sensor_data']}, "
                f"ресурсов — {counts['resource_usage']}, "
                f"отклонений — {counts['deviations']}, "
                f"рекомендаций — {counts['recommendations']}, "
                f"событий — {counts['events']}, "
                f"статусов оборудования — {counts['equipment_statuses']}"
            ),
        )
        self.audit_action("database_statistics_viewed", "Просмотр статистики БД")

    @staticmethod
    def get_current_time() -> str:
        return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    def apply_status_style(self, status: str) -> None:
        base_style = """
            font-size: 16px;
            padding: 12px;
            border: 1px solid #cccccc;
            border-radius: 6px;
            font-weight: bold;
        """

        if status == "норма":
            self.status_label.setStyleSheet(
                base_style + "background-color: #d9fdd3; color: #1f6b2a;"
            )
        elif status == "предупреждение":
            self.status_label.setStyleSheet(
                base_style + "background-color: #fff3cd; color: #8a6d00;"
            )
        elif status == "авария":
            self.status_label.setStyleSheet(
                base_style + "background-color: #f8d7da; color: #842029;"
            )
        else:
            self.status_label.setStyleSheet(base_style)
