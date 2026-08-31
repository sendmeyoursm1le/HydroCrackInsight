from dataclasses import dataclass


@dataclass(frozen=True)
class RoleDefinition:
    code: str
    title: str
    responsibility: str


def get_role_definitions() -> tuple[RoleDefinition, ...]:
    return (
        RoleDefinition(
            code="operator",
            title="Оператор",
            responsibility="Оперативный мониторинг, фиксация событий и итогов смены.",
        ),
        RoleDefinition(
            code="technologist",
            title="Технолог",
            responsibility=(
                "Анализ режима, управление уставками, сценарии прогноза и отчеты."
            ),
        ),
        RoleDefinition(
            code="instrumentation_engineer",
            title="Инженер КИПиА/АСУ ТП",
            responsibility=(
                "Диагностика датчиков, клапанов, насосов, компрессоров, "
                "каналов измерения и технических событий."
            ),
        ),
        RoleDefinition(
            code="manager",
            title="Руководитель",
            responsibility="Просмотр KPI, отчетов, отклонений и производственной сводки.",
        ),
        RoleDefinition(
            code="administrator",
            title="Администратор",
            responsibility="Настройка пользователей, ролей и справочников системы.",
        ),
    )
