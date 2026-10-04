"""Una casa de ejemplo, para probar lan-radar (y la ventana) sin tocar ninguna red.

Los aparatos son inventados, pero lo que "cuentan" es lo que cuentan los de verdad (los
mismos anuncios, puertos y fichas), y pasan por el mismo código que una pasada real: el
tipo, el modelo y los avisos los saca lan-radar, no están escritos aquí.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .device import Device, finish, observations
from .scan import Result

NETWORK = "192.168.1.0/24"


def _svc(stype: str, name: str, port: int, **txt: str) -> dict:
    return {"type": stype, "name": name, "port": port, "txt": txt}


def devices() -> list[Device]:
    return [
        Device(
            "192.168.1.1",
            "00:0E:59:3A:7B:01",
            is_gateway=True,
            dns_name="router.home",
            upnp=[
                {
                    "deviceType": "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
                    "friendlyName": "Router de casa",
                    "manufacturer": "Sagemcom",
                    "modelName": "F@st 5657",
                }
            ],
            upnp_server="Linux/4.1.52 UPnP/1.0 MiniUPnPd/2.1",
            ports=[53, 80],
            web={"80": {"status": "200", "server": "lighttpd", "title": "Configuración del router"}},
        ),
        Device(
            "192.168.1.20",
            "DA:A1:19:5E:22:01",
            mdns_name="iPhone-de-Ana.local",
            dns_name="iPhone-de-Ana.home",
            services=[
                _svc("_companion-link._tcp", "iPhone de Ana", 49152, rpmd="iPhone15,2"),
                _svc("_apple-mobdev2._tcp", "da:a1:19:5e:22:01@fe80::1", 32498),
            ],
            ports=[62078],
        ),
        Device("192.168.1.21", "6E:3B:90:11:A4:0C", dns_name="Galaxy-S23-de-Pablo.home"),
        Device(
            "192.168.1.30",
            "F4:F5:D8:6C:11:02",
            services=[_svc("_googlecast._tcp", "Chromecast-1a2b3c4d5e6f7a8b9c0d", 8009, md="Chromecast", fn="Salón")],
            upnp=[
                {
                    "deviceType": "urn:dial-multiscreen-org:device:dial:1",
                    "friendlyName": "Salón",
                    "manufacturer": "Google Inc.",
                    "modelName": "Eureka Dongle",
                }
            ],
            ports=[8008, 8009],
        ),
        Device(
            "192.168.1.31",
            "8C:79:F5:12:34:56",
            mdns_name="Samsung-TV.local",
            services=[_svc("_airplay._tcp", "Tele del salón", 7000, manufacturer="Samsung", model="QE55Q60B")],
            upnp=[
                {
                    "deviceType": "urn:schemas-upnp-org:device:MediaRenderer:1",
                    "friendlyName": "[TV] Tele del salón",
                    "manufacturer": "Samsung Electronics",
                    "modelName": "QE55Q60B",
                }
            ],
            ports=[7000, 8080],
        ),
        Device(
            "192.168.1.34",
            "F0:D5:BF:12:34:56",
            is_self=True,
            netbios_name="PORTATIL-ANA",
            workgroup="WORKGROUP",
            dns_name="PORTATIL-ANA.home",
            ports=[139, 445],
        ),
        Device(
            "192.168.1.35",
            "A4:83:E7:20:91:3D",
            mdns_name="MacBook-Air-de-Pablo.local",
            services=[
                _svc("_companion-link._tcp", "MacBook Air de Pablo", 49153, rpmd="MacBookAir10,1"),
                _svc("_smb._tcp", "MacBook Air de Pablo", 445),
            ],
            ports=[445, 5000, 7000],
            web={"7000": {"status": "403", "server": "AirTunes/860.7.1"}},
        ),
        Device(
            "192.168.1.40",
            "9C:8E:99:5A:1B:2C",
            mdns_name="HP5A1B2C.local",
            services=[
                _svc("_ipp._tcp", "HP LaserJet M110w (5A1B2C)", 631, ty="HP LaserJet M110w", usb_mfg="HP"),
                _svc("_uscan._tcp", "HP LaserJet M110w (5A1B2C)", 8080, ty="HP LaserJet M110w"),
            ],
            ports=[80, 631, 9100],
            web={"80": {"status": "200", "server": "HP HTTP Server; HP LaserJet M110w", "title": "HP LaserJet M110w"}},
        ),
        Device("192.168.1.45", "44:65:0D:8E:2F:10", dns_name="amazon-1f2e3d4c5.home"),
        Device("192.168.1.50", "00:D9:D1:7A:31:B5", dns_name="PS5-de-Pablo.home", ports=[]),
        Device("192.168.1.60", "A4:CF:12:9F:00:01", dns_name="ESP_9F0001.home"),
        Device("192.168.1.61", "50:91:E3:62:4A:7C", dns_name="Tapo_C200_4A7C.home", ports=[554, 2020]),
        Device(
            "192.168.1.70",
            "DC:A6:32:AB:CD:EF",
            mdns_name="homeassistant.local",
            services=[_svc("_home-assistant._tcp", "Casa", 8123, version="2025.9.1")],
            ports=[22, 8123],
            banners={"22": "SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3"},
            web={"8123": {"status": "200", "server": "Python/3.13 aiohttp/3.12", "title": "Home Assistant"}},
        ),
        Device(
            "192.168.1.80",
            "00:BC:99:44:55:66",
            ports=[23, 80, 554],
            web={"80": {"status": "200", "server": "webs", "title": "Web Client"}},
        ),
        Device("192.168.1.112", "3A:F1:07:C2:55:9E"),
    ]


def result(now: datetime | None = None) -> Result:
    now = now or datetime.now()
    found = [finish(d) for d in devices()]
    earlier = (now - timedelta(days=41)).isoformat(timespec="seconds")
    for device in found:
        device.first_seen = earlier
        device.last_seen = now.isoformat(timespec="seconds")
        if device.ip == "192.168.1.112":  # el que no estaba la otra vez
            device.is_new = True
            device.first_seen = device.last_seen
        if device.ip == "192.168.1.60":
            device.nickname = "Enchufe de la cafetera"
        device.notes = observations(device)
    missing = [
        {
            "key": "B0:BE:83:12:9A:01",
            "name": "Portátil de Juan",
            "kind": "Ordenador",
            "ip": "192.168.1.36",
            "brand": "Apple",
            "last_seen": (now - timedelta(days=3, hours=2)).isoformat(timespec="seconds"),
        }
    ]
    return Result(
        network=NETWORK,
        interface="Wi-Fi",
        address="192.168.1.34",
        gateway="192.168.1.1",
        started=now.isoformat(timespec="seconds"),
        seconds=14.2,
        network_key="demo",
        devices=found,
        missing=missing,
    )
