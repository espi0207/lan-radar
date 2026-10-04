# Receta de PyInstaller para el programa de Windows y la app de macOS:
#     pyinstaller --noconfirm packaging/lan-radar.spec
# Deja el resultado en dist/lan-radar (y dist/lan-radar.app en macOS).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from lanradar import __version__  # noqa: E402

icon = str(root / "packaging" / "icon.png")  # PyInstaller lo pasa a .ico o .icns con Pillow

a = Analysis(
    [str(root / "packaging" / "lan-radar-app.py")],
    pathex=[str(root)],
    datas=collect_data_files("lanradar"),  # el icono y la lista de fabricantes
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lan-radar", console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="lan-radar")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="lan-radar.app",
        icon=icon,
        bundle_identifier="io.github.espi0207.lanradar",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": "lan-radar",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # Desde macOS 15, una app tiene que pedir permiso para hablar con la red local, y
            # decir para qué (es el texto del aviso) y qué servicios de Bonjour pregunta.
            "NSLocalNetworkUsageDescription": "lan-radar busca los aparatos conectados a tu red de casa y les "
            "pregunta quiénes son (nombre, marca y modelo).",
            "NSBonjourServices": [
                "_services._dns-sd._udp", "_googlecast._tcp", "_airplay._tcp", "_raop._tcp", "_ipp._tcp",
                "_printer._tcp", "_pdl-datastream._tcp", "_hap._tcp", "_companion-link._tcp",
                "_apple-mobdev2._tcp", "_spotify-connect._tcp", "_sonos._tcp", "_amzn-wplay._tcp",
                "_androidtvremote2._tcp", "_smb._tcp", "_workstation._tcp", "_hue._tcp", "_esphomelib._tcp",
                "_matter._tcp", "_home-assistant._tcp", "_shelly._tcp", "_uscan._tcp", "_ssh._tcp",
                "_device-info._tcp",
            ],
        },
    )
