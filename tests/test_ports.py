import socket
from app.core import ports

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1156
  TCP    127.0.0.1:10808        0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:10809        0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:50000        127.0.0.1:10809        ESTABLISHED     999
"""

def test_parse_netstat_and_tasklist():
    assert ports.parse_netstat(NETSTAT, 10809) == 4242
    assert ports.parse_netstat(NETSTAT, 135) == 1156
    assert ports.parse_netstat(NETSTAT, 50000) is None            # ESTABLISHED is not a listener
    assert ports.parse_netstat(NETSTAT, 7777) is None
    assert ports.parse_tasklist('"xray.exe","4242","Console","1","31,284 K"\n') == "xray.exe"
    assert ports.parse_tasklist("INFO: No tasks are running which match the specified criteria.") is None
    assert ports.parse_tasklist("") is None

def test_pick_ports_skips_used_pairs():
    busy = {10808, 10819}
    assert ports.pick_ports(free=lambda p: p not in busy) == (10828, 10829)      # 10808 busy; 10818/10819: 10819 busy
    assert ports.pick_ports(free=lambda p: True) == (10808, 10809)

def test_is_free_detects_a_listener():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1)
    port = s.getsockname()[1]
    assert ports.is_free(port) is False
    s.close()
    assert ports.is_free(port) is True
