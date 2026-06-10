#!/usr/bin/env python3
"""
goalkeeper_dispatcher.py — the ONLY process that owns the serial port.

Architecture (mirrors the proven pi_dispatcher pattern):

    systemd
      └─ goalkeeper_dispatcher.py        <- owns /dev/goalkeeper_serial
           └─ vision_raw.py  (subprocess)
                └─ prints  VISION:XX / VISION:FIRE  to stdout

The dispatcher:
  * opens the serial port once and reconnects if the Arduino disappears,
  * launches the vision script as a subprocess and reads its stdout,
  * parses tagged lines and writes the correct BYTE to the Arduino,
  * re-launches the vision script if it crashes (with backoff),
  * forwards the vision script's stderr and the Arduino's replies to the log,
  * shuts the child down cleanly on Ctrl-C / systemctl stop.

VISION protocol (from the vision script -> dispatcher):
    VISION:7F     position, 2 hex digits, logical 0..255 (00=left, FF=right)
    VISION:FIRE   fire the solenoid

Wire protocol (dispatcher -> Arduino), MUST match the firmware:
    0x00..0xFD    position (logical 0..255 is CLAMPED to 0..253 here, because
                  0xFE is reserved and 0xFF means FIRE in the firmware)
    0xFF          FIRE

So a position byte can never accidentally trigger a kick.

Run:  python3 goalkeeper_dispatcher.py --config config.json
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time

try:
    import serial
except ImportError:
    serial = None

log = logging.getLogger("dispatcher")

# Wire-protocol constants (match the Arduino firmware).
WIRE_POS_MAX = 0xFD     # 253: highest legal POSITION byte
BYTE_RSVD    = 0xFE
BYTE_FIRE    = 0xFF


# ─────────────────────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "serial_port": "/dev/goalkeeper_serial",
    "serial_baud": 115200,
    "serial_retry_s": 2.0,
    "vision_script": "vision_raw.py",      # relative to this file unless absolute
    "vision_restart_s": 2.0,               # base delay before relaunch
    "vision_restart_max_s": 30.0,          # cap for backoff after fast crashes
}


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                user = json.load(f)
            for k in DEFAULT_CONFIG:
                if k in user:
                    cfg[k] = user[k]
            log.info("Loaded config: %s", path)
        except Exception as e:
            log.error("Bad config %s: %s — using defaults", path, e)
    else:
        log.warning("Config %s missing — using defaults", path)
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
#  Serial manager — single owner, robust reconnect
# ─────────────────────────────────────────────────────────────────────────────
class SerialManager:
    def __init__(self, port, baud, retry_s=2.0):
        self.port = port
        self.baud = baud
        self.retry_s = retry_s
        self._ser = None
        self._lock = threading.Lock()
        self._last_attempt = 0.0
        self._warned_down = False
        self._warned_drop = False

    def ensure(self):
        """Open the port if needed. Logs the outage only once."""
        if self._ser is not None:
            return
        now = time.monotonic()
        if now - self._last_attempt < self.retry_s:
            return
        self._last_attempt = now
        if serial is None:
            if not self._warned_down:
                log.error("pyserial not installed — no serial output")
                self._warned_down = True
            return
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0, write_timeout=0.2)
            time.sleep(2.0)                       # let the Arduino reset
            log.info("Serial connected: %s @ %d", self.port, self.baud)
            self._warned_down = False
            self._warned_drop = False
        except Exception as e:
            self._ser = None
            if not self._warned_down:
                log.warning("Serial %s down: %s — retry every %.0fs",
                            self.port, e, self.retry_s)
                self._warned_down = True

    @property
    def connected(self):
        return self._ser is not None

    def write_byte(self, b):
        with self._lock:
            if self._ser is None:
                if not self._warned_drop:
                    log.warning("Serial down — dropping bytes until reconnect")
                    self._warned_drop = True
                return
            try:
                self._ser.write(bytes([b & 0xFF]))
            except Exception as e:
                log.warning("Serial write failed (%s) — will reconnect", e)
                self._close_locked()

    def read_replies(self):
        """Read and log any text the Arduino sends back (CAL_MM, [AXIS], ...)."""
        with self._lock:
            if self._ser is None:
                return
            try:
                n = self._ser.in_waiting
                if not n:
                    return
                data = self._ser.read(n).decode(errors="ignore")
            except Exception:
                self._close_locked()
                return
        for line in data.splitlines():
            line = line.strip()
            if line:
                log.info("[ARD] %s", line)

    def _close_locked(self):
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def close(self):
        with self._lock:
            self._close_locked()


# ─────────────────────────────────────────────────────────────────────────────
#  Parse a VISION line -> action on the serial port
# ─────────────────────────────────────────────────────────────────────────────
_bad_line_count = 0
_bad_line_last_log = 0.0


def handle_vision_line(line, ser):
    """Parse one stdout line from the vision script and act on it."""
    global _bad_line_count, _bad_line_last_log
    line = line.strip()
    if not line:
        return
    if not line.startswith("VISION:"):
        return                                    # not for us (stray print)

    payload = line[len("VISION:"):].strip().upper()

    if payload == "FIRE":
        ser.write_byte(BYTE_FIRE)
        log.info("FIRE -> 0x%02X", BYTE_FIRE)
        return

    # Otherwise expect 1-2 hex digits = logical position 0..255.
    try:
        value = int(payload, 16)
        if not (0 <= value <= 255):
            raise ValueError("out of range")
    except ValueError:
        _bad_line_count += 1
        now = time.monotonic()
        if now - _bad_line_last_log > 2.0:        # throttle warning spam
            log.warning("Ignoring %d invalid VISION line(s); last: %r",
                        _bad_line_count, line)
            _bad_line_count = 0
            _bad_line_last_log = now
        return

    wire = min(WIRE_POS_MAX, value)               # protect 0xFE/0xFF
    ser.write_byte(wire)


# ─────────────────────────────────────────────────────────────────────────────
#  Vision subprocess supervision
# ─────────────────────────────────────────────────────────────────────────────
class Dispatcher:
    def __init__(self, cfg, config_path):
        self.cfg = cfg
        self.config_path = config_path
        self.ser = SerialManager(cfg["serial_port"], cfg["serial_baud"], cfg["serial_retry_s"])
        self._shutdown = threading.Event()
        self._proc = None
        here = os.path.dirname(os.path.abspath(__file__))
        vs = cfg["vision_script"]
        self.vision_path = vs if os.path.isabs(vs) else os.path.join(here, vs)

    # ── serial maintenance thread (reconnect + read replies) ────────────────
    def _serial_thread(self):
        while not self._shutdown.is_set():
            self.ser.ensure()
            self.ser.read_replies()
            time.sleep(0.05)

    # ── forward child's stderr to our log ───────────────────────────────────
    def _stderr_thread(self, proc):
        for raw in iter(proc.stderr.readline, ""):
            if self._shutdown.is_set():
                break
            msg = raw.rstrip()
            if msg:
                log.info("[vision] %s", msg)

    # ── read child's stdout (VISION lines) and act ──────────────────────────
    def _pump_stdout(self, proc):
        for raw in iter(proc.stdout.readline, ""):
            if self._shutdown.is_set():
                break
            handle_vision_line(raw, self.ser)

    def _launch_vision(self):
        cmd = [sys.executable, self.vision_path, "--config", self.config_path]
        log.info("Launching vision: %s", " ".join(cmd))
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,                             # line-buffered
        )

    def _stop_child(self, proc):
        if proc is None or proc.poll() is not None:
            return
        log.info("Stopping vision child (pid %d)", proc.pid)
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log.warning("Vision didn't stop — killing")
            proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
        except Exception:
            pass

    def run(self):
        threading.Thread(target=self._serial_thread, daemon=True).start()

        base_delay = float(self.cfg["vision_restart_s"])
        max_delay = float(self.cfg["vision_restart_max_s"])
        delay = base_delay

        while not self._shutdown.is_set():
            started = time.monotonic()
            try:
                self._proc = self._launch_vision()
            except Exception as e:
                log.error("Failed to launch vision: %s — retry in %.0fs", e, delay)
                self._shutdown.wait(delay)
                delay = min(max_delay, delay * 2)
                continue

            err_t = threading.Thread(target=self._stderr_thread, args=(self._proc,), daemon=True)
            err_t.start()

            # Pump stdout in THIS thread; returns when the child's stdout closes.
            try:
                self._pump_stdout(self._proc)
            except Exception as e:
                log.error("stdout pump error: %s", e)

            self._proc.wait()
            ran = time.monotonic() - started
            code = self._proc.returncode

            if self._shutdown.is_set():
                break

            # Backoff policy: a child that ran a while = healthy -> reset delay.
            # A fast crash -> grow the delay so we don't hammer.
            if ran >= 20:
                delay = base_delay
            log.warning("Vision exited (code=%s) after %.1fs — restart in %.0fs",
                        code, ran, delay)
            self._shutdown.wait(delay)
            if ran < 10:
                delay = min(max_delay, delay * 2)

        self._stop_child(self._proc)
        self.ser.close()
        log.info("Dispatcher stopped")

    def request_shutdown(self, *_):
        log.info("Shutdown requested")
        self._shutdown.set()
        self._stop_child(self._proc)


def main():
    ap = argparse.ArgumentParser(description="Goalkeeper serial dispatcher (owns the port)")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "config.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [dispatcher %(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    cfg = load_config(args.config)
    disp = Dispatcher(cfg, args.config)

    signal.signal(signal.SIGINT, disp.request_shutdown)
    signal.signal(signal.SIGTERM, disp.request_shutdown)

    log.info("Goalkeeper dispatcher starting — port=%s baud=%d",
             cfg["serial_port"], cfg["serial_baud"])
    disp.run()


if __name__ == "__main__":
    main()
