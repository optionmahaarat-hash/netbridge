"""Tiny DNS client: ask ONE DNS server for the A records of a name (used to test a Smart DNS server)."""
import ipaddress
import random
import socket
import struct


def build_query(name, qid=None):
    qid = random.randrange(65536) if qid is None else qid
    hdr = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    q = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.strip(".").split(".")) + b"\0"
    return qid, hdr + q + struct.pack(">HH", 1, 1)


def _skip_name(data, pos):
    while True:
        n = data[pos]
        if n & 0xC0 == 0xC0:
            return pos + 2
        if n == 0:
            return pos + 1
        pos += n + 1


def parse_answers(data, qid):
    """Returns (rcode, [ipv4 strings])."""
    id_, flags, qd, an, _, _ = struct.unpack(">HHHHHH", data[:12])
    if id_ != qid:
        raise ValueError("DNS answer id mismatch")
    pos = 12
    for _ in range(qd):
        pos = _skip_name(data, pos) + 4
    ips = []
    for _ in range(an):
        pos = _skip_name(data, pos)
        typ, _, _, rdlen = struct.unpack(">HHIH", data[pos:pos + 10])
        pos += 10
        if typ == 1 and rdlen == 4:
            ips.append(".".join(str(b) for b in data[pos:pos + 4]))
        pos += rdlen
    return flags & 0xF, ips


def resolve(name, server, port=53, timeout=3.0):
    qid, pkt = build_query(name)
    fam = socket.AF_INET6 if ":" in server else socket.AF_INET
    with socket.socket(fam, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(pkt, (server, port))
        data, _ = s.recvfrom(2048)
    return parse_answers(data, qid)


def describe(name, server, port=53):
    """Human-readable test result."""
    try:
        rcode, ips = resolve(name, server, port)
    except Exception as e:
        return False, f"No answer from {server}:{port} ({e}). The DNS server may be unreachable from your network."
    if rcode != 0 or not ips:
        return False, f"{server} has no address for {name} (code {rcode}); it probably does not support this site."
    bad = [i for i in ips if ipaddress.ip_address(i).is_private]
    if bad:
        return False, f"{name} -> {', '.join(ips)}: private/fake address, this DNS does not really serve the site."
    return True, f"{name} -> {', '.join(ips)}  (resolved by {server})"
