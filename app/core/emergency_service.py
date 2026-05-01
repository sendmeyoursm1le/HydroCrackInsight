from dataclasses import dataclass

from app.core.deviation_analyzer import DeviationResult
from app.models.equipment import Equipment


@dataclass
class EmergencyAction:
    equipment_name: str
    new_status: str
    action_description: str


@dataclass
class EmergencyResponse:
    is_required: bool
    emergency_type: str
    operator_message: str
    actions: list[EmergencyAction]


class EmergencyService:
    """
    Подсистема аварийного реагирования.

    Задачи:
    - определить тип аварийной ситуации;
    - изменить состояние связанного оборудования;
    - сформировать корректирующие действия;
    - передать оператору описание аварии и рекомендации.
    """

    def process_emergency(
        self,
        deviation: DeviationResult,
        equipment_list: list[Equipment],
    ) -> EmergencyResponse:
        if not deviation.is_emergency:
            return EmergencyResponse(
                is_required=False,
                emergency_type="",
                operator_message="Аварийное реагирование не требуется",
                actions=[],
            )

        if deviation.parameter == "Температура":
            return self._handle_temperature_emergency(equipment_list)

        if deviation.parameter == "Давление":
            return self._handle_pressure_emergency(equipment_list)

        if deviation.parameter == "Расход водорода":
            return self._handle_hydrogen_emergency(equipment_list)

        return EmergencyResponse(
            is_required=True,
            emergency_type="Неизвестная авария",
            operator_message="Обнаружено аварийное состояние неизвестного типа",
            actions=[
                EmergencyAction(
                    equipment_name="Установка гидрокрекинга",
                    new_status="Авария",
                    action_description="Перевести установку в безопасный режим",
                )
            ],
        )

    def reset_equipment(self, equipment_list: list[Equipment]) -> None:
        for equipment in equipment_list:
            equipment.status = "Работает"

    def _handle_temperature_emergency(
        self,
        equipment_list: list[Equipment],
    ) -> EmergencyResponse:
        actions = [
            EmergencyAction(
                equipment_name="Реактор R-101",
                new_status="Авария",
                action_description="Снизить тепловую нагрузку на реактор",
            ),
            EmergencyAction(
                equipment_name="Теплообменник H-501",
                new_status="Требуется проверка",
                action_description="Увеличить охлаждение и проверить теплообменник",
            ),
            EmergencyAction(
                equipment_name="Насос P-201",
                new_status="Сниженная нагрузка",
                action_description="Снизить подачу сырья",
            ),
        ]

        self._apply_actions(equipment_list, actions)

        return EmergencyResponse(
            is_required=True,
            emergency_type="Перегрев реактора",
            operator_message=(
                "Обнаружен перегрев реактора. Система инициировала снижение "
                "нагрузки и проверку контура охлаждения."
            ),
            actions=actions,
        )

    def _handle_pressure_emergency(
        self,
        equipment_list: list[Equipment],
    ) -> EmergencyResponse:
        actions = [
            EmergencyAction(
                equipment_name="Клапан V-401",
                new_status="Аварийное регулирование",
                action_description="Открыть клапан сброса давления",
            ),
            EmergencyAction(
                equipment_name="Насос P-201",
                new_status="Сниженная нагрузка",
                action_description="Снизить подачу сырья",
            ),
            EmergencyAction(
                equipment_name="Реактор R-101",
                new_status="Контроль давления",
                action_description="Контролировать давление в реакторе",
            ),
        ]

        self._apply_actions(equipment_list, actions)

        return EmergencyResponse(
            is_required=True,
            emergency_type="Превышение давления",
            operator_message=(
                "Обнаружено критическое превышение давления. Система инициировала "
                "аварийное регулирование давления."
            ),
            actions=actions,
        )

    def _handle_hydrogen_emergency(
        self,
        equipment_list: list[Equipment],
    ) -> EmergencyResponse:
        actions = [
            EmergencyAction(
                equipment_name="Компрессор C-301",
                new_status="Авария",
                action_description="Проверить подачу водорода",
            ),
            EmergencyAction(
                equipment_name="Насос P-201",
                new_status="Сниженная нагрузка",
                action_description="Снизить расход сырья",
            ),
            EmergencyAction(
                equipment_name="Реактор R-101",
                new_status="Безопасный режим",
                action_description="Перевести реактор в безопасный режим",
            ),
        ]

        self._apply_actions(equipment_list, actions)

        return EmergencyResponse(
            is_required=True,
            emergency_type="Недостаток водорода",
            operator_message=(
                "Обнаружено критическое снижение расхода водорода. Система "
                "инициировала снижение подачи сырья и проверку компрессора."
            ),
            actions=actions,
        )

    def _apply_actions(
        self,
        equipment_list: list[Equipment],
        actions: list[EmergencyAction],
    ) -> None:
        for action in actions:
            equipment = self._find_equipment(equipment_list, action.equipment_name)

            if equipment is not None:
                equipment.status = action.new_status

    @staticmethod
    def _find_equipment(
        equipment_list: list[Equipment],
        equipment_name: str,
    ) -> Equipment | None:
        for equipment in equipment_list:
            if equipment.name == equipment_name:
                return equipment

        return None