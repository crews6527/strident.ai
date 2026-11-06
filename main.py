import multiprocessing
import sys
import traceback


def main():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from pcs_agent.config import load
    from pcs_agent.ui import ConsoleWindow
    # Avoid blurry text on high-DPI displays (Windows scaling).
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    # Qt 6 enables high-DPI pixmaps automatically; the Qt 5 attribute was removed.
    app.setApplicationName("Strident.AI")
    app.setStyle("Fusion")
    stage = "loading saved settings"
    try:
        config = load()
        stage = "opening the data folder and acquiring the instance lock"
        from pcs_agent.instance import InstanceLock
        lock = InstanceLock(config["data_dir"])
    except Exception as exc:
        print(f"Startup failed while {stage}:", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.stderr.flush()
        QMessageBox.critical(None, "Strident needs attention", str(exc))
        return 2
    try:
        window = ConsoleWindow(config)
        window.show()
        # Exceptions in Qt callbacks do not propagate out of app.exec(). Without
        # a Python hook PyQt calls abort(), bypassing our outer try/finally.
        previous_hook = sys.excepthook
        notices = []
        def callback_error(kind, error, tb):
            traceback.print_exception(kind, error, tb, file=sys.stderr)
            sys.stderr.flush()
            try:
                if window.controller:
                    window.controller.cancel_all()
                if notices:
                    return
                notice = QMessageBox(window)
                notice.setIcon(QMessageBox.Icon.Critical)
                notice.setWindowTitle("Strident encountered an error")
                notice.setText("An interface action failed. Active and queued tasks were cancelled. "
                               "The window remains open; review the error before retrying.")
                notice.setInformativeText(f"{kind.__name__}: {error}")
                notice.setStandardButtons(QMessageBox.StandardButton.Ok)
                notices.append(notice)
                notice.finished.connect(lambda _: notices.clear())
                notice.open()
            except Exception:
                # Reporting must never raise back into PyQt's fatal handler.
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()
                app.exit(1)
        sys.excepthook = callback_error
        try:
            return app.exec()
        finally:
            sys.excepthook = previous_hook
    except Exception as exc:
        print("Startup failed while opening the desktop window:", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.stderr.flush()
        QMessageBox.critical(None, "Strident could not start", str(exc))
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
