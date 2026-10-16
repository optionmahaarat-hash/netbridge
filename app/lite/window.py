import platform, sys, time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from app.core import ports, system_proxy
from app.core.config_generator import write_config
from app.core.xray_manager import XrayManager
from app.core import autobypass, bypass, presets, tlsup
from app.lite import engine as E, paths, updater
from app.lite.i18n import lang, set_lang, tr
from app.lite.version import LITE_VERSION
from app.storage.profiles import load_profiles, save_profiles
from app.ui.about_dialog import AboutDialog
from app.ui.icon import app_icon, logo_pixmap
from app.ui import theme
from app.utils.latency import exit_info, real_delay

IDLE, FINDING, CONNECTED = "idle", "finding", "connected"
BTN = {IDLE: theme.GRAD_BLUE, FINDING: theme.GRAD_AMBER, CONNECTED: theme.GRAD_GREEN}


class Task(QThread):
    """Runs fn(progress, cancelled) in a thread; result comes back through signals."""
    progress = Signal(object)
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn, self.cancel = fn, False

    def run(self):
        try:
            self.ok.emit(self.fn(self.progress.emit, lambda: self.cancel))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class LiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = E.load_settings()
        set_lang(self.settings["lang"])
        self.profiles = load_profiles()
        self.xray = XrayManager(str(paths.xray_exe()))
        self.state, self.http, self.socks = IDLE, 0, 0
        self.tasks, self.log, self.upd = set(), [], None
        self._proxy_server = None                 # the Windows proxy value WE set (so we only ever undo our own)
        self._clip_seen, self._clip_text, self._warn = "", "", ""
        self.setWindowIcon(app_icon())
        self.resize(400, 620)
        self.setMinimumWidth(380)
        self._build()
        self.apply_texts()
        self.refresh_combo()
        self.watch = QTimer(self); self.watch.timeout.connect(self.poll); self.watch.start(1000)
        QGuiApplication.clipboard().dataChanged.connect(self.check_clipboard)
        QApplication.instance().applicationStateChanged.connect(lambda _: self.check_clipboard())
        QTimer.singleShot(400, self.check_clipboard)
        if updater.take_failure_flag(paths.app_dir()):
            QTimer.singleShot(600, lambda: QMessageBox.information(self, self.windowTitle(), tr("upd_failed_prev")))

    # ---------- UI ----------
    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setSpacing(10); v.setContentsMargins(16, 12, 16, 12)
        top = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(logo_pixmap("mark.png", 40))
        self.title = QLabel(theme.BRAND_HTML); self.title.setObjectName("brand")
        self.menu_btn = QToolButton(); self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setStyleSheet(f"QToolButton{{font-size:20px;color:{theme.CYAN};background:{theme.CARD};border:1px solid {theme.LINE};border-radius:9px;padding:2px 10px}}QToolButton:hover{{border:1px solid {theme.BLUE}}}QToolButton::menu-indicator{{image:none}}")
        top.addWidget(logo); top.addWidget(self.title); top.addStretch(1); top.addWidget(self.menu_btn)
        v.addLayout(top)

        self.empty = QLabel(); self.empty.setAlignment(Qt.AlignCenter); self.empty.setWordWrap(True)
        self.empty.setStyleSheet(f"color:{theme.MUTED};padding:18px;border:1px dashed {theme.LINE};border-radius:12px")
        v.addWidget(self.empty)

        self.status = QLabel(); self.status.setAlignment(Qt.AlignCenter); self.status.setWordWrap(True)
        self.status.setStyleSheet("font-size:16px;font-weight:700;padding:6px")
        self.sub = QLabel(); self.sub.setAlignment(Qt.AlignCenter); self.sub.setWordWrap(True)
        self.sub.setStyleSheet(f"color:{theme.MUTED}")
        v.addWidget(self.status); v.addWidget(self.sub)

        self.btn = QPushButton(); self.btn.setMinimumHeight(84); self.btn.clicked.connect(self.on_button)
        v.addWidget(self.btn)

        row = QHBoxLayout()
        self.server_lbl = QLabel(); self.combo = QComboBox(); self.combo.setMinimumHeight(30)
        self.combo.currentIndexChanged.connect(self.combo_changed)
        row.addWidget(self.server_lbl); row.addWidget(self.combo, 1)
        v.addLayout(row)

        self.add_btn = QPushButton(); self.add_btn.setMinimumHeight(36)
        self.add_menu = QMenu(self); self.add_btn.setMenu(self.add_menu)
        v.addWidget(self.add_btn)

        self.clip_bar = QFrame(); self.clip_bar.setStyleSheet(f"QFrame{{background:{theme.CARD2};border:1px solid {theme.BLUE};border-radius:10px}}")
        cb = QHBoxLayout(self.clip_bar); self.clip_lbl = QLabel(); self.clip_go = QPushButton()
        self.clip_go.clicked.connect(self.add_clip_banner)
        cb.addWidget(self.clip_lbl, 1); cb.addWidget(self.clip_go)
        self.clip_bar.hide(); v.addWidget(self.clip_bar)

        self.upd_bar = QFrame(); self.upd_bar.setStyleSheet(f"QFrame{{background:{theme.CARD};border:1px solid {theme.GREEN};border-radius:10px}}")
        ub = QHBoxLayout(self.upd_bar); self.upd_lbl = QLabel(); self.upd_go = QPushButton()
        self.upd_go.clicked.connect(self.install_update)
        ub.addWidget(self.upd_lbl, 1); ub.addWidget(self.upd_go)
        self.upd_bar.hide(); v.addWidget(self.upd_bar)

        v.addStretch(1)
        self.iran = QCheckBox(); self.iran.setChecked(self.settings["iran_direct"])
        self.iran.toggled.connect(lambda c: self.set_opt("iran_direct", c))
        self.sysp = QCheckBox(); self.sysp.setChecked(self.settings["system_proxy"])
        self.sysp.toggled.connect(lambda c: self.set_opt("system_proxy", c))
        if not system_proxy.supported():
            self.sysp.setEnabled(False)
        v.addWidget(self.iran); v.addWidget(self.sysp)
        self.foot = QLabel(); self.foot.setAlignment(Qt.AlignCenter); self.foot.setStyleSheet(f"color:{theme.MUTED};font-size:11px")
        v.addWidget(self.foot)

    def apply_texts(self):
        app = QApplication.instance()
        app.setLayoutDirection(Qt.RightToLeft if lang() == "fa" else Qt.LeftToRight)
        self.setWindowTitle(tr("app"))
        self.title.setText(theme.BRAND_HTML + f"<span style='font-size:13px;color:{theme.MUTED}'> Lite</span>"
                           if lang() != "fa" else tr("app"))
        self.menu_btn.setText(tr("menu")); self.add_btn.setText(tr("add")); self.server_lbl.setText(tr("server"))
        self.iran.setText(tr("iran")); self.sysp.setText(tr("sysproxy")); self.clip_go.setText(tr("clip_add"))
        self.empty.setText(tr("empty")); self.upd_go.setText(tr("upd_btn"))
        self.add_menu.clear()
        self.add_menu.addAction(tr("add_clip"), self.add_from_clipboard)
        self.add_menu.addAction(tr("add_paste"), self.add_from_dialog)
        self.add_menu.addAction(tr("add_file"), self.add_from_file)
        m = QMenu(self)
        for key, fn in (("m_refresh", self.refresh_subs), ("m_test", self.test_servers), ("m_tls", self.convert_tls), ("m_del", self.delete_selected),
                        ("m_del_all", self.delete_all), ("m_update", lambda: self.check_updates(manual=True)),
                        ("m_lang", self.toggle_lang), ("m_report", self.show_report), ("m_about", self.about)):
            m.addAction(tr(key), fn)
        self.menu_btn.setMenu(m)
        self.set_state(self.state)
        self.foot.setText(f"{tr('n_servers', n=len(self.profiles))}  ·  v{LITE_VERSION}")
        self.empty.setVisible(not self.profiles)

    def set_state(self, st, **kw):
        self.state = st
        text = {IDLE: tr("connect"), FINDING: tr("cancel"), CONNECTED: tr("disconnect")}[st]
        self.btn.setText(text)
        self.btn.setStyleSheet(theme.big_button(BTN[st]))
        if st == IDLE:
            self.status.setText(tr("st_idle")); self.sub.setText("")
        elif st == FINDING:
            self.status.setText(tr("st_finding", done=kw.get("done", 0), total=kw.get("total", "…")))
        else:
            self.status.setText(tr("st_ok"))
        for w in (self.combo, self.add_btn):
            w.setEnabled(st == IDLE)

    def toast(self, text):
        self.sub.setText(text)

    def set_opt(self, key, val):
        self.settings[key] = val; E.save_settings(self.settings)
        if key == "iran_direct" and self.state == CONNECTED:
            self.toast(tr("st_starting")); self.reconnect()

    # ---------- servers list ----------
    def refresh_combo(self):
        self.combo.blockSignals(True)
        self.combo.clear(); self.combo.addItem(tr("auto"), "auto")
        for p in sorted(self.profiles, key=E._rank):
            d = p.get("delay")
            tag = "" if d is None else (" ✗" if d < 0 else f"  {d} ms")
            self.combo.addItem(f"{p.get('name') or p.get('server')}{tag}", E.profile_key(p))
        i = self.combo.findData(self.settings["selected"])
        self.combo.setCurrentIndex(max(0, i))
        self.combo.blockSignals(False)
        self.empty.setVisible(not self.profiles)
        self.foot.setText(f"{tr('n_servers', n=len(self.profiles))}  ·  v{LITE_VERSION}")

    def combo_changed(self, _):
        self.settings["selected"] = self.combo.currentData() or "auto"; E.save_settings(self.settings)

    def selected_profile(self):
        key = self.settings["selected"]
        return next((p for p in self.profiles if E.profile_key(p) == key), None) if key != "auto" else None

    def save(self):
        save_profiles(self.profiles); E.save_settings(self.settings)

    def delete_selected(self):
        p = self.selected_profile()
        if not p:
            QMessageBox.information(self, tr("app"), tr("pick_server")); return
        self.profiles.remove(p); self.settings["selected"] = "auto"; self.save(); self.refresh_combo()

    def delete_all(self):
        if QMessageBox.question(self, tr("app"), tr("confirm_del_all")) == QMessageBox.Yes:
            self.profiles.clear(); self.settings["selected"] = "auto"; self.settings["subs"] = []
            self.save(); self.refresh_combo()

    # ---------- adding configs ----------
    def run(self, fn, ok, failed=None, progress=None):
        t = Task(fn, self); self.tasks.add(t)
        t.ok.connect(ok)
        t.failed.connect(failed or (lambda e: QMessageBox.warning(self, tr("app"), e)))
        if progress: t.progress.connect(progress)
        t.finished.connect(lambda: self.tasks.discard(t))
        t.start(); return t

    def proxy_url(self):
        return f"http://127.0.0.1:{self.http}" if self.state == CONNECTED else None

    def add_from_clipboard(self):
        self.handle_text(QGuiApplication.clipboard().text())

    def add_from_dialog(self):
        text, ok = QInputDialog.getMultiLineText(self, tr("app"), tr("add_paste"))
        if ok: self.handle_text(text)

    def add_from_file(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("app"), "", "Text / JSON (*.txt *.json *.conf);;*.*")
        if f: self.handle_text(Path(f).read_text(encoding="utf-8", errors="replace"))

    def add_clip_banner(self):
        self.clip_bar.hide(); self._clip_seen = self._clip_text
        self.handle_text(self._clip_text)

    def handle_text(self, text):
        kind = E.classify_text(text)
        if kind is None:
            QMessageBox.information(self, tr("app"), tr("no_valid")); return
        if kind == "subscription":
            url = text.strip()
            self.toast("…")
            self.run(lambda p, c: E.add_subscription(self.profiles, url, self.settings, self.proxy_url()),
                     self.after_add,
                     lambda e: QMessageBox.warning(self, tr("app"), tr("sub_fail", err=e)))
        else:
            self.after_add(E.add_text(self.profiles, text))

    def after_add(self, r):
        added, dup = r[0], r[1]
        self.save(); self.refresh_combo()
        self.toast(tr("added_dup", n=added, d=dup) if dup and added else tr("added", n=added) if added else tr("nothing_new"))
        self.apply_texts_light()
        if any(p.get("insecure") and not p.get("pcs") for p in self.profiles):
            from app.utils.certhash import fetch_pin
            self.run(lambda p, c: E.pin_pending(self.profiles, fetch_pin), lambda n: self.save())

    def apply_texts_light(self):
        self.empty.setVisible(not self.profiles)

    def refresh_subs(self):
        if not self.settings["subs"]:
            QMessageBox.information(self, tr("app"), tr("no_subs")); return
        self.toast("…")
        self.run(lambda p, c: E.refresh_subscriptions(self.profiles, self.settings, self.proxy_url()),
                 lambda r: (self.save(), self.refresh_combo(), self.toast(tr("sub_updated", n=r[0]))))

    def test_servers(self):
        if not self.profiles or self.state != IDLE: return
        if not paths.xray_exe().exists():
            QMessageBox.critical(self, tr("app"), tr("no_core", p=paths.xray_exe())); return
        self.set_state(FINDING)
        def prog(v):
            self.toast(tr("testing", done=v[0], total=v[1]))
        t = self.run(lambda p, c: E.find_fastest(self.xray.executable, self.profiles, want=10**6, max_total=200,
                                                 on_progress=lambda d, n: p((d, n)), cancelled=c),
                     lambda ok: self._tested(ok), progress=prog)
        self.finding = t

    def _tested(self, ok):
        self.save(); self.refresh_combo(); self.set_state(IDLE)
        self.toast(tr("test_done", ok=len(ok), n=len(self.profiles)))

    # ---------- clipboard ----------
    def check_clipboard(self):
        text = QGuiApplication.clipboard().text()
        if not text or text == self._clip_seen:
            return
        if E.classify_text(text) not in ("links", "json"):
            self.clip_bar.hide(); return
        from app.utils.parser import parse_many
        found, _ = parse_many(text[:400_000])
        have = {E.profile_key(p) for p in self.profiles}
        new = [p for p in found if E.profile_key(p) not in have]
        if not new:
            self.clip_bar.hide(); return
        self._clip_text = text
        self.clip_lbl.setText(tr("clip_found", n=len(new))); self.clip_bar.show()

    # ---------- connect / disconnect ----------
    def on_button(self):
        if self.state == IDLE: self.start()
        elif self.state == FINDING: self.cancel_finding()
        else: self.disconnect()

    def cancel_finding(self):
        t = getattr(self, "finding", None)
        if t: t.cancel = True
        self.set_state(IDLE)

    def xray_settings(self):
        return {"routing": {"lan": True, "iran": self.settings["iran_direct"], "ads": False, "direct": [], "proxy": []}}

    def start(self):
        if not self.profiles:
            QMessageBox.information(self, tr("app"), tr("empty")); return
        if not paths.xray_exe().exists():
            QMessageBox.critical(self, tr("app"), tr("no_core", p=paths.xray_exe())); return
        sel = self.selected_profile()
        if sel:
            self.launch([sel], "manual"); return
        self._upgraded = False
        self.begin_find()

    def begin_find(self):
        self.set_state(FINDING)
        def prog(v):
            if self.state == FINDING: self.set_state(FINDING, done=v[0], total=v[1])
        def work(p, c):
            res = presets.auto_update(bypass.STATE["version"])        # newest bypass values first; silent, failure changes nothing
            if res and res[0] == "updated":
                bypass.reload()
                self.log.append(f"AUTO: bypass values updated to version {res[1]['version']}")
            r = E.auto_find(self.xray.executable, self.profiles, on_progress=lambda d, n: p((d, n)), cancelled=c,
                            on_status=lambda t: self.log.append("AUTO: " + t))
            return r
        self.finding = self.run(work, self.found_fastest, progress=prog,
                                failed=lambda e: (self.set_state(IDLE), QMessageBox.warning(self, tr("app"), e)))

    def found_fastest(self, r):
        ok, res = r
        if self.state != FINDING:
            return                                          # user pressed cancel
        self.save(); self.refresh_combo()
        if ok:
            pool, mode = E.choose_connection(ok)
            self._warn = (tr("warn_relaxed") if res.get("relaxed_fallback") else
                          tr("warn_plain") if res.get("insecure_fallback") or not any(autobypass.is_tls(p) for p in pool) else "")
            self.launch(pool, mode)
            return
        self.set_state(IDLE)
        QMessageBox.warning(self, tr("app"), tr("all_dead"))

    def upgraded_then_find(self, results):
        if self.state != FINDING: return
        n = E.apply_upgrade(self.profiles, results)
        self.save(); self.refresh_combo()
        if n: self.begin_find()                             # test again, now including the TLS versions
        else:
            self.set_state(IDLE); QMessageBox.warning(self, tr("app"), tr("tls_none"))

    def convert_tls(self):
        """Menu: try to give every non-TLS server a TLS port (same as the automatic step, but on demand)."""
        if self.state != IDLE: return
        if not E.plain_profiles(self.profiles, force=True):
            QMessageBox.information(self, tr("app"), tr("tls_no_plain")); return
        if not paths.xray_exe().exists():
            QMessageBox.critical(self, tr("app"), tr("no_core", p=paths.xray_exe())); return
        self.set_state(FINDING)
        def prog(v):
            if self.state == FINDING: self.status.setText(tr("st_tls", done=v[0], total=v[1]))
        self.status.setText(tr("st_tls", done=0, total="…"))
        def done(results):
            n = E.apply_upgrade(self.profiles, results); self.save(); self.refresh_combo(); self.set_state(IDLE)
            self.toast(tr("tls_done", n=n) if n else tr("tls_nothing"))
        self.finding = self.run(lambda p, c: E.upgrade_plain(self.xray.executable, self.profiles, force=True, cap=60,
                                                             on_progress=lambda d, n: p((d, n)), cancelled=c),
                                done, progress=prog)

    def launch(self, pool, mode):
        try:
            self.socks, self.http = ports.pick_ports()
            cfg = Path("configs/active.json")
            write_config(pool, cfg, self.xray_settings(), mode=mode, socks_port=self.socks, http_port=self.http,
                         all_profiles=self.profiles)
            self.xray.start(cfg)
        except Exception as e:
            self.set_state(IDLE); QMessageBox.critical(self, tr("app"), tr("start_fail", err=e)); return
        self.set_state(CONNECTED); self.status.setText(tr("st_starting")); self.btn.setEnabled(False)
        QTimer.singleShot(1000, self.after_start)

    def after_start(self):
        self.btn.setEnabled(True)
        if self.state != CONNECTED: return
        if not self.xray.running:
            self.fail_connection(); return
        self.set_proxy(True)
        self.status.setText(tr("st_ok"))
        port = self.http
        def verify(p, c):
            last = None
            for _ in range(3):                                  # one flaky request must not show "no internet"
                try:
                    return exit_info(f"http://127.0.0.1:{port}", 10)
                except Exception as e:
                    last = e
                try:
                    real_delay(f"http://127.0.0.1:{port}", E.PROBE_URL, 10)   # HTTPS: sites can open even if the IP service is down
                    return None
                except Exception as e:
                    last = e
            raise last
        self.run(verify, self.verified, lambda e: self.state == CONNECTED and self.sub.setText(tr("st_noinet")))
        self.maybe_check_updates()

    def verified(self, info):
        if self.state != CONNECTED: return
        t = tr("st_exit", ip=info.get("query", ""), country=info.get("country", "")) if info else ""
        self.sub.setText((t + "\n" + self._warn).strip() if getattr(self, "_warn", "") else t)

    def set_proxy(self, on):
        if not system_proxy.supported():
            return
        try:
            if on:
                if self.settings["system_proxy"]:
                    self._proxy_server = f"127.0.0.1:{self.http}"
                    system_proxy.set_proxy(True, self._proxy_server)
            elif self._proxy_server:                # never touch a proxy that another VPN app set
                srv, self._proxy_server = self._proxy_server, None
                system_proxy.disable_if_ours(srv)
        except Exception as e:
            self.log.append(f"system proxy: {e}")

    def disconnect(self):
        self.xray.stop(); self.set_proxy(False); self.set_state(IDLE)

    def reconnect(self):
        self.disconnect(); QTimer.singleShot(300, self.start)

    def fail_connection(self):
        self.log.extend(self.xray.read_all_available())          # poll() may already have drained the queue into self.log
        tail = [l for l in self.log if l and "exited" not in l][-1:] or [""]
        self.disconnect()
        QMessageBox.warning(self, tr("app"), tr("start_fail", err=tail[0][-300:]))

    def poll(self):
        self.log.extend(self.xray.read_all_available()); del self.log[:-300]
        if self.state == CONNECTED and self.btn.isEnabled() and not self.xray.running:
            self.fail_connection()

    # ---------- updates ----------
    def update_urls(self):
        urls = list(self.settings.get("update_urls") or [])
        f = updater.ASSETS / "update_url.txt"
        if f.exists():
            urls += [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip().startswith("http")]
        return urls

    def maybe_check_updates(self):
        if time.time() - self.settings["last_update_check"] > 12 * 3600 and self.update_urls():
            self.check_updates(manual=False)

    def check_updates(self, manual):
        urls = self.update_urls()
        if not urls:
            if manual: QMessageBox.information(self, tr("app"), tr("upd_nourl"))
            return
        px = self.proxy_url()
        def work(p, c):
            return updater.check(LITE_VERSION, urls, updater.load_public_key(), px)
        def done(m):
            self.settings["last_update_check"] = int(time.time()); E.save_settings(self.settings)
            if m:
                self.upd = m; self.upd_lbl.setText(tr("upd_new", v=m["version"])); self.upd_bar.show()
            elif manual:
                QMessageBox.information(self, tr("app"), tr("upd_none"))
        self.run(work, done, (lambda e: QMessageBox.warning(self, tr("app"), tr("upd_fail", err=e))) if manual else (lambda e: self.log.append("update check: " + e)))

    def install_update(self):
        m = self.upd
        if not m: return
        notes = (m.get("notes") or {}).get(lang(), "")
        if QMessageBox.question(self, tr("app"), tr("upd_ask", v=m["version"], notes=notes)) != QMessageBox.Yes:
            return
        app_dir, px = paths.app_dir(), self.proxy_url()
        self.upd_go.setEnabled(False)
        def work(p, c):
            z = updater.download(m, app_dir / "updates", px, progress=lambda pct: p(pct))
            return z, updater.stage(z, app_dir / "updates" / "staging", paths.exe_name())
        def staged(r):
            z, stage_dir = r
            if not updater.apply_supported():
                self.upd_go.setEnabled(True); QMessageBox.information(self, tr("app"), tr("upd_frozen")); return
            updater.launch_apply(app_dir, stage_dir, paths.exe_name(), z)
            self.close()
        self.run(work, staged, lambda e: (self.upd_go.setEnabled(True), QMessageBox.warning(self, tr("app"), tr("upd_fail", err=e))),
                 progress=lambda pct: self.upd_lbl.setText(tr("upd_dl", pct=pct)))

    # ---------- misc ----------
    def toggle_lang(self):
        self.settings["lang"] = "en" if lang() == "fa" else "fa"; E.save_settings(self.settings)
        set_lang(self.settings["lang"]); self.apply_texts(); self.refresh_combo()

    def about(self):
        AboutDialog(self, LITE_VERSION, "NetBridge Lite").exec()

    def show_report(self):
        d = QDialog(self); d.setWindowTitle(tr("report_title")); d.resize(520, 420)
        lay = QVBoxLayout(d)
        box = QPlainTextEdit(); box.setReadOnly(True)
        xv = self.xray.version()
        head = [f"NetBridge Lite {LITE_VERSION} · Xray {'.'.join(map(str, xv)) if xv else '?'} · {platform.platform()}",
                f"servers: {len(self.profiles)} · state: {self.state} · ports: {self.socks}/{self.http}", ""]
        box.setPlainText("\n".join(head + self.log[-120:]))
        lay.addWidget(box)
        row = QHBoxLayout()
        cp = QPushButton(tr("copy")); cp.clicked.connect(lambda: QGuiApplication.clipboard().setText(box.toPlainText()))
        cl = QPushButton(tr("close")); cl.clicked.connect(d.accept)
        row.addWidget(cp); row.addWidget(cl); lay.addLayout(row)
        d.exec()

    def closeEvent(self, e):
        for t in list(self.tasks):
            t.cancel = True
        for t in list(self.tasks):
            t.wait(4000)
        self.xray.stop(); self.set_proxy(False); self.save(); e.accept()
