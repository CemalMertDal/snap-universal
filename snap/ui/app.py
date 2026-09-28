"""Application entry point."""
import contextlib
import io
import sys
import traceback

from snap import APP_NAME, i18n
from snap.core.settings import Settings
from snap.paths import user_data_dir

ACCENT = "#6D5DFC"


def _install_crash_handler() -> None:
    def handler(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            (user_data_dir() / "crash.log").write_text(text, encoding="utf-8")
        except OSError:
            pass
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, APP_NAME, f"{exc_type.__name__}: {exc}\n\n{user_data_dir() / 'crash.log'}")
        except Exception:
            pass
    sys.excepthook = handler


def _set_app_id() -> None:
    """Own taskbar icon/grouping instead of python.exe's."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Snap.Universal.App")
        except Exception:
            pass


def main(argv=None) -> int:
    argv = list(argv or sys.argv)
    _install_crash_handler()
    _set_app_id()
    settings = Settings.load()
    i18n.set_language(settings.language or i18n.detect_language())

    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    with contextlib.redirect_stdout(io.StringIO()):     # the widget library prints an ad banner
        import qfluentwidgets  # noqa: F401
    from snap.ui.main_window import MainWindow, apply_theme

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(str(user_data_dir() / "snap.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, i18n.t("app.already_running"))
        return 0

    from qfluentwidgets import setThemeColor
    setThemeColor(ACCENT)
    apply_theme(settings.theme)
    window = MainWindow(settings)
    window.show()
    code = app.exec()
    lock.unlock()
    return code
