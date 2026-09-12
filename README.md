# Oukitel Power Station — Home Assistant integration

[![GitHub release](https://img.shields.io/github/v/release/bordeux/ha-oukitel-powerstation)](https://github.com/bordeux/ha-oukitel-powerstation/releases)
[![GitHub stars](https://img.shields.io/github/stars/bordeux/ha-oukitel-powerstation?style=flat)](https://github.com/bordeux/ha-oukitel-powerstation/stargazers)
[![HACS](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant integration for Quectel/Acceleronix **"WonderFree"-app** power stations — verified on
the **Oukitel P2001E Plus** and the **Oukitel P1500E Plus**. After a one-time cloud login to fetch the
per-device key, runtime communication is **local** (LAN, no cloud) and **push-based** (the station
streams updates). A station you cannot reach on the LAN can still be monitored read-only through the
cloud.

- **iot_class:** `local_push` (a cloud-only entry polls the cloud shadow instead — see below)
- **Requires:** Home Assistant **2026.1+**. No extra Python packages.
- Protocol fully reverse-engineered & verified — see [`REVERSE_ENGINEERING.md`](REVERSE_ENGINEERING.md).

## How it works
The station speaks a Quectel TTLV protocol over the LAN (UDP `6606` discovery, TCP `6607` control),
with an AES-128-CBC session keyed by a per-device `authKey`. The integration fetches that `authKey`
once from the Quectel cloud using your account (`regenerateAuthKey`, the same call the vendor app
makes), then connects directly to the station on your network.

At setup it also downloads the product's **thing model** (`productTSL`) and stores it with the entry.
That manifest decides which entities exist, so each model only gets what it actually reports — see
[Supported models](#supported-models).

## Install (HACS)
1. HACS → three-dot menu → **Custom repositories** → add this repo (category *Integration*).
2. Install **Oukitel Power Station**, then **restart Home Assistant**.
3. **Settings → Devices & Services → Add Integration → Oukitel Power Station**.

(Manual: copy `custom_components/oukitel_power_station/` into your HA `config/custom_components/`, restart.)

## Setup flow
1. **Cloud login** — region (EU/US/CN) + your WonderFree/Oukitel email & password. Used to get the
   device key; the credentials are stored in HA's local config entry so the key can be refreshed
   automatically if it ever rotates.
2. **Pick device** (skipped if you have only one). Stations are listed with their product name.
3. **Locate on LAN** — the station is found automatically via UDP discovery. If it is not found
   (e.g. it sits on another VLAN), you choose:
   - **Enter a local IP address** — normal local operation, full feature set;
   - **Cloud-only monitoring (read-only)** — no LAN link at all, see [Cloud-only mode](#cloud-only-mode).
4. Done — the device and entities are created.

> Tip: give the station a DHCP reservation. If its IP changes, the integration re-discovers it by MAC.

> ⚠️ **Do not block the station's internet access.** Control and polling stay local, but the station
> only streams its telemetry once it has a live cloud connection. Firewalled off the internet it still
> completes the handshake and acks commands, yet sends no data at all — so every sensor goes
> unavailable while the device looks perfectly reachable. This is device behaviour, not something the
> integration can work around. See issue #6.

## Entities
Which entities appear depends on the product's thing model — a tag the station does not report is not
created at all.

**Sensors:** Battery %, Remaining time\*, Charging time\*, Total input power, Total output power,
AC charging input power, DC charging input power, Temperature\*\*, Inverter version, BMS version.

**Per-port sensors** (from the AC/USB/Type-C/DC structs): AC output power, AC output voltage†,
USB-A power, USB-C (QC) power, Type-C 1–4 power, DC (car) output power, DC output voltage†,
DC output current†.

**Binary sensor:** Battery-powered (inferred). Derived from `total input power == 0`; there is no
"mains present" tag on this hardware. At a full battery with no load the firmware may report zero
input while mains is still connected, so debounce it before acting on it.

**Button:** Reload — reloads the config entry, the same as the integration's Reload menu action. It
stays available while the other entities are unavailable, so it can recover a stuck entry from a
dashboard or an automation.

**Controls — off by default, see [Options](#options):**
Switches: AC output, USB output‡, DC output. Select: Output voltage (100–240 V), Output frequency
(50/60 Hz), LED mode‡. Number: AC charge limit (%).

\* Not created on the P1500E Plus — its firmware pins both to `5940`.
\*\* Temperature (and the output-voltage select) are never sent over the LAN on this firmware; they
need **Fetch temperature & voltage from the cloud** enabled.
† Disabled by default; enable them in the entity settings if you want them.
‡ Model-dependent: USB output exists on the P2001E Plus, LED mode on the P1500E Plus.

> Total input power is everything drawn from the source; the AC/DC *charging* input power sensors
> count only the share going into the battery. Charging from AC while a load sits on the AC output,
> the difference is that passthrough load. Verified live on a P1500E Plus: full battery → `ac charging
> input power` reads 0 W while total input = total output = 156 W (pure passthrough); charging →
> 329 W in = 175 W charging + 154 W to the loads.

## Options
**Settings → Devices & Services → Oukitel Power Station → Configure.** A station on the LAN has two
toggles, both off by default:

- **Fetch temperature & voltage from the cloud** — pulls the two values the station never sends over
  the LAN (temperature and the output-voltage setting) from the cloud shadow every 5 minutes, using
  your stored credentials. Everything else stays local.
- **Enable device control** — exposes the writable entities (output switches, output
  voltage/frequency, LED mode, AC charge limit). Off by default because these stations are usually
  deployed as a UPS, where an accidental toggle cuts power to whatever is plugged in. Entries created
  before this option existed keep their controls enabled, so upgrading changes nothing for them.

A cloud-only station has just one option: the **Cloud poll interval** (60–3600 s, default 300 s).

## Cloud-only mode
Pick this when Home Assistant cannot reach the station directly — a different site, a network you do
not control, or a station that is simply not on your LAN. The integration then serves every value
from the cloud shadow instead of the local link.

- **Read-only.** No switches, selects or number: writes only exist over the local protocol.
- **Freshness is bounded by the station**, not by the poll interval — the shadow only moves when the
  device itself reports to the cloud. Polling faster than that gains nothing.
- Everything else (sensors, the battery binary sensor, the reload button, diagnostics) works as usual.

An entry can be created this way from the start; switching an existing entry between local and
cloud-only means re-adding it.

## Supported models
The integration ships thing-model snapshots for the products below and resolves a manifest in this
order: the snapshot stored with the config entry → a snapshot bundled in the repo → a live
`productTSL` fetch. A WonderFree-family station that is not on this list therefore still works — its
thing model is fetched from the cloud at setup.

| | P2001E Plus (`p11wN7`) | P1500E Plus (`p11uve`) |
|---|---|---|
| USB output switch (tag 44) | yes | no |
| LED mode (tag 10) | no | yes |
| Type-C ports | 4 | 2 |
| Remaining / charging time (tags 2, 3) | reported | pinned to `5940`, excluded |

Everything else — telemetry, AC/DC switches, frequency, voltage, charge limit, versions — is
identical across both. **Adding a model** is a matter of dropping its `productTSL` snapshot into
`custom_components/oukitel_power_station/tsl/<productKey>.json`; only firmware quirks the thing model
cannot express (like the pinned time values above) need a curated override in `product.py`.

## Energy dashboard
The power sensors are `device_class: power` (W), not `energy` (kWh) — the station reports no
cumulative counter, and the integration deliberately doesn't fabricate one. For the Energy
dashboard add an **Integration — Riemann sum integral** helper on **Total input power**
(kilo, hours, left) and pick the resulting kWh sensor. Name helpers explicitly: *Total input
energy* for the wall draw, *AC charging energy* for the charging-only sensor (an "AC input energy"
helper would wrongly suggest it also covers passthrough power).

> If you migrated from another integration, check that the helper still points at an entity that
> exists — a Riemann helper whose source disappeared silently stops counting. The source can be
> changed in the helper's own Configure dialog.

## Troubleshooting
- **Setup fails to connect:** the phone app's "add device" must have completed once so the device is
  bound to your account; make sure HA and the station are on the same L2 network (or enter the IP).
  If it is unreachable by design, use cloud-only monitoring instead.
- **"Reauthentication required":** the cloud `authKey` no longer matches the device — re-enter your
  password when prompted. On **shared** accounts (a station someone else bound and shared with you)
  the device list serves a key frozen at binding time, so the integration always refreshes through
  `regenerateAuthKey`; that call returns the current key and does not disturb the vendor app.
- **Entities show unavailable:** the station went offline / left WiFi; they recover on reconnect.
- **Connected but no data, especially right after a Home Assistant restart:** the station can accept
  the handshake and ack every write while streaming nothing. The coordinator notices after ~150 s
  without telemetry and drops the session to resubscribe; recovery can take a couple of those cycles,
  so give it a few minutes before assuming something is broken. If it never recovers, check that the
  station still has internet access (see the warning above).
- **Temperature or output voltage missing:** they only come from the cloud — enable **Fetch
  temperature & voltage from the cloud** in the options.
- **No switches or selects:** control entities are opt-in — enable **Enable device control** in the
  options.
- **Diagnostics:** download from the device page (secrets are redacted) for bug reports.

## Status / development
See [`PLAN.md`](PLAN.md). The protocol library is unit-tested against captured device traffic
(`tests/`), and the thing-model layer (`tsl.py` / `product.py`) is plain Python with no Home
Assistant imports, so it can be tested offline. Write commands (output toggles) are derived from
captured app traffic and verified live on a P2001E Plus; verify on your own device before relying on
them in automations.

## Contributors
Thanks to everyone who has helped with the protocol work, testing on other models, and translations.

[![Contributors](https://contrib.rocks/image?repo=bordeux/ha-oukitel-powerstation)](https://github.com/bordeux/ha-oukitel-powerstation/graphs/contributors)

## Star history
[![Star History Chart](https://api.star-history.com/svg?repos=bordeux/ha-oukitel-powerstation&type=Date)](https://star-history.com/#bordeux/ha-oukitel-powerstation&Date)

## Credits / disclaimer
Independent, unofficial integration for personal use with your own hardware. Not affiliated with
Oukitel or Quectel.

## License
Released under the [MIT License](LICENSE).
