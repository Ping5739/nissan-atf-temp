# nissan-aft-temp

Live automatic transmission fluid (ATF) temperature for the **Nissan Y62 / Z62** platform (Nissan Patrol / Armada and their Infiniti equivalent) with the 7-speed automatic, using an inexpensive ELM327-compatible OBD adapter instead of the dealer diagnostic tool.

## Why

ATF temperature isn't a standard OBD-II value. It lives in the transmission control module (TCM) and is normally read with Nissan's dealer software and interface. You need it for:

- **Fluid level checks.** Nissan's procedure calls for the fluid to be in a specific temperature range.
- **Towing,** to keep an eye on transmission temperature under load.

An infrared thermometer on the pan is not a substitute. The finned aluminium pan sheds heat and reads well below the actual fluid temperature once things are warm (in testing: 71 °C on the pan vs 83 °C reported by the TCM).

## How it works

The script talks to the TCM over CAN (11-bit, 500 kbit/s) through an adapter in ELM327 mode:

| Step | Command | Purpose |
|---|---|---|
| 1 | `ATSH7E1` / `ATCRA7E9` | Address the TCM and listen for its replies |
| 2 | `10C0` | Open a Nissan diagnostic session (expected reply `50 C0`) |
| 3 | `2101` | Request the TCM data block (108 bytes, reply starts `61 01`) |

**ATF Temp 1** is the 20th data byte after `61 01`, and **ATF Temp 2** is the 21st.
Formula: **`value − 50 = °C`**

The formula was checked against a cold soak (22 °C reported vs 18.5 °C measured), a warm pan reading (43 °C vs 41 °C), and engine coolant once fully warm (ATF 86–87 °C vs coolant 91–93 °C). The byte right after the two temperatures behaves like the raw sensor value and falls as the fluid warms. The script prints it as `sensor raw` for reference.

Optionally, the script also reads **engine coolant temperature** (standard PID `0105` from the engine module at `7E0`, `value − 40 = °C`) and switches back to the TCM each cycle.

## Requirements

- **An ELM327-mode adapter that honours header changes (`ATSH`).** This is the most important requirement. Many cheap Bluetooth "ELM327 v1.5" clones reply `OK` to `ATSH7E1` but keep talking to the engine module (`7E8`), so the TCM is never reached. Tested working with a USB J2534 cable that also has an ELM327 mode. Genuine OBDLink, vLinker and Veepeak adapters are also known to switch headers properly.
- Windows 8/10/11 (the script itself is plain Python and should also work on Linux/macOS with a `/dev/tty...` port)
- Python 3 from [python.org](https://www.python.org/) (tick **"Add Python to PATH"** during install)
- [`pyserial`](https://pypi.org/project/pyserial/), installed automatically by `atf.bat`, or run `pip install pyserial`

**Check your adapter first.** In any serial terminal, with the ignition on, send:

```
ATZ
ATE0
ATH1
ATSP6
ATSH7E1
ATCRA7E9
10C0
```

A reply of `7E9 02 50 C0` means the adapter reaches the TCM. A reply starting with `7E8`, or `NO DATA`, means it doesn't.

## Usage

### Windows: double-click

1. Put `atf_monitor.py` and `atf.bat` in the same folder.
2. Plug the adapter into the OBD port and turn the ignition on (or start the engine).
3. Close any other OBD software that might be using the COM port.
4. Double-click **`atf.bat`**.

By default it reads ATF temperature only, on `COM6`, every 2 seconds. Find your adapter's port in Device Manager under **Ports (COM & LPT)**.

### Options (`atf.bat`)

Run from Command Prompt in the same folder (in PowerShell, use `.\atf.bat`):

```
atf.bat                 ATF only, COM6
atf.bat -p COM5         use a different COM port
atf.bat -c              also show engine coolant temperature
atf.bat -l              log readings to atf_log_YYYYMMDD_HHMMSS.csv
atf.bat -f              show °F
atf.bat -i 5            read every 5 seconds
atf.bat -c -l -f        options can be combined
```

### Running the Python script directly

```
pip install pyserial
python atf_monitor.py --port COM6
python atf_monitor.py --port COM6 --no-coolant
python atf_monitor.py --port COM6 --log atf_log.csv --fahrenheit --interval 5
```

Note: when run directly, coolant is **on** by default. Use `--no-coolant` to turn it off. (`atf.bat` defaults to off.)

### Example output

```
15:10:02  ATF Temp 1:    86 °C   ATF Temp 2:    87 °C   Coolant:    93 °C   (sensor raw 28)
15:10:04  ATF Temp 1:    86 °C   ATF Temp 2:    87 °C   Coolant:    92 °C   (sensor raw 28)
```

Press **Ctrl+C** to stop. With `-l` / `--log`, readings are saved as CSV (`time, atf1_c, atf2_c, coolant_c, sensor_raw`).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Cannot open COM6` | Wrong port, or another program (OBD app, serial terminal) is holding it open |
| `session not opened`, reply from `7E8` | The adapter is ignoring the header. See [Requirements](#requirements) |
| `module rejected 2101 (code 7F)` | The diagnostic session wasn't accepted or timed out. The script re-initialises automatically |
| Repeated `re-initialising adapter` after starting the engine | The adapter resets on cranking. It reconnects on its own |
| `Coolant: --` | The engine module didn't answer that cycle. ATF reading is unaffected |

## Using the values in a phone app

If your adapter switches headers properly, the same reading can be set up as a custom PID in apps such as Car Scanner ELM OBD2:

| Field | Value |
|---|---|
| Header | `7E1` |
| Command | `2101` |
| Start diagnostics command | `10C0` |
| Formula | `T-50` (20th data byte) |
| Units / Min / Max | °C / −40 / 150 |

## Disclaimer

This is an unofficial, community tool with no affiliation to Nissan or Infiniti. It only sends read-only diagnostic requests (`10C0` session, `2101` read, `0105` read). Values were verified on one vehicle and may differ on other model years, markets or TCM software versions, so sanity-check against a known reference before relying on it. For fluid level checks, follow the official service procedure and temperature range for your transmission. Use at your own risk.
