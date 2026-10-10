import multiprocessing
import sys


def main():
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from pcs_agent.config import load
    from pcs_agent.ui import ConsoleWindow
    app = QApplication(sys.argv)
    app.setApplicationName("Strident.AI")
    app.setStyle("Fusion")
    try:
        config = load()
        from pcs_agent.instance import InstanceLock
        lock = InstanceLock(config["data_dir"])
    except Exception as exc:
        QMessageBox.critical(None, "Strident needs attention", str(exc))
        return 2
    try:
        window = ConsoleWindow(config)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "Strident could not start", str(exc))
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
