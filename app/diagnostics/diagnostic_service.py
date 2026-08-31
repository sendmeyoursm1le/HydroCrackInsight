from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DiagnosticItem:
    name: str
    value: str
    status: str


@dataclass(frozen=True)
class DiagnosticSnapshot:
    overall_status: str
    generated_at: str
    items: tuple[DiagnosticItem, ...]


@dataclass(frozen=True)
class BackupResult:
    path: Path
    size_bytes: int
    created_at: str


class DiagnosticService:
    def __init__(self, database_service: Any) -> None:
        self.database_service = database_service

    def build_snapshot(
        self,
        simulator_is_running: bool,
        simulator_mode: str,
        simulator_status: str,
    ) -> DiagnosticSnapshot:
        generated_at = self._now()
        database_path = self.database_service.database_path
        database_exists = database_path.exists()
        table_names = self.database_service.get_table_names() if database_exists else set()
        missing_tables = sorted(set(self.database_service.COUNTED_TABLES) - table_names)
        counts = self.database_service.get_counts() if database_exists and not missing_tables else {}
        process_values = (
            self.database_service.get_recent_process_values(limit=1)
            if database_exists and not missing_tables
            else ()
        )
        events = (
            self.database_service.get_recent_events(limit=1)
            if database_exists and not missing_tables
            else ()
        )

        database_status = "ok" if database_exists and not missing_tables else "warning"
        items = [
            DiagnosticItem(
                name="База данных",
                value=str(database_path.resolve()) if database_exists else str(database_path),
                status=database_status,
            ),
            DiagnosticItem(
                name="Размер БД",
                value=self._format_size(database_path.stat().st_size) if database_exists else "файл не найден",
                status=database_status,
            ),
            DiagnosticItem(
                name="Схема БД",
                value=(
                    f"таблиц: {len(table_names)}, отсутствуют: {', '.join(missing_tables)}"
                    if missing_tables
                    else f"таблиц: {len(table_names)}, обязательные таблицы на месте"
                ),
                status=database_status,
            ),
            DiagnosticItem(
                name="Версия схемы",
                value=self.database_service.get_meta_value("schema_version") or "не задана",
                status=database_status,
            ),
            DiagnosticItem(
                name="Записей процесса",
                value=str(counts.get("process_values", 0)),
                status="ok",
            ),
            DiagnosticItem(
                name="Последнее измерение",
                value=process_values[-1].timestamp if process_values else "нет данных",
                status="ok" if process_values else "warning",
            ),
            DiagnosticItem(
                name="Последнее событие",
                value=events[-1].timestamp if events else "нет событий",
                status="ok" if events else "warning",
            ),
            DiagnosticItem(
                name="Симулятор",
                value="запущен" if simulator_is_running else "остановлен",
                status="ok" if simulator_is_running else "warning",
            ),
            DiagnosticItem(
                name="Режим симулятора",
                value=simulator_mode,
                status="ok",
            ),
            DiagnosticItem(
                name="Статус процесса",
                value=simulator_status,
                status="critical" if simulator_status == "авария" else "ok",
            ),
        ]
        overall_status = self._calculate_overall_status(tuple(items))

        return DiagnosticSnapshot(
            overall_status=overall_status,
            generated_at=generated_at,
            items=tuple(items),
        )

    def backup_database(self, backup_dir: str | Path = "backups") -> BackupResult:
        backup_root = Path(backup_dir)
        backup_root.mkdir(parents=True, exist_ok=True)
        created_at = self._now()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = (backup_root / f"hydrocrack_{timestamp}.db").resolve()

        self.database_service.backup_database(destination)

        return BackupResult(
            path=destination,
            size_bytes=destination.stat().st_size,
            created_at=created_at,
        )

    def _calculate_overall_status(self, items: tuple[DiagnosticItem, ...]) -> str:
        if any(item.status == "critical" for item in items):
            return "critical"
        if any(item.status == "warning" for item in items):
            return "warning"
        return "ok"

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} Б"

        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} КБ"

        return f"{size_bytes / (1024 * 1024):.1f} МБ"

    def _now(self) -> str:
        return datetime.now().strftime("%d.%m.%Y %H:%M:%S")
