from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.database.records import ProcessValueRecord


@dataclass(frozen=True)
class ReportGenerationResult:
    report_type: str
    title: str
    pdf_path: Path
    created_at: str


class ReportService:
    REPORT_TITLES = {
        "daily": "Суточный отчет по работе установки",
        "resources": "Отчет по расходу ресурсов",
        "emergency": "Отчет по отклонениям и авариям",
        "shift": "Сменный отчет",
    }

    def __init__(
        self,
        database_service: Any,
        output_dir: str | Path = "reports/generated",
    ) -> None:
        self.database_service = database_service
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.font_name = self._register_font()

    def generate_daily_report(self, created_by: str) -> ReportGenerationResult:
        process_values = self.database_service.get_recent_process_values()
        deviations = self.database_service.get_recent_deviations()
        events = self.database_service.get_recent_events()

        rows = [
            ("Показатель", "Значение"),
            ("Количество сохраненных состояний", str(len(process_values))),
            ("Средняя температура, °C", self._format_average(process_values, "temperature")),
            ("Среднее давление, атм", self._format_average(process_values, "pressure")),
            ("Средняя подача сырья, т/ч", self._format_average(process_values, "feed_flow")),
            ("Средний выход продукции, %", self._format_average(process_values, "product_yield")),
            ("Количество отклонений", str(len(deviations))),
            ("Количество событий", str(len(events))),
        ]

        if process_values:
            latest = process_values[-1]
            rows.extend(
                [
                    ("Последний статус", latest.status),
                    ("Последний режим", latest.mode),
                    ("Последнее измерение", latest.timestamp),
                ]
            )

        return self._write_report(
            report_type="daily",
            created_by=created_by,
            sections=(("Сводка", rows),),
            period_start=process_values[0].timestamp if process_values else "-",
            period_end=process_values[-1].timestamp if process_values else "-",
        )

    def generate_resources_report(self, created_by: str) -> ReportGenerationResult:
        resources = self.database_service.get_resource_usage_summary()
        rows = [
            (
                "Ресурс",
                "За смену",
                "Лимит смены",
                "Статус смены",
                "За сутки",
                "Лимит суток",
                "Статус суток",
                "Ед.",
            )
        ]
        rows.extend(
            (
                item.resource_name,
                f"{item.shift_total:.2f}",
                f"{item.shift_limit:.2f}",
                item.shift_status,
                f"{item.daily_total:.2f}",
                f"{item.daily_limit:.2f}",
                item.daily_status,
                item.measurement_unit,
            )
            for item in resources
        )

        created_at = self._now()
        return self._write_report(
            report_type="resources",
            created_by=created_by,
            sections=(("Расход ресурсов", rows),),
            period_start="текущая смена",
            period_end=created_at,
        )

    def generate_emergency_report(self, created_by: str) -> ReportGenerationResult:
        deviations = tuple(
            item
            for item in self.database_service.get_recent_deviations()
            if item.level in ("Авария", "critical") or item.message.lower().find("авар") >= 0
        )
        events = tuple(
            item
            for item in self.database_service.get_recent_events()
            if item.level in ("CRITICAL", "ACTION", "WARNING")
        )

        deviation_rows = [("Время", "Параметр", "Значение", "Уровень", "Сообщение")]
        deviation_rows.extend(
            (
                item.timestamp,
                item.parameter,
                item.value,
                item.level,
                item.message,
            )
            for item in deviations
        )
        if len(deviation_rows) == 1:
            deviation_rows.append(("-", "-", "-", "-", "Аварийных отклонений нет"))

        event_rows = [("Время", "Уровень", "Сообщение")]
        event_rows.extend((item.timestamp, item.level, item.message) for item in events)
        if len(event_rows) == 1:
            event_rows.append(("-", "-", "Критичных событий нет"))

        return self._write_report(
            report_type="emergency",
            created_by=created_by,
            sections=(
                ("Аварийные отклонения", deviation_rows),
                ("События и действия", event_rows),
            ),
            period_start=deviations[-1].timestamp if deviations else "-",
            period_end=deviations[0].timestamp if deviations else self._now(),
        )

    def generate_shift_report(self, created_by: str) -> ReportGenerationResult:
        journal_entries = self.database_service.get_recent_shift_journal_entries()
        handovers = self.database_service.get_recent_shift_handovers()

        journal_rows = [
            ("Время", "Смена", "Автор", "Уровень", "Оборудование", "Действие", "Сообщение")
        ]
        journal_rows.extend(
            (
                item.timestamp,
                item.shift_code,
                item.author_username,
                item.level,
                item.equipment_name or "-",
                "да" if item.action_required else "нет",
                item.message,
            )
            for item in journal_entries
        )
        if len(journal_rows) == 1:
            journal_rows.append(("-", "-", "-", "-", "-", "-", "Записей сменного журнала нет"))

        handover_rows = [
            (
                "Время",
                "Смена",
                "Ответственный",
                "Ознакомлен",
                "Чек-лист",
                "Итог",
                "Открытые действия",
            )
        ]
        handover_rows.extend(
            (
                item.timestamp,
                item.shift_code,
                item.from_user,
                item.to_user,
                f"{item.checked_items}/{item.total_items}",
                item.summary,
                item.open_actions,
            )
            for item in handovers
        )
        if len(handover_rows) == 1:
            handover_rows.append(("-", "-", "-", "-", "-", "Итогов смены нет", "-"))

        return self._write_report(
            report_type="shift",
            created_by=created_by,
            sections=(
                ("Сменный журнал", journal_rows),
                ("Итоги смен", handover_rows),
            ),
            period_start=journal_entries[-1].timestamp if journal_entries else "-",
            period_end=journal_entries[0].timestamp if journal_entries else self._now(),
        )

    def _write_report(
        self,
        report_type: str,
        created_by: str,
        sections: tuple[tuple[str, list[tuple[str, ...]]], ...],
        period_start: str,
        period_end: str,
    ) -> ReportGenerationResult:
        created_at = self._now()
        title = self.REPORT_TITLES[report_type]
        stem = f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        pdf_path = (self.output_dir / f"{stem}.pdf").resolve()

        self._write_pdf(pdf_path, title, created_at, created_by, sections)

        self.database_service.save_report(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            title=title,
            file_path=str(pdf_path),
            created_at=created_at,
            created_by=created_by,
        )

        return ReportGenerationResult(
            report_type=report_type,
            title=title,
            pdf_path=pdf_path,
            created_at=created_at,
        )

    def _write_pdf(
        self,
        pdf_path: Path,
        title: str,
        created_at: str,
        created_by: str,
        sections: tuple[tuple[str, list[tuple[str, ...]]], ...],
    ) -> None:
        styles = getSampleStyleSheet()
        for style_name in ("Title", "Heading2", "Normal"):
            styles[style_name].fontName = self.font_name

        document = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            rightMargin=28,
            leftMargin=28,
            topMargin=28,
            bottomMargin=28,
        )

        elements = [
            Paragraph(title, styles["Title"]),
            Paragraph(f"Создан: {created_at}", styles["Normal"]),
            Paragraph(f"Пользователь: {created_by}", styles["Normal"]),
            Spacer(1, 12),
        ]

        for section_title, rows in sections:
            elements.append(Paragraph(section_title, styles["Heading2"]))
            elements.append(self._build_table(rows))
            elements.append(Spacer(1, 12))

        document.build(elements)

    def _build_table(self, rows: list[tuple[str, ...]]) -> Table:
        wrapped_rows = [
            [Paragraph(str(cell), self._table_cell_style()) for cell in row]
            for row in rows
        ]
        table = Table(wrapped_rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), self.font_name),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa7b2")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
                ]
            )
        )
        return table

    def _table_cell_style(self) -> Any:
        style = getSampleStyleSheet()["Normal"]
        style.fontName = self.font_name
        style.fontSize = 8
        style.leading = 10
        return style

    def _format_average(
        self,
        records: tuple[ProcessValueRecord, ...],
        attribute_name: str,
    ) -> str:
        if not records:
            return "-"

        average = sum(float(getattr(item, attribute_name)) for item in records) / len(records)
        return f"{average:.2f}"

    def _now(self) -> str:
        return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    def _register_font(self) -> str:
        font_path = Path("C:/Windows/Fonts/arial.ttf")
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("HydroCrackArial", str(font_path)))
            return "HydroCrackArial"

        return "Helvetica"
