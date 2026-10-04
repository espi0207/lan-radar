"""Los protocolos: los paquetes se leen bien, los raros no rompen nada, y las preguntas
llegan y vuelven de verdad (con respondedores falsos en 127.0.0.1)."""

import ipaddress
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lanradar import dns, mdns, netbios, ssdp

LOCAL = ipaddress.ip_network("127.0.0.0/8")


def rr(name, rtype, rdata, ttl=120):
    return dns.encode_name(name) + struct.pack("!HHIH", rtype, 1, ttl, len(rdata)) + rdata


def txt(*strings):
    return b"".join(bytes([len(s.encode())]) + s.encode() for s in strings)


def response(records, questions=(), qid=0):
    q = b"".join(dns.encode_name(n) + struct.pack("!HH", t, 1) for n, t in questions)
    header = struct.pack("!HHHHHH", qid, 0x8400, len(questions), len(records), 0, 0)
    return header + q + b"".join(records)


# DNS


def test_pregunta_y_respuesta_con_nombres_comprimidos():
    query = dns.build_query([("_ipp._tcp.local", dns.PTR)], query_id=7)
    parsed = dns.parse(query)
    assert parsed.id == 7 and not parsed.is_response and parsed.questions == [("_ipp._tcp.local", dns.PTR)]

    # «HP._ipp._tcp.local» apunta (0xC0 0x0C) al nombre de la pregunta, en el byte 12
    data = bytearray(struct.pack("!HHHHHH", 0, 0x8400, 1, 1, 0, 0))
    data += dns.encode_name("_ipp._tcp.local") + struct.pack("!HH", dns.PTR, 1)
    target = b"\x02HP\xc0\x0c"
    data += b"\xc0\x0c" + struct.pack("!HHIH", dns.PTR, 1, 120, len(target)) + target
    msg = dns.parse(bytes(data))
    assert msg.records[0].data == "HP._ipp._tcp.local"


def test_registros_srv_txt_a():
    data = response(
        [
            rr("HP._ipp._tcp.local", dns.SRV, struct.pack("!HHH", 0, 0, 631) + dns.encode_name("hp.local")),
            rr("HP._ipp._tcp.local", dns.TXT, txt("ty=HP LaserJet", "note=Despacho", "raro")),
            rr("hp.local", dns.A, socket.inet_aton("192.168.1.40")),
        ]
    )
    srv, text, a = dns.parse(data).records
    assert srv.data == (0, 0, 631, "hp.local")
    assert dns.txt_dict(text.data) == {"ty": "HP LaserJet", "note": "Despacho"}
    assert a.data == ipaddress.IPv4Address("192.168.1.40")


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x00" * 11,
        struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\xc0\x0c",  # puntero a sí mismo
        struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\x3fabc",  # etiqueta que se sale
        struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\x00" + struct.pack("!HHIH", 1, 1, 0, 400),
        struct.pack("!HHHHHH", 0, 0x8400, 5, 0, 0, 0),  # dice 5 preguntas y no trae ninguna
    ],
)
def test_paquetes_rotos_no_cuelgan_ni_rompen(data):
    with pytest.raises(dns.BadPacket):
        dns.parse(data)


def test_nombres_demasiado_largos_no_se_preguntan():
    with pytest.raises(ValueError):
        dns.encode_name("a" * 64 + ".local")
    assert dns.reverse_name("192.168.1.23") == "23.1.168.192.in-addr.arpa"


# mDNS


def test_mdns_junta_cada_anuncio_con_su_aparato():
    collector = mdns.Collector(ipaddress.ip_network("192.168.1.0/24"))
    iphone = response(
        [
            rr("23.1.168.192.in-addr.arpa", dns.PTR, dns.encode_name("iPhone-de-Ana.local")),
            rr("_services._dns-sd._udp.local", dns.PTR, dns.encode_name("_companion-link._tcp.local")),
            rr("_companion-link._tcp.local", dns.PTR, dns.encode_name("iPhone de Ana._companion-link._tcp.local")),
            rr(
                "iPhone de Ana._companion-link._tcp.local",
                dns.SRV,
                struct.pack("!HHH", 0, 0, 49152) + dns.encode_name("iPhone-de-Ana.local"),
            ),
            rr("iPhone de Ana._companion-link._tcp.local", dns.TXT, txt("rpMd=iPhone15,2")),
            rr("iPhone-de-Ana.local", dns.A, socket.inet_aton("192.168.1.23")),
            rr("iPhone de Ana._device-info._tcp.local", dns.TXT, txt("model=iPhone15,2")),
        ]
    )
    collector.handle("192.168.1.23", 5353, iphone)
    # Un Apple TV que contesta por un Mac dormido: va al Mac, por su registro A.
    proxy = response(
        [
            rr("Mac de Pablo._smb._tcp.local", dns.SRV, struct.pack("!HHH", 0, 0, 445) + dns.encode_name("mac.local")),
            rr("mac.local", dns.A, socket.inet_aton("192.168.1.35")),
        ]
    )
    collector.handle("192.168.1.31", 5353, proxy)
    collector.handle("8.8.8.8", 5353, iphone)  # de fuera de la red: ni caso
    collector.handle("192.168.1.50", 5353, b"basura")

    found = collector.result()
    ip = ipaddress.IPv4Address
    info = found[ip("192.168.1.23")]
    assert info.hostname == "iPhone-de-Ana.local" and info.model == "iPhone15,2"
    (service,) = info.services
    assert (service.type, service.name, service.port, service.txt) == (
        "_companion-link._tcp",
        "iPhone de Ana",
        49152,
        {"rpmd": "iPhone15,2"},
    )
    assert [s.name for s in found[ip("192.168.1.35")].services] == ["Mac de Pablo"]
    assert ip("192.168.1.31") not in found and ip("8.8.8.8") not in found


def serve_udp(handler):
    """Un respondedor UDP en 127.0.0.1, en un puerto libre. Devuelve el puerto."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(5)

    def loop():
        try:
            while True:
                data, addr = sock.recvfrom(9000)
                for reply in handler(data):
                    sock.sendto(reply, addr)
        except OSError:
            pass

    threading.Thread(target=loop, daemon=True).start()
    return sock.getsockname()[1]


def test_mdns_pregunta_y_sigue_el_hilo_con_sockets_de_verdad():
    asked = []

    def device(data):
        msg = dns.parse(data)
        asked.extend(msg.questions)
        records = []
        for name, _qtype in msg.questions:
            if name == "_services._dns-sd._udp.local":
                records.append(rr(name, dns.PTR, dns.encode_name("_ipp._tcp.local")))
            elif name == "_ipp._tcp.local":
                records.append(rr(name, dns.PTR, dns.encode_name("HP M110w._ipp._tcp.local")))
            elif name == "HP M110w._ipp._tcp.local":
                records.append(rr(name, dns.TXT, txt("ty=HP LaserJet M110w")))
                records.append(rr(name, dns.SRV, struct.pack("!HHH", 0, 0, 631) + dns.encode_name("hp.local")))
        yield response(records, msg.questions, msg.id) if records else b""

    port = serve_udp(lambda data: [r for r in device(data) if r])
    found = mdns.query("127.0.0.1", LOCAL, ["127.0.0.1"], wait=0.4, port=port, group=None)
    (service,) = found[ipaddress.IPv4Address("127.0.0.1")].services
    assert service.txt == {"ty": "HP LaserJet M110w"} and service.port == 631
    # Primero qué servicios tiene; luego el anuncio entero de cada uno.
    assert ("_ipp._tcp.local", dns.PTR) in asked and ("HP M110w._ipp._tcp.local", dns.ANY) in asked


# NetBIOS


def nbstat_reply(query: bytes, names, mac="f0:d5:bf:12:34:56") -> bytes:
    rdata = bytes([len(names)])
    for name, suffix, flags in names:
        rdata += name.encode().ljust(15, b" ") + bytes([suffix]) + struct.pack("!H", flags)
    rdata += bytes.fromhex(mac.replace(":", "")) + b"\x00" * 40
    return (
        query[:2]
        + struct.pack("!HHHHH", 0x8400, 0, 1, 0, 0)
        + query[12:46]
        + struct.pack("!HHIH", 0x21, 1, 0, len(rdata))
        + rdata
    )


def test_netbios_pregunta_bien_codificada():
    query = netbios.build_query(1)
    assert query[13:45] == b"CK" + b"A" * 30  # «*» y quince ceros, a la manera de NetBIOS
    assert query[-4:] == struct.pack("!HH", 0x21, 1)


def test_netbios_nombre_grupo_y_mac():
    names = [("PORTATIL-ANA", 0x00, 0x0400), ("WORKGROUP", 0x00, 0x8400), ("PORTATIL-ANA", 0x20, 0x0400)]
    info = netbios.parse_response(nbstat_reply(netbios.build_query(1), names))
    assert (info.name, info.workgroup, info.shares_files, info.mac) == (
        "PORTATIL-ANA",
        "WORKGROUP",
        True,
        "F0:D5:BF:12:34:56",
    )
    samba = netbios.parse_response(nbstat_reply(netbios.build_query(1), names[:2], mac="00:00:00:00:00:00"))
    assert samba.mac == ""  # Samba da ceros: no es una MAC


@pytest.mark.parametrize("data", [b"", b"\x00" * 12, netbios.build_query(1), b"\x00\x01\x84\x00" + b"\xff" * 60])
def test_netbios_respuestas_raras(data):
    assert netbios.parse_response(data) is None


def test_netbios_con_sockets_de_verdad():
    names = [("NAS-CASA", 0x00, 0x0400), ("WORKGROUP", 0x00, 0x8400)]
    port = serve_udp(lambda q: [nbstat_reply(q, names, "00:11:32:aa:bb:cc")])
    found = netbios.query("127.0.0.1", LOCAL, ["127.0.0.1"], wait=0.4, port=port)
    assert found[ipaddress.IPv4Address("127.0.0.1")].name == "NAS-CASA"


# SSDP / UPnP

DESCRIPTION = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
    <friendlyName>[TV] Tele del salón</friendlyName>
    <manufacturer>Samsung Electronics</manufacturer>
    <modelName>QE55Q60B</modelName>
    <deviceList><device><deviceType>urn:x:device:Dial:1</deviceType><friendlyName>Dial</friendlyName></device>
    </deviceList>
  </device>
</root>"""


def test_cabeceras_ssdp():
    data = (
        b"HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.31:9197/dmr\r\nSERVER: SHP, UPnP/1.0\r\n"
        b"ST: upnp:rootdevice\r\n\r\n"
    )
    headers = ssdp.parse_headers(data)
    assert headers["location"] == "http://192.168.1.31:9197/dmr" and headers["st"] == "upnp:rootdevice"
    assert ssdp.parse_headers(b"M-SEARCH * HTTP/1.1\r\n\r\n") == {}


def test_ficha_upnp_con_aparatos_dentro():
    devices = ssdp.parse_description(DESCRIPTION)
    assert [d.friendlyName for d in devices] == ["[TV] Tele del salón", "Dial"]
    assert devices[0].modelName == "QE55Q60B"


def test_ficha_con_entidades_se_descarta():
    bomb = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><root>&b;</root>'
    assert ssdp.parse_description(bomb) == []
    assert ssdp.parse_description("<root><device>") == []


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://192.168.1.31:9197/dmr", True),
        ("http://192.168.1.99/desc.xml", False),  # otra IP que la que contesta
        ("https://192.168.1.31/desc.xml", False),
        ("http://example.com/desc.xml", False),
        ("http://192.168.1.31:abc/", False),
    ],
)
def test_solo_fichas_del_propio_aparato(url, ok):
    assert ssdp.location_allowed(url, ipaddress.IPv4Address("192.168.1.31")) is ok


def test_ssdp_con_sockets_y_ficha_de_verdad():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = DESCRIPTION.encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    location = f"http://127.0.0.1:{server.server_address[1]}/dmr"
    reply = f"HTTP/1.1 200 OK\r\nLOCATION: {location}\r\nSERVER: Linux/4.1 UPnP/1.0\r\nST: upnp:rootdevice\r\n\r\n"
    port = serve_udp(lambda q: [reply.encode()] if q.startswith(b"M-SEARCH") else [])
    try:
        found = ssdp.query("127.0.0.1", LOCAL, ["127.0.0.1"], wait=0.4, port=port, group=None)
    finally:
        server.shutdown()
    info = found[ipaddress.IPv4Address("127.0.0.1")]
    assert info.server == "Linux/4.1 UPnP/1.0" and info.devices[0].manufacturer == "Samsung Electronics"
