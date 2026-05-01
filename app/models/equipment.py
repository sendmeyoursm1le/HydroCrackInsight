from dataclasses import dataclass


@dataclass
class Equipment:
    name: str
    equipment_type: str
    status: str
    description: str


def create_default_equipment() -> list[Equipment]:
    return [
        Equipment(
            name="Реактор R-101",
            equipment_type="Реактор",
            status="Работает",
            description="Основной реактор гидрокрекинга",
        ),
        Equipment(
            name="Насос P-201",
            equipment_type="Насос",
            status="Работает",
            description="Подача сырья",
        ),
        Equipment(
            name="Компрессор C-301",
            equipment_type="Компрессор",
            status="Работает",
            description="Подача водорода",
        ),
        Equipment(
            name="Клапан V-401",
            equipment_type="Клапан",
            status="Работает",
            description="Регулирование давления",
        ),
        Equipment(
            name="Теплообменник H-501",
            equipment_type="Теплообменник",
            status="Работает",
            description="Контроль температуры",
        ),
    ]