from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.deviation_analyzer import DeviationAnalyzer, DeviationResult
from app.core.emergency_service import EmergencyResponse, EmergencyService
from app.models.equipment import Equipment, create_default_equipment
from app.simulation.sensor_simulator import SensorSimulator


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("HydroCrack Insight")
        self.resize(1200, 750)

        self.simulator = SensorSimulator()
        self.deviation_analyzer = DeviationAnalyzer()
        self.emergency_service = EmergencyService()

        self.equipment_list: list[Equipment] = create_default_equipment()

        self.last_status = "норма"

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_process_values)

        self.tabs = QTabWidget()

        self.tabs.addTab(self.create_monitoring_tab(), "Мониторинг")
        self.tabs.addTab(self.create_equipment_tab(), "Оборудование")
        self.tabs.addTab(self.create_deviations_tab(), "Отклонения")
        self.tabs.addTab(self.create_reports_tab(), "Отчеты")
        self.tabs.addTab(self.create_logs_tab(), "Журнал")

        self.setCentralWidget(self.tabs)

        self.add_log("INFO", "Система HydroCrack Insight запущена")
        self.add_log("INFO", "Главное окно успешно загружено")
        self.update_process_values()

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

        buttons_layout = QHBoxLayout()

        self.start_button = QPushButton("Запустить мониторинг")
        self.stop_button = QPushButton("Остановить мониторинг")
        self.emergency_button = QPushButton("Сымитировать аварию")
        self.reset_button = QPushButton("Сбросить аварию")

        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.emergency_button.clicked.connect(self.simulate_emergency)
        self.reset_button.clicked.connect(self.reset_emergency_state)

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.emergency_button)
        buttons_layout.addWidget(self.reset_button)

        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addLayout(buttons_layout)
        layout.addStretch()

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

        reset_equipment_button = QPushButton("Сбросить статусы оборудования")
        reset_equipment_button.clicked.connect(self.reset_equipment_statuses)

        layout.addWidget(title)
        layout.addWidget(self.equipment_table)
        layout.addWidget(reset_equipment_button)

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

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(daily_report_button)
        layout.addWidget(resources_report_button)
        layout.addWidget(emergency_report_button)
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

    def start_monitoring(self) -> None:
        self.simulator.reset_to_normal()
        self.simulator.start()
        self.timer.start()
        self.last_status = "норма"
        self.add_log("INFO", "Мониторинг технологического процесса запущен")

    def stop_monitoring(self) -> None:
        self.simulator.stop()
        self.timer.stop()
        self.update_process_values()
        self.add_log("INFO", "Мониторинг технологического процесса остановлен")

    def simulate_emergency(self) -> None:
        self.simulator.start()
        self.timer.start()

        scenario_name = self.simulator.simulate_emergency()
        self.add_log("WARNING", f"Запущен сценарий отклонения: {scenario_name}")

    def reset_emergency_state(self) -> None:
        self.simulator.reset_to_normal()
        self.emergency_service.reset_equipment(self.equipment_list)
        self.update_equipment_table()
        self.last_status = "норма"
        self.add_log("INFO", "Аварийное состояние сброшено. Оборудование возвращено в рабочий режим.")
        self.update_process_values()

    def reset_equipment_statuses(self) -> None:
        self.emergency_service.reset_equipment(self.equipment_list)
        self.update_equipment_table()
        self.add_log("INFO", "Статусы оборудования сброшены вручную")

    def update_process_values(self) -> None:
        state = self.simulator.generate_next_state()

        analysis_result = self.deviation_analyzer.analyze(state)
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

        self.apply_status_style(state.status)

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

    def update_equipment_table(self) -> None:
        self.equipment_table.setRowCount(len(self.equipment_list))

        for row, equipment in enumerate(self.equipment_list):
            self.equipment_table.setItem(row, 0, QTableWidgetItem(equipment.name))
            self.equipment_table.setItem(row, 1, QTableWidgetItem(equipment.equipment_type))
            self.equipment_table.setItem(row, 2, QTableWidgetItem(equipment.status))
            self.equipment_table.setItem(row, 3, QTableWidgetItem(equipment.description))

            self.apply_equipment_status_style(row, equipment.status)

        self.equipment_table.resizeColumnsToContents()

    def apply_equipment_status_style(self, row: int, status: str) -> None:
        status_item = self.equipment_table.item(row, 2)

        if status_item is None:
            return

        if status in ("Работает",):
            status_item.setBackground(Qt.GlobalColor.green)
        elif status in ("Требуется проверка", "Сниженная нагрузка", "Контроль давления"):
            status_item.setBackground(Qt.GlobalColor.yellow)
        elif status in ("Авария", "Аварийное регулирование", "Безопасный режим"):
            status_item.setBackground(Qt.GlobalColor.red)

    def add_deviation(
        self,
        parameter: str,
        value: str,
        level: str,
        message: str,
        recommendation: str,
    ) -> None:
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

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

    def add_log(self, level: str, message: str) -> None:
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.logs_text.append(f"[{current_time}] [{level}] {message}")

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