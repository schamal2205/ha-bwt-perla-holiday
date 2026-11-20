# BWT Perla Holiday Mode for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/schamal2205/ha-bwt-perla-holiday/actions/workflows/validate.yml/badge.svg)](https://github.com/schamal2205/ha-bwt-perla-holiday/actions/workflows/validate.yml)

Switch the **holiday mode** ("Urlaubsmodus") of a **BWT Perla** water softener from Home Assistant.
In holiday mode the Perla closes its valve and **shuts off the water supply to the house**.
Combined with a water leak sensor, this turns the Perla into an automatic shut-off valve.

> 🇩🇪 Deutsche Kurzanleitung [weiter unten](#deutsch).

## Why this exists

The Perla's local HTTP API (port 8080) is **read-only**. It exposes `GetCurrentData`, `GetDailyData`,
`GetMonthlyData` and `GetYearlyData`, but nothing to change settings. The holiday mode can only be
switched in the BWT app or on the device's touch display.

The device's web page (`http://<perla>/`) is a noVNC mirror of that display, backed by a
**VNC server on port 5900 without a password**. This integration:

1. **reads** the holiday mode from the API: `HolidayModeStartTime` is `1` while it is active, `0` otherwise;
2. **switches** it by operating the touch display over VNC, the same way you would by hand.
   It identifies each screen by its colours (independent of the display language), navigates
   *Home → Menu → Functions → Holiday mode*, taps the toggle only if it is not yet in the wanted
   position, returns to the home screen, and confirms the result through the API.

## Entities

| Entity | Description |
|---|---|
| `switch.bwt_perla_holiday_mode` | Holiday mode. **On = water supply shut off.** |
| `camera.bwt_perla_display` | Live still of the device display (disabled by default; enable for troubleshooting). |

For consumption and salt sensors, use it alongside
[dkarv/hacs-bwt-perla](https://github.com/dkarv/hacs-bwt-perla).

## Requirements

- BWT Perla (One / Duo) with firmware **2.02xx** and an 800×480 display. Tested on Perla One, firmware 2.0212.
- Local API enabled on the device, and its **login code**.
- Display VNC on port 5900 reachable from Home Assistant without a password (the default on tested firmware).
- Home Assistant 2025.2 or newer.

## Installation

**HACS:** HACS → ⋮ → *Custom repositories* → add `https://github.com/schamal2205/ha-bwt-perla-holiday`, category *Integration*.
Install **BWT Perla Holiday Mode**, restart Home Assistant.

**Manual:** copy `custom_components/bwt_perla_holiday` into your `config/custom_components/` folder and restart.

Then: *Settings → Devices & services → Add integration → BWT Perla Holiday Mode*, enter the IP address and the login code.

## Example: shut off water on a leak

```yaml
automation:
  - alias: "Water leak: shut off main water"
    mode: single
    triggers:
      - trigger: state
        entity_id:
          - binary_sensor.leak_kitchen
          - binary_sensor.leak_basement
        to: "on"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.bwt_perla_holiday_mode
        continue_on_error: true
      - action: notify.notify
        data:
          title: "💧 Water leak detected"
          message: >
            {{ trigger.to_state.name }} reports water. Perla holiday mode:
            {{ states('switch.bwt_perla_holiday_mode') }}.
```

Switching takes about 5–15 seconds because the integration taps through the menu.
If switching fails (for example an unexpected dialog on the display), the action raises an error,
so you can add a fallback notification.

## Testing without Home Assistant

```bash
python scripts/perla_cli.py 192.168.1.50 screen          # which screen is shown
PERLA_CODE=xxxxxx python scripts/perla_cli.py 192.168.1.50 status
python scripts/perla_cli.py 192.168.1.50 on               # ⚠ shuts off the water
python scripts/perla_cli.py 192.168.1.50 off
```

## Limitations and caveats

- **Not affiliated with or endorsed by BWT.** This uses an undocumented side channel.
  A firmware update may change the layout or close the VNC port, and switching will then fail with an error.
- The first touch after the display has gone dark only wakes it. The integration handles this by re-checking the screen after every tap.
- If someone is using the display at the same moment, the integration may take over the screen.
- Only screens and the toggle position are recognised. Unexpected dialogs make the switch fail rather than tap blindly.

## Security note

The Perla's VNC server accepts connections **without a password**: any device on your network can operate the
softener, including its holiday mode (water shut-off). Consider putting it into a separate IoT network/VLAN
and allowing only Home Assistant to reach ports 5900 and 8080.

---

## Deutsch

Mit dieser Integration lässt sich der **Urlaubsmodus** einer **BWT Perla** aus Home Assistant schalten.
Im Urlaubsmodus **sperrt die Perla die Wasserzufuhr zum Haus ab**. Zusammen mit einem Wassermelder wird sie damit zum automatischen Absperrventil.

Die lokale API der Perla (Port 8080) kann nur lesen. Die Integration liest den Status darüber aus (`HolidayModeStartTime` = 1 bei aktivem Urlaubsmodus)
und schaltet über den passwortlosen VNC-Server des Touch-Displays (Port 5900), indem sie sich wie ein Mensch durch das Menü tippt:
*Start → Menü → Funktionen → Urlaubsmodus*. Die Bildschirme erkennt sie an Farben und nicht an Text, deshalb ist die Display-Sprache egal.

**Einrichtung:** Über HACS als benutzerdefiniertes Repository hinzufügen und installieren, dann Home Assistant neu starten.
Danach *Einstellungen → Geräte & Dienste → Integration hinzufügen → BWT Perla Holiday Mode* öffnen und IP-Adresse sowie Login-Code eingeben.

**Hinweis:** Dies ist kein offizielles BWT-Produkt. Ein Firmware-Update kann das Schalten unterbrechen. Die Integration meldet das dann als Fehler und tippt nicht blind weiter.
Weil der VNC-Server kein Passwort verlangt, sollte die Perla in ein abgetrenntes IoT-Netz.

## License

MIT
