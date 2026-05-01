import sqlite3
from pathlib import Path

from app.models.equipment import Equipment
from app.models.process_state import ProcessState


class DatabaseService:
    """
    Сервис работы с локальной базой данных SQLite.

    Отвечает за:
    - создание таблиц;
    - сохранение параметров процесса;
    - сохранение отклонений;
    - сохранение журнала событий;
    - сохранение статусов оборудования.
    """

    def __init__(self, database_path: str = "data/hydrocrack.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize_database(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS process_values (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    temperature REAL NOT NULL,
                    pressure REAL NOT NULL,
                    feed_flow REAL NOT NULL,
                    hydrogen_flow REAL NOT NULL,
                    energy REAL NOT NULL,
                    water_consumption REAL NOT NULL,
                    catalyst_consumption REAL NOT NULL,
                    product_yield REAL NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS deviations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    parameter TEXT NOT NULL,
                    value TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    recommendation TEXT NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS equipment_statuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equipment_name TEXT NOT NULL,
                    equipment_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )

            connection.commit()

    def save_process_state(self, timestamp: str, state: ProcessState) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO process_values (
                    timestamp,
                    temperature,
                    pressure,
                    feed_flow,
                    hydrogen_flow,
                    energy,
                    water_consumption,
                    catalyst_consumption,
                    product_yield,
                    mode,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    state.temperature,
                    state.pressure,
                    state.feed_flow,
                    state.hydrogen_flow,
                    state.energy,
                    state.water_consumption,
                    state.catalyst_consumption,
                    state.product_yield,
                    state.mode,
                    state.status,
                ),
            )

            connection.commit()

    def save_deviation(
        self,
        timestamp: str,
        parameter: str,
        value: str,
        level: str,
        message: str,
        recommendation: str,
    ) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO deviations (
                    timestamp,
                    parameter,
                    value,
                    level,
                    message,
                    recommendation
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    parameter,
                    value,
                    level,
                    message,
                    recommendation,
                ),
            )

            connection.commit()

    def save_event(self, timestamp: str, level: str, message: str) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO events (
                    timestamp,
                    level,
                    message
                )
                VALUES (?, ?, ?)
                """,
                (
                    timestamp,
                    level,
                    message,
                ),
            )

            connection.commit()

    def save_equipment_statuses(
        self,
        timestamp: str,
        equipment_list: list[Equipment],
    ) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()

            for equipment in equipment_list:
                cursor.execute(
                    """
                    INSERT INTO equipment_statuses (
                        timestamp,
                        equipment_name,
                        equipment_type,
                        status,
                        description
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        equipment.name,
                        equipment.equipment_type,
                        equipment.status,
                        equipment.description,
                    ),
                )

            connection.commit()

    def get_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            cursor = connection.cursor()

            tables = [
                "process_values",
                "deviations",
                "events",
                "equipment_statuses",
            ]

            result: dict[str, int] = {}

            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                result[table] = int(cursor.fetchone()[0])

            return result

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)