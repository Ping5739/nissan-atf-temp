"""
ATF temperature monitor for Nissan Y62/Z62 (7-speed automatic) via an ELM327-mode adapter.

Reads the transmission module (header 7E1 / reply 7E9) with:
    10C0  -> open Nissan diagnostic session
    2101  -> data block; bytes 20 and 21 after "61 01" are ATF Temp 1 / ATF Temp 2
Formula: value - 50 = degrees C   (verified against IR pan readings: 22 vs 18.5 cold, 43 vs 41 warm)

Usage (Windows):
    pip install pyserial
    python atf_monitor.py --port COM6
    python atf_monitor.py --port COM6 --log atf_log.csv --fahrenheit
    python atf_monitor.py --port COM6 --no-coolant      (ATF only)

Each cycle also asks the engine module (7E0) for coolant temperature (0105, value - 40),
then re-addresses the transmission module.

Close any other OBD software / serial terminal first - only one program can use the COM port at a time.
Press Ctrl+C to stop.
"""

import argparse
import csv
import datetime
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial is not installed. Run:  pip install pyserial")
    sys.exit(1)

TCM_HEADER = "7E1"
TCM_REPLY = "7E9"
ATF1_INDEX = 19   # 20th data byte after "61 01" (0-based index 19)
ATF2_INDEX = 20   # 21st data byte
SENSOR_INDEX = 21  # raw ATF sensor byte (falls as fluid warms)
OFFSET = 50


class AdapterError(Exception):
    pass


class ELM:
    def __init__(self, port, baud, timeout=5.0):
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.timeout = timeout

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def cmd(self, text, timeout=None):
        """Send a command and return the reply lines (without the '>' prompt)."""
        timeout = timeout or self.timeout
        self.ser.reset_input_buffer()
        self.ser.write((text + "\r").encode("ascii"))
        buf = b""
        end = time.time() + timeout
        while time.time() < end:
            chunk = self.ser.read(256)
            if chunk:
                buf += chunk
                if b">" in buf:
                    break
        else:
            raise AdapterError(f"no prompt after '{text}' (got {buf!r})")
        raw = buf.decode("ascii", errors="ignore").replace(">", "")
        lines = [l.strip() for l in raw.replace("\r", "\n").split("\n")]
        # drop empty lines and an echo of our own command
        return [l for l in lines if l and l.replace(" ", "").upper() != text.upper()]

    def init(self):
        self.cmd("ATZ", timeout=8)
        time.sleep(0.5)
        for c in ("ATE0", "ATL0", "ATS1", "ATH1", "ATSP6",
                  f"ATSH{TCM_HEADER}", f"ATCRA{TCM_REPLY}"):
            reply = self.cmd(c)
            if not any("OK" in r for r in reply):
                raise AdapterError(f"'{c}' was not accepted: {reply}")


def assemble_isotp(lines, reply_id=TCM_REPLY):
    """Turn ELM output lines (with headers) into one payload byte list."""
    frames = []
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or parts[0].upper() != reply_id:
            continue
        try:
            frames.append([int(p, 16) for p in parts[1:]])
        except ValueError:
            continue
    if not frames:
        return None
    first = frames[0]
    pci = first[0] >> 4
    if pci == 0:                      # single frame
        length = first[0] & 0x0F
        return first[1:1 + length]
    if pci == 1:                      # first frame + consecutive frames
        length = ((first[0] & 0x0F) << 8) | first[1]
        data = first[2:]
        # consecutive frames (0x21..0x2F, then wrap to 0x20) in arrival order
        cons = [f for f in frames[1:] if f and f[0] >> 4 == 2]
        for f in cons:
            data.extend(f[1:])
        if len(data) < length:
            return None               # incomplete
        return data[:length]
    return None


def read_atf(elm):
    reply = elm.cmd("10C0")
    joined = " ".join(reply).upper()
    if "50 C0" not in joined:
        raise AdapterError(f"session not opened: {reply}")
    reply = elm.cmd("2101")
    payload = assemble_isotp(reply)
    if payload is None:
        raise AdapterError(f"no usable data block: {reply[:3]}")
    if payload[0] == 0x7F:
        raise AdapterError(f"module rejected 2101 (code {payload[-1]:02X})")
    if payload[:2] != [0x61, 0x01] or len(payload) < 2 + SENSOR_INDEX + 1:
        raise AdapterError(f"unexpected reply: {' '.join(f'{b:02X}' for b in payload[:6])}")
    data = payload[2:]
    return data[ATF1_INDEX] - OFFSET, data[ATF2_INDEX] - OFFSET, data[SENSOR_INDEX]


def read_coolant(elm):
    """Ask the engine module for coolant temp (0105), then point the adapter back at the TCM."""
    value = None
    try:
        elm.cmd("ATSH7E0")
        elm.cmd("ATCRA7E8")
        for line in elm.cmd("0105"):
            parts = line.split()
            # expected: 7E8 03 41 05 XX
            if len(parts) >= 5 and parts[0].upper() == "7E8" and parts[2] == "41" and parts[3] == "05":
                value = int(parts[4], 16) - 40
                break
    finally:
        # always restore transmission addressing, even if coolant failed
        for c in (f"ATSH{TCM_HEADER}", f"ATCRA{TCM_REPLY}"):
            reply = elm.cmd(c)
            if not any("OK" in r for r in reply):
                raise AdapterError(f"could not re-address transmission after coolant read: {reply}")
    return value


def main():
    ap = argparse.ArgumentParser(description="Live ATF temperature for Nissan Y62/Z62 via ELM327 adapter")
    ap.add_argument("--port", default="COM6", help="COM port of the adapter (default COM6)")
    ap.add_argument("--baud", type=int, default=38400, help="baud rate (default 38400)")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between readings")
    ap.add_argument("--log", help="CSV file to append readings to")
    ap.add_argument("--fahrenheit", action="store_true", help="show degrees F")
    ap.add_argument("--no-coolant", action="store_true", help="skip engine coolant reading")
    args = ap.parse_args()

    def fmt(c):
        if args.fahrenheit:
            return f"{c * 9 / 5 + 32:6.1f} °F"
        return f"{c:5d} °C"

    log_file = writer = None
    if args.log:
        log_file = open(args.log, "a", newline="")
        writer = csv.writer(log_file)
        if log_file.tell() == 0:
            writer.writerow(["time", "atf1_c", "atf2_c", "coolant_c", "sensor_raw"])

    print(f"Connecting on {args.port} at {args.baud} baud... (Ctrl+C to stop)")
    elm = None
    try:
        while True:
            try:
                if elm is None:
                    elm = ELM(args.port, args.baud)
                    elm.init()
                    print("Adapter ready, reading transmission module.\n")
                atf1, atf2, raw = read_atf(elm)
                coolant = None if args.no_coolant else read_coolant(elm)
                now = datetime.datetime.now()
                cool_txt = "" if args.no_coolant else (
                    f"   Coolant: {fmt(coolant)}" if coolant is not None else "   Coolant:    --")
                print(f"{now:%H:%M:%S}  ATF Temp 1: {fmt(atf1)}   ATF Temp 2: {fmt(atf2)}{cool_txt}   (sensor raw {raw})")
                if writer:
                    writer.writerow([now.isoformat(timespec="seconds"), atf1, atf2,
                                     "" if coolant is None else coolant, raw])
                    log_file.flush()
            except serial.SerialException as e:
                print(f"Cannot open {args.port}: {e}\nIs another OBD program or terminal still open? Retrying in 5 s...")
                if elm:
                    elm.close()
                elm = None
                time.sleep(5)
                continue
            except AdapterError as e:
                print(f"{datetime.datetime.now():%H:%M:%S}  {e} - re-initialising adapter...")
                if elm:
                    elm.close()
                elm = None
                time.sleep(2)
                continue
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if elm:
            elm.close()
        if log_file:
            log_file.close()


if __name__ == "__main__":
    main()
