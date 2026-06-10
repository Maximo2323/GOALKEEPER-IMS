#!/usr/bin/env python3
"""
vision_uart_test.py — Mac-side sender for testing the Arduino VisionUART.

Replaces the Pi: opens the Arduino's USB serial port, sends position bytes
(0-255), and prints whatever the Arduino sends back.

Modes:
  sweep      — slowly sweep 0 → 255 → 0 forever
  step       — step to a given byte and hold
  ramp       — go to target byte, then back to 0, repeat (with dwell)
  interactive— type numbers (or h/p/s/c) and hit Enter to send
  manual     — read bytes from stdin one per line

Usage examples:
  python3 vision_uart_test.py --port /dev/tty.usbmodem14101 sweep
  python3 vision_uart_test.py --port /dev/tty.usbmodem14101 step 128
  python3 vision_uart_test.py --port /dev/tty.usbmodem14101 ramp --target 200 --dwell 1.0
  python3 vision_uart_test.py --port /dev/tty.usbmodem14101 interactive

Notes:
  - Default baud is 9600 to match the Uno-friendly recommendation. Use --baud
    to override.
  - The Arduino prints status every ~500 ms; this script reads those lines
    asynchronously and prints them with a [ARD] prefix.
"""

import argparse
import sys
import time
import threading

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed — run:  pip3 install pyserial")
    sys.exit(1)


# ─────────────────────────────────────────────
def reader_thread(ser, stop_evt):
    buf = b""
    while not stop_evt.is_set():
        try:
            data = ser.read(64)
        except serial.SerialException:
            break
        if not data:
            continue
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                print(f"[ARD] {line.decode(errors='ignore').rstrip()}")
            except Exception:
                pass


# ─────────────────────────────────────────────
def send_byte(ser, b: int):
    b = int(b) & 0xFF
    ser.write(bytes([b]))
    ser.flush()


# ─────────────────────────────────────────────
def mode_sweep(ser, args):
    """0 → 255 → 0 → 255 …"""
    step  = args.step
    delay = args.delay
    print(f"[TX ] sweep step={step} delay={delay}s   Ctrl-C to stop")
    direction = 1
    val = 0
    while True:
        send_byte(ser, val)
        print(f"[TX ] -> {val}")
        val += direction * step
        if val >= 255:
            val = 255; direction = -1
        elif val <= 0:
            val = 0;   direction = +1
        time.sleep(delay)


def mode_step(ser, args):
    print(f"[TX ] step -> {args.value}   Ctrl-C to stop")
    while True:
        send_byte(ser, args.value)
        time.sleep(0.5)


def mode_ramp(ser, args):
    """0 → target → 0 → target …"""
    print(f"[TX ] ramp 0<->{args.target} dwell={args.dwell}s   Ctrl-C to stop")
    while True:
        send_byte(ser, args.target); print(f"[TX ] -> {args.target}")
        time.sleep(args.dwell)
        send_byte(ser, 0);           print(f"[TX ] -> 0")
        time.sleep(args.dwell)


def mode_interactive(ser, args):
    print("Interactive mode. Enter a number 0-255, or one of h/p/s/c, then Enter.")
    print("Type q to quit.")
    while True:
        try:
            s = input("> ").strip()
        except EOFError:
            break
        if not s: continue
        if s in ("q", "quit", "exit"): break
        if s in ("h", "p", "s", "c"):
            ser.write(s.encode())
            ser.flush()
            print(f"[TX ] cmd '{s}'")
            continue
        try:
            v = int(s)
            if not 0 <= v <= 255:
                print("out of range 0-255"); continue
            send_byte(ser, v)
            print(f"[TX ] -> {v}")
        except ValueError:
            print("not a number, not h/p/s/c")


def mode_manual(ser, args):
    print("Manual mode — pipe values in, one per line (newline-terminated).")
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            v = int(line)
            if 0 <= v <= 255:
                send_byte(ser, v)
        except ValueError:
            pass


# ─────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="e.g. /dev/tty.usbmodem14101")
    ap.add_argument("--baud", type=int, default=9600)
    sp = ap.add_subparsers(dest="mode", required=True)

    s = sp.add_parser("sweep");   s.add_argument("--step", type=int, default=5); s.add_argument("--delay", type=float, default=0.05)
    s = sp.add_parser("step");    s.add_argument("value", type=int)
    s = sp.add_parser("ramp");    s.add_argument("--target", type=int, default=255); s.add_argument("--dwell", type=float, default=1.0)
    s = sp.add_parser("interactive")
    s = sp.add_parser("manual")

    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.05)
    except serial.SerialException as e:
        sys.exit(f"ERROR: cannot open {args.port}: {e}")

    # let Arduino reset after open
    time.sleep(2.0)
    print(f"[OPEN] {args.port} @ {args.baud}")

    stop_evt = threading.Event()
    t = threading.Thread(target=reader_thread, args=(ser, stop_evt), daemon=True)
    t.start()

    try:
        {
            "sweep":       mode_sweep,
            "step":        mode_step,
            "ramp":        mode_ramp,
            "interactive": mode_interactive,
            "manual":      mode_manual,
        }[args.mode](ser, args)
    except KeyboardInterrupt:
        print("\n[BYE]")
    finally:
        stop_evt.set()
        ser.close()


if __name__ == "__main__":
    main()