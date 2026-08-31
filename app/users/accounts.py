from dataclasses import dataclass


@dataclass(frozen=True)
class DemoUserDefinition:
    username: str
    display_name: str
    role_code: str
    password: str


@dataclass(frozen=True)
class UserAccount:
    username: str
    display_name: str
    role_code: str
    role_title: str
    responsibility: str
    is_active: bool


@dataclass(frozen=True)
class UserSession:
    username: str
    display_name: str
    role_code: str
    role_title: str


DEMO_USERS: tuple[DemoUserDefinition, ...] = (
    DemoUserDefinition(
        username="operator",
        display_name="Демо-оператор",
        role_code="operator",
        password="demo",
    ),
    DemoUserDefinition(
        username="technologist",
        display_name="Демо-технолог",
        role_code="technologist",
        password="demo",
    ),
    DemoUserDefinition(
        username="instrumentation",
        display_name="Демо-инженер КИПиА",
        role_code="instrumentation_engineer",
        password="demo",
    ),
    DemoUserDefinition(
        username="manager",
        display_name="Демо-руководитель",
        role_code="manager",
        password="demo",
    ),
    DemoUserDefinition(
        username="admin",
        display_name="Демо-администратор",
        role_code="administrator",
        password="demo",
    ),
)
