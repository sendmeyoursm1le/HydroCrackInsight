VIEW_MONITORING = "view_monitoring"
VIEW_EQUIPMENT = "view_equipment"
VIEW_DEVIATIONS = "view_deviations"
VIEW_REPORTS = "view_reports"
VIEW_LOGS = "view_logs"
VIEW_RESOURCES = "view_resources"
VIEW_SHIFT_JOURNAL = "view_shift_journal"
MANAGE_USERS = "manage_users"

CONTROL_MONITORING = "control_monitoring"
SIMULATE_EMERGENCY = "simulate_emergency"
RESET_EMERGENCY = "reset_emergency"
RESET_EQUIPMENT_STATUSES = "reset_equipment_statuses"
VIEW_DATABASE_STATISTICS = "view_database_statistics"
IMPORT_PROCESS_DATA = "import_process_data"
CHANGE_OPERATING_MODE = "change_operating_mode"
CREATE_SHIFT_ENTRY = "create_shift_entry"
CREATE_SHIFT_HANDOVER = "create_shift_handover"


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "operator": frozenset(
        {
            VIEW_MONITORING,
            VIEW_EQUIPMENT,
            VIEW_DEVIATIONS,
            VIEW_LOGS,
            VIEW_RESOURCES,
            VIEW_SHIFT_JOURNAL,
            CONTROL_MONITORING,
            SIMULATE_EMERGENCY,
            RESET_EMERGENCY,
            RESET_EQUIPMENT_STATUSES,
            IMPORT_PROCESS_DATA,
            CREATE_SHIFT_ENTRY,
            CREATE_SHIFT_HANDOVER,
        }
    ),
    "technologist": frozenset(
        {
            VIEW_MONITORING,
            VIEW_EQUIPMENT,
            VIEW_DEVIATIONS,
            VIEW_REPORTS,
            VIEW_LOGS,
            VIEW_RESOURCES,
            VIEW_SHIFT_JOURNAL,
            VIEW_DATABASE_STATISTICS,
            IMPORT_PROCESS_DATA,
            CHANGE_OPERATING_MODE,
            CREATE_SHIFT_ENTRY,
        }
    ),
    "instrumentation_engineer": frozenset(
        {
            VIEW_MONITORING,
            VIEW_EQUIPMENT,
            VIEW_LOGS,
            VIEW_SHIFT_JOURNAL,
            RESET_EQUIPMENT_STATUSES,
            IMPORT_PROCESS_DATA,
            CREATE_SHIFT_ENTRY,
        }
    ),
    "manager": frozenset(
        {
            VIEW_MONITORING,
            VIEW_DEVIATIONS,
            VIEW_REPORTS,
            VIEW_LOGS,
            VIEW_RESOURCES,
            VIEW_SHIFT_JOURNAL,
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
            VIEW_RESOURCES,
            VIEW_SHIFT_JOURNAL,
            MANAGE_USERS,
            CONTROL_MONITORING,
            SIMULATE_EMERGENCY,
            RESET_EMERGENCY,
            RESET_EQUIPMENT_STATUSES,
            VIEW_DATABASE_STATISTICS,
            IMPORT_PROCESS_DATA,
            CHANGE_OPERATING_MODE,
            CREATE_SHIFT_ENTRY,
            CREATE_SHIFT_HANDOVER,
        }
    ),
}

TAB_PERMISSIONS: dict[str, str] = {
    "monitoring": VIEW_MONITORING,
    "equipment": VIEW_EQUIPMENT,
    "deviations": VIEW_DEVIATIONS,
    "resources": VIEW_RESOURCES,
    "reports": VIEW_REPORTS,
    "shift_journal": VIEW_SHIFT_JOURNAL,
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
