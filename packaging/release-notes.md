| Sistema | Descarga |
|---|---|
| Windows 10 y 11 | `lan-radar-windows.exe` (instalador) |
| macOS 11 o posterior, con chip de Apple (M1 o más nuevo) | `lan-radar-mac.dmg` |
| Ubuntu, Debian, Linux Mint... | `lan-radar-linux.deb` |

No están firmados (firmar cuesta dinero cada año), así que la primera vez el sistema
avisa:

- **Windows**: "Windows protegió su PC". Pulsa *Más información* y luego *Ejecutar de
  todas formas*. Al buscar por primera vez, el Firewall puede preguntar si lan-radar
  puede usar la red: marca *Redes privadas* y acepta (si no, encuentra menos detalles).
- **macOS**: arrastra lan-radar a Aplicaciones y ábrelo. Dirá que no se puede comprobar;
  ve a *Ajustes del Sistema > Privacidad y seguridad*, baja hasta el aviso de lan-radar y
  pulsa *Abrir igualmente*. En macOS 15 o posterior también pregunta si puede buscar
  aparatos en la red local: dile que sí.
- **Linux**: `sudo apt install ./lan-radar-linux.deb`
