import ipaddress

import pytest

from lanradar import arp, oui


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),
        ("AA-BB-CC-DD-EE-FF", "AA:BB:CC:DD:EE:FF"),
        ("aabb.ccdd.eeff", "AA:BB:CC:DD:EE:FF"),
        ("0:1b:2:a:b:c", "00:1B:02:0A:0B:0C"),  # macOS se come los ceros
        ("aabbccddeeff", "AA:BB:CC:DD:EE:FF"),
        ("no es una mac", ""),
        ("aa:bb:cc", ""),
    ],
)
def test_normaliza_macs(raw, norm):
    assert oui.normalize(raw) == norm


def test_fabricantes():
    assert oui.vendor("BC:D0:74:11:22:33") == "Apple, Inc."
    assert oui.short_vendor(oui.vendor("DC:A6:32:00:00:01")) == "Raspberry Pi"
    assert oui.short_vendor("TP-LINK TECHNOLOGIES CO.,LTD.") == "TP-Link"
    assert oui.short_vendor("Shenzhen Foo Technology Co.,Ltd") == "Shenzhen Foo"
    assert oui.short_vendor("NETGEAR") == "Netgear"
    assert oui.vendor("00:00:00:00:00:00") == "XEROX CORPORATION"  # el primero que asignó el IEEE


def test_la_lista_de_fabricantes_va_entera():
    assert len(oui._table()) > 35_000


def test_mac_privada():
    assert oui.is_random("DA:A1:19:5E:22:01")  # el segundo bit del primer byte
    assert not oui.is_random("BC:D0:74:11:22:33")
    assert oui.vendor("DA:A1:19:5E:22:01") == ""  # una inventada no tiene fabricante


def test_lo_que_no_es_un_aparato():
    assert not oui.is_device("FF:FF:FF:FF:FF:FF")
    assert not oui.is_device("01:00:5E:00:00:16")  # multidifusión
    assert not oui.is_device("00:00:00:00:00:00")
    assert oui.is_device("BC:D0:74:11:22:33")


PROC = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         00:0e:59:3a:7b:01     *        wlan0
192.168.1.20     0x1         0x2         da:a1:19:5e:22:01     *        wlan0
192.168.1.99     0x1         0x0         00:00:00:00:00:00     *        wlan0
"""

IP_NEIGH = """192.168.1.1 dev wlan0 lladdr 00:0e:59:3a:7b:01 REACHABLE
192.168.1.20 dev wlan0 lladdr da:a1:19:5e:22:01 STALE
192.168.1.99 dev wlan0  FAILED
192.168.1.98 dev wlan0 lladdr 11:22:33:44:55:66 FAILED
"""

ARP_MAC = """? (192.168.1.1) at 0:e:59:3a:7b:1 on en0 ifscope [ethernet]
? (192.168.1.20) at da:a1:19:5e:22:1 on en0 ifscope [ethernet]
? (192.168.1.99) at (incomplete) on en0 ifscope [ethernet]
? (224.0.0.251) at 1:0:5e:0:0:fb on en0 ifscope permanent [ethernet]
"""

ARP_WINDOWS = """
Interfaz: 192.168.1.34 --- 0xc
  Dirección de Internet          Dirección física      Tipo
  192.168.1.1           00-0e-59-3a-7b-01     dinámico
  192.168.1.20          da-a1-19-5e-22-01     dinámico
  192.168.1.255         ff-ff-ff-ff-ff-ff     estático
"""


@pytest.mark.parametrize(
    ("parse", "text"),
    [(arp.parse_proc, PROC), (arp.parse_ip_neigh, IP_NEIGH), (arp.parse_arp, ARP_MAC), (arp.parse_arp, ARP_WINDOWS)],
)
def test_tabla_arp_de_cada_sistema(parse, text):
    found = {ip: mac for ip, mac in parse(text).items() if oui.is_device(mac)}
    assert found == {"192.168.1.1": "00:0E:59:3A:7B:01", "192.168.1.20": "DA:A1:19:5E:22:01"}


def test_tabla_del_sistema_sin_difusion_ni_multidifusion(monkeypatch):
    monkeypatch.setattr(arp.sys, "platform", "win32")
    monkeypatch.setattr(arp.net, "_run", lambda _cmd: ARP_WINDOWS)
    assert arp.table() == {
        ipaddress.IPv4Address("192.168.1.1"): "00:0E:59:3A:7B:01",
        ipaddress.IPv4Address("192.168.1.20"): "DA:A1:19:5E:22:01",
    }
