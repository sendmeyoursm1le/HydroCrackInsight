from collections.abc import Callable
from datetime import datetime

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QComboBox,
    QHBoxLayout,
    QFileDialog,
    QLabel,
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
from app.models.equipment import Equipment
from app.monitoring.deviation_analyzer import DeviationAnalyzer, DeviationResult
from app.monitoring.parameter_snapshot import (
    PARAMETER_DEFINITIONS,
    ParameterSnapshot,
    build_parameter_snapshots,
)
from app.monitoring.process_data_importer import ProcessDataImporter
from app.simulation.sensor_simulator import SensorSimulator
from app.users import (
    CHANGE_OPERATING_MODE,
    CONTROL_MONITORING,
    IMPORT_PROCESS_DATA,
    RESET_EMERGENCY,
    RESET_EQUIPMENT_STATUSES,
    SIMULATE_EMERGENCY,
    VIEW_DATABASE_STATISTICS,
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

        self.database_service = database_service or DatabaseService()
        self.database_service.initialize_database()
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
        self.add_tab_if_allowed("reports", "Отчеты", self.create_reports_tab)
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
        self.import_button = QPushButton("Импорт CSV/Excel")

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

    def create_reports_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Отчетность")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        description = QLabel(
            "В этом разделе позже будет формирование суточных, недельных "
            "и аварийных отчетов по работе установки."
        )
        description.setWordWrap(True)

        daily_report_button = QPushButton("Сформировать суточный отчет")
        resources_report_button = QPushButton("Сформировать отчет по ресурсам")
        emergency_report_button = QPushButton("Сформировать отчет по авариям")
        database_stats_button = QPushButton("Показать статистику БД")

        database_stats_button.clicked.connect(self.show_database_statistics)
        self.configure_button_permission(
            database_stats_button,
            VIEW_DATABASE_STATISTICS,
        )

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(daily_report_button)
        layout.addWidget(resources_report_button)
        layout.addWidget(emergency_report_button)
        layout.addWidget(database_stats_button)
        layout.addStretch()

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
