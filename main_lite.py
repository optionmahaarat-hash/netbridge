import os, sys

from app.lite import paths


def main():
    os.chdir(paths.app_dir())                       # data/, configs/, cores/ are relative to the program folder
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AppBaz.NetBridgeLite")
        except Exception:
            pass
    from PySide6.QtCore import QDir, QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.core import ports, system_proxy
    from app.lite import engine
    from app.lite.i18n import set_lang, tr
    from app.ui.icon import app_icon

    app = QApplication(sys.argv)
    app.setApplicationName("NetBridge Lite")
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    try:                                                              # first run: start with the servers bundled in the installer
        from app.lite import updater
        engine.seed_profiles("data/profiles.json", updater.ASSETS / "seed_profiles.json")
    except Exception:
        pass
    set_lang(engine.load_settings()["lang"])

    lock = QLockFile(QDir.temp().filePath("netbridge-lite.lock"))      # one copy only (ports + system proxy)
    if not lock.tryLock(100):
        QMessageBox.information(None, "NetBridge Lite", tr("already_running")); return 0
    try:                                                              # a crash can leave Windows pointing at a dead proxy
        system_proxy.clear_stale(lambda port: not ports.is_free(port))
    except Exception:
        pass

    from app.lite.window import LiteWindow
    w = LiteWindow()
    if "--selftest" in sys.argv:                                      # used to verify a frozen build
        from app.lite import updater
        import aioquic.quic.connection, cryptography.hazmat.primitives.asymmetric.ed25519      # noqa: F401 (lazy imports)
        from app.utils.certhash import quic_cert_hash                                         # noqa: F401
        key = (updater.ASSETS / "update_pubkey.txt").exists()
        print("selftest ok", w.windowTitle(), "| icon:", not w.windowIcon().isNull(), "| xray:", paths.xray_exe().exists(),
              "| assets:", updater.ASSETS.exists(), "| update key:", key, "| frozen:", paths.frozen())
        return 0
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
