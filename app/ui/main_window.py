from pathlib import Path
from urllib.parse import quote
from PySide6.QtCore import QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QLabel, QTextEdit, QLineEdit, QMessageBox, QDialog, QFormLayout,
    QDialogButtonBox, QFileDialog, QSplitter, QComboBox, QCheckBox, QInputDialog, QAbstractItemView, QScrollArea, QFrame, QApplication
)
import json
import html
import time
from app.core.bypass import PRESETS, CIPHER_SUITES, FM_STANDARD, FM_PATTNG
from app.core import bypass as bypass_mod, presets as presets_mod, worker_exit
from app.ui import theme
from app.core import aether as aether_mod, cf_deploy, gscript as gscript_mod, sources as sources_mod
from app.storage.profiles import load_profiles, save_profiles
from app.utils.parser import parse_many
from app.utils.validator import validate_profile
from app.core.config_generator import write_config, profile_key as _pkey
from app.core.xray_manager import XrayManager
from app.core import system_proxy
from app.utils.subscription import fetch_subscription
from app.utils.latency import real_delay
from app.storage.settings import load_settings, save_settings
from app.core.delay_all import test_many
from app.core.autobypass import auto_run, apply_variant, is_tls, label as variant_label
from app.utils.latency import exit_info
from app.utils.leakcheck import full_report
from app.core import browser, ipscan, ports
from app.core.routing import SERVICE_PRESETS, SDNS_PRESETS, parse_dns_server, split_entries
from app.utils import dnscheck
from app.ui.scan_dialog import ScanDialog
from app.ui.exit_dialog import ExitDialog
from app.ui.tls_worker import TlsWorker
from app.core import tlsup
from app.utils.certhash import fetch_pin
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

MODES = [("manual", "Manual - the profile I select"),
         ("best", "Best now - test all, connect to the fastest"),
         ("auto", "Auto balancer - always uses the fastest (live)")]
AUTO_MAX = 30

from app.version import VERSION
from app.ui.icon import app_icon, logo_pixmap
from app.ui.about_dialog import AboutDialog
from app.ui.help_dialog import HelpDialog
from app.ui.gscript_dialog import GScriptDialog
from app.ui.tg_dialog import TgProxyDialog
from app.ui import tor_bridges_dialog
from app.core import feeder as feeder_mod


class ImportDialog(QDialog):
    def __init__(self, parent=None, title="Import profiles"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 380)
        layout = QVBoxLayout(self)
        self.name = QLineEdit()
        self.text = QTextEdit()
        self.text.setPlaceholderText("Paste VLESS / VMess / Trojan / Shadowsocks / Hysteria2 links, a subscription, or a sing-box JSON here...")
        form = QFormLayout()
        form.addRow("Name for single profile:", self.name)
        layout.addLayout(form)
        layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    def value(self):
        return self.name.text().strip(), self.text.toPlainText().strip()


class BypassDialog(QDialog):
    """Per-profile Fragment + unsafe fingerprint + cipherSuites + clean IP."""
    def __init__(self, profile, parent=None, profiles=()):
        super().__init__(parent)
        self.setWindowTitle("Bypass settings")
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.mode = QComboBox()
        for k, v in PRESETS.items(): self.mode.addItem(v, k)
        self.mode.setCurrentIndex(max(0, self.mode.findData(profile.get("bypass") or "off")))
        self.ip = QLineEdit(profile.get("address_override", ""))
        self.ip.setPlaceholderText("Clean Cloudflare IP (optional) - SNI/Host stay unchanged")
        self.ech = QLineEdit(profile.get("ech", ""))
        self.ech.setPlaceholderText("ECH config list, e.g. cloudflare-ech.com+https://1.1.1.1/dns-query  (empty = off)")
        self.wexit = QLineEdit(profile.get("worker_exit", ""))
        self.wexit.setPlaceholderText("Worker exit (optional): proxyip=1.2.3.4:443  or  socks5=user:pass@host:1080  or  http=host:8080")
        self.chain = QComboBox(); self.chain.addItem("(none)", "")
        for q in profiles:
            if _pkey(q) != _pkey(profile):
                self.chain.addItem(f"{q.get('name','?')}  [{q.get('server')}]", _pkey(q))
        self.chain.setCurrentIndex(max(0, self.chain.findData(profile.get("chain_key", ""))))
        form.addRow("Mode:", self.mode)
        form.addRow("Clean IP:", self.ip)
        form.addRow("ECH:", self.ech)
        form.addRow("Worker exit:", self.wexit)
        form.addRow("Chain via (first hop):", self.chain)
        lay.addLayout(form)
        lay.addWidget(QLabel("finalMask (JSON) - used in Custom mode:"))
        self.fm = QTextEdit(); self.fm.setPlainText(profile.get("fm", "")); lay.addWidget(self.fm)
        lay.addWidget(QLabel("cipherSuites (colon-separated, no spaces) - used in Custom mode:"))
        self.cs = QTextEdit(); self.cs.setPlainText(profile.get("cs", "")); lay.addWidget(self.cs)
        row = QHBoxLayout()
        # the values come from the preset files (updatable); the compiled-in ones are only the fallback
        def preset_value(name, key, fallback):
            p = bypass_mod.get_preset(name) or {}
            return p.get(key) or fallback
        for txt, name, fb in [("Fill standard fragment", "standard", FM_STANDARD), ("Fill PattNG fragment", "pattng", FM_PATTNG)]:
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, n=name, f=fb: self.fm.setPlainText(json.dumps(preset_value(n, "finalmask", f))))
            row.addWidget(b)
        b = QPushButton("Fill cipherSuites")
        b.clicked.connect(lambda: self.cs.setPlainText(preset_value("pattng", "cipherSuites", CIPHER_SUITES))); row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(QLabel("Needs a TLS config. Result depends on operator/city; no guarantee."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)

    def apply(self, p):
        wexit = worker_exit.normalize(self.wexit.text())       # raises ValueError BEFORE anything is changed
        p["bypass"] = self.mode.currentData()
        for k, v in [("address_override", self.ip.text().strip()),
                     ("worker_exit", wexit),
                     ("ech", self.ech.text().strip()),
                     ("chain_key", self.chain.currentData() or ""),
                     ("fm", self.fm.toPlainText().strip()),
                     ("cs", self.cs.toPlainText().strip().replace("\n", "").replace(" ", ""))]:
            if v: p[k] = v
            else: p.pop(k, None)
        if p["fm"] if "fm" in p else False:
            json.loads(p["fm"])   # raises on invalid JSON

def profile_key(p):
    return "|".join(str(p.get(k, "")) for k in ("type", "server", "port", "uuid", "password"))


class IpWorker(QThread):
    done = Signal(str)
    def __init__(self, proxy, parent=None):
        super().__init__(parent); self.proxy = proxy
    def run(self):
        try:
            self.done.emit(full_report(self.proxy))
        except Exception as e:
            self.done.emit(f"Exit check failed: {e}")


class PresetWorker(QThread):
    """Downloads the bypass values file (see app/core/presets.py). Only the network part runs here;
    the result is applied in the window (UI thread), so the menus never see a half-changed list."""
    done = Signal(object)                      # ("updated"|"current", doc, errors)  or  an error text
    def __init__(self, current_version, proxy, parent=None):
        super().__init__(parent); self.current, self.proxy = current_version, proxy
    def run(self):
        try:
            self.done.emit(presets_mod.update(self.current, proxy=self.proxy))
        except Exception as e:
            self.done.emit(f"{e}")


class SourceWorker(QThread):
    """Downloads a public config list from its mirrors (network, so off the UI thread)."""
    done = Signal(object)                      # (source, profiles, mirror, errors) or an error text
    def __init__(self, source, proxy, parent=None):
        super().__init__(parent); self.source, self.proxy = source, proxy
    def run(self):
        try:
            profiles, mirror, errors = sources_mod.fetch_source(self.source, fetch_subscription, proxy=self.proxy)
            self.done.emit((self.source, profiles, mirror, errors))
        except Exception as e:
            self.done.emit(str(e))


class DeployWorker(QThread):
    """Creates the personal Worker on the user's Cloudflare account (network calls, so off the UI thread)."""
    status = Signal(str)
    done = Signal(object)                      # a profile dict or an error text
    def __init__(self, token, parent=None):
        super().__init__(parent); self.token = token
    def run(self):
        try:
            self.done.emit(cf_deploy.deploy(self.token, progress=self.status.emit))
        except Exception as e:
            self.done.emit(str(e))


WARP_CHOICES = [("MASQUE IPv4 (default)", "masque", "4"), ("MASQUE IPv6", "masque", "6"),
                ("WireGuard IPv4", "wg", "4"), ("WireGuard IPv6", "wg", "6"), ("WARP-in-WARP (gool)", "gool", "4")]


PSIPHON_REGIONS = [("Auto", ""), ("Germany", "DE"), ("Netherlands", "NL"), ("United States", "US"), ("United Kingdom", "GB"),
                   ("France", "FR"), ("Canada", "CA"), ("Sweden", "SE"), ("Japan", "JP"), ("Singapore", "SG")]


class AetherWorker(QThread):
    """Installs the Aether core when it is missing, then starts it and waits for its SOCKS5 port.
    Runs off the UI thread: the first start scans for a gateway and can take a minute."""
    status = Signal(str)
    done = Signal(object)                      # the port (int) or an error text
    def __init__(self, manager, proxy, kind="warp", parent=None, protocol="masque", family="4", region=None):
        super().__init__(parent); self.mgr, self.proxy, self.kind, self._stop = manager, proxy, kind, False
        self.protocol, self.family, self.region = protocol, family, region
    def stop(self):
        self._stop = True
    def run(self):
        try:
            if not aether_mod.installed():
                path, tag = aether_mod.download_core(proxy=self.proxy, progress=self.status.emit)
                self.status.emit(f"Aether {tag} installed: {path}")
            self.mgr.proxy_env = self.proxy
            port = self.mgr.start(cancelled=lambda: self._stop, progress=self.status.emit, kind=self.kind,
                                 protocol=self.protocol, family=self.family, region=self.region)
            self.done.emit(port)
        except Exception as e:
            self.done.emit(str(e))


class PinWorker(QThread):
    """Fetches the certificate hash of self-signed (insecure) servers."""
    result = Signal(object, str, str)          # profile, hash or "", error or ""
    def __init__(self, profiles, parent=None):
        super().__init__(parent); self.profiles = profiles
    def run(self):
        def job(p):
            try: self.result.emit(p, fetch_pin(p), "")
            except Exception as e: self.result.emit(p, "", f"{type(e).__name__}: {e}"[:120])
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(job, self.profiles))


class RoutingDialog(QDialog):
    """Sites that skip the tunnel (use your real IP) or must always use it."""
    def __init__(self, r, profiles=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Routing - skip the tunnel for some sites")
        outer = QVBoxLayout(self)                      # the form scrolls, the OK / Cancel buttons stay visible on small screens
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget(); scroll.setWidget(body); outer.addWidget(scroll)
        lay = QVBoxLayout(body)
        scr = QApplication.primaryScreen()
        self.resize(680, min(760, int(scr.availableGeometry().height() * 0.9)) if scr else 700)
        self.iran = QCheckBox("Iranian sites go direct (.ir + Iranian site list) - they reject foreign IPs")
        self.iran.setChecked(bool(r.get("iran")))
        self.lan = QCheckBox("Local network / private IPs go direct")
        self.lan.setChecked(bool(r.get("lan", True)))
        self.ads = QCheckBox("Block ads (geosite:category-ads-all)")
        self.ads.setChecked(bool(r.get("ads")))
        for c in (self.iran, self.lan, self.ads): lay.addWidget(c)
        lay.addWidget(QLabel("<b>Sites that reject Iranian IPs</b> - send them out through this server (pick one that is NOT Cloudflare/Workers):"))
        self.pin_profile = QComboBox(); self.pin_profile.addItem("(none)", "")
        for p in profiles: self.pin_profile.addItem(f"{p.get('name','?')}  [{p.get('server')}]", profile_key(p))
        self.pin_profile.setCurrentIndex(max(0, self.pin_profile.findData(r.get("pin_profile", ""))))
        lay.addWidget(self.pin_profile)
        self.pin_sites = QTextEdit(); self.pin_sites.setPlainText("\n".join(r.get("pin_sites", [])))
        self.pin_sites.setPlaceholderText("site-that-blocks-iran.com")
        self.pin_sites.setMaximumHeight(90); lay.addWidget(self.pin_sites)
        prow = QHBoxLayout()
        self.preset = QComboBox()
        for name in SERVICE_PRESETS: self.preset.addItem(name)
        pb = QPushButton("Add this service's sites"); pb.clicked.connect(self.add_preset)
        prow.addWidget(self.preset); prow.addWidget(pb); lay.addLayout(prow)
        lay.addWidget(QLabel("<b>Sanction DNS (Smart DNS)</b> - for sanctioned sites that are NOT filtered: these sites skip the tunnel "
                             "and are resolved by this DNS server (it returns a foreign proxy address). Leave empty to disable."))
        drow = QHBoxLayout()
        self.sdns_server = QLineEdit(r.get("sdns_server", "")); self.sdns_server.setPlaceholderText("DNS server IP, e.g. 178.22.122.100")
        self.sdns_preset = QComboBox(); self.sdns_preset.addItem("Presets...", "")
        for n, ip in SDNS_PRESETS.items(): self.sdns_preset.addItem(n, ip)
        self.sdns_preset.currentIndexChanged.connect(lambda _: self.sdns_server.setText(self.sdns_preset.currentData()) if self.sdns_preset.currentData() else None)
        tb = QPushButton("Test DNS"); tb.clicked.connect(self.test_sdns)
        drow.addWidget(self.sdns_server); drow.addWidget(self.sdns_preset); drow.addWidget(tb); lay.addLayout(drow)
        self.sdns_sites = QTextEdit(); self.sdns_sites.setPlainText("\n".join(r.get("sdns_sites", [])))
        self.sdns_sites.setPlaceholderText("sanctioned-site.com  (one per line)")
        self.sdns_sites.setMaximumHeight(80); lay.addWidget(self.sdns_sites)
        lay.addWidget(QLabel("Skip the tunnel for these (one per line: site, URL, IP, CIDR, geosite:xxx, geoip:xx):"))
        self.direct = QTextEdit(); self.direct.setPlainText("\n".join(r.get("direct", [])))
        self.direct.setPlaceholderText("snapp.ir\nhttps://www.example.com/page\n185.10.0.0/16")
        lay.addWidget(self.direct)
        lay.addWidget(QLabel("Always use the tunnel for these (wins over the skip list):"))
        self.proxy = QTextEdit(); self.proxy.setPlainText("\n".join(r.get("proxy", [])))
        self.proxy.setPlaceholderText("some-site.ir")
        lay.addWidget(self.proxy)
        lay.addWidget(QLabel("A site name also covers its subdomains. Applies on the next connect (auto-reconnects if connected)."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); outer.addWidget(bb)

    def add_preset(self):
        have = {x.strip() for x in self.pin_sites.toPlainText().splitlines() if x.strip()}
        new = [d for d in SERVICE_PRESETS[self.preset.currentText()] if d not in have]
        if new:
            cur = self.pin_sites.toPlainText().rstrip("\n")
            self.pin_sites.setPlainText((cur + "\n" if cur else "") + "\n".join(new))

    def test_sdns(self):
        try:
            ip, port = parse_dns_server(self.sdns_server.text())
        except ValueError:
            QMessageBox.warning(self, "Sanction DNS", "Enter a valid DNS server IP first."); return
        doms, _ = split_entries([x for x in self.sdns_sites.toPlainText().splitlines()])
        name = doms[0].split(":", 1)[1] if doms else "github.com"
        ok, msg = dnscheck.describe(name, ip, port)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Sanction DNS test", msg)

    def accept(self):
        if self.sdns_server.text().strip():
            try: parse_dns_server(self.sdns_server.text())
            except ValueError:
                QMessageBox.warning(self, "Sanction DNS", "The DNS server must be an IP address (optionally ip:port)."); return
        super().accept()

    def value(self):
        lines = lambda w: [x.strip() for x in w.toPlainText().splitlines() if x.strip()]
        return {"sdns_server": self.sdns_server.text().strip(), "sdns_sites": lines(self.sdns_sites),
                "iran": self.iran.isChecked(), "lan": self.lan.isChecked(), "ads": self.ads.isChecked(),
                "direct": lines(self.direct), "proxy": lines(self.proxy),
                "pin_sites": lines(self.pin_sites), "pin_profile": self.pin_profile.currentData() or ""}


class DelayWorker(QThread):
    result = Signal(object, int)          # profile dict, ms (-1 = failed)
    def __init__(self, exe, profiles, parent=None):
        super().__init__(parent)
        self.exe, self.profiles, self._stop = exe, profiles, False
    def stop(self): self._stop = True
    def run(self):
        test_many(self.exe, [(p, p) for p in self.profiles],
                  lambda k, ms: self.result.emit(k, ms), cancelled=lambda: self._stop)


class AutoWorker(QThread):
    """Finds, per profile, the bypass method that really works here (see app/core/autobypass.py)."""
    win = Signal(object, object, int)          # profile dict, variant dict, ms
    status = Signal(str)
    progress = Signal(int, int)
    summary = Signal(object)
    def __init__(self, exe, profiles, parent=None):
        super().__init__(parent)
        self.exe, self.profiles, self._stop = exe, profiles, False
    def stop(self): self._stop = True
    def run(self):
        try:
            res = auto_run(self.exe, self.profiles, lambda p, v, ms: self.win.emit(p, v, ms),
                           on_status=self.status.emit, on_progress=self.progress.emit,
                           cancelled=lambda: self._stop)
        except Exception as e:
            self.status.emit(f"Auto bypass error: {e}")
            res = {"tls": 0, "plain": 0, "insecure_fallback": False}
        self.summary.emit(res)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"NetBridge v{VERSION}")
        self.setWindowIcon(app_icon())
        tm = self.menuBar().addMenu("&Tools")
        self.free_auto_act = tm.addAction("Refresh free configs once a day (on start)")
        self.free_auto_act.setCheckable(True)
        tm.addAction("Telegram proxy (my Cloudflare Worker) ...", lambda: self.telegram_proxy())
        hm = self.menuBar().addMenu("&Help")
        hm.addAction("&Guide / راهنما", lambda: HelpDialog(self).exec())
        hm.addAction("&About NetBridge", lambda: AboutDialog(self).exec())
        self.resize(1150, 700)
        self.profiles = load_profiles()
        self.settings = load_settings()
        self.free_auto_act.setChecked(bool(self.settings.get("free_auto")))
        self.free_auto_act.toggled.connect(self._set_free_auto)
        QTimer.singleShot(4000, self._free_auto_check)
        self.view = []; self.worker = None; self.auto_worker = None; self._auto_wins = []; self.pending_best = False; self._done = 0; self._total = 0
        self.xray = XrayManager()
        self.feeder = XrayManager()               # hidden second Xray: keeps the working route for Aether (see core/feeder.py)
        self.aether = aether_mod.AetherManager()
        self.aether.bridges, self.aether.bridges_now = tor_bridges_dialog.load()
        self.gscript = None                                      # running Google Script relay (local SOCKS5 port) or None
        self.socks_port, self.http_port = ports.SOCKS, ports.HTTP
        self.active_config = Path("configs/active.json")
        self.check_config_path = Path("configs/check.json")      # validation writes here, never over the live config
        self._proxy_server = None                               # the Windows proxy value WE set
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll)

        root = QWidget(); self.setCentralWidget(root)
        main = QHBoxLayout(root)
        splitter = QSplitter()

        left = QWidget(); ll = QVBoxLayout(left)
        head = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(logo_pixmap("mark.png", 38))
        brand = QLabel(theme.BRAND_HTML); brand.setObjectName("brand")
        head.addWidget(logo); head.addWidget(brand); head.addStretch(1)
        ll.addLayout(head)
        gr = QHBoxLayout()
        self.group_combo = QComboBox(); self.group_combo.currentIndexChanged.connect(self.group_changed)
        self.sort_delay = QCheckBox("Sort by delay"); self.sort_delay.setChecked(True)
        self.sort_delay.toggled.connect(lambda _: self.refresh())
        gr.addWidget(QLabel("Group:")); gr.addWidget(self.group_combo, 1); gr.addWidget(self.sort_delay)
        ll.addLayout(gr)
        self.list = QListWidget(); self.refresh()
        ll.addWidget(self.list)
        r1 = QHBoxLayout()
        for txt, fn in [("Add", self.add), ("Subscription", self.subscription),
                        ("Import file", self.import_file), ("Delete", self.delete)]:
            b = QPushButton(txt); b.clicked.connect(fn); r1.addWidget(b)
            if txt == "Delete": b.setObjectName("danger")
        ll.addLayout(r1)
        r2 = QHBoxLayout()
        for txt, fn in [("Edit", self.edit), ("Bypass", self.bypass),
                        ("Export", self.export), ("Test", self.test)]:
            b = QPushButton(txt); b.clicked.connect(fn); r2.addWidget(b)
        ll.addLayout(r2)
        r_auto = QHBoxLayout()
        self.auto_btn = QPushButton("AUTO: find the working method + connect")
        self.auto_btn.setMinimumHeight(44); self.auto_btn.setObjectName("primary"); self.auto_btn.clicked.connect(self.auto_bypass)
        r_auto.addWidget(self.auto_btn)
        r3 = QHBoxLayout()
        b = QPushButton("Bypass all TLS"); b.clicked.connect(self.bypass_all); r3.addWidget(b)
        self.test_btn = QPushButton("Test all (delay)"); self.test_btn.clicked.connect(lambda: self.test_all())
        r3.addWidget(self.test_btn)
        b = QPushButton("Skip sites (Routing)"); b.clicked.connect(self.routing); r3.addWidget(b)
        r4 = QHBoxLayout()
        self.pin_btn = QPushButton("Pin certs (self-signed servers)"); self.pin_btn.clicked.connect(lambda: self.pin_certs())
        r4.addWidget(self.pin_btn)
        self.preset_btn = QPushButton("Update bypass values (finalMask / ciphers)")
        self.preset_btn.clicked.connect(self.update_presets); r4.addWidget(self.preset_btn)
        r5 = QHBoxLayout()
        b = QPushButton("Select all"); b.clicked.connect(lambda: self.list.selectAll()); r5.addWidget(b)
        b = QPushButton("Select failed (x)"); b.clicked.connect(self.select_failed); r5.addWidget(b)
        self.tls_btn = QPushButton("Convert non-TLS to TLS (try)"); self.tls_btn.clicked.connect(self.convert_tls); r5.addWidget(self.tls_btn)
        r6 = QHBoxLayout()
        b = QPushButton("Select non-TLS (plain) profiles"); b.clicked.connect(self.select_plain); r6.addWidget(b)
        self.warp_btn = QPushButton("WARP (Aether core)"); self.warp_btn.setObjectName("primary")
        self.warp_btn.clicked.connect(lambda: self.warp_aether("warp")); r6.addWidget(self.warp_btn)
        self.warp_mode = QComboBox()
        for label, proto, fam in WARP_CHOICES:
            self.warp_mode.addItem(label, (proto, fam))
        self.warp_mode.setToolTip("Which WARP transport and IP version Aether uses. If the first one does not connect, try another.")
        r6.addWidget(self.warp_mode)
        self.deploy_btn = QPushButton("Deploy my Worker (Cloudflare)"); self.deploy_btn.setObjectName("primary")
        self.deploy_btn.clicked.connect(self.deploy_worker); r6.addWidget(self.deploy_btn)
        r7 = QHBoxLayout()
        self.gs_btn = QPushButton("Google Script"); self.gs_btn.setObjectName("primary"); self.gs_btn.clicked.connect(self.google_script)
        r7.addWidget(self.gs_btn)
        self.tor_btn = QPushButton("Tor via WARP"); self.tor_btn.clicked.connect(lambda: self.warp_aether("tor")); r7.addWidget(self.tor_btn)
        self.toronly_btn = QPushButton("Tor alone (bridges)"); self.toronly_btn.clicked.connect(lambda: self.warp_aether("tor-only")); r7.addWidget(self.toronly_btn)
        self.torbr_btn = QPushButton("Tor bridges..."); self.torbr_btn.clicked.connect(self.tor_bridges); r7.addWidget(self.torbr_btn)
        self.free_btn = QPushButton("Get free configs"); self.free_btn.setObjectName("primary"); self.free_btn.clicked.connect(self.get_free_configs)
        r7.addWidget(self.free_btn)
        b = QPushButton("Help / راهنما"); b.clicked.connect(lambda: HelpDialog(self).exec()); r7.addWidget(b)
        r8 = QHBoxLayout()
        self.psi_btn = QPushButton("Psiphon via WARP"); self.psi_btn.clicked.connect(lambda: self.warp_aether("psiphon")); r8.addWidget(self.psi_btn)
        self.psionly_btn = QPushButton("Psiphon alone"); self.psionly_btn.clicked.connect(lambda: self.warp_aether("psiphon-only")); r8.addWidget(self.psionly_btn)
        self.psi_region = QComboBox()
        for label, cc in PSIPHON_REGIONS:
            self.psi_region.addItem(label, cc)
        self.psi_region.setToolTip("Exit country for Psiphon (Auto = Psiphon decides).")
        r8.addWidget(self.psi_region)
        self.tg_btn = QPushButton("Telegram proxy"); self.tg_btn.clicked.connect(self.telegram_proxy); r8.addWidget(self.tg_btn)
        self.via_chk = QCheckBox("Aether through my current connection")
        self.via_chk.setToolTip("When Psiphon / Tor / WARP cannot start on their own, connect to a profile that works first, tick this and press the Aether button: "
                                "Aether then dials through that connection.")
        r8.addWidget(self.via_chk)
        ll.addLayout(r_auto); ll.addLayout(r3); ll.addLayout(r4); ll.addLayout(r5); ll.addLayout(r6); ll.addLayout(r7); ll.addLayout(r8)
        splitter.addWidget(left)

        right = QWidget(); rl = QVBoxLayout(right)
        self.info = QLabel("Select a profile")
        rl.addWidget(self.info)
        self.mode = QComboBox()
        for k, v in MODES: self.mode.addItem(v, k)
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.settings.get("mode", "manual"))))
        self.mode.currentIndexChanged.connect(self.mode_changed)
        rl.addWidget(QLabel("Connection mode:")); rl.addWidget(self.mode)
        self.connect_btn = QPushButton("CONNECT")
        self.connect_btn.setMinimumHeight(52); self.connect_btn.clicked.connect(self.toggle); self._style_connect(False)
        rl.addWidget(self.connect_btn)
        self.sys_proxy = QCheckBox("Set Windows system proxy when connecting")
        self.sys_proxy.setChecked(system_proxy.supported())
        self.sys_proxy.setEnabled(system_proxy.supported())
        rl.addWidget(self.sys_proxy)
        self.ip_btn = QPushButton("Full location check: IP, geo databases, leaks (connected)")
        self.ip_btn.clicked.connect(self.check_ip); rl.addWidget(self.ip_btn)
        self.browser_btn = QPushButton("Open clean browser (proxied, no WebRTC / language leak)")
        self.browser_btn.clicked.connect(self.open_browser); rl.addWidget(self.browser_btn)
        self.scan_btn = QPushButton("Clean IP scanner (Cloudflare) for the selected profile")
        self.scan_btn.clicked.connect(self.scan_ips); rl.addWidget(self.scan_btn)
        self.exit_btn = QPushButton("Exit scan: find profiles that are NOT Cloudflare (for Gemini, etc.)")
        self.exit_btn.clicked.connect(self.exit_scan); rl.addWidget(self.exit_btn)
        self.delay_btn = QPushButton("Real delay test (connected)")
        self.delay_btn.clicked.connect(self.delay_test); rl.addWidget(self.delay_btn)
        self.status = QLabel("Status: Disconnected")
        rl.addWidget(self.status)
        rl.addWidget(QLabel("Logs"))
        self.log = QTextEdit(); self.log.setReadOnly(True); rl.addWidget(self.log)
        splitter.addWidget(right)
        splitter.setSizes([360, 790])
        main.addWidget(splitter)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)   # Ctrl/Shift-click, Ctrl+A
        self.list.currentRowChanged.connect(self.select)
        v = self.xray.version()
        if v is None:
            self.log.append("Xray core not found. Run setup.bat (or: python get_xray.py).")
        else:
            self.log.append("Xray core: " + ".".join(map(str, v)))
            if v < (26, 7, 0):
                self.log.append("WARNING: this Xray is older than 26.7 - the 'Video/PattNG exact' mode will be rejected. Run: python get_xray.py (v26.7.28)")

    def refresh(self, keep=None):
        keep = keep if keep is not None else self.selected()
        groups = sorted({p.get("group", "") for p in self.profiles if p.get("group")})
        self.group_combo.blockSignals(True)
        self.group_combo.clear(); self.group_combo.addItem("All", "")
        for g in groups: self.group_combo.addItem(g, g)
        self.group_combo.setCurrentIndex(max(0, self.group_combo.findData(self.settings.get("group", ""))))
        self.group_combo.blockSignals(False)
        g = self.group_combo.currentData() or ""
        idxs = [i for i, p in enumerate(self.profiles) if not g or p.get("group", "") == g]
        if self.sort_delay.isChecked():
            def key(i):
                d = self.profiles[i].get("delay")
                return (1, 0) if d is None else ((2, 0) if d < 0 else (0, d))
            idxs.sort(key=key)
        self.view = idxs
        self.list.blockSignals(True)
        self.list.clear()
        row = -1
        for n, i in enumerate(idxs):
            p = self.profiles[i]
            d = p.get("delay")
            tag = "" if d is None else ("   x" if d < 0 else f"   {d} ms")
            self.list.addItem(f"{p.get('name','Unnamed')}  [{p.get('type','?').upper()}]{tag}")
            if p is keep: row = n
        self.list.setCurrentRow(row)
        self.list.blockSignals(False)

    def group_changed(self, _):
        self.settings["group"] = self.group_combo.currentData() or ""
        save_settings(self.settings); self.refresh(keep=None)

    def mode_changed(self, _):
        self.settings["mode"] = self.mode.currentData()
        save_settings(self.settings)

    def _cur_index(self):
        r = self.list.currentRow()
        return self.view[r] if 0 <= r < len(self.view) else -1

    def selected(self):
        i = self._cur_index()
        return self.profiles[i] if i >= 0 else None

    def select(self, _):
        p = self.selected()
        if not p:
            return
        self.info.setText(
            f"<h3>{html.escape(str(p.get('name')))}</h3>"
            f"Protocol: {html.escape(str(p.get('type')))}<br>"
            f"Server: {html.escape(str(p.get('server')))}:{html.escape(str(p.get('port')))}<br>"
            f"Network: {html.escape(str(p.get('network','-')))} &nbsp; Security: {html.escape(str(p.get('security','-')))}<br>"
            f"Bypass: {html.escape(str(p.get('bypass','off')))}"
            + (f" &nbsp; Delay: {p['delay']} ms" if p.get('delay', -1) >= 0 else "")
            + (f" &nbsp; Clean IP: {html.escape(str(p['address_override']))}" if p.get('address_override') else "")
        )

    def add(self):
        d = ImportDialog(self)
        if d.exec() != QDialog.Accepted: return
        name, raw = d.value()
        profiles, errors = parse_many(raw)
        if not profiles:
            QMessageBox.critical(self, "Import error", "No valid profiles found.")
            return
        profiles = self._filter_tls(profiles)
        if len(profiles) == 1 and name:
            profiles[0]["name"] = name
        self._report(*self._add_profiles(profiles), errors)

    def _add_profiles(self, profiles, group=None):
        """Adds new profiles; skips invalid ones and duplicates (same server/port/credentials)."""
        key = lambda x: (x.get("type"), x.get("server"), x.get("port"), x.get("uuid"), x.get("password"))
        seen = {key(x) for x in self.profiles}
        added = invalid = dup = 0
        reasons = {}
        for p in profiles:
            err = validate_profile(p)
            if err:
                invalid += 1
                for e in err: reasons[e] = reasons.get(e, 0) + 1
                continue
            if key(p) in seen:
                dup += 1; continue
            seen.add(key(p))
            if group: p["group"] = group
            self.profiles.append(p); added += 1
        save_profiles(self.profiles); self.refresh()
        return added, invalid, dup, reasons

    def _report(self, added, invalid, dup, reasons, errors=()):
        msg = f"Imported {added} new profile(s)"
        if dup: msg += f", {dup} duplicate(s) skipped"
        if invalid: msg += f", {invalid} invalid skipped"
        if errors: msg += f", {len(errors)} not understood"
        self.log.append(msg + ".")
        for r, n in sorted(reasons.items(), key=lambda x: -x[1])[:5]:
            self.log.append(f"   skipped: {r} x{n}")
        self.pin_certs()

    def _filter_tls(self, profiles):
        """Plain (no TLS) profiles: keep them (default) so 'Convert non-TLS to TLS' can try, or skip them."""
        non = [p for p in profiles if p.get("security") not in ("tls", "reality")]
        if not non: return profiles
        box = QMessageBox(self); box.setWindowTitle("Non-TLS profiles")
        box.setText(f"{len(non)} of {len(profiles)} profiles have no TLS (plain WebSocket/TCP).\n"
                    "The bypass method does not work on them, but 'Convert non-TLS to TLS (try)' can upgrade the ones whose server offers TLS.")
        keep = box.addButton("Keep them", QMessageBox.AcceptRole); skip = box.addButton("Skip them", QMessageBox.DestructiveRole)
        box.setDefaultButton(keep); box.exec()
        return [p for p in profiles if p not in non] if box.clickedButton() is skip else profiles

    def bypass_all(self):
        tls = [p for p in self.profiles if p.get("security") == "tls" and p.get("type") != "hysteria2"]
        if not tls:
            QMessageBox.information(self, "NetBridge", "No TLS profiles."); return
        names = list(PRESETS.values())
        choice, ok = QInputDialog.getItem(self, "Bypass all TLS profiles",
                                          f"Apply to {len(tls)} TLS profiles:", names, 2, False)
        if not ok: return
        mode = [k for k, v in PRESETS.items() if v == choice][0]
        if mode == "custom": return
        for p in tls: p["bypass"] = mode
        save_profiles(self.profiles); self.refresh()
        self.log.append(f"Bypass '{mode}' applied to {len(tls)} TLS profiles.")

    def subscription(self):
        url, ok = QInputDialog.getText(self, "Subscription", "Subscription URL:")
        if not ok or not url.strip(): return
        proxy = self.proxy_url() if self.xray.running else None
        try:
            profiles, errors = fetch_subscription(url, proxy=proxy)
        except Exception as e:
            QMessageBox.critical(self, "Subscription error", str(e)); return
        grp = urlparse(url.strip()).hostname or "subscription"
        self._report(*self._add_profiles(profiles, grp), errors)

    def delay_test(self):
        if not self.xray.running:
            QMessageBox.information(self, "NetBridge", "Connect first."); return
        try:
            self.log.append(f"Real delay: {real_delay(self.proxy_url())} ms")
        except Exception as e:
            self.log.append(f"Real delay FAILED: {e}")
        try:
            from app.utils.latency import check_sites
            for label, ok, ms, detail in check_sites(self.proxy_url()):
                self.log.append(f"  {label}: " + (f"OK ({ms} ms)" if ok else f"FAILED ({detail})"))
        except Exception as e:
            self.log.append(f"Site check error: {e}")

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "Text files (*.txt *.conf *.json);;All files (*.*)")
        if not path: return
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        profiles, errors = parse_many(raw)
        profiles = self._filter_tls(profiles)
        self._report(*self._add_profiles(profiles, Path(path).stem), errors)

    def edit(self):
        p = self.selected()
        if not p: return
        d = ImportDialog(self, "Edit profile")
        d.name.setText(p.get("name",""))
        d.text.setPlainText(self.to_uri(p))
        if d.exec() != QDialog.Accepted: return
        profiles, _ = parse_many(d.value()[1])
        if not profiles:
            QMessageBox.critical(self, "Edit error", "Invalid profile.")
            return
        p2 = profiles[0]
        if d.value()[0]: p2["name"] = d.value()[0]
        for k in ("group", "bypass", "address_override", "delay", "ech", "chain_key", "early_data", "early_data_header", "worker_exit"):
            if k in p and k not in p2: p2[k] = p[k]
        if (p.get("server"), p.get("port")) == (p2.get("server"), p2.get("port")):   # same server: its pinned certificate is still valid
            for k in ("insecure", "pcs"):
                if k in p and k not in p2: p2[k] = p[k]
        self.profiles[self._cur_index()] = p2
        save_profiles(self.profiles); self.refresh(keep=p2)

    def bypass(self):
        p = self.selected()
        if not p: return
        d = BypassDialog(p, self, self.profiles)
        if d.exec() != QDialog.Accepted: return
        try:
            d.apply(p)
            write_config(p, self.check_config_path, all_profiles=self.profiles)   # validates the combination
        except Exception as e:
            QMessageBox.critical(self, "Bypass error", str(e)); return
        save_profiles(self.profiles); self.select(0)
        self.log.append(f"Bypass mode for '{p.get('name')}': {p.get('bypass','off')}")

    def selected_indices(self):
        rows = sorted({self.list.row(it) for it in self.list.selectedItems()})
        return [self.view[r] for r in rows if 0 <= r < len(self.view)]

    def select_failed(self):
        self.list.clearSelection()
        for n, i in enumerate(self.view):
            if self.profiles[i].get("delay", 0) == -1:
                self.list.item(n).setSelected(True)
        k = len(self.list.selectedItems())
        self.log.append(f"{k} failed profile(s) selected. Press Delete to remove them." if k else
                        "No failed profiles (run 'Test all (delay)' first).")

    def select_plain(self):
        self.list.clearSelection()
        for n, i in enumerate(self.view):
            if tlsup.is_plain(self.profiles[i]):
                self.list.item(n).setSelected(True)
        k = len(self.list.selectedItems())
        self.log.append(f"{k} non-TLS profile(s) selected. Press Delete to remove them." if k else "No non-TLS profiles in this group.")

    def delete(self):
        idx = self.selected_indices() or ([self._cur_index()] if self._cur_index() >= 0 else [])
        if not idx: return
        if len(idx) > 1 and QMessageBox.question(self, "Delete", f"Delete {len(idx)} selected profiles?",
                                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        for i in sorted(set(idx), reverse=True):
            self.profiles.pop(i)
        save_profiles(self.profiles)
        self.view = []                       # stale indices must not be used by refresh()
        self.refresh(keep=False)
        self.log.append(f"Deleted {len(idx)} profile(s).")

    # ---- plain -> TLS
    def convert_tls(self):
        if self.xray.version() is None:
            QMessageBox.warning(self, "NetBridge", "Xray core not found."); return
        if getattr(self, "tlsw", None) and self.tlsw.isRunning():
            self.tlsw.stop(); self.log.append("Stopping TLS conversion ..."); return
        pool = [self.profiles[i] for i in self.selected_indices()] or [self.profiles[i] for i in self.view]
        todo = [p for p in pool if tlsup.is_plain(p)]
        if not todo:
            QMessageBox.information(self, "NetBridge", "No plain (non-TLS) vless/vmess/trojan profile to convert."); return
        self._tls_ok = self._tls_bad = 0
        self.log.append(f"Looking for a TLS port on {len(todo)} plain profile(s) (443, 8443, 2053, 2083, 2087, 2096 and the same port) ... "
                        "A client cannot add TLS to a server that has none; only servers that offer it are converted.")
        self.tls_btn.setText("Stop TLS conversion")
        self.tlsw = TlsWorker(self.xray.executable, todo, self)
        self.tlsw.result.connect(self._tls_one); self.tlsw.finished.connect(self._tls_done)
        self.tlsw.start()

    def _tls_one(self, p, q, text):
        if not q:
            self._tls_bad += 1; self.log.append(f"   x {p.get('name')}: {text}"); return
        self._tls_ok += 1
        same_port = int(q["port"]) == int(p["port"])
        if same_port and any(x is p for x in self.profiles):      # the server already offered TLS on that port: fix it in place
            self.profiles[[i for i, x in enumerate(self.profiles) if x is p][0]] = q
            save_profiles(self.profiles); self.refresh(keep=False)
            self.log.append(f"   + {p.get('name')}: TLS works on the same port {q['port']} (profile upgraded): {text}")
        else:
            added, *_ = self._add_profiles([q], q.get("group"))
            self.log.append(f"   + {p.get('name')} -> new profile with TLS {q['port']}: {text}" + ("" if added else "  (already in the list)"))

    def _tls_done(self):
        self.tls_btn.setText("Convert non-TLS to TLS (try)")
        self.log.append(f"TLS conversion finished: {self._tls_ok} converted (a different TLS port is added as a new profile, the original is kept), {self._tls_bad} not possible.")

    def export(self):
        p = self.selected()
        if not p: return
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"{p.get('name','profile')}.txt", "Text (*.txt)")
        if path: Path(path).write_text(self.to_uri(p), encoding="utf-8")

    def to_uri(self, p):
        import base64
        typ, name = p.get("type"), quote(p.get("name", ""))
        def query(keys):
            names = {"network": "type", "service_name": "serviceName"}
            q = [f"{names.get(k, k)}={quote(str(p[k]))}" for k in keys if p.get(k)]
            return "&".join(q)
        srv = str(p['server'])
        host = f"[{srv}]:{p['port']}" if ":" in srv and not srv.startswith("[") else f"{srv}:{p['port']}"
        if typ == "vless":
            return f"vless://{p['uuid']}@{host}?" + query(["network","security","sni","host","path","fp","alpn","flow","cs","fm","ech","pbk","sid","spx","service_name","pcs"]) + f"#{name}"
        if typ == "trojan":
            return f"trojan://{quote(p['password'])}@{host}?" + query(["network","security","sni","host","path","fp","cs","fm","ech","pcs"]) + f"#{name}"
        if typ == "shadowsocks":
            cred = base64.urlsafe_b64encode(f"{p['method']}:{p['password']}".encode()).decode().rstrip("=")
            return f"ss://{cred}@{host}#{name}"
        if typ == "vmess":
            d = {"v": "2", "ps": p.get("name", ""), "add": p["server"], "port": str(p["port"]), "id": p["uuid"],
                 "net": p.get("network", "tcp"), "tls": p.get("security", ""), "sni": p.get("sni", ""),
                 "host": p.get("host", ""), "path": p.get("service_name", "") if p.get("network") == "grpc" else p.get("path", ""),
                 "fp": p.get("fp", ""), "alpn": p.get("alpn", "")}
            return "vmess://" + base64.b64encode(json.dumps(d, ensure_ascii=False).encode()).decode()
        if typ == "hysteria2":
            q = []
            if p.get("sni"): q.append(f"sni={quote(p['sni'])}")
            if p.get("obfs_password"): q.append(f"obfs=salamander&obfs-password={quote(p['obfs_password'])}")
            if p.get("pcs"): q.append(f"pcs={quote(p['pcs'])}")
            return f"hysteria2://{quote(p['password'], safe='')}@{host}?{'&'.join(q)}#{name}"
        return f"# {p.get('name','')} ({typ})"

    def test(self):
        p = self.selected()
        if not p: return
        try:
            self.check_config_path.parent.mkdir(parents=True, exist_ok=True)
            write_config(p, self.check_config_path, self.settings, all_profiles=self.profiles)
            self.log.append(f"Config written: {self.check_config_path.resolve()}")
            ok, msg = self.xray.check_config(self.check_config_path)
            self.log.append(("Xray check OK: " if ok else "Xray check FAILED: ") + msg)
            (QMessageBox.information if ok else QMessageBox.warning)(
                self, "NetBridge", msg if not ok else "Config is valid for this Xray core.")
        except Exception as e:
            QMessageBox.critical(self, "Config error", str(e))

    def toggle(self):
        if self.xray.running:
            self.disconnect_(); return
        if self.mode.currentData() == "best":
            if not self.view:
                return
            self.test_all(then_connect=True); return
        self.connect_()

    def _style_connect(self, connected):
        """Blue while not connected, green once connected (green is the colour people expect for 'connected')."""
        self.connect_btn.setStyleSheet(theme.big_button(theme.GRAD_GREEN if connected else theme.GRAD_BLUE, radius=12, size=16))

    def start_feeder(self):
        """Starts the hidden Xray copy of the active connection; returns its SOCKS port or None (with a message shown)."""
        if not self.xray.running or self.aether.running:
            QMessageBox.information(self, "Aether", "First connect to a normal profile that works (not an Aether / Tor / Psiphon one), then tick this "
                                    "box and press the Aether button again.")
            return None
        try:
            self.feeder.stop()
            sp = aether_mod.free_port(1900)
            hp = aether_mod.free_port(sp + 1)
            feeder_mod.make_feeder_config(self.active_config, Path("configs/feeder.json"), sp, hp)
            self.feeder.start(Path("configs/feeder.json"))
            for _ in range(40):
                if aether_mod.socks_ready(sp):
                    return sp
                time.sleep(0.25)
            raise RuntimeError("the helper connection did not start")
        except Exception as e:
            self.feeder.stop()
            QMessageBox.warning(self, "Aether", f"Could not keep the current connection for Aether: {e}")
            return None

    def tor_bridges(self):
        dlg = tor_bridges_dialog.TorBridgesDialog(self)
        if dlg.exec():
            self.aether.bridges, self.aether.bridges_now = dlg.result_bridges, dlg.result_now
            self.log.append(f"Tor bridges: {len(dlg.result_bridges)} of your own saved" if dlg.result_bridges
                            else "Tor bridges: none saved - Aether finds bridges by itself.")

    # ---------- WARP through the Aether core ----------
    def warp_aether(self, kind="warp"):
        """kind: "warp", "tor" (Tor carried inside WARP) or "tor-only" (plain Tor, bridges when blocked)."""
        if getattr(self, "aetherw", None) and self.aetherw.isRunning():
            if QMessageBox.question(self, "Aether", "Aether is still starting (Tor / Psiphon can take a few minutes).\n\n"
                                    "Cancel it?") == QMessageBox.Yes:
                self.aetherw.stop()
                self.log.append("Aether: cancelling ...")
            return
        if kind in ("tor", "tor-only") and QMessageBox.question(self, "Tor (Aether)",
                "Tor is slow and meant for light browsing; the first start downloads Tor's directory and can take several minutes.\n"
                + ("It runs inside the WARP tunnel, so a network that blocks Tor does not see it." if kind == "tor"
                   else "No WARP: if Tor is blocked, Aether fetches bridges by itself.") + "\n\nStart?") != QMessageBox.Yes:
            return
        if kind in ("psiphon", "psiphon-only") and QMessageBox.question(self, "Psiphon (Aether)",
                "Psiphon is built into the Aether download (no separate install). The first start can take up to a few minutes.\n"
                + ("It runs inside the WARP tunnel." if kind == "psiphon" else "No WARP: Psiphon connects on its own.") + "\n\nStart?") != QMessageBox.Yes:
            return
        self._aether_kind = kind
        if not aether_mod.installed():
            if QMessageBox.question(self, "Aether core",
                    "WARP uses the separate open-source program Aether (AGPL-3.0, github.com/CluvexStudio/Aether).\n\n"
                    "It is not part of NetBridge. It will be downloaded now from its official GitHub releases (about 20 MB), "
                    "checked with its SHA-256 and kept in cores/aether/. Continue?") != QMessageBox.Yes:
                return
        self.aether.upstream = None
        if self.via_chk.isChecked():
            port = self.start_feeder()
            if not port:
                return
            self.aether.upstream = feeder_mod.upstream_url(port)
            self.log.append(f"Aether will dial through your current connection ({self.aether.upstream}).")
        self.log.append(f"Aether ({kind}): starting - the buttons stay active; press one again to cancel.")
        proto, fam = self.warp_mode.currentData() if kind == "warp" else ("masque", "4")
        self.aetherw = AetherWorker(self.aether, self.proxy_url_for_download(), kind, self, protocol=proto, family=fam,
                                  region=(self.psi_region.currentData() or None) if kind.startswith("psiphon") else None)
        self.aetherw.status.connect(self.log.append)
        self.aetherw.done.connect(self._warp_ready)
        self.aetherw.start()

    # ---------- one-click personal Worker on the user's own Cloudflare account ----------
    def deploy_worker(self):
        if getattr(self, "deployw", None) and self.deployw.isRunning():
            return
        token, ok = QInputDialog.getText(self, "Deploy my Worker",
            "Creates a private relay on YOUR free Cloudflare account.\n\n"
            "1) dash.cloudflare.com > My Profile > API Tokens > Create Token > 'Edit Cloudflare Workers' template.\n"
            "2) Paste the token here. It is used once and never saved.\n\nAPI token:", QLineEdit.Password)
        if not ok or not token.strip():
            return
        self.deploy_btn.setEnabled(False)
        self.deployw = DeployWorker(token, self)
        self.deployw.status.connect(self.log.append)
        self.deployw.done.connect(self._deploy_done)
        self.deployw.start()

    def _deploy_done(self, result):
        self.deploy_btn.setEnabled(True)
        if not isinstance(result, dict):
            QMessageBox.warning(self, "Deploy my Worker", str(result)); return
        self._add_profiles([result])
        self.log.append(f"Your Worker is ready: {result['server']} (it may take a minute before it answers).")
        QMessageBox.information(self, "Deploy my Worker", f"Done. Added profile '{result['name']}'.\nAddress: {result['server']}")

    # ---------- public config lists ----------
    def _set_free_auto(self, on):
        self.settings["free_auto"] = bool(on); save_settings(self.settings)
        if on:
            QMessageBox.information(self, "Free configs", "On start, NetBridge will download the public list (at most once a day) and replace its old servers. "
                "These servers belong to other people - do not use them for banking or private accounts.")
            self._free_auto_check()

    def _free_auto_check(self):
        if not self.settings.get("free_auto") or not sources_mod.due(self.settings.get("free_last"), time.time()):
            return
        self.get_free_configs(silent=True)

    def get_free_configs(self, silent=False):
        if getattr(self, "srcw", None) and self.srcw.isRunning():
            return
        self._free_silent = silent
        srcs = sources_mod.load_sources()
        if not srcs:
            QMessageBox.warning(self, "Free configs", "No config source is listed in assets/config_sources.json."); return
        src = srcs[0]
        if not silent and QMessageBox.question(self, "Free configs",
                f"Downloads the public list '{src['name']}' ({src['page']}) and replaces its previous servers.\n\n"
                "Careful: these servers belong to other people. Your traffic passes through them, so do not use them for banking or "
                "private accounts - use your own Worker (Deploy my Worker) for that.\n\nAfter it finishes, press AUTO to find the best one. Continue?") != QMessageBox.Yes:
            return
        self.free_btn.setEnabled(False)
        self.srcw = SourceWorker(src, self.proxy_url() if self.xray.running else None, self)
        self.srcw.done.connect(self._free_done)
        self.srcw.start()

    def _free_done(self, result):
        self.free_btn.setEnabled(True)
        if not isinstance(result, tuple):
            if getattr(self, "_free_silent", False):
                self.log.append(f"Free configs: could not refresh the list ({result})")
            else:
                QMessageBox.warning(self, "Free configs", f"Could not download the list:\n{result}")
            return
        self.settings["free_last"] = time.time(); save_settings(self.settings)
        src, profiles, mirror, errors = result
        self.profiles[:] = sources_mod.drop_group(self.profiles, src["group"])
        profiles = self._filter_tls(profiles)
        self.log.append(f"Free configs from {mirror}")
        self._report(*self._add_profiles(profiles, src["group"]), errors)
        self.log.append("Press AUTO to test them and connect to the best one.")

    # ---------- Telegram web proxy on the user's own Cloudflare account ----------
    def telegram_proxy(self):
        TgProxyDialog(self, self.proxy_url_for_download()).exec()

    # ---------- Google Script relay ----------
    def google_script(self):
        dlg = GScriptDialog(self, self.gscript)
        dlg.started.connect(self._gscript_ready)
        dlg.exec()

    def _gscript_ready(self, server):
        self.gscript = server
        p = next((q for q in self.profiles if gscript_mod.is_gscript(q)), None)
        if p is None:
            p = gscript_mod.local_profile(server.port)
            self.profiles.append(p)
        p["port"] = server.port
        save_profiles(self.profiles); self.refresh(keep=p)
        self.log.append(f"Google Script relay is running on 127.0.0.1:{server.port}. Select 'Google Script' and press CONNECT (web pages only).")

    def proxy_url_for_download(self):
        return f"http://127.0.0.1:{self.http_port}" if self.xray.running else None

    def _warp_ready(self, result):
        for b in (self.warp_btn, self.tor_btn, self.toronly_btn, self.psi_btn, self.psionly_btn):
            b.setEnabled(True)
        kind = getattr(self, "_aether_kind", "warp")
        if not isinstance(result, int):
            if str(result) == "cancelled":
                self.log.append("Aether: cancelled."); return
            self.feeder.stop()
            QMessageBox.warning(self, "Aether", str(result)); return
        p = next((q for q in self.profiles if aether_mod.needs_kind(q) == kind), None)
        if p is None:
            p = (aether_mod.warp_profile(result) if kind == "warp" else aether_mod.psiphon_profile(result, kind) if kind.startswith("psiphon")
                 else aether_mod.tor_profile(result, kind))
            self.profiles.append(p)
        p["port"] = result
        save_profiles(self.profiles); self.refresh(keep=p)
        self.log.append(f"Aether ({kind}) is ready: SOCKS5 127.0.0.1:{result}. Connecting through it ...")
        self.connect_(profile=p)

    def disconnect_(self):
        self.aether.stop(); self.feeder.stop()
        self.xray.stop(); self.timer.stop(); self._proxy(False)
        self.connect_btn.setText("CONNECT"); self._style_connect(False); self.status.setText("Status: Disconnected")
        self.log.append("Xray stopped.")

    def connect_(self, profile=None, pool=None):
        mode = self.mode.currentData()
        try:
            if pool:
                # AUTO search result: connect ONLY through the servers that passed the real test
                # (each already carries its winning bypass method). Never mix in untested servers.
                profs = list(pool)
                cmode = "auto" if len(profs) > 1 else "manual"
                note = (f"Auto balancer over {len(profs)} verified profile(s)" if cmode == "auto"
                        else profs[0].get("name", ""))
            elif mode == "auto":
                pool = [self.profiles[i] for i in self.view if self.profiles[i].get("delay", 0) != -1
                        and self.profiles[i].get("engine") not in ("aether", "gscript")]
                pool = pool[:AUTO_MAX]
                if not pool:
                    QMessageBox.information(self, "NetBridge", "No usable profiles in this group."); return
                profs, cmode = pool, "auto"
                note = f"Auto balancer over {len(pool)} profile(s)"
            else:
                p = profile or self.selected()
                if not p: return
                profs, cmode, note = [p], "manual", p.get("name", "")
            self.socks_port, self.http_port = ports.pick_ports()
            if (self.socks_port, self.http_port) != (ports.SOCKS, ports.HTTP):
                who = ports.port_owner(ports.HTTP) or ports.port_owner(ports.SOCKS) or "another program"
                self.log.append(f"Ports {ports.SOCKS}/{ports.HTTP} are in use by {who}. Using {self.socks_port}/{self.http_port} instead.")
            need = {aether_mod.needs_kind(q) for q in profs if aether_mod.is_aether(q)}
            if need and not (self.aether.running and self.aether.kind in need):
                names = {"warp": "WARP (Aether core)", "tor": "Tor via WARP", "tor-only": "Tor alone (bridges)",
                         "psiphon": "Psiphon via WARP", "psiphon-only": "Psiphon alone"}
                QMessageBox.information(self, "NetBridge", "This profile needs the Aether core in the matching mode. Press the '%s' button." % names[sorted(need)[0]]); return
            if not need and self.aether.running:
                self.aether.stop()
            if any(gscript_mod.is_gscript(q) for q in profs) and not (self.gscript and self.gscript.running):
                QMessageBox.information(self, "NetBridge", "The Google Script profile needs the relay running. Open 'Google Script' and press 'Test and Start'."); return
            write_config(profs, self.active_config, self.settings, mode=cmode, pin_profile=self._pin_profile(), all_profiles=self.profiles,
                         socks_port=self.socks_port, http_port=self.http_port)
            self.xray.start(self.active_config)
            self.timer.start(100)
            self._proxy(True)
            self.connect_btn.setText("DISCONNECT"); self._style_connect(True)
            self.status.setText(f"Status: running ({note}) - SOCKS 127.0.0.1:{self.socks_port}  HTTP {self.http_port}")
            self.log.append(f"Xray started: {note}")
        except Exception as e:
            if not self.xray.running:
                self.timer.stop(); self._proxy(False)
                self.connect_btn.setText("CONNECT"); self._style_connect(False); self.status.setText("Status: Disconnected")
            QMessageBox.critical(self, "Start error", str(e))

    def pin_certs(self):
        todo = [p for p in self.profiles if p.get("insecure") and not p.get("pcs") and not p.get("pin_failed")]
        if not todo:
            if self.sender() is self.pin_btn:
                todo = [p for p in self.profiles if p.get("insecure") and not p.get("pcs")]
            if not todo: return
        if getattr(self, "pinw", None) and self.pinw.isRunning(): return
        self._pin_ok = self._pin_bad = 0
        self.log.append(f"Pinning certificates of {len(todo)} self-signed server(s) ...")
        self.pin_btn.setEnabled(False)
        self.pinw = PinWorker(todo, self)
        self.pinw.result.connect(self._pin_one)
        self.pinw.finished.connect(self._pin_done)
        self.pinw.start()

    def _pin_one(self, p, h, err):
        if h:
            p["pcs"] = h; p.pop("pin_failed", None); self._pin_ok += 1
        else:
            p["pin_failed"] = True; self._pin_bad += 1
            self.log.append(f"   no certificate from '{p.get('name')}': {err}")

    def _pin_done(self):
        save_profiles(self.profiles); self.pin_btn.setEnabled(True)
        self.log.append(f"Pinned {self._pin_ok}, failed {self._pin_bad}."
                        + (" Failed servers are offline or need a different obfs/port; press the button to retry." if self._pin_bad else ""))

    def update_presets(self):
        """Fetch newer bypass values (through the tunnel if connected, else directly) and apply them."""
        self.preset_btn.setEnabled(False)
        proxy = self.proxy_url() if self.xray.running else None
        self.log.append(f"Updating bypass values (now version {bypass_mod.STATE['version']}) ...")
        self.prw = PresetWorker(bypass_mod.STATE["version"], proxy, self)
        self.prw.done.connect(self._presets_done); self.prw.start()

    def _presets_done(self, res):
        self.preset_btn.setEnabled(True)
        if isinstance(res, str):
            self.log.append("Bypass values: update failed - " + res); return
        status, doc, errs = res
        if status == "updated":
            bypass_mod.reload()
            self.log.append(f"Bypass values updated to version {doc['version']} "
                            f"({', '.join(doc['presets'])}). Run AUTO again, or pick the method in Bypass.")
        else:
            self.log.append(f"Bypass values are already the newest (version {bypass_mod.STATE['version']}).")
        for e in errs + bypass_mod.STATE["errors"]:
            self.log.append("  skipped: " + e)

    def check_ip(self):
        if not self.xray.running:
            QMessageBox.information(self, "NetBridge", "Connect first."); return
        self.log.append("Checking exit IP, geo databases and local signals ...")
        self.ipw = IpWorker(self.proxy_url(), self); self.ipw.done.connect(self.log.append); self.ipw.start()

    def exit_scan(self):
        if self.xray.version() is None:
            QMessageBox.warning(self, "NetBridge", "Xray core not found."); return
        items = [(i, self.profiles[i]) for i in self.view] or list(enumerate(self.profiles))
        if not items:
            QMessageBox.information(self, "NetBridge", "No profiles. Import some first (Subscription / Import file)."); return
        d = ExitDialog(self.xray.executable, items, self, group=self.group_combo.currentText() or "All", to_uri=self.to_uri)
        d.exec()
        if not d.action: return
        p = self.profiles[d.action[1]]
        r = self.settings["routing"]
        r["pin_profile"] = profile_key(p)
        have = set(r.get("pin_sites", []))
        r["pin_sites"] = list(r.get("pin_sites", [])) + [x for x in SERVICE_PRESETS["Google AI (Gemini, AI Studio)"] if x not in have]
        save_settings(self.settings)
        self.log.append(f"Exit for Google AI sites: '{p.get('name')}'. Open the sites with 'Open clean browser'.")
        if self.xray.running:
            self.xray.stop(); self.connect_()

    def scan_ips(self):
        p = self.selected()
        if not p:
            QMessageBox.information(self, "NetBridge", "Select a profile first."); return
        grp = self.group_combo.currentData() or ""      # the group shown in the list (a subscription); "" = all
        cf = ipscan.cloudflare_in_group(self.profiles, grp)
        d = ScanDialog(p, len(cf), self, group=grp)
        d.exec()
        if not d.action: return
        kind, val = d.action
        if kind == "one":
            p["address_override"] = val
            msg = f"Clean IP {val} set for '{p.get('name')}'."
        else:
            scope = f"group '{grp}'" if grp else "all groups"
            if QMessageBox.question(self, "NetBridge",
                    f"Set Clean IP on {len(cf)} Cloudflare profile(s) of {scope}, using {len(val)} tested IP(s)?\n"
                    "Existing Clean IP values of those profiles will be replaced. Other groups are not touched.") != QMessageBox.Yes:
                return
            ipscan.spread_clean_ips(self.profiles, val, grp)
            msg = f"Clean IPs applied to {len(cf)} profile(s): " + ", ".join(val)
        save_profiles(self.profiles); self.select(0)
        self.log.append(msg + (" Reconnect to use it." if self.xray.running else ""))

    def open_browser(self):
        if not self.xray.running:
            QMessageBox.information(self, "NetBridge", "Connect first."); return
        try:
            exe = browser.launch(self.http_port)
            self.log.append("Clean browser started: " + exe)
        except Exception as e:
            QMessageBox.warning(self, "NetBridge", str(e))

    def _pin_profile(self):
        key = self.settings["routing"].get("pin_profile", "")
        return next((p for p in self.profiles if key and profile_key(p) == key), None)

    def routing(self):
        d = RoutingDialog(self.settings["routing"], self.profiles, self)
        if d.exec() != QDialog.Accepted: return
        self.settings["routing"] = d.value()
        save_settings(self.settings)
        self.log.append("Routing saved.")
        if self.xray.running:
            self.xray.stop(); self.connect_()

    # ---- delay test for many profiles
    def test_all(self, then_connect=False):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.pending_best = False
            self.test_btn.setText("Stopping..."); return
        if not self.xray.executable.exists():
            QMessageBox.warning(self, "NetBridge", "Xray core not found. Run setup.bat."); return
        profs = [self.profiles[i] for i in self.view]
        if not profs:
            QMessageBox.information(self, "NetBridge", "No profiles."); return
        self.pending_best = then_connect
        self._done, self._total = 0, len(profs)
        self.test_btn.setText("Stop test")
        self.status.setText(f"Status: testing 0/{self._total} ...")
        self.worker = DelayWorker(self.xray.executable, profs, self)
        self.worker.result.connect(self._one_result)
        self.worker.finished.connect(self._tests_done)
        self.worker.start()

    def _one_result(self, p, ms):
        p["delay"] = ms
        self._done += 1
        self.status.setText(f"Status: testing {self._done}/{self._total} ...")
        self._refresh_soon()

    def _refresh_soon(self):
        """Coalesce bursts of results into one list rebuild every 300 ms."""
        if getattr(self, "_refresh_pending", False): return
        self._refresh_pending = True
        def go():
            self._refresh_pending = False
            self.refresh()
        QTimer.singleShot(300, go)

    def _tests_done(self):
        self.test_btn.setText("Test all (delay)")
        save_profiles(self.profiles); self.refresh()
        ok = [self.profiles[i] for i in self.view if self.profiles[i].get("delay", -1) >= 0]
        self.log.append(f"Delay test finished: {len(ok)}/{self._total} working.")
        self.status.setText("Status: " + ("Xray running" if self.xray.running else "Disconnected"))
        if self.pending_best:
            self.pending_best = False
            if not ok:
                QMessageBox.warning(self, "NetBridge", "No profile responded."); return
            best = min(ok, key=lambda p: p["delay"])
            self.refresh(keep=best)
            self.select(0)
            self.log.append(f"Fastest: {best.get('name')} ({best['delay']} ms)")
            self.connect_(best)

    # -- automatic bypass: try every method on every profile, keep what works, connect to the best
    def auto_bypass(self):
        if self.auto_worker and self.auto_worker.isRunning():
            self.auto_worker.stop(); self.auto_btn.setText("Stopping..."); return
        if not self.xray.executable.exists():
            QMessageBox.warning(self, "NetBridge", "Xray core not found. Run setup.bat."); return
        profs = [self.profiles[i] for i in self.view]
        if not profs:
            QMessageBox.information(self, "NetBridge", "No profiles."); return
        self._auto_wins = []
        self.auto_btn.setText("Stop auto search")
        self.log.append(f"AUTO: testing {len(profs)} profile(s) with every method (this can take a few minutes)...")
        self.auto_worker = AutoWorker(self.xray.executable, profs, self)
        self.auto_worker.win.connect(self._auto_win)
        self.auto_worker.status.connect(self._auto_status)
        self.auto_worker.progress.connect(lambda d, t: self.status.setText(f"Status: auto search {d}/{t} ..."))
        self.auto_worker.summary.connect(self._auto_done)
        self.auto_worker.start()

    def _auto_status(self, text):
        self.log.append("AUTO: " + text)

    def _auto_win(self, p, v, ms):
        apply_variant(p, v)
        p["delay"] = ms
        self._auto_wins.append((p, ms))
        self.log.append(f"AUTO: works -> {p.get('name')} [{variant_label(v)}] {ms} ms")
        self.refresh()

    def _auto_done(self, res):
        self.auto_btn.setText("AUTO: find the working method + connect")
        save_profiles(self.profiles); self.refresh()
        self.status.setText("Status: " + ("Xray running" if self.xray.running else "Disconnected"))
        if res.get("relaxed_fallback"):
            self.log.append("AUTO: WARNING - no profile passed the YouTube/Instagram check; the connected one only passed "
                            "the basic test, so those sites may not open. Try again later or import a fresh subscription.")
        tls_wins = [x for x in self._auto_wins if is_tls(x[0])]
        pool = tls_wins or self._auto_wins
        if not pool:
            self.log.append("AUTO: nothing worked. Try again later, import a fresh subscription, or change network.")
            QMessageBox.warning(self, "NetBridge", "No profile worked with any method right now.\n"
                                "Try a fresh subscription, another network, or try again later.")
            return
        best, ms = min(pool, key=lambda x: x[1])
        if not tls_wins:
            self.log.append("AUTO: WARNING - only plain (not encrypted) profiles work; websites and your ISP can read this traffic.")
        self.refresh(keep=best); self.select(0)
        self.log.append(f"AUTO: connecting to {best.get('name')} [{best.get('bypass', 'off')}] ({ms} ms)")
        winners = [p for p, _ in sorted(pool, key=lambda x: x[1])][:4]   # fastest first; the best one is p0
        self.connect_(pool=winners)

    def proxy_url(self):
        return f"http://127.0.0.1:{self.http_port}"

    def _proxy(self, on):
        if not system_proxy.supported(): return
        try:
            if on:
                if not self.sys_proxy.isChecked(): return
                self._proxy_server = f"127.0.0.1:{self.http_port}"
                system_proxy.set_proxy(True, self._proxy_server)
                self.log.append(f"System proxy ON {self._proxy_server}")
            elif self._proxy_server:                 # never switch off a proxy that another VPN app set
                srv, self._proxy_server = self._proxy_server, None
                if system_proxy.disable_if_ours(srv):
                    self.log.append("System proxy OFF")
        except Exception as e:
            self.log.append(f"System proxy error: {e}")

    def poll(self):
        lines = self.xray.read_all_available()
        for line in lines:
            self.log.append(line)
        if self.connect_btn.text() == "DISCONNECT" and not self.xray.running:
            self.timer.stop(); self._proxy(False)
            self.connect_btn.setText("CONNECT"); self._style_connect(False); self.status.setText("Status: Disconnected (Xray stopped)")
            tail = [l for l in lines if l and "exited" not in l][-1:] or ["(no message)"]
            self.log.append("Xray stopped unexpectedly, system proxy switched OFF. " + tail[0][-300:])
            QMessageBox.warning(self, "NetBridge", "The connection failed to start.\n\n" + tail[0][-400:])

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.worker.wait(5000)
        if self.auto_worker and self.auto_worker.isRunning():
            self.auto_worker.stop(); self.auto_worker.wait(8000)
        for name, wait in (("tlsw", 8000), ("pinw", 8000), ("ipw", 12000)):
            w = getattr(self, name, None)
            if w is not None and w.isRunning():
                if hasattr(w, "stop"): w.stop()
                w.wait(wait)
        w = getattr(self, "aetherw", None)
        if w is not None and w.isRunning():
            w.stop(); w.wait(8000)
        self.aether.stop(); self.feeder.stop()
        if self.gscript: self.gscript.stop()
        self.xray.stop(); self._proxy(False); save_profiles(self.profiles); e.accept()
