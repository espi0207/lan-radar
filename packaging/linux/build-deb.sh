#!/bin/sh
# Construye dist/lan-radar-linux.deb para Ubuntu, Debian, Linux Mint y derivados.
#
# No lleva un Python dentro: instala el paquete tal cual y usa el Python del sistema, más
# python3-tk para la ventana. Por eso pesa unos pocos KB y vale para cualquier
# arquitectura. Uso: packaging/linux/build-deb.sh
set -eu

root=$(cd "$(dirname "$0")/../.." && pwd)
version=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$root/lanradar/__init__.py")
pkg=$(mktemp -d)
trap 'rm -rf "$pkg"' EXIT
chmod 755 "$pkg"  # mktemp la crea solo para su dueño, y es la raíz del paquete

mkdir -p "$pkg/DEBIAN" "$pkg/usr/bin" "$pkg/usr/lib/python3/dist-packages" \
  "$pkg/usr/share/applications" "$pkg/usr/share/doc/lan-radar" \
  "$pkg/usr/share/icons/hicolor/scalable/apps" "$pkg/usr/share/icons/hicolor/256x256/apps"

cp -r "$root/lanradar" "$pkg/usr/lib/python3/dist-packages/"
find "$pkg" -name __pycache__ -prune -exec rm -rf {} +

cat > "$pkg/usr/bin/lan-radar" <<'PY'
#!/usr/bin/python3
from lanradar.__main__ import main

raise SystemExit(main())
PY
cat > "$pkg/usr/bin/lan-radar-app" <<'PY'
#!/usr/bin/python3
from lanradar.gui import main

main()
PY
chmod 755 "$pkg/usr/bin/lan-radar" "$pkg/usr/bin/lan-radar-app"

cp "$root/packaging/linux/lan-radar.desktop" "$pkg/usr/share/applications/"
cp "$root/packaging/icon.svg" "$pkg/usr/share/icons/hicolor/scalable/apps/lan-radar.svg"
cp "$root/lanradar/icon.png" "$pkg/usr/share/icons/hicolor/256x256/apps/lan-radar.png"
cp "$root/LICENSE" "$pkg/usr/share/doc/lan-radar/copyright"

cat > "$pkg/DEBIAN/control" <<CONTROL
Package: lan-radar
Version: $version
Architecture: all
Maintainer: espi0207 <espi0207@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-tk
Section: net
Priority: optional
Homepage: https://github.com/espi0207/lan-radar
Description: quién está conectado a tu wifi
 Lista los aparatos de la red de casa con todo lo que cuentan de sí mismos:
 fabricante (por la MAC), nombre, modelo, sistema y servicios (Bonjour, UPnP,
 NetBIOS). Avisa de los aparatos nuevos y de lo que conviene revisar. Solo
 revisa la red privada a la que está conectado el ordenador.
CONTROL

# Compilar a bytecode al instalar (como hacen los paquetes de Python de Debian) y
# limpiarlo al desinstalar, que dpkg no sabe que esos archivos son del paquete.
cat > "$pkg/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
python3 -m compileall -q /usr/lib/python3/dist-packages/lanradar >/dev/null 2>&1 || true
SH
cat > "$pkg/DEBIAN/prerm" <<'SH'
#!/bin/sh
set -e
rm -rf /usr/lib/python3/dist-packages/lanradar/__pycache__
SH
chmod 755 "$pkg/DEBIAN/postinst" "$pkg/DEBIAN/prerm"

mkdir -p "$root/dist"
dpkg-deb --build --root-owner-group "$pkg" "$root/dist/lan-radar-linux.deb"
