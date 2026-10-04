import ipaddress

import pytest

from lanradar import net

IP_ADDR = """1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever
3: wlan0    inet 192.168.1.23/24 brd 192.168.1.255 scope global dynamic wlan0\\       valid_lft 86000sec
4: docker0    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0\\       valid_lft forever
"""

IP_ROUTE = "default via 192.168.1.1 dev wlan0 proto dhcp metric 600\n"

MAC_IFCONFIG = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tether 3c:22:fb:1:a:5f
\tinet6 fe80::1c8a:2b4d:9b3e:1f2a%en0 prefixlen 64 secured scopeid 0xe
\tinet 192.168.1.23 netmask 0xffffff00 broadcast 192.168.1.255
utun3: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
\tinet 10.8.0.2 --> 10.8.0.1 netmask 0xffffff00
"""

ROUTE_GET = """   route to: default
destination: default
       mask: default
    gateway: 192.168.1.1
  interface: en0
"""

OLD_IFCONFIG = """wlan0     Link encap:Ethernet  HWaddr b8:27:eb:12:34:56
          inet addr:192.168.0.17  Bcast:192.168.0.255  Mask:255.255.255.0
"""

IPCONFIG_ES = """
Configuración IP de Windows

   Nombre de host. . . . . . . . . : PORTATIL-ANA

Adaptador de Ethernet Ethernet:

   Estado de los medios. . . . . . . . . . . : medios desconectados
   Dirección física. . . . . . . . . . . . . : 00-D8-61-AA-BB-CC

Adaptador de LAN inalámbrica Wi-Fi:

   Sufijo DNS específico para la conexión. . : home
   Dirección física. . . . . . . . . . . . . : 8C-C6-81-12-34-56
   Vínculo: dirección IPv6 local. . . : fe80::5d2c:1a2b:3c4d:5e6f%12(Preferido)
   Dirección IPv4. . . . . . . . . . . . . . : 192.168.1.34(Preferido)
   Máscara de subred . . . . . . . . . . . . : 255.255.255.0
   Puerta de enlace predeterminada . . . . . : fe80::1%12
                                               192.168.1.1
   Servidor DHCP . . . . . . . . . . . . . . : 192.168.1.1
"""

IPCONFIG_EN = """
Wireless LAN adapter Wi-Fi:

   Physical Address. . . . . . . . . : 8C-C6-81-12-34-56
   IPv4 Address. . . . . . . . . . . : 10.0.0.7(Preferred)
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 10.0.0.1
   DHCP Server . . . . . . . . . . . : 10.0.0.1
"""


@pytest.mark.parametrize("text", ["192.168.1.0/24", "10.0.0.0/22", "172.16.5.0/24", "192.168.1.77"])
def test_acepta_redes_de_casa(text):
    assert net.parse_network(text).version == 4


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("8.8.8.0/24", "no es una red privada"),
        ("192.0.2.0/24", "no es una red privada"),
        ("100.64.0.0/24", "no es una red privada"),
        ("10.0.0.0/21", "demasiado grande"),
        ("10.0.0.0/8", "demasiado grande"),
        ("fd00::/64", "IPv4"),
        ("hola", "no entiendo"),
    ],
)
def test_rechaza_lo_que_no_es_una_red_de_casa(text, why):
    with pytest.raises(net.NotAllowed, match=why):
        net.parse_network(text)


def local(cidr="192.168.1.0/24", ip="192.168.1.23"):
    return net.LocalNet(ipaddress.ip_network(cidr), ipaddress.ip_address(ip), "wlan0")


def test_solo_la_red_a_la_que_esta_conectado():
    mine = [local()]
    target = net.choose_target(ipaddress.ip_network("192.168.1.0/25"), mine)
    assert str(target.network) == "192.168.1.0/25" and target.interface == "wlan0"
    with pytest.raises(net.NotAllowed, match="no es la red de este ordenador"):
        net.choose_target(ipaddress.ip_network("192.168.2.0/24"), mine)


def test_en_una_red_grande_solo_su_trozo():
    big = local("10.20.0.0/16", "10.20.30.40")
    assert str(net.default_target(big)) == "10.20.30.0/24"
    assert net.default_target(local()) == local().network


def test_linux_ip_addr_y_route():
    nets = net.parse_ip_addr(IP_ADDR, {"wlan0": "aa:bb:cc:00:11:22"}, net.parse_ip_route(IP_ROUTE))
    wlan = next(n for n in nets if n.interface == "wlan0")
    assert str(wlan.network) == "192.168.1.0/24" and str(wlan.address) == "192.168.1.23"
    assert wlan.mac == "AA:BB:CC:00:11:22" and str(wlan.gateway) == "192.168.1.1"
    assert all(not n.address.is_loopback for n in nets)


def test_macos_ifconfig_con_mascara_hexadecimal():
    nets = net.parse_ifconfig(MAC_IFCONFIG, *net.parse_route_get(ROUTE_GET))
    en0 = nets[0]
    assert (str(en0.network), en0.interface, en0.mac, str(en0.gateway)) == (
        "192.168.1.0/24",
        "en0",
        "3C:22:FB:01:0A:5F",
        "192.168.1.1",
    )
    assert nets[1].gateway is None  # la VPN no lleva al router


def test_ifconfig_antiguo_de_linux():
    (wlan,) = net.parse_ifconfig(OLD_IFCONFIG)
    assert str(wlan.network) == "192.168.0.0/24" and wlan.mac == "B8:27:EB:12:34:56"


def test_windows_en_espanol_con_la_puerta_de_enlace_en_otra_linea():
    (wifi,) = net.parse_ipconfig(IPCONFIG_ES)
    assert str(wifi.address) == "192.168.1.34" and str(wifi.gateway) == "192.168.1.1"
    assert wifi.mac == "8C:C6:81:12:34:56"


def test_windows_con_las_tildes_mal_descodificadas():
    garbled = IPCONFIG_ES.encode("cp850").decode("cp1252", errors="replace")
    (wifi,) = net.parse_ipconfig(garbled)
    assert str(wifi.network) == "192.168.1.0/24" and wifi.mac == "8C:C6:81:12:34:56"


def test_windows_en_ingles():
    (wifi,) = net.parse_ipconfig(IPCONFIG_EN)
    assert str(wifi.network) == "10.0.0.0/24" and str(wifi.gateway) == "10.0.0.1"


def test_hosts_sin_red_ni_difusion():
    hosts = net.hosts(ipaddress.ip_network("192.168.1.0/29"), skip=["192.168.1.3"])
    assert [str(h) for h in hosts] == ["192.168.1.1", "192.168.1.2", "192.168.1.4", "192.168.1.5", "192.168.1.6"]
