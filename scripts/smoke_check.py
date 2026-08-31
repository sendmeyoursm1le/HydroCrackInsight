import tempfile
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtWidgets import QApplication

from app.database.database_service import DatabaseService
from app.demo import seed_demo_database
from app.ui.main_window import MainWindow


EXPECTED_TABS = {
    "operator": {"Мониторинг", "Оборудование", "Отклонения", "Ресурсы", "Сменный журнал", "Журнал"},
    "technologist": {
        "Мониторинг",
        "Оборудование",
        "Отклонения",
        "Ресурсы",
        "Прогноз",
        "Отчеты",
        "Диагностика",
        "Сменный журнал",
        "Журнал",
    },
    "instrumentation": {"Мониторинг", "Оборудование", "Диагностика", "Сменный журнал", "Журнал"},
    "manager": {
        "Мониторинг",
        "Отклонения",
        "Ресурсы",
        "Прогноз",
        "Отчеты",
        "Диагностика",
        "Сменный журнал",
        "Журнал",
    },
    "admin": {
        "Мониторинг",
        "Оборудование",
        "Отклонения",
        "Ресурсы",
        "Прогноз",
        "Отчеты",
        "Диагностика",
        "Сменный журнал",
        "Журнал",
        "Пользователи",
    },
}


def main() -> None:
    app = QApplication([])

    with tempfile.TemporaryDirectory() as temp_dir:
        database = DatabaseService(str(Path(temp_dir) / "hydrocrack.db"))
        seed_demo_database(database)

        for username, expected_tabs in EXPECTED_TABS.items():
            session = database.get_user_session(username)
            if session is None:
                raise AssertionError(f"Пользователь не найден: {username}")

            window = MainWindow(database_service=database, current_user=session)
            actual_tabs = {window.tabs.tabText(index) for index in range(window.tabs.count())}
            missing_tabs = expected_tabs - actual_tabs
            if missing_tabs:
                raise AssertionError(f"{username}: нет вкладок {sorted(missing_tabs)}")

            window.prepare_for_session_switch()
            window.close()

    print("Smoke-check пройден: роли, вкладки, БД и главное окно работают.")


if __name__ == "__main__":
    main()
