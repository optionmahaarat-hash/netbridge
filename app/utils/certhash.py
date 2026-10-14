"""Fetch the SHA256 of a server's leaf certificate (trust-on-first-use).

Xray >= 26.7 removed `allowInsecure`; a self-signed server must be pinned with
pinnedPeerCertSha256 instead. This does the handshake itself and returns that hash.
 - Hysteria2 (QUIC/UDP, optional salamander obfs): needs `pip install aioquic`
 - TLS over TCP (vless/trojan/vmess): standard library
Note: the first fetch trusts whatever the network answers (same as 'insecure' once);
after that the certificate is pinned.
"""
import hashlib, socket, ssl, time


def tcp_cert_hash(host, port, sni="", timeout=6):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, int(port)), timeout=timeout) as s:
        with ctx.wrap_socket(s, server_hostname=sni or None) as t:
            return hashlib.sha256(t.getpeercert(binary_form=True)).hexdigest()


def _salamander(psk: bytes, data: bytes, salt: bytes) -> bytes:
    key = hashlib.blake2b(psk + salt, digest_size=32).digest()
    return bytes(b ^ key[i % 32] for i, b in enumerate(data))


def quic_cert_hash(host, port, sni="", obfs_password="", timeout=6):
    try:
        from aioquic.quic.configuration import QuicConfiguration
        from aioquic.quic.connection import QuicConnection
        from aioquic.quic.events import ConnectionTerminated
        from cryptography.hazmat.primitives.serialization import Encoding
    except ImportError:
        raise RuntimeError("aioquic is not installed. Run:  python -m pip install aioquic")
    cfg = QuicConfiguration(is_client=True, alpn_protocols=["h3"], server_name=sni or None,
                            verify_mode=ssl.CERT_NONE)
    conn = QuicConnection(configuration=cfg)
    addr = (socket.gethostbyname(host), int(port))
    psk = obfs_password.encode() if obfs_password else b""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    end = time.time() + timeout
    try:
        conn.connect(addr, now=time.time())
        while time.time() < end:
            now = time.time()
            for data, _ in conn.datagrams_to_send(now=now):
                if psk:
                    import os
                    salt = os.urandom(8)
                    data = salt + _salamander(psk, data, salt)
                sock.sendto(data, addr)
            peer = getattr(getattr(conn, "tls", None), "_peer_certificate", None)
            if peer is not None:
                return hashlib.sha256(peer.public_bytes(Encoding.DER)).hexdigest()
            while (ev := conn.next_event()) is not None:
                if isinstance(ev, ConnectionTerminated):
                    raise RuntimeError(f"server closed the handshake: {ev.reason_phrase or ev.error_code}")
            timer = conn.get_timer()
            wait = 0.2 if timer is None else max(0.01, min(0.2, timer - time.time()))
            sock.settimeout(wait)
            try:
                data, _ = sock.recvfrom(65535)
                if psk:
                    if len(data) <= 8: continue
                    data = _salamander(psk, data[8:], data[:8])
                conn.receive_datagram(data, addr, now=time.time())
            except socket.timeout:
                pass
            if conn.get_timer() is not None and conn.get_timer() <= time.time():
                conn.handle_timer(now=time.time())
        raise TimeoutError("no answer (server down, wrong port, or wrong obfs password)")
    finally:
        sock.close()


def fetch_pin(profile, timeout=6):
    """Returns the lowercase hex SHA256 for a profile (raises on failure)."""
    sni = profile.get("sni") or ""
    if profile.get("type") == "hysteria2":
        return quic_cert_hash(profile["server"], profile["port"], sni, profile.get("obfs_password", ""), timeout)
    return tcp_cert_hash(profile["server"], profile["port"], sni, timeout)
