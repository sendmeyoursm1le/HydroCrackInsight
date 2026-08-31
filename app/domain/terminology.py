from dataclasses import dataclass


PROJECT_NAME = "HydroCrack Insight"
SYSTEM_PURPOSE = (
    "Desktop-система мониторинга, анализа и поддержки принятия решений для "
    "процесса гидрокрекинга."
)
SYSTEM_BOUNDARY = (
    "HydroCrack Insight является информационно-аналитической надстройкой над "
    "SCADA/DCS. Приложение показывает рекомендации, фиксирует действия и "
    "демонстрирует реакции в учебной модели, но не заменяет промышленный "
    "управляющий контур DCS/PLC."
)


@dataclass(frozen=True)
class DomainTerm:
    code: str
    title: str
    definition: str


def get_domain_terms() -> tuple[DomainTerm, ...]:
    return (
        DomainTerm(
            code="unit",
            title="Установка",
            definition="Объект автоматизации: установка гидрокрекинга или ее линия.",
        ),
        DomainTerm(
            code="equipment",
            title="Оборудование",
            definition="Реактор, насос, компрессор, клапан, теплообменник и другие узлы.",
        ),
        DomainTerm(
            code="sensor",
            title="Датчик или тег",
            definition=(
                "Источник технологического параметра: температура, давление, "
                "расход, уровень, перепад давления или показатель качества."
            ),
        ),
        DomainTerm(
            code="process_value",
            title="Показание процесса",
            definition="Значение технологического параметра с отметкой времени.",
        ),
        DomainTerm(
            code="operating_mode",
            title="Технологический режим",
            definition=(
                "Набор целевых диапазонов и уставок для ведения процесса: мягкий, "
                "нормальный, жесткий и другие режимы."
            ),
        ),
        DomainTerm(
            code="deviation",
            title="Отклонение",
            definition=(
                "Выход параметра за нормальный диапазон или приближение к "
                "регламентной границе."
            ),
        ),
        DomainTerm(
            code="recommendation",
            title="Рекомендация",
            definition=(
                "Подсказка системы оператору, технологу или инженеру по возможному "
                "действию при отклонении."
            ),
        ),
        DomainTerm(
            code="event_log",
            title="Журнал событий",
            definition="История сообщений, предупреждений, аварий и действий системы.",
        ),
        DomainTerm(
            code="shift_journal",
            title="Сменный журнал",
            definition="Оперативные записи и итоговый чек-лист смены.",
        ),
        DomainTerm(
            code="resource_usage",
            title="Расход ресурсов",
            definition=(
                "Потребление водорода, энергии, воды, катализатора и реагентов "
                "за период."
            ),
        ),
        DomainTerm(
            code="report",
            title="Отчет",
            definition="Сформированная сводка по режиму, отклонениям, ресурсам или KPI.",
        ),
    )
