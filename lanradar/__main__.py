"""Uso desde la terminal. Sin nada más, revisa la red del wifi de este ordenador."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap

from . import __version__, arp, demo, net
from .ansi import clean, paint
from .device import ALTA, MEDIA
from .history import History, network_key
from .report import LEVEL_LABEL, ago, alerts, brand_text, details, display_name, headline, summary_line
from .scan import Result, scan


def print_table(result: Result) -> None:
    rows = [(d.ip, clean(display_name(d)), d.kind_label(), clean(brand_text(d)), d) for d in result.devices]
    widths = [max(len(r[i]) for r in rows + [("IP", "Nombre", "Tipo", "Marca", None)]) for i in range(4)]
    widths[1] = min(widths[1], 38)
    header = "  ".join(h.ljust(w) for h, w in zip(("IP", "Nombre", "Tipo", "Marca"), widths, strict=True))
    print(paint("  " + header.rstrip(), "bold"))
    for ip, name, kind, brand, device in rows:
        name = name if len(name) <= widths[1] else name[: widths[1] - 1] + "…"
        line = f"  {ip:<{widths[0]}}  {name:<{widths[1]}}  {kind:<{widths[2]}}  {brand:<{widths[3]}}"
        if device.is_new:
            print(paint(line.rstrip() + "  ← nuevo", "green", "bold"))
        elif any(n["level"] == ALTA for n in device.notes):
            print(paint(line.rstrip(), "red"))
        else:
            print(line.rstrip())


def print_details(result: Result) -> None:
    for device in result.devices:
        title = f"{device.ip}  {clean(display_name(device))}"
        print("\n" + paint(title, "bold") + (paint("  ← nuevo", "green", "bold") if device.is_new else ""))
        rows = details(device)
        width = max((len(label) for label, _ in rows), default=0) + 2
        for label, value in rows:
            lines = textwrap.wrap(clean(value), width=max(40, 100 - width)) or [""]
            print(f"  {paint(label.ljust(width), 'gray')}{lines[0]}")
            for more in lines[1:]:
                print(f"  {' ' * width}{more}")
        for note in device.notes:
            color = {ALTA: "red", MEDIA: "yellow"}.get(note["level"], "gray")
            print("  " + paint(f"{LEVEL_LABEL[note['level']]}: ", color, "bold") + note["text"])


def print_result(result: Result, detail: bool) -> None:
    print(paint(headline(result), "bold"))
    print(paint(summary_line(result), "gray") + "\n")
    if detail:
        print_details(result)
    else:
        print_table(result)

    found = alerts(result)
    if found:
        print("\n" + paint("Para revisar:", "bold"))
        for level, device, text in found:
            color = "red" if level == ALTA else "yellow"
            mark = paint("!" if level == ALTA else "·", color, "bold")
            lines = textwrap.wrap(f"{device.ip} {clean(device.name())}: {text}", width=96)
            print(f"  {mark} " + "\n    ".join(lines))
    new = [d for d in result.devices if d.is_new]
    if new:
        print(
            "\n"
            + paint(f"Nuevos desde la última vez: {len(new)}.", "green", "bold")
            + " Si alguno no te suena, mira su ficha (--detalle) o búscalo en la lista de tu router."
        )
    elif result.first_scan:
        print("\nEs la primera vez que miro esta red. Desde la próxima te diré qué aparatos son nuevos.")
    if result.missing:
        print("\n" + paint("Otras veces estaban, ahora no:", "bold"))
        for entry in result.missing[:8]:
            seen = ago(entry.get("last_seen", ""))
            print(f"  {clean(entry.get('name', '?'))} ({entry.get('kind', '')}, {entry.get('ip', '')}) — visto {seen}")
        if len(result.missing) > 8:
            print(f"  … y {len(result.missing) - 8} más")


def run_scan(args: argparse.Namespace) -> int:
    locals_ = net.local_networks()
    if args.red:
        local = net.choose_target(net.parse_network(args.red), locals_)
    elif locals_:
        local = locals_[0]
        local = net.choose_target(net.default_target(local), [local])
    else:
        print("No encuentro ninguna red privada en este ordenador. ¿Está conectado al wifi?", file=sys.stderr)
        return 2
    quiet = args.json == "-"
    if not quiet:
        print(paint(f"Revisando {local.label()} desde {local.address}…", "gray"), file=sys.stderr)

    def progress(text, _fraction):
        if not quiet and sys.stderr.isatty():
            print(f"\r\033[K{text}", end="", file=sys.stderr, flush=True)

    history = History()
    result = scan(local, services=not args.rapido, progress=progress, history=history)
    if not quiet and sys.stderr.isatty():
        print("\r\033[K", end="", file=sys.stderr, flush=True)
    return output(result, args)


def output(result: Result, args: argparse.Namespace) -> int:
    if args.json:
        data = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        if args.json == "-":
            print(data)
            return 0
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(data + "\n")
    print_result(result, args.detalle)
    if args.json:
        print(f"\nTodo guardado en {args.json}.")
    elif not args.detalle:
        print(paint("\nPara ver todo lo que cuenta cada aparato: lan-radar --detalle", "gray"))
    return 0


def run_rename(args: argparse.Namespace) -> int:
    who, nickname = args.nombrar
    locals_ = net.local_networks()
    if not locals_:
        print("No encuentro la red de este ordenador.", file=sys.stderr)
        return 2
    local = locals_[0]
    gateway_mac = arp.table().get(local.gateway, "") if local.gateway else ""
    history = History()
    key = network_key(str(net.default_target(local)), gateway_mac)
    known = history.network(key)["devices"]
    wanted = who.strip().upper()
    match = next((k for k, v in known.items() if k.upper() == wanted or v.get("ip") == who.strip()), None)
    if match is None:
        print(f"No conozco ningún aparato «{who}» en esta red. Pasa antes lan-radar para que lo vea.", file=sys.stderr)
        return 1
    history.rename(key, match, nickname)
    history.save()
    shown = known[match].get("ip", match)
    if nickname.strip():
        print(f"Hecho: {shown} se llamará «{nickname.strip()}» a partir de ahora.")
    else:
        print(f"Hecho: {shown} vuelve a llamarse como él dice.")
    return 0


def run_networks() -> int:
    locals_ = net.local_networks()
    if not locals_:
        print("No hay ninguna red privada en este ordenador.")
        return 1
    for local in locals_:
        target = net.default_target(local)
        note = "" if target == local.network else f" (se revisa solo {target}: la red es muy grande)"
        router = f", router {local.gateway}" if local.gateway else ""
        print(f"{local.label()}: este ordenador es {local.address}{router}{note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # que un nombre raro no tire el programa en Windows
    parser = argparse.ArgumentParser(
        prog="lan-radar",
        description="¿Quién está en mi wifi? Lista los aparatos conectados a la red de casa con todo lo que "
        "cuentan de sí mismos: marca, modelo, nombre, sistema y servicios. Solo revisa la red privada a la "
        "que está conectado este ordenador.",
    )
    parser.add_argument("red", nargs="?", help="la red a revisar, como 192.168.1.0/24 (si no, la del wifi)")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--demo", action="store_true", help="enseñar una casa de ejemplo, sin tocar la red")
    action.add_argument("--redes", action="store_true", help="ver las redes de este ordenador")
    action.add_argument(
        "--nombrar", nargs=2, metavar=("IP_O_MAC", "NOMBRE"), help='ponerle nombre a un aparato (o quitárselo con "")'
    )
    parser.add_argument("--detalle", action="store_true", help="la ficha completa de cada aparato")
    parser.add_argument("--rapido", action="store_true", help="sin mirar puertos ni páginas web (más rápido)")
    parser.add_argument("--json", metavar="ARCHIVO", help="guardarlo todo en JSON (- para sacarlo por pantalla)")
    parser.add_argument("--version", action="version", version=f"lan-radar {__version__}")
    args = parser.parse_args(argv)
    if (args.demo or args.redes or args.nombrar) and args.red:
        parser.error("esa opción no lleva red")

    try:
        if args.demo:
            return output(demo.result(), args)
        if args.redes:
            return run_networks()
        if args.nombrar:
            return run_rename(args)
        return run_scan(args)
    except net.NotAllowed as exc:
        print(f"No reviso esa red: {exc}.", file=sys.stderr)
        return 2
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"No se puede seguir: {exc.strerror or exc}.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
