# zlan6042_loop.py
# - Toggles DO1..DO4 every second (together)
# - Verifies readback after each write; increments error_count if mismatch
# - Displays two updating status lines (no scrolling), and prints NEW lines only on errors

import inspect
import time
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ----------------- CONFIG -----------------
IP = "192.168.1.200"
PORT = 502
DEVICE_ID = 1

DO_BASE = 16      # DO1..DO4 coils at 16..19
DI_BASE = 0       # DI1..DI4 discrete inputs at 0..3 (adjust if needed)
AI_BASE = 0       # AI1..AI2 input regs at 0..1

POLL_SECONDS = 1.0

VERIFY_RETRIES = 3
VERIFY_RETRY_DELAY = 0.10   # seconds between verify reads

# ----------------- STATE -----------------
error_count = 0
toggle_state = False


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


def read_do(c):
    r = must_ok(call_with_unit(c.read_coils, DO_BASE, count=4), "Read DO coils")
    return r.bits[:4]


def read_di(c):
    r = must_ok(call_with_unit(c.read_discrete_inputs, DI_BASE, count=4), "Read DI inputs")
    return r.bits[:4]


def write_do(c, ch_1_to_4, state):
    addr = DO_BASE + (ch_1_to_4 - 1)
    must_ok(call_with_unit(c.write_coil, addr, state), f"Write DO{ch_1_to_4}={state}")


def read_ai(c):
    r = must_ok(call_with_unit(c.read_input_registers, AI_BASE, count=2), "Read AI regs")
    return r.registers[:2]


def raw_to_volts(raw):
    # ZLAN doc: volts = (value/1024)*5
    return (raw / 1024.0) * 5.0


def verify_expected(c, expected_bits):
    last = None
    for _ in range(VERIFY_RETRIES):
        last = read_do(c)
        if last == expected_bits:
            return True, last
        time.sleep(VERIFY_RETRY_DELAY)
    return False, last


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


def two_line(status_top, status_bottom, width=120):
    """
    Overwrite the same two console lines.
    - '\r' returns to start of line
    - ljust clears leftovers from previous longer line
    - ANSI cursor-up keeps output in place
    """
    line_top = status_top.ljust(width)
    line_bottom = status_bottom.ljust(width)
    print("\r" + line_top + "\n" + line_bottom + "\x1b[1A\r", end="", flush=True)


def main():
    global error_count, toggle_state

    print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  Starting: {IP}:{PORT} device_id={DEVICE_ID}  (Ctrl+C to stop)")

    c = ModbusTcpClient(IP, port=PORT, timeout=2)
    if not c.connect():
        raise SystemExit("ERROR: could not connect")

    try:
        next_poll = time.time()

        while True:
            # Toggle every cycle
            toggle_state = not toggle_state

            desired_do = [toggle_state] * 4

            # Write DO1..DO4
            try:
                write_do(c, 1, desired_do[0])
                write_do(c, 2, desired_do[1])
                write_do(c, 3, desired_do[2])
                write_do(c, 4, desired_do[3])

                # Verify
                ok, actual = verify_expected(c, desired_do)
                if not ok:
                    error_count += 1
                    # Print an error on its own line (this will scroll, but only on errors)
                    print(
                        f"\n{datetime.now():%Y-%m-%d %H:%M:%S}  VERIFY FAIL  "
                        f"desired={desired_do} actual={actual} errors={error_count}"
                    )

                # Read AI
                ai_raw = read_ai(c)
                ai_v1 = raw_to_volts(ai_raw[0])
                ai_v2 = raw_to_volts(ai_raw[1])

                # Read DI
                di = read_di(c)

                # Keep status SHORT to avoid wrapping
                status_top = (
                    f"{now_hms()} DO={actual} "
                    f"AI1={ai_raw[0]}({ai_v1:.2f}V) "
                    f"AI2={ai_raw[1]}({ai_v2:.2f}V) "
                    f"err={error_count}"
                )
                status_bottom = f"DI={di}"
                two_line(status_top, status_bottom, width=120)

            except Exception as e:
                error_count += 1
                print(f"\n{datetime.now():%Y-%m-%d %H:%M:%S}  EXCEPTION  {e}  errors={error_count}")
                # Try to keep going (device/network hiccup). Small pause.
                time.sleep(0.5)

            # Keep steady 1 Hz
            next_poll += POLL_SECONDS
            sleep_for = next_poll - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_poll = time.time()

    except KeyboardInterrupt:
        print(f"\n{datetime.now():%Y-%m-%d %H:%M:%S}  Stopped. errors={error_count}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
