from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.models.process_state import ProcessState


@dataclass(frozen=True)
class ProcessDataImportResult:
    imported_count: int
    states: tuple[ProcessState, ...]
    timestamps: tuple[str | None, ...]

    @property
    def last_state(self) -> ProcessState | None:
        if not self.states:
            return None

        return self.states[-1]


class ProcessDataImporter:
    COLUMN_ALIASES = {
        "timestamp": ("timestamp", "time", "datetime", "Дата", "Время"),
        "temperature": ("temperature", "temperature_c", "Температура"),
        "pressure": ("pressure", "pressure_atm", "Давление"),
        "feed_flow": ("feed_flow", "feed", "Расход сырья"),
        "hydrogen_flow": ("hydrogen_flow", "hydrogen", "Расход водорода"),
        "energy": ("energy", "energy_consumption", "Энергия"),
        "water_consumption": (
            "water_consumption",
            "cooling_water_flow",
            "Вода",
            "Расход воды",
        ),
        "catalyst_consumption": (
            "catalyst_consumption",
            "catalyst",
            "Катализатор",
        ),
        "product_yield": ("product_yield", "yield", "Выход продукции"),
        "mode": ("mode", "Режим"),
        "status": ("status", "Статус"),
    }

    REQUIRED_FIELDS = (
        "temperature",
        "pressure",
        "feed_flow",
        "hydrogen_flow",
    )

    OPTIONAL_NUMERIC_FIELDS = (
        "energy",
        "water_consumption",
        "catalyst_consumption",
        "product_yield",
    )

    def import_file(self, file_path: str) -> ProcessDataImportResult:
        path = Path(file_path)
        dataframe = self._read_dataframe(path)
        if dataframe.empty:
            raise ValueError("Файл не содержит строк с данными.")

        column_map = self._build_column_map(dataframe)
        missing_fields = [
            field for field in self.REQUIRED_FIELDS if field not in column_map
        ]
        if missing_fields:
            raise ValueError(
                "Не найдены обязательные колонки: " + ", ".join(missing_fields)
            )

        states: list[ProcessState] = []
        timestamps: list[str | None] = []

        for _, row in dataframe.iterrows():
            default_state = ProcessState()
            state = ProcessState(
                temperature=self._get_float(row, column_map, "temperature"),
                pressure=self._get_float(row, column_map, "pressure"),
                feed_flow=self._get_float(row, column_map, "feed_flow"),
                hydrogen_flow=self._get_float(row, column_map, "hydrogen_flow"),
                energy=self._get_float(
                    row,
                    column_map,
                    "energy",
                    default_state.energy,
                ),
                water_consumption=self._get_float(
                    row,
                    column_map,
                    "water_consumption",
                    default_state.water_consumption,
                ),
                catalyst_consumption=self._get_float(
                    row,
                    column_map,
                    "catalyst_consumption",
                    default_state.catalyst_consumption,
                ),
                product_yield=self._get_float(
                    row,
                    column_map,
                    "product_yield",
                    default_state.product_yield,
                ),
                mode=self._get_text(row, column_map, "mode", "импорт данных"),
                status=self._get_text(row, column_map, "status", default_state.status),
            )
            states.append(state)
            timestamps.append(self._get_optional_text(row, column_map, "timestamp"))

        return ProcessDataImportResult(
            imported_count=len(states),
            states=tuple(states),
            timestamps=tuple(timestamps),
        )

    def _read_dataframe(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()

        if suffix == ".csv":
            return pd.read_csv(path)

        if suffix in (".xlsx", ".xls"):
            try:
                return pd.read_excel(path)
            except ImportError as exc:
                raise RuntimeError(
                    "Для импорта Excel нужен пакет openpyxl. "
                    "Установите его командой: python -m pip install openpyxl."
                ) from exc

        raise ValueError("Поддерживаются только файлы CSV, XLSX и XLS.")

    def _build_column_map(self, dataframe: pd.DataFrame) -> dict[str, str]:
        column_map: dict[str, str] = {}
        available_columns = {str(column).strip(): str(column) for column in dataframe.columns}

        for field, aliases in self.COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in available_columns:
                    column_map[field] = available_columns[alias]
                    break

        return column_map

    def _get_float(
        self,
        row,
        column_map: dict[str, str],
        field: str,
        default_value: float | None = None,
    ) -> float:
        column = column_map.get(field)
        if column is None:
            if default_value is None:
                raise ValueError(f"Не найдена колонка {field}.")
            return default_value

        value = row[column]
        if pd.isna(value):
            if default_value is None:
                raise ValueError(f"Пустое значение в колонке {column}.")
            return default_value

        return float(value)

    def _get_text(
        self,
        row,
        column_map: dict[str, str],
        field: str,
        default_value: str,
    ) -> str:
        value = self._get_optional_text(row, column_map, field)
        if value is None:
            return default_value

        return value

    @staticmethod
    def _get_optional_text(
        row,
        column_map: dict[str, str],
        field: str,
    ) -> str | None:
        column = column_map.get(field)
        if column is None:
            return None

        value = row[column]
        if pd.isna(value):
            return None

        return str(value)
