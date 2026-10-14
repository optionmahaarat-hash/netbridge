"""Windows system proxy (the same thing as 'Set system proxy' in v2rayN/Hiddify)."""
import sys

PROXY = "127.0.0.1:10809"
KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

def supported():
    return sys.platform == "win32"

def _refresh():
    import ctypes
    w = ctypes.windll.Wininet
    w.InternetSetOptionW(0, 39, 0, 0)   # SETTINGS_CHANGED
    w.InternetSetOptionW(0, 37, 0, 0)   # REFRESH

def set_proxy(enable, server=PROXY):
    if not supported():
        raise OSError("System proxy is only available on Windows.")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
        if enable:
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
            winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, "localhost;127.*;10.*;192.168.*;<local>")
    _refresh()


def current():
    """(enabled, 'host:port') from the registry, or None (not Windows / unreadable)."""
    if not supported():
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            en = winreg.QueryValueEx(k, "ProxyEnable")[0]
            try: srv = winreg.QueryValueEx(k, "ProxyServer")[0]
            except OSError: srv = ""
        return bool(en), srv
    except OSError:
        return None


def disable_if_ours(server):
    """Switch the Windows proxy off ONLY if it still points to `server` (our own 127.0.0.1:port).
    Closing NetBridge used to switch it off unconditionally, which broke other VPN apps (v2rayN, Hiddify ...)
    that had set their own proxy. Returns True if it was switched off."""
    cur = current()
    if not cur or not cur[0]:
        return False
    srv = (cur[1] or "").strip()
    if srv == server or srv in (f"http={server}", f"http={server};https={server}") or f"={server}" in srv.split(";"):
        set_proxy(False)
        return True
    return False


def clear_stale(is_listening):
    """After a crash the proxy can stay ON pointing at a dead local port: Windows then has 'no internet'.
    Turns it off only if it points to 127.0.0.1:<port> and nothing listens there (so other VPN apps are never touched)."""
    import re
    cur = current()
    if not cur or not cur[0]:
        return False
    m = re.fullmatch(r"(?:http=)?127\.0\.0\.1:(\d+)(?:;.*)?", cur[1].strip())
    if m and not is_listening(int(m.group(1))):
        set_proxy(False)
        return True
    return False
