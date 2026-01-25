# Zlan6042_Codex.py
# Set one or more relays (DO1..DO4) to open/closed and report DO + AI1 voltage.
# Also supports a separate DI read command.

import argparse
import inspect
import os
import subprocess
import sys
import time
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ----------------- CONFIG -----------------
IP = "192.168.1.200"
PORT = 502
DEVICE_ID = 1

DO_BASE = 16      # DO1..DO4 coils at 16..19
DI_BASE = 0       # DI1..DI4 discrete inputs at 0..3
AI_BASE = 0       # AI1..AI2 input regs at 0..1

TIMEOUT_SECONDS = 2

# ----------------- HELPERS -----------------

def must_ok(resp, label):
    if resp is None:
        raise RuntimeError(f"{label}: No response (None)")
    if resp.isError():
        raise RuntimeError(f"{label}: {resp}")
    return resp


def call_with_unit(func, *args, **kwargs):
    """Call pymodbus functions across versions (unit keyword changes)."""
    sig = inspect.signature(func)
    if "device_id" in sig.parameters:
        kwargs["device_id"] = DEVICE_ID
    elif "slave" in sig.parameters:
        kwargs["slave"] = DEVICE_ID
    elif "unit" in sig.parameters:
        kwargs["unit"] = DEVICE_ID
    return func(*args, **kwargs)


def write_do(c, ch_1_to_4, state):
    addr = DO_BASE + (ch_1_to_4 - 1)
    must_ok(call_with_unit(c.write_coil, addr, state), f"Write DO{ch_1_to_4}={state}")


def read_do(c):
    r = must_ok(call_with_unit(c.read_coils, DO_BASE, count=4), "Read DO coils")
    return r.bits[:4]


def read_di(c):
    r = must_ok(call_with_unit(c.read_discrete_inputs, DI_BASE, count=4), "Read DI inputs")
    return r.bits[:4]


def read_ai(c):
    r = must_ok(call_with_unit(c.read_input_registers, AI_BASE, count=2), "Read AI regs")
    return r.registers[:2]


def raw_to_volts(raw):
    # ZLAN doc: volts = (value/1024)*5, then scale up for external divider
    return ((raw / 1024.0) * 5.0) * 3.9


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Set one or more relays and report DO + AI1 voltage, or read one DI."
        ),
        epilog=(
            "Syntax notes: IP suffix can be '<n>,' or just '<n>' when <n> > 4; "
            "timed relay is '<relay>,<seconds> closed' or '<relay> <seconds> closed'; "
            "'all,<seconds> closed' or 'all <seconds> closed' are allowed."
        ),
    )
    parser.add_argument(
        "--reopen",
        nargs=3,
        metavar=("IP", "RELAY", "SECONDS"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="Relay/state pairs or DI read command",
    )
    return parser.parse_args()


def parse_ip_suffix_and_shift(raw_args):
    if not raw_args:
        return IP, raw_args
    token_raw = raw_args[0].strip().rstrip(",")
    if token_raw.isdigit():
        suffix = int(token_raw)
        if suffix < 0 or suffix > 255:
            raise SystemExit("Syntax Violation")
        if suffix > 4:
            return f"192.168.1.{suffix}", raw_args[1:]
    return IP, raw_args


def schedule_reopen(ip_addr, relay, delay_seconds):
    script_path = os.path.abspath(__file__)
    subprocess.Popen(
        [
            sys.executable,
            script_path,
            "--reopen",
            ip_addr,
            str(relay),
            str(delay_seconds),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def handle_reopen(ip_addr, relay_arg, delay_seconds):
    time.sleep(delay_seconds)
    c = ModbusTcpClient(ip_addr, port=PORT, timeout=TIMEOUT_SECONDS)
    if not c.connect():
        return
    try:
        if relay_arg == "all":
            for relay in range(1, 5):
                write_do(c, relay, False)
        else:
            relay_num = int(relay_arg)
            if relay_num < 1 or relay_num > 4:
                return
            write_do(c, relay_num, False)
    finally:
        c.close()


def main():
    args = parse_args()
    if args.reopen:
        ip_addr, relay_arg, delay_str = args.reopen
        try:
            delay_seconds = float(delay_str)
        except ValueError:
            raise SystemExit("Syntax Violation")
        if delay_seconds <= 0:
            raise SystemExit("Syntax Violation")
        handle_reopen(ip_addr, relay_arg, delay_seconds)
        return
    if not args.args:
        raise SystemExit("Syntax Violation")
    raw_args = [str(a).strip().lower() for a in args.args]
    ip_addr, raw_args = parse_ip_suffix_and_shift(raw_args)
    if not raw_args:
        raise SystemExit("Syntax Violation")

    print(
        f"{datetime.now():%Y-%m-%d %H:%M:%S}  Connecting to {ip_addr}:{PORT} device_id={DEVICE_ID}"
    )
    c = ModbusTcpClient(ip_addr, port=PORT, timeout=TIMEOUT_SECONDS)
    if not c.connect():
        raise SystemExit("ERROR: could not connect")

    try:
        if len(raw_args) == 2 and raw_args[0] in ("ai1", "ai2") and raw_args[1] == "read":
            if any("," in a for a in raw_args):
                raise SystemExit("Syntax Violation")
            ai_raw = read_ai(c)
            idx = 0 if raw_args[0] == "ai1" else 1
            ai_v = raw_to_volts(ai_raw[idx])
            print("OK")
            print(f"AI{idx + 1} raw: {ai_raw[idx]}  volts: {ai_v:.2f}V")
            return

        if len(raw_args) == 2 and raw_args[0] == "ai" and raw_args[1] == "read":
            if any("," in a for a in raw_args):
                raise SystemExit("Syntax Violation")
            ai_raw = read_ai(c)
            ai1_v = raw_to_volts(ai_raw[0])
            ai2_v = raw_to_volts(ai_raw[1])
            print("OK")
            print(f"AI1 raw: {ai_raw[0]}  volts: {ai1_v:.2f}V")
            print(f"AI2 raw: {ai_raw[1]}  volts: {ai2_v:.2f}V")
            return

        if len(raw_args) == 3 and raw_args[0] == "di" and raw_args[2] == "read":
            if any("," in a for a in raw_args):
                raise SystemExit("Syntax Violation")
            try:
                di_num = int(raw_args[1])
            except ValueError:
                raise SystemExit("Syntax Violation")
            if di_num < 1 or di_num > 4:
                raise SystemExit("Syntax Violation")
            di_states = read_di(c)
            print("OK")
            print(f"Digital input DI{di_num}: {di_states[di_num - 1]}")
            return

        if raw_args and raw_args[0].startswith("all"):
            if len(raw_args) < 2:
                raise SystemExit("Syntax Violation")
            all_duration_seconds = None
            state_token = raw_args[1]
            if "," in raw_args[0]:
                all_parts = raw_args[0].split(",", 1)
                if len(all_parts) != 2 or all_parts[0] != "all":
                    raise SystemExit("Syntax Violation")
                try:
                    all_duration_seconds = float(all_parts[1])
                except ValueError:
                    raise SystemExit("Syntax Violation")
                state_token = raw_args[1]
            elif len(raw_args) >= 3 and raw_args[0] == "all" and raw_args[1].isdigit():
                try:
                    all_duration_seconds = float(raw_args[1])
                except ValueError:
                    raise SystemExit("Syntax Violation")
                state_token = raw_args[2]
            if state_token not in ("open", "closed"):
                raise SystemExit("Syntax Violation")
            if all_duration_seconds is not None:
                if all_duration_seconds <= 0:
                    raise SystemExit("Syntax Violation")
                if state_token != "closed":
                    raise SystemExit("Syntax Violation")
            desired_state = state_token == "closed"
            for relay in range(1, 5):
                write_do(c, relay, desired_state)
            if all_duration_seconds is not None:
                schedule_reopen(ip_addr, "all", all_duration_seconds)
        else:
            i = 0
            while i < len(raw_args):
                relay_arg = raw_args[i]
                if i + 1 >= len(raw_args):
                    raise SystemExit("Syntax Violation")
                if "," in relay_arg:
                    relay_parts = relay_arg.split(",", 1)
                    if len(relay_parts) != 2:
                        raise SystemExit("Syntax Violation")
                    relay_str, duration_str = relay_parts
                    try:
                        relay_num = int(relay_str)
                    except ValueError:
                        raise SystemExit("Syntax Violation")
                    try:
                        duration_seconds = float(duration_str)
                    except ValueError:
                        raise SystemExit("Syntax Violation")
                    state_arg = raw_args[i + 1]
                    i += 2
                else:
                    try:
                        relay_num = int(relay_arg)
                    except ValueError:
                        raise SystemExit("Syntax Violation")
                    duration_seconds = None
                    if i + 2 < len(raw_args) and raw_args[i + 1].isdigit():
                        try:
                            duration_seconds = float(raw_args[i + 1])
                        except ValueError:
                            raise SystemExit("Syntax Violation")
                        state_arg = raw_args[i + 2]
                        i += 3
                    else:
                        state_arg = raw_args[i + 1]
                        i += 2
                if state_arg not in ("open", "closed"):
                    raise SystemExit("Syntax Violation")
                if duration_seconds is not None:
                    if duration_seconds <= 0:
                        raise SystemExit("Syntax Violation")
                    if state_arg != "closed":
                        raise SystemExit("Syntax Violation")
                if relay_num < 1 or relay_num > 4:
                    raise SystemExit("Syntax Violation")
                write_do(c, relay_num, state_arg == "closed")
                if duration_seconds is not None:
                    schedule_reopen(ip_addr, relay_num, duration_seconds)

        do_states = read_do(c)
        ai_raw = read_ai(c)
        ai1_v = raw_to_volts(ai_raw[0])

        print("OK")
        print(f"Relay states (DO1..DO4): {do_states}")
        print(f"AI1 raw: {ai_raw[0]}  volts: {ai1_v:.2f}V")
    finally:
        c.close()


if __name__ == "__main__":
    main()
