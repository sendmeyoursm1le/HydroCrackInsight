import sys
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QDialog

from app.database.database_service import DatabaseService
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)

    database_service = DatabaseService()
    database_service.initialize_database()

    login_dialog = LoginDialog(database_service)
    if login_dialog.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    user_session = login_dialog.user_session
    if user_session is None:
        sys.exit(0)

    database_service.save_audit_event(
        timestamp=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        username=user_session.username,
        role_code=user_session.role_code,
        action="login",
        details="Вход в систему",
    )

    window = MainWindow(
        database_service=database_service,
        current_user=user_session,
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
