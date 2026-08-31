from datetime import datetime, timedelta

from app.database.database_service import DatabaseService
from app.models.process_state import ProcessState


def seed_demo_database(database_service: DatabaseService) -> None:
    database_service.initialize_database()
    profile = database_service.get_active_operating_mode_profile()
    start_time = datetime(2026, 1, 12, 8, 0, 0)

    states = (
        ProcessState(
            temperature=389.5,
            pressure=149.0,
            feed_flow=80.0,
            hydrogen_flow=3000.0,
            energy=895.0,
            water_consumption=35.0,
            catalyst_consumption=1.5,
            product_yield=83.8,
            mode="демо: стабильная работа",
            status="норма",
        ),
        ProcessState(
            temperature=414.0,
            pressure=164.0,
            feed_flow=88.0,
            hydrogen_flow=3050.0,
            energy=980.0,
            water_consumption=38.0,
            catalyst_consumption=1.6,
            product_yield=81.2,
            mode="демо: рост нагрузки",
            status="предупреждение",
        ),
        ProcessState(
            temperature=452.0,
            pressure=168.0,
            feed_flow=22.0,
            hydrogen_flow=3000.0,
            energy=620.0,
            water_consumption=52.0,
            catalyst_consumption=0.3,
            product_yield=0.0,
            mode="аварийная остановка",
            status="авария",
        ),
        ProcessState(
            temperature=397.0,
            pressure=151.0,
            feed_flow=74.0,
            hydrogen_flow=2860.0,
            energy=870.0,
            water_consumption=36.0,
            catalyst_consumption=1.35,
            product_yield=82.4,
            mode="демо: восстановление",
            status="норма",
        ),
    )

    for index, state in enumerate(states):
        timestamp = (start_time + timedelta(minutes=index * 30)).strftime(
            "%d.%m.%Y %H:%M:%S"
        )
        database_service.save_process_state(
            timestamp,
            state,
            operating_mode_profile=profile,
        )

    database_service.save_event(
        "12.01.2026 08:30:30",
        "WARNING",
        "Демо: рост температуры реактора",
    )
    database_service.save_event(
        "12.01.2026 09:00:30",
        "CRITICAL",
        "Демо: аварийная остановка выпуска продукции",
    )
    database_service.save_deviation(
        timestamp="12.01.2026 09:00:30",
        parameter="Температура",
        value="452.0 °C",
        level="Авария",
        message="Демо: критическое превышение температуры реактора",
        recommendation="Снизить подачу сырья и проверить теплообменник",
    )
    database_service.save_shift_journal_entry(
        timestamp="12.01.2026 09:05:00",
        shift_code="Смена A",
        author_username="operator",
        level="ACTION",
        message="После аварийной остановки проконтролировать реактор R-101",
        equipment_name="Реактор R-101",
        action_required=True,
    )
    database_service.create_shift_handover(
        timestamp="12.01.2026 20:00:00",
        from_user="operator",
        to_user="technologist",
        shift_code="Смена A",
        summary="Демо-смена: авария зафиксирована, установка восстановлена",
        open_actions="Проверить журнал отклонений и ресурсный отчет",
        checklist_items=(
            ("parameters_checked", "Параметры процесса проверены", True, ""),
            ("deviations_reviewed", "Отклонения и рекомендации просмотрены", True, ""),
            ("equipment_checked", "Статусы оборудования актуальны", True, ""),
            ("resources_checked", "Расход ресурсов проверен", False, ""),
        ),
    )
