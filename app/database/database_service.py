import sqlite3
from contextlib import closing
from pathlib import Path

from app.database.records import (
    AuditRecord,
    DeviationRecord,
    EventRecord,
    SensorDataRecord,
)
from app.monitoring.parameter_snapshot import PARAMETER_DEFINITIONS
from app.models.equipment import Equipment, create_default_equipment
from app.models.process_state import ProcessState
from app.users import DEMO_USERS, UserAccount, UserSession, get_role_definitions
from app.users.security import hash_password


SENSOR_EQUIPMENT_BY_CODE = {
    "reactor_temperature": ("Реактор R-101", "Реакторный блок"),
    "reactor_pressure": ("Реактор R-101", "Реакторный блок"),
    "feed_flow": ("Насос P-201", "Линия подачи сырья"),
    "hydrogen_flow": ("Компрессор C-301", "Линия водорода"),
    "energy_consumption": ("Теплообменник H-501", "Энергоблок"),
    "cooling_water_flow": ("Теплообменник H-501", "Система охлаждения"),
    "catalyst_consumption": ("Реактор R-101", "Катализаторный узел"),
    "product_yield": ("Реактор R-101", "Выход установки"),
}


class DatabaseService:
    """
    Сервис работы с локальной базой данных SQLite.

    Схема хранит текущие MVP-данные и справочники, которые нужны для дальнейшего
    развития системы по ТЗ ЛР5: роли, оборудование, датчики, режимы, ресурсы,
    рекомендации, отчеты, сменный журнал и лабораторные результаты.
    """

    SCHEMA_VERSION = "3"

    COUNTED_TABLES = (
        "roles",
        "users",
        "units",
        "equipment_catalog",
        "sensors",
        "operating_modes",
        "operating_mode_limits",
        "process_values",
        "sensor_data",
        "deviations",
        "events",
        "audit_log",
        "equipment_statuses",
        "plans",
        "resource_usage",
        "recommendations",
        "reports",
        "shift_journal_entries",
        "lab_results",
    )

    SENSOR_DEFINITIONS = tuple(
        {
            "code": definition.code,
            "equipment_name": SENSOR_EQUIPMENT_BY_CODE[definition.code][0],
            "parameter_name": definition.title,
            "measurement_unit": definition.measurement_unit,
            "location": SENSOR_EQUIPMENT_BY_CODE[definition.code][1],
            "normal_min": definition.normal_min,
            "normal_max": definition.normal_max,
        }
        for definition in PARAMETER_DEFINITIONS
    )

    PROCESS_SENSOR_FIELDS = (
        ("reactor_temperature", "temperature"),
        ("reactor_pressure", "pressure"),
        ("feed_flow", "feed_flow"),
        ("hydrogen_flow", "hydrogen_flow"),
        ("energy_consumption", "energy"),
        ("cooling_water_flow", "water_consumption"),
        ("catalyst_consumption", "catalyst_consumption"),
        ("product_yield", "product_yield"),
    )

    RESOURCE_FIELDS = (
        ("hydrogen", "Водород", "hydrogen_flow", "нм³/ч"),
        ("energy", "Электроэнергия", "energy", "кВт⋅ч"),
        ("cooling_water", "Охлаждающая вода", "water_consumption", "м³/ч"),
        ("catalyst", "Катализатор", "catalyst_consumption", "кг/ч"),
    )

    OPERATING_MODES = (
        (
            "mild_diesel",
            "Мягкий режим",
            "дизельная фракция",
            "Стабильная переработка с повышенным ресурсом катализатора.",
        ),
        (
            "balanced",
            "Нормальный режим",
            "вакуумный газойль",
            "Баланс выхода светлых продуктов и энергопотребления.",
        ),
        (
            "deep_hydrocracking",
            "Жесткий режим",
            "тяжелое сырье",
            "Максимальная глубина превращения тяжелых фракций.",
        ),
        (
            "max_kerosene",
            "Максимум керосина",
            "средние дистилляты",
            "Смещение режима к увеличению выхода керосиновой фракции.",
        ),
        (
            "energy_saving",
            "Энергосберегающий режим",
            "стабильное сырье",
            "Снижение энергопотребления при допустимом выходе продукции.",
        ),
    )

    OPERATING_MODE_LIMITS = {
        "mild_diesel": {
            "reactor_temperature": (365.0, 395.0, "°C"),
            "reactor_pressure": (125.0, 155.0, "атм"),
            "feed_flow": (65.0, 85.0, "т/ч"),
            "hydrogen_flow": (2400.0, 3200.0, "нм³/ч"),
        },
        "balanced": {
            "reactor_temperature": (380.0, 415.0, "°C"),
            "reactor_pressure": (135.0, 170.0, "атм"),
            "feed_flow": (70.0, 95.0, "т/ч"),
            "hydrogen_flow": (2600.0, 3500.0, "нм³/ч"),
        },
        "deep_hydrocracking": {
            "reactor_temperature": (405.0, 435.0, "°C"),
            "reactor_pressure": (150.0, 185.0, "атм"),
            "feed_flow": (60.0, 85.0, "т/ч"),
            "hydrogen_flow": (3000.0, 3800.0, "нм³/ч"),
        },
        "max_kerosene": {
            "reactor_temperature": (390.0, 425.0, "°C"),
            "reactor_pressure": (140.0, 175.0, "атм"),
            "feed_flow": (75.0, 100.0, "т/ч"),
            "hydrogen_flow": (2700.0, 3600.0, "нм³/ч"),
        },
        "energy_saving": {
            "reactor_temperature": (360.0, 390.0, "°C"),
            "reactor_pressure": (120.0, 150.0, "атм"),
            "feed_flow": (65.0, 90.0, "т/ч"),
            "hydrogen_flow": (2300.0, 3100.0, "нм³/ч"),
        },
    }

    def __init__(self, database_path: str = "data/hydrocrack.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._sensor_definitions_by_code = {
            str(item["code"]): item for item in self.SENSOR_DEFINITIONS
        }

    def initialize_database(self) -> None:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            self._create_metadata_schema(cursor)
            self._create_reference_schema(cursor)
            self._create_runtime_schema(cursor)
            self._seed_reference_data(cursor)

            connection.commit()

    def save_process_state(self, timestamp: str, state: ProcessState) -> None:
        with closing(self._connect()) as connection:
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

            self._save_sensor_data_rows(cursor, timestamp, state)
            self._save_resource_usage_rows(cursor, timestamp, state)
            connection.commit()

    def get_last_process_state(self) -> ProcessState | None:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
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
                FROM process_values
                ORDER BY id DESC
                LIMIT 1
                """
            )

            row = cursor.fetchone()
            if row is None:
                return None

            return ProcessState(
                temperature=float(row[0]),
                pressure=float(row[1]),
                feed_flow=float(row[2]),
                hydrogen_flow=float(row[3]),
                energy=float(row[4]),
                water_consumption=float(row[5]),
                catalyst_consumption=float(row[6]),
                product_yield=float(row[7]),
                mode=str(row[8]),
                status=str(row[9]),
            )

    def get_equipment_catalog(self) -> list[Equipment]:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    name,
                    equipment_type,
                    status,
                    description
                FROM equipment_catalog
                ORDER BY id
                """
            )

            equipment_list = [
                Equipment(
                    name=str(row[0]),
                    equipment_type=str(row[1]),
                    status=str(row[2]),
                    description=str(row[3]),
                )
                for row in cursor.fetchall()
            ]

            return equipment_list or create_default_equipment()

    def get_recent_events(self, limit: int = 100) -> tuple[EventRecord, ...]:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    timestamp,
                    level,
                    message
                FROM (
                    SELECT
                        id,
                        timestamp,
                        level,
                        message
                    FROM events
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id
                """,
                (self._normalize_limit(limit),),
            )

            return tuple(
                EventRecord(
                    timestamp=str(row[0]),
                    level=str(row[1]),
                    message=str(row[2]),
                )
                for row in cursor.fetchall()
            )

    def get_recent_deviations(self, limit: int = 50) -> tuple[DeviationRecord, ...]:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    timestamp,
                    parameter,
                    value,
                    level,
                    message,
                    recommendation
                FROM deviations
                ORDER BY id DESC
                LIMIT ?
                """,
                (self._normalize_limit(limit),),
            )

            return tuple(
                DeviationRecord(
                    timestamp=str(row[0]),
                    parameter=str(row[1]),
                    value=str(row[2]),
                    level=str(row[3]),
                    message=str(row[4]),
                    recommendation=str(row[5]),
                )
                for row in cursor.fetchall()
            )

    def get_recent_sensor_data(
        self,
        sensor_codes: tuple[str, ...],
        limit_per_sensor: int = 60,
    ) -> tuple[SensorDataRecord, ...]:
        if not sensor_codes:
            return ()

        normalized_limit = self._normalize_limit(limit_per_sensor)
        placeholders = ", ".join("?" for _ in sensor_codes)

        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                f"""
                SELECT
                    timestamp,
                    sensor_code,
                    parameter_name,
                    value,
                    measurement_unit,
                    status,
                    mode
                FROM (
                    SELECT
                        sensor_data.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY sensor_code
                            ORDER BY id DESC
                        ) AS row_number
                    FROM sensor_data
                    WHERE sensor_code IN ({placeholders})
                )
                WHERE row_number <= ?
                ORDER BY id
                """,
                (*sensor_codes, normalized_limit),
            )

            return tuple(
                SensorDataRecord(
                    timestamp=str(row[0]),
                    sensor_code=str(row[1]),
                    parameter_name=str(row[2]),
                    value=float(row[3]),
                    measurement_unit=str(row[4]),
                    status=str(row[5]),
                    mode=str(row[6]),
                )
                for row in cursor.fetchall()
            )

    def get_user_accounts(self) -> tuple[UserAccount, ...]:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    users.username,
                    users.display_name,
                    users.role_code,
                    roles.title,
                    roles.responsibility,
                    users.is_active
                FROM users
                JOIN roles ON roles.code = users.role_code
                ORDER BY users.username
                """
            )

            return tuple(
                UserAccount(
                    username=str(row[0]),
                    display_name=str(row[1]),
                    role_code=str(row[2]),
                    role_title=str(row[3]),
                    responsibility=str(row[4]),
                    is_active=bool(row[5]),
                )
                for row in cursor.fetchall()
            )

    def get_active_user_accounts(self) -> tuple[UserAccount, ...]:
        return tuple(user for user in self.get_user_accounts() if user.is_active)

    def get_default_user_session(self) -> UserSession:
        operator_session = self.get_user_session("operator")
        if operator_session is not None:
            return operator_session

        user = self.get_active_user_accounts()[0]
        return UserSession(
            username=user.username,
            display_name=user.display_name,
            role_code=user.role_code,
            role_title=user.role_title,
        )

    def get_user_session(self, username: str) -> UserSession | None:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    users.username,
                    users.display_name,
                    users.role_code,
                    roles.title,
                    users.is_active
                FROM users
                JOIN roles ON roles.code = users.role_code
                WHERE users.username = ?
                """,
                (username,),
            )

            row = cursor.fetchone()
            if row is None or not bool(row[4]):
                return None

            return UserSession(
                username=str(row[0]),
                display_name=str(row[1]),
                role_code=str(row[2]),
                role_title=str(row[3]),
            )

    def authenticate_user(self, username: str, password: str) -> UserSession | None:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    users.username,
                    users.display_name,
                    users.role_code,
                    users.password_hash,
                    users.is_active,
                    roles.title
                FROM users
                JOIN roles ON roles.code = users.role_code
                WHERE users.username = ?
                """,
                (username,),
            )

            row = cursor.fetchone()
            if row is None or not bool(row[4]):
                return None

            expected_hash = str(row[3])
            if hash_password(username, password) != expected_hash:
                return None

            return UserSession(
                username=str(row[0]),
                display_name=str(row[1]),
                role_code=str(row[2]),
                role_title=str(row[5]),
            )

    def save_audit_event(
        self,
        timestamp: str,
        username: str,
        role_code: str,
        action: str,
        details: str,
        level: str = "INFO",
    ) -> None:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO audit_log (
                    timestamp,
                    username,
                    role_code,
                    action,
                    details,
                    level
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    username,
                    role_code,
                    action,
                    details,
                    level,
                ),
            )

            connection.commit()

    def get_recent_audit_events(self, limit: int = 50) -> tuple[AuditRecord, ...]:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    timestamp,
                    username,
                    role_code,
                    action,
                    details,
                    level
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (self._normalize_limit(limit),),
            )

            return tuple(
                AuditRecord(
                    timestamp=str(row[0]),
                    username=str(row[1]),
                    role_code=str(row[2]),
                    action=str(row[3]),
                    details=str(row[4]),
                    level=str(row[5]),
                )
                for row in cursor.fetchall()
            )

    def save_deviation(
        self,
        timestamp: str,
        parameter: str,
        value: str,
        level: str,
        message: str,
        recommendation: str,
    ) -> None:
        with closing(self._connect()) as connection:
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

            if recommendation:
                cursor.execute(
                    """
                    INSERT INTO recommendations (
                        timestamp,
                        recommendation_type,
                        priority,
                        message,
                        status,
                        source_parameter
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        "deviation_response",
                        level,
                        recommendation,
                        "new",
                        parameter,
                    ),
                )

            connection.commit()

    def save_event(self, timestamp: str, level: str, message: str) -> None:
        with closing(self._connect()) as connection:
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
        with closing(self._connect()) as connection:
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

                cursor.execute(
                    """
                    INSERT INTO equipment_catalog (
                        unit_code,
                        name,
                        equipment_type,
                        status,
                        description
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        equipment_type = excluded.equipment_type,
                        status = excluded.status,
                        description = excluded.description
                    """,
                    (
                        "hc_unit_1",
                        equipment.name,
                        equipment.equipment_type,
                        equipment.status,
                        equipment.description,
                    ),
                )

            connection.commit()

    def get_counts(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()
            result: dict[str, int] = {}

            for table in self.COUNTED_TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                result[table] = int(cursor.fetchone()[0])

            return result

    def get_table_names(self) -> set[str]:
        with closing(self._connect()) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            return {str(row[0]) for row in cursor.fetchall()}

    def _create_metadata_schema(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS database_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            INSERT INTO database_meta (key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (self.SCHEMA_VERSION,),
        )

    def _create_reference_schema(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                responsibility TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                role_code TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(role_code) REFERENCES roles(code)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS units (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                design_capacity REAL NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_code TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                equipment_type TEXT NOT NULL,
                status TEXT NOT NULL,
                description TEXT NOT NULL,
                FOREIGN KEY(unit_code) REFERENCES units(code)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sensors (
                code TEXT PRIMARY KEY,
                unit_code TEXT NOT NULL,
                equipment_name TEXT NOT NULL,
                parameter_name TEXT NOT NULL,
                measurement_unit TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                normal_min REAL NOT NULL,
                normal_max REAL NOT NULL,
                FOREIGN KEY(unit_code) REFERENCES units(code),
                FOREIGN KEY(equipment_name) REFERENCES equipment_catalog(name)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS operating_modes (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                feedstock_type TEXT NOT NULL,
                goal TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS operating_mode_limits (
                mode_code TEXT NOT NULL,
                parameter_code TEXT NOT NULL,
                min_value REAL NOT NULL,
                max_value REAL NOT NULL,
                measurement_unit TEXT NOT NULL,
                PRIMARY KEY(mode_code, parameter_code),
                FOREIGN KEY(mode_code) REFERENCES operating_modes(code),
                FOREIGN KEY(parameter_code) REFERENCES sensors(code)
            )
            """
        )

    def _create_runtime_schema(self, cursor: sqlite3.Cursor) -> None:
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
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sensor_code TEXT NOT NULL,
                parameter_name TEXT NOT NULL,
                value REAL NOT NULL,
                measurement_unit TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                FOREIGN KEY(sensor_code) REFERENCES sensors(code)
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
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                role_code TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                level TEXT NOT NULL,
                FOREIGN KEY(username) REFERENCES users(username),
                FOREIGN KEY(role_code) REFERENCES roles(code)
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

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                mode_code TEXT NOT NULL,
                planned_feed_flow REAL NOT NULL,
                planned_product_yield REAL NOT NULL,
                planned_resource_limit REAL NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT,
                FOREIGN KEY(mode_code) REFERENCES operating_modes(code),
                FOREIGN KEY(created_by) REFERENCES users(username)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS resource_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                resource_code TEXT NOT NULL,
                resource_name TEXT NOT NULL,
                value REAL NOT NULL,
                measurement_unit TEXT NOT NULL,
                mode TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                recommendation_type TEXT NOT NULL,
                priority TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                source_parameter TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                title TEXT NOT NULL,
                file_path TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT,
                status TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(username)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shift_journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                shift_code TEXT NOT NULL,
                author_username TEXT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                equipment_name TEXT,
                action_required INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(author_username) REFERENCES users(username),
                FOREIGN KEY(equipment_name) REFERENCES equipment_catalog(name)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sample_code TEXT NOT NULL,
                product_type TEXT NOT NULL,
                density REAL,
                sulfur_content REAL,
                viscosity REAL,
                product_yield REAL,
                comment TEXT
            )
            """
        )

    def _seed_reference_data(self, cursor: sqlite3.Cursor) -> None:
        for role in get_role_definitions():
            cursor.execute(
                """
                INSERT OR IGNORE INTO roles (
                    code,
                    title,
                    responsibility
                )
                VALUES (?, ?, ?)
                """,
                (role.code, role.title, role.responsibility),
            )

        for user in DEMO_USERS:
            password_hash = hash_password(user.username, user.password)

            cursor.execute(
                """
                INSERT OR IGNORE INTO users (
                    username,
                    display_name,
                    role_code,
                    password_hash,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user.username,
                    user.display_name,
                    user.role_code,
                    password_hash,
                    1,
                ),
            )

            cursor.execute(
                """
                UPDATE users
                SET
                    display_name = ?,
                    role_code = ?,
                    password_hash = ?,
                    is_active = 1
                WHERE username = ?
                    AND password_hash = 'demo-password-placeholder'
                """,
                (
                    user.display_name,
                    user.role_code,
                    password_hash,
                    user.username,
                ),
            )

        cursor.execute(
            """
            INSERT OR IGNORE INTO units (
                code,
                name,
                location,
                status,
                design_capacity
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "hc_unit_1",
                "Установка гидрокрекинга",
                "Нефтехимическое производство",
                "работает",
                250.0,
            ),
        )

        for equipment in create_default_equipment():
            cursor.execute(
                """
                INSERT OR IGNORE INTO equipment_catalog (
                    unit_code,
                    name,
                    equipment_type,
                    status,
                    description
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "hc_unit_1",
                    equipment.name,
                    equipment.equipment_type,
                    equipment.status,
                    equipment.description,
                ),
            )

        for sensor in self.SENSOR_DEFINITIONS:
            cursor.execute(
                """
                INSERT OR IGNORE INTO sensors (
                    code,
                    unit_code,
                    equipment_name,
                    parameter_name,
                    measurement_unit,
                    location,
                    status,
                    normal_min,
                    normal_max
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sensor["code"],
                    "hc_unit_1",
                    sensor["equipment_name"],
                    sensor["parameter_name"],
                    sensor["measurement_unit"],
                    sensor["location"],
                    "active",
                    sensor["normal_min"],
                    sensor["normal_max"],
                ),
            )

        for mode_code, title, feedstock_type, goal in self.OPERATING_MODES:
            cursor.execute(
                """
                INSERT OR IGNORE INTO operating_modes (
                    code,
                    title,
                    feedstock_type,
                    goal,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (mode_code, title, feedstock_type, goal, 1),
            )

        for mode_code, mode_limits in self.OPERATING_MODE_LIMITS.items():
            for parameter_code, limit in mode_limits.items():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO operating_mode_limits (
                        mode_code,
                        parameter_code,
                        min_value,
                        max_value,
                        measurement_unit
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        mode_code,
                        parameter_code,
                        limit[0],
                        limit[1],
                        limit[2],
                    ),
                )

    def _save_sensor_data_rows(
        self,
        cursor: sqlite3.Cursor,
        timestamp: str,
        state: ProcessState,
    ) -> None:
        for sensor_code, state_attribute in self.PROCESS_SENSOR_FIELDS:
            sensor = self._sensor_definitions_by_code[sensor_code]
            value = float(getattr(state, state_attribute))

            cursor.execute(
                """
                INSERT INTO sensor_data (
                    timestamp,
                    sensor_code,
                    parameter_name,
                    value,
                    measurement_unit,
                    status,
                    mode
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    sensor_code,
                    sensor["parameter_name"],
                    value,
                    sensor["measurement_unit"],
                    self._classify_sensor_status(sensor_code, value),
                    state.mode,
                ),
            )

    def _save_resource_usage_rows(
        self,
        cursor: sqlite3.Cursor,
        timestamp: str,
        state: ProcessState,
    ) -> None:
        for code, name, state_attribute, measurement_unit in self.RESOURCE_FIELDS:
            cursor.execute(
                """
                INSERT INTO resource_usage (
                    timestamp,
                    resource_code,
                    resource_name,
                    value,
                    measurement_unit,
                    mode
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    code,
                    name,
                    float(getattr(state, state_attribute)),
                    measurement_unit,
                    state.mode,
                ),
            )

    def _classify_sensor_status(self, sensor_code: str, value: float) -> str:
        sensor = self._sensor_definitions_by_code[sensor_code]
        minimum = float(sensor["normal_min"])
        maximum = float(sensor["normal_max"])

        if minimum <= value <= maximum:
            return "норма"

        return "отклонение"

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(limit, 500))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
