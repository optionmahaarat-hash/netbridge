import pathlib, subprocess, pytest
from app.core.config_generator import write_config

NEW = pathlib.Path("/tmp/xr2/xray")

@pytest.mark.skipif(not NEW.exists(), reason="needs Xray >= 26.7 binary at /tmp/xr2/xray")
def test_pattng_exact_ok_on_new_xray(tmp_path):
    p = tmp_path / "c.json"
    write_config({"name": "T", "type": "vless", "server": "1.1.1.1", "port": 443,
                  "uuid": "123e4567-e89b-12d3-a456-426614174000", "network": "ws",
                  "security": "tls", "sni": "a.workers.dev", "host": "a.workers.dev",
                  "path": "/x", "bypass": "pattng"}, p)
    r = subprocess.run([str(NEW), "run", "-test", "-c", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
