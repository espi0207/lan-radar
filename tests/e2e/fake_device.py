"""Un aparato de mentira para la prueba de verdad (tests/test_e2e.py).

Cada aparato vive en su propio "namespace" de red de Linux, con su IP y su MAC, conectado
a un puente como si fuera el wifi de casa, y contesta como lo haría uno real: mDNS,
SSDP/UPnP, NetBIOS, saludos y páginas web. Así lan-radar se prueba con paquetes de verdad,
ARP incluido, sin salir de la máquina.

Uso (dentro del namespace): python fake_device.py <perfil> <ip>
"""

from __future__ import annotations

import socket
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lanradar import dns  # noqa: E402

# perfil → lo que anuncia. "mdns": nombre, servicios (tipo, nombre, puerto, txt) y modelo;
# "upnp": ficha; "netbios": (nombre, grupo); "tcp": puerto → saludo; "http": puerto → (título, Server)
PROFILES = {
    "router": {
        "upnp": {
            "deviceType": "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
            "friendlyName": "Router de casa",
            "manufacturer": "Sagemcom",
            "modelName": "F@st 5657",
            "server": "Linux/4.1.52 UPnP/1.0 MiniUPnPd/2.1",
        },
        "tcp": {53: None},
        "http": {80: ("Configuración del router", "lighttpd")},
    },
    "iphone": {
        "mdns": {
            "host": "iPhone-de-Ana",
            "model": "iPhone15,2",
            "services": [
                ("_companion-link._tcp", "iPhone de Ana", 49152, ["rpMd=iPhone15,2", "rpVr=360.4"]),
                ("_apple-mobdev2._tcp", "da:a1:19:5e:22:01@fe80::1", 32498, []),
            ],
        },
        "tcp": {62078: None},
    },
    "chromecast": {
        "mdns": {
            "host": "1a2b3c4d-5e6f-7a8b-9c0d-ee11ff223344",
            "services": [
                (
                    "_googlecast._tcp",
                    "Chromecast-1a2b3c4d5e6f7a8b9c0d",
                    8009,
                    ["id=1a2b3c4d5e6f7a8b9c0d", "md=Chromecast", "fn=Salón", "ve=05"],
                )
            ],
        },
        "upnp": {
            "deviceType": "urn:dial-multiscreen-org:device:dial:1",
            "friendlyName": "Salón",
            "manufacturer": "Google Inc.",
            "modelName": "Eureka Dongle",
            "server": "Linux/3.8.13 UPnP/1.0",
        },
        "tcp": {8008: None, 8009: None},
    },
    "printer": {
        "mdns": {
            "host": "HP5A1B2C",
            "services": [
                (
                    "_ipp._tcp",
                    "HP LaserJet M110w (5A1B2C)",
                    631,
                    ["ty=HP LaserJet M110w", "usb_MFG=HP", "usb_MDL=LaserJet M110w", "note=Despacho"],
                ),
                ("_uscan._tcp", "HP LaserJet M110w (5A1B2C)", 8080, ["ty=HP LaserJet M110w"]),
            ],
        },
        "tcp": {631: None, 9100: None},
        "http": {80: ("HP LaserJet M110w", "HP HTTP Server; HP LaserJet M110w")},
    },
    "windows": {
        "netbios": ("PORTATIL-ANA", "WORKGROUP"),
        "tcp": {139: None, 445: None, 3389: None},
    },
    "raspberry": {
        "mdns": {
            "host": "homeassistant",
            "hinfo": ("AARCH64", "LINUX"),
            "services": [("_home-assistant._tcp", "Casa", 8123, ["version=2025.9.1", "location_name=Casa"])],
        },
        "tcp": {22: b"SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3\r\n"},
        "http": {8123: ("Home Assistant", "Python/3.13 aiohttp/3.12")},
    },
    "plug": {},  # un enchufe que no cuenta nada: solo contesta a ARP
    "camera": {
        "tcp": {554: None, 23: b"\xff\xfd\x18\xff\xfd\x20"},
        "http": {80: ("Web Client", "webs")},
    },
    "tv": {
        "mdns": {
            "host": "Samsung-TV",
            "services": [
                (
                    "_airplay._tcp",
                    "Tele del salón",
                    7000,
                    ["manufacturer=Samsung", "model=QE55Q60B", "deviceid=8C:79:F5:12:34:56"],
                )
            ],
        },
        "upnp": {
            "deviceType": "urn:schemas-upnp-org:device:MediaRenderer:1",
            "friendlyName": "[TV] Tele del salón",
            "manufacturer": "Samsung Electronics",
            "modelName": "QE55Q60B",
            "server": "SHP, UPnP/1.0, Samsung UPnP SDK/1.0",
        },
        "http": {7000: ("", "AirTunes/377.40.00")},
    },
}

DESC_PORT = 49000


def rr(name: str, rtype: int, rdata: bytes, ttl: int = 120) -> bytes:
    return dns.encode_name(name) + struct.pack("!HHIH", rtype, 1, ttl, len(rdata)) + rdata


def txt(strings) -> bytes:
    return b"".join(bytes([len(s.encode())]) + s.encode() for s in strings) or b"\x00"


class Mdns:
    def __init__(self, profile: dict, ip: str):
        self.p, self.ip = profile, ip
        self.host = f"{profile['host']}.local"

    def answer(self, name: str, qtype: int) -> tuple[list[bytes], list[bytes]]:
        lname = name.lower()
        answers, extra = [], []
        a_record = rr(self.host, dns.A, socket.inet_aton(self.ip))
        if lname == dns.reverse_name(self.ip):
            answers.append(rr(name, dns.PTR, dns.encode_name(self.host)))
        if lname == self.host.lower() and qtype in (dns.A, dns.ANY):
            answers.append(a_record)
            if "hinfo" in self.p:
                answers.append(rr(self.host, dns.HINFO, txt(self.p["hinfo"])))
        for stype, label, port, strings in self.p.get("services", []):
            full = f"{label}.{stype}.local"
            srv = rr(full, dns.SRV, struct.pack("!HHH", 0, 0, port) + dns.encode_name(self.host))
            if lname == "_services._dns-sd._udp.local":
                answers.append(rr(name, dns.PTR, dns.encode_name(f"{stype}.local")))
            elif lname == f"{stype}.local":
                answers.append(rr(name, dns.PTR, dns.encode_name(full)))
                extra += [srv, rr(full, dns.TXT, txt(strings)), a_record]
            elif lname == full.lower():
                answers += [srv, rr(full, dns.TXT, txt(strings))]
                extra.append(a_record)
            elif lname == f"{label.split('@')[-1]}._device-info._tcp.local".lower() and self.p.get("model"):
                answers.append(rr(name, dns.TXT, txt([f"model={self.p['model']}"])))
        return answers, extra

    def serve(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 5353))
        mreq = socket.inet_aton("224.0.0.251") + socket.inet_aton(self.ip)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        while True:
            data, addr = sock.recvfrom(9000)
            try:
                msg = dns.parse(data)
            except dns.BadPacket:
                continue
            if msg.is_response:
                continue
            answers, extra = [], []
            for name, qtype in msg.questions:
                a, e = self.answer(name, qtype)
                answers += a
                extra += [x for x in e if x not in extra and x not in answers]
            if not answers:
                continue
            questions = b"".join(dns.encode_name(n) + struct.pack("!HH", t, 1) for n, t in msg.questions)
            header = struct.pack("!HHHHHH", msg.id, 0x8400, len(msg.questions), len(answers), 0, len(extra))
            sock.sendto(header + questions + b"".join(answers) + b"".join(extra), addr)


def serve_ssdp(profile: dict, ip: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", 1900))
    sock.setsockopt(
        socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton("239.255.255.250") + socket.inet_aton(ip)
    )
    upnp = profile["upnp"]
    while True:
        data, addr = sock.recvfrom(4096)
        if not data.startswith(b"M-SEARCH"):
            continue
        reply = (
            "HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=1800\r\nEXT:\r\n"
            f"LOCATION: http://{ip}:{DESC_PORT}/desc.xml\r\nSERVER: {upnp['server']}\r\n"
            f"ST: {upnp['deviceType']}\r\nUSN: uuid:1234::{upnp['deviceType']}\r\n\r\n"
        )
        sock.sendto(reply.encode(), addr)


def description(upnp: dict) -> bytes:
    fields = "".join(f"<{k}>{v}</{k}>" for k, v in upnp.items() if k != "server")
    return (
        '<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0">'
        f"<specVersion><major>1</major><minor>0</minor></specVersion><device>{fields}</device></root>"
    ).encode()


def serve_http(port: int, title: str, server: str, upnp: dict | None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/desc.xml" and upnp:
                body, kind = description(upnp), "text/xml"
            else:
                body, kind = f"<html><head><title>{title}</title></head><body></body></html>".encode(), "text/html"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def version_string(self):
            return server

        def log_message(self, *args):
            pass

    ThreadingHTTPServer(("", port), Handler).serve_forever()


def serve_tcp(port: int, greeting: bytes | None):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", port))
    srv.listen(16)
    while True:
        conn, _ = srv.accept()
        try:
            if greeting:
                conn.sendall(greeting)
        except OSError:
            pass
        finally:
            conn.close()


def serve_netbios(name: str, group: str, mac: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", 137))
    entries = [(name, 0x00, 0x0400), (group, 0x00, 0x8400), (name, 0x20, 0x0400)]
    rdata = bytes([len(entries)])
    for n, suffix, flags in entries:
        rdata += n.encode().ljust(15, b" ") + bytes([suffix]) + struct.pack("!H", flags)
    rdata += bytes.fromhex(mac.replace(":", "")) + b"\x00" * 40
    while True:
        data, addr = sock.recvfrom(1024)
        if len(data) < 12:
            continue
        qid = data[:2]
        name_part = data[12 : 12 + 34]
        reply = qid + struct.pack("!HHHHH", 0x8400, 0, 1, 0, 0) + name_part
        reply += struct.pack("!HHIH", 0x21, 1, 0, len(rdata)) + rdata
        sock.sendto(reply, addr)


def main():
    profile_name, ip, mac = sys.argv[1], sys.argv[2], sys.argv[3]
    profile = PROFILES[profile_name]
    threads = []
    if "mdns" in profile:
        threads.append(threading.Thread(target=Mdns(profile["mdns"], ip).serve))
    if "upnp" in profile:
        threads.append(threading.Thread(target=serve_ssdp, args=(profile, ip)))
        threads.append(threading.Thread(target=serve_http, args=(DESC_PORT, "", "UPnP", profile["upnp"])))
    if "netbios" in profile:
        threads.append(threading.Thread(target=serve_netbios, args=(*profile["netbios"], mac)))
    for port, greeting in profile.get("tcp", {}).items():
        threads.append(threading.Thread(target=serve_tcp, args=(port, greeting)))
    for port, (title, server) in profile.get("http", {}).items():
        threads.append(threading.Thread(target=serve_http, args=(port, title, server, None)))
    for t in threads:
        t.daemon = True
        t.start()
    print("listo", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
