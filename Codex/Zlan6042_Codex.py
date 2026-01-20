# Zlan6042_Codex.py
# Set a single relay (DO1..DO4) to open/closed and report all relay states plus AI1 voltage.

import argparse
import inspect
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ----------------- CONFIG -----------------
IP = "192.168.1.200"
PORT = 502
DEVICE_ID = 1

DO_BASE = 16      # DO1..DO4 coils at 16..19
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


def read_ai(c):
    r = must_ok(call_with_unit(c.read_input_registers, AI_BASE, count=2), "Read AI regs")
    return r.registers[:2]


def raw_to_volts(raw):
    # ZLAN doc: volts = (value/1024)*5
    return (raw / 1024.0) * 5.0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Set one relay and report all relay states + AI1 voltage.",
    )
    parser.add_argument(
        "relay",
        type=int,
        choices=range(1, 5),
        help="Relay number (1-4)",
    )
    parser.add_argument(
        "state",
        choices=["open", "closed"],
        help="Relay state: open or closed",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    desired_state = args.state == "closed"

    print(
        f"{datetime.now():%Y-%m-%d %H:%M:%S}  Connecting to {IP}:{PORT} device_id={DEVICE_ID}"
    )
    c = ModbusTcpClient(IP, port=PORT, timeout=TIMEOUT_SECONDS)
    if not c.connect():
        raise SystemExit("ERROR: could not connect")

    try:
        write_do(c, args.relay, desired_state)
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
