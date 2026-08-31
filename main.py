import sys
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QDialog

from app.database.database_service import DatabaseService
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.users import UserSession


class ApplicationController:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.database_service = DatabaseService()
        self.database_service.initialize_database()
        self.current_window: MainWindow | None = None

    def start(self) -> int:
        if not self.open_login_window():
            return 0

        return self.app.exec()

    def open_login_window(self) -> bool:
        login_dialog = LoginDialog(self.database_service)
        if login_dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        user_session = login_dialog.user_session
        if user_session is None:
            return False

        self.open_main_window(user_session)
        return True

    def open_main_window(self, user_session: UserSession) -> None:
        self.save_audit_event(
            user_session=user_session,
            action="login",
            details="Вход в систему",
        )

        window = MainWindow(
            database_service=self.database_service,
            current_user=user_session,
        )
        window.switch_user_requested.connect(self.switch_user)
        window.show()

        self.current_window = window

    def switch_user(self) -> None:
        if self.current_window is None:
            return

        previous_window = self.current_window
        previous_user = previous_window.current_user
        previous_window.hide()

        login_dialog = LoginDialog(self.database_service)
        if login_dialog.exec() != QDialog.DialogCode.Accepted:
            previous_window.show()
            return

        next_user = login_dialog.user_session
        if next_user is None:
            previous_window.show()
            return

        self.save_audit_event(
            user_session=previous_user,
            action="logout",
            details="Смена пользователя",
        )

        previous_window.prepare_for_session_switch()
        self.open_main_window(next_user)
        previous_window.close()

    def save_audit_event(
        self,
        user_session: UserSession,
        action: str,
        details: str,
    ) -> None:
        self.database_service.save_audit_event(
            timestamp=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            username=user_session.username,
            role_code=user_session.role_code,
            action=action,
            details=details,
        )


def main() -> None:
    app = QApplication(sys.argv)
    controller = ApplicationController(app)

    sys.exit(controller.start())


if __name__ == "__main__":
    main()
