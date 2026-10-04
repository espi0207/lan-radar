from datetime import datetime, timedelta

import pytest

from lanradar import demo
from lanradar.catalog import (
    CAMERA,
    COMPUTER,
    CONSOLE,
    MOBILE,
    PRINTER,
    ROUTER,
    SMART_HOME,
    SPEAKER,
    STREAMER,
    TV,
    UNKNOWN,
)
from lanradar.device import (
    ALTA,
    MEDIA,
    NUEVO,
    Device,
    apple_model,
    finish,
    observations,
    os_from_banner,
    os_from_server,
)
from lanradar.history import History, network_key


def svc(stype, name="", port=0, **txt):
    return {"type": stype, "name": name, "port": port, "txt": txt}


@pytest.mark.parametrize(
    ("device", "kind"),
    [
        (Device("1", "00:0E:59:3A:7B:01", is_gateway=True), ROUTER),
        (Device("1", "DA:A1:19:5E:22:01", ports=[62078]), MOBILE),
        (Device("1", "BC:D0:74:11:22:33", services=[svc("_companion-link._tcp", "Ana", rpmd="iPhone14,5")]), MOBILE),
        (Device("1", services=[svc("_googlecast._tcp", "x", md="Chromecast")]), STREAMER),
        (Device("1", services=[svc("_googlecast._tcp", "x", md="Google Nest Mini")]), SPEAKER),
        (Device("1", services=[svc("_googlecast._tcp", "x", md="BRAVIA 4K VH2")]), TV),
        (Device("1", "9C:8E:99:00:00:01", ports=[631, 9100]), PRINTER),
        (Device("1", "00:BC:99:44:55:66", ports=[554]), CAMERA),
        (Device("1", "00:D9:D1:7A:31:B5"), CONSOLE),
        (Device("1", dns_name="PS5-123.home"), CONSOLE),
        (Device("1", "A4:CF:12:00:00:01"), SMART_HOME),
        (Device("1", netbios_name="PORTATIL-ANA", ports=[445]), COMPUTER),
        (Device("1", "6E:3B:90:11:A4:0C", dns_name="Galaxy-S23.home"), MOBILE),
        (Device("1"), UNKNOWN),
    ],
)
def test_tipo_de_aparato(device, kind):
    assert finish(device).kind == kind


def test_dice_por_que():
    device = finish(Device("1", "DA:A1:19:5E:22:01", ports=[62078], mdns_name="iPhone-de-Ana.local"))
    assert device.confidence == "seguro"
    assert any("62078" in r for r in device.reasons) and any("iPhone" in r for r in device.reasons)
    weak = finish(Device("1", "44:65:0D:8E:2F:10"))  # solo la marca: Amazon
    assert (weak.kind, weak.confidence) == (SPEAKER, "puede")
    assert weak.kind_label() == "Altavoz (puede)"


def test_modelos_de_apple():
    assert apple_model("iPhone15,2") == ("iPhone 14 Pro (iPhone15,2)", MOBILE, "iOS")
    assert apple_model("MacBookAir10,1")[0] == "MacBook Air (MacBookAir10,1)"
    assert apple_model("AudioAccessory5,1")[1] == SPEAKER
    assert apple_model("Chromecast") == ("", None, "")
    device = finish(Device("1", services=[svc("_airplay._tcp", "Salón", model="AppleTV11,1")]))
    assert (device.kind, device.model, device.os, device.manufacturer) == (
        STREAMER,
        "Apple TV (AppleTV11,1)",
        "tvOS",
        "Apple",
    )


def test_modelo_del_anuncio_antes_que_el_de_la_ficha_upnp():
    device = finish(
        Device(
            "1",
            services=[svc("_googlecast._tcp", "Chromecast-1a2b3c4d5e6f7a8b9c0d", md="Chromecast", fn="Salón")],
            upnp=[{"deviceType": "urn:dial-multiscreen-org:device:dial:1", "modelName": "Eureka Dongle"}],
        )
    )
    assert device.model == "Chromecast" and device.name() == "Salón"


def test_sistema():
    assert os_from_banner("SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3") == "Debian"
    assert os_from_banner("SSH-2.0-OpenSSH_for_Windows_8.1") == "Windows"
    assert os_from_banner("SSH-2.0-dropbear_2020.81") == "Linux (aparato pequeño)"
    assert os_from_server("Linux/4.1.52 UPnP/1.0 MiniUPnPd/2.1") == "Linux 4.1.52"
    assert os_from_server("Microsoft-Windows/10.0 UPnP/1.0") == "Windows 10.0"
    assert os_from_server("SHP, UPnP/1.0, Samsung UPnP SDK/1.0") == ""


def test_nombres_que_no_son_nombres():
    device = finish(Device("1", services=[svc("_googlecast._tcp", "Chromecast-1a2b3c4d5e6f7a8b9c0d1e2f")]))
    assert device.friendly_name == ""
    linux = finish(Device("1", mdns_name="nas.local", services=[svc("_workstation._tcp", "nas [00:11:32:aa:bb:cc]")]))
    assert linux.friendly_name == "" and linux.mac == "00:11:32:AA:BB:CC"  # la MAC, del anuncio


def test_avisos():
    camera = finish(Device("1", "00:BC:99:44:55:66", ports=[23, 554]))
    assert camera.notes[0]["level"] == ALTA and "Telnet" in camera.notes[0]["text"]
    router = finish(
        Device(
            "1",
            is_gateway=True,
            ports=[80],
            upnp=[{"deviceType": "urn:schemas-upnp-org:device:InternetGatewayDevice:1"}],
        )
    )
    assert [n["level"] for n in router.notes][:1] == [MEDIA] and "UPnP" in router.notes[0]["text"]
    quiet = finish(Device("1", "A4:CF:12:00:00:01"))
    assert all(n["level"] not in (ALTA, MEDIA) for n in quiet.notes)


def test_la_demo_pasa_por_el_mismo_codigo():
    result = demo.result()
    kinds = {d.ip: d.kind for d in result.devices}
    assert kinds["192.168.1.1"] == ROUTER and kinds["192.168.1.40"] == PRINTER and kinds["192.168.1.20"] == MOBILE
    assert sum(d.is_new for d in result.devices) == 1


def test_historial_nuevos_nombres_y_los_que_faltan(tmp_path):
    history = History(tmp_path / "conocidos.json")
    key = network_key("192.168.1.0/24", "00:0E:59:3A:7B:01")
    day1 = datetime(2026, 10, 1, 20, 0)
    first = [finish(Device("192.168.1.20", "DA:A1:19:5E:22:01")), finish(Device("192.168.1.30", "F4:F5:D8:6C:11:02"))]
    assert history.record(key, "192.168.1.0/24", first, day1) == []
    assert not any(d.is_new for d in first)  # la primera vez todo es "lo de siempre"
    history.rename(key, "F4:F5:D8:6C:11:02", "Chromecast del salón")
    history.save()

    again = History(tmp_path / "conocidos.json")
    second = [
        finish(Device("192.168.1.21", "DA:A1:19:5E:22:01")),  # otra IP, misma MAC: el mismo
        finish(Device("192.168.1.66", "3A:F1:07:C2:55:9E")),
    ]
    missing = again.record(key, "192.168.1.0/24", second, day1 + timedelta(days=1))
    assert [d.is_new for d in second] == [False, True]
    assert [m["key"] for m in missing] == ["F4:F5:D8:6C:11:02"] and missing[0]["nickname"] == "Chromecast del salón"
    assert not again.is_first_scan(key)


def test_historial_roto_no_impide_nada(tmp_path):
    path = tmp_path / "conocidos.json"
    path.write_text("{esto no es json", encoding="utf-8")
    history = History(path)
    devices = [finish(Device("192.168.1.20", "DA:A1:19:5E:22:01"))]
    history.record("red:x", "x", devices)
    history.save()
    assert "DA:A1:19:5E:22:01" in History(path).network("red:x")["devices"]


def test_nuevo_lleva_aviso():
    device = finish(Device("1", "3A:F1:07:C2:55:9E"))
    device.is_new = True
    assert observations(device)[0]["level"] == NUEVO


def test_router_con_proxy_arp_no_llena_la_lista_de_fantasmas():
    from ipaddress import IPv4Address as ip

    from lanradar.scan import _without_proxy_arp

    router = "00:0E:59:3A:7B:01"
    macs = {ip(f"192.168.1.{n}"): router for n in range(1, 60)}
    macs[ip("192.168.1.70")] = "DA:A1:19:5E:22:01"
    kept = _without_proxy_arp(macs, keep={ip("192.168.1.1"), ip("192.168.1.34")})
    assert set(kept) == {ip("192.168.1.1"), ip("192.168.1.34"), ip("192.168.1.70")}
    few = {ip("192.168.1.1"): router, ip("192.168.1.2"): router}  # dos con la misma: eso es normal
    assert _without_proxy_arp(few, keep=set()) == few


def test_mac_compartida_por_un_repetidor():
    device = finish(Device("192.168.1.80", "00:0E:59:3A:7B:01"))
    device.shared_mac = True
    assert device.key() == "00:0E:59:3A:7B:01@192.168.1.80"
    assert any("repetidor" in n["text"] for n in observations(device))
