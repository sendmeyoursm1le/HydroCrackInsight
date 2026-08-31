from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.database_service import DatabaseService
from app.demo import seed_demo_database
from app.reports import ReportService


def main() -> None:
    database = DatabaseService()
    seed_demo_database(database)

    report_service = ReportService(database)
    report_service.generate_daily_report("admin")
    report_service.generate_resources_report("admin")
    report_service.generate_emergency_report("admin")
    report_service.generate_shift_report("admin")

    print(f"Демо-данные записаны в {Path(database.database_path).resolve()}")
    print("Демо-отчеты PDF созданы в reports/generated")


if __name__ == "__main__":
    main()
