from dataclasses import dataclass


@dataclass(frozen=True)
class SubsystemDefinition:
    code: str
    title: str
    package: str
    responsibility: str
    status: str


def get_subsystems() -> tuple[SubsystemDefinition, ...]:
    return (
        SubsystemDefinition(
            code="monitoring",
            title="Мониторинг и анализ данных",
            package="app.monitoring",
            responsibility=(
                "Получение параметров процесса, проверка технологических "
                "ограничений и выявление отклонений."
            ),
            status="частично реализовано",
        ),
        SubsystemDefinition(
            code="equipment",
            title="Оборудование и аварийное реагирование",
            package="app.equipment",
            responsibility=(
                "Отображение состояния оборудования и демонстрационная обработка "
                "аварийных ситуаций."
            ),
            status="частично реализовано",
        ),
        SubsystemDefinition(
            code="resources",
            title="Учет расхода ресурсов",
            package="app.resources",
            responsibility=(
                "Расчет и анализ расхода водорода, энергии, воды, катализатора "
                "и реагентов."
            ),
            status="каркас",
        ),
        SubsystemDefinition(
            code="forecasting",
            title="Прогнозирование и оптимизация",
            package="app.forecasting",
            responsibility=(
                "Расчет прогнозных показателей и сравнение сценариев изменения "
                "технологического режима."
            ),
            status="каркас",
        ),
        SubsystemDefinition(
            code="reports",
            title="Отчетность и аналитика",
            package="app.reports",
            responsibility=(
                "Формирование сменных, суточных, аварийных и ресурсных отчетов."
            ),
            status="каркас",
        ),
        SubsystemDefinition(
            code="users",
            title="Пользователи и права доступа",
            package="app.users",
            responsibility=(
                "Аутентификация пользователей и разграничение функций по ролям."
            ),
            status="каркас",
        ),
        SubsystemDefinition(
            code="journals",
            title="Журналы и аудит",
            package="app.journals",
            responsibility=(
                "Журналирование событий, действий пользователей, отклонений и "
                "передачи смены."
            ),
            status="каркас",
        ),
        SubsystemDefinition(
            code="simulation",
            title="Имитация источника данных",
            package="app.simulation",
            responsibility=(
                "Учебная генерация параметров вместо промышленной интеграции "
                "со SCADA/DCS."
            ),
            status="частично реализовано",
        ),
        SubsystemDefinition(
            code="persistence",
            title="Хранение данных",
            package="app.database",
            responsibility="Создание локальной БД и сохранение данных приложения.",
            status="частично реализовано",
        ),
        SubsystemDefinition(
            code="ui",
            title="Пользовательский интерфейс",
            package="app.ui",
            responsibility="Desktop-интерфейс оператора и других ролей на PyQt.",
            status="частично реализовано",
        ),
    )
