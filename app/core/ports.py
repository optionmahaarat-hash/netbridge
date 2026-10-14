"""Local proxy ports: never fail because another program (v2rayN, MLM VPN, an old NetBridge window ...) holds 10808/10809."""
import socket
import subprocess
import sys

SOCKS, HTTP = 10808, 10809


def is_free(port):
    """True if nothing is listening on 127.0.0.1:port (and we could bind it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if sys.platform == "win32":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_ports(socks=SOCKS, http=HTTP, tries=50, free=is_free):
    """First free (socks, http) pair, starting with the preferred ones and moving up by 10."""
    for k in range(tries):
        a, b = socks + 10 * k, http + 10 * k
        if free(a) and free(b):
            return a, b
    raise OSError("No free local port found for the proxy.")


def parse_netstat(text, port):
    """PID listening on the port, from `netstat -ano -p TCP` output (Windows), or None."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
            return int(parts[4])
    return None


def parse_tasklist(text):
    """Process name from `tasklist /FO CSV /NH` output for one PID."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line.split('","')[0].strip('"') if line.startswith('"') else None


def port_owner(port):
    """'name.exe (PID 123)' or None. Best effort, Windows only."""
    if sys.platform != "win32":
        return None
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=8, creationflags=flags).stdout
        pid = parse_netstat(out, port)
        if pid is None:
            return None
        t = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                           timeout=8, creationflags=flags).stdout
        return f"{parse_tasklist(t) or 'unknown program'} (PID {pid})"
    except Exception:
        return None
