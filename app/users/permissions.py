VIEW_MONITORING = "view_monitoring"
VIEW_EQUIPMENT = "view_equipment"
VIEW_DEVIATIONS = "view_deviations"
VIEW_REPORTS = "view_reports"
VIEW_LOGS = "view_logs"
MANAGE_USERS = "manage_users"

CONTROL_MONITORING = "control_monitoring"
SIMULATE_EMERGENCY = "simulate_emergency"
RESET_EMERGENCY = "reset_emergency"
RESET_EQUIPMENT_STATUSES = "reset_equipment_statuses"
VIEW_DATABASE_STATISTICS = "view_database_statistics"
IMPORT_PROCESS_DATA = "import_process_data"
CHANGE_OPERATING_MODE = "change_operating_mode"


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "operator": frozenset(
        {
            VIEW_MONITORING,
            VIEW_EQUIPMENT,
            VIEW_DEVIATIONS,
            VIEW_LOGS,
            CONTROL_MONITORING,
            SIMULATE_EMERGENCY,
            RESET_EMERGENCY,
            RESET_EQUIPMENT_STATUSES,
            IMPORT_PROCESS_DATA,
        }
    ),
    "technologist": frozenset(
        {
            VIEW_MONITORING,
            VIEW_EQUIPMENT,
            VIEW_DEVIATIONS,
            VIEW_REPORTS,
            VIEW_LOGS,
            VIEW_DATABASE_STATISTICS,
            IMPORT_PROCESS_DATA,
            CHANGE_OPERATING_MODE,
        }
    ),
    "instrumentation_engineer": frozenset(
        {
            VIEW_MONITORING,
            VIEW_EQUIPMENT,
            VIEW_LOGS,
            RESET_EQUIPMENT_STATUSES,
            IMPORT_PROCESS_DATA,
        }
    ),
    "manager": frozenset(
        {
            VIEW_MONITORING,
            VIEW_DEVIATIONS,
            VIEW_REPORTS,
            VIEW_LOGS,
            VIEW_DATABASE_STATISTICS,
        }
    ),
    "administrator": frozenset(
        {
            VIEW_MONITORING,
            VIEW_EQUIPMENT,
            VIEW_DEVIATIONS,
            VIEW_REPORTS,
            VIEW_LOGS,
            MANAGE_USERS,
            CONTROL_MONITORING,
            SIMULATE_EMERGENCY,
            RESET_EMERGENCY,
            RESET_EQUIPMENT_STATUSES,
            VIEW_DATABASE_STATISTICS,
            IMPORT_PROCESS_DATA,
            CHANGE_OPERATING_MODE,
        }
    ),
}

TAB_PERMISSIONS: dict[str, str] = {
    "monitoring": VIEW_MONITORING,
    "equipment": VIEW_EQUIPMENT,
    "deviations": VIEW_DEVIATIONS,
    "reports": VIEW_REPORTS,
    "logs": VIEW_LOGS,
    "users": MANAGE_USERS,
}


def get_permissions_for_role(role_code: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role_code, frozenset())


def has_permission(role_code: str, permission: str) -> bool:
    return permission in get_permissions_for_role(role_code)


def get_accessible_tabs(role_code: str) -> tuple[str, ...]:
    return tuple(
        tab_code
        for tab_code, permission in TAB_PERMISSIONS.items()
        if has_permission(role_code, permission)
    )
