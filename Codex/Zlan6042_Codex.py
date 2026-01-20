# Zlan6042_Codex.py
# Set one or more relays (DO1..DO4) to open/closed and report DO + AI1 voltage.
# Also supports a separate DI read command.

import argparse
import inspect
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
    # ZLAN doc: volts = (value/1024)*5
    return (raw / 1024.0) * 5.0


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Set one or more relays and report DO + AI1 voltage, or read one DI."
        ),
    )
    parser.add_argument(
        "args",
        nargs="+",
        help="Relay/state pairs or DI read command",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    raw_args = [str(a).strip().lower() for a in args.args]

    print(
        f"{datetime.now():%Y-%m-%d %H:%M:%S}  Connecting to {IP}:{PORT} device_id={DEVICE_ID}"
    )
    c = ModbusTcpClient(IP, port=PORT, timeout=TIMEOUT_SECONDS)
    if not c.connect():
        raise SystemExit("ERROR: could not connect")

    try:
        if len(raw_args) == 3 and raw_args[0] == "di" and raw_args[2] == "read":
            try:
                di_num = int(raw_args[1])
            except ValueError:
                raise SystemExit("ERROR: DI must be 1-4")
            if di_num < 1 or di_num > 4:
                raise SystemExit("ERROR: DI must be 1-4")
            di_states = read_di(c)
            print("OK")
            print(f"Digital input DI{di_num}: {di_states[di_num - 1]}")
            return

        if len(raw_args) == 2 and raw_args[0] == "all":
            if raw_args[1] not in ("open", "closed"):
                raise SystemExit("ERROR: state must be open or closed")
            desired_state = raw_args[1] == "closed"
            for relay in range(1, 5):
                write_do(c, relay, desired_state)
        else:
            if len(raw_args) % 2 != 0:
                raise SystemExit("ERROR: provide relay/state pairs, e.g. 1 open 3 closed")
            for i in range(0, len(raw_args), 2):
                relay_arg = raw_args[i]
                state_arg = raw_args[i + 1]
                if state_arg not in ("open", "closed"):
                    raise SystemExit("ERROR: state must be open or closed")
                try:
                    relay_num = int(relay_arg)
                except ValueError:
                    raise SystemExit("ERROR: relay must be 1-4 or use 'all'")
                if relay_num < 1 or relay_num > 4:
                    raise SystemExit("ERROR: relay must be 1-4 or use 'all'")
                write_do(c, relay_num, state_arg == "closed")

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
