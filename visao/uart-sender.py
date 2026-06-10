#!/usr/bin/env python3
"""
vision_sender.py — send 1-byte position commands to the goalkeeper Arduino/Teensy.

The byte (0-255) maps linearly to the full axis travel:
  target_mm = (byte / 255.0) * axis_length_mm

Run as a systemd service and output goes straight to journalctl.
"""

import logging
import serial
import time

# ── device path ───────────────────────────────────────────────────────────────
# After installing the udev rule (see below) this is always stable.
SERIAL_PORT = "/dev/goalkeeper"
BAUD        = 9600

# ── axis geometry (must match the Arduino's measured length after calibration) ─
AXIS_LENGTH_MM = 500.0   # update after first calibration run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [vision_sender] %(message)s",
)
log = logging.getLogger(__name__)


def position_to_byte(position_mm: float, axis_length_mm: float) -> int:
    """Convert a target position in mm to the 0-255 byte the Arduino expects."""
    clamped = max(0.0, min(position_mm, axis_length_mm))
    return round((clamped / axis_length_mm) * 255)


class GoalkeeperSerial:
    def __init__(self, port: str = SERIAL_PORT, baud: int = BAUD):
        self._ser = serial.Serial(port, baud, timeout=0.1)
        log.info("Opened %s @ %d baud", port, baud)

    def send_position_mm(self, position_mm: float) -> None:
        byte = position_to_byte(position_mm, AXIS_LENGTH_MM)
        self._ser.write(bytes([byte]))
        log.info("→ %.1f mm  (byte %d / 255)", position_mm, byte)

    def send_raw(self, byte: int) -> None:
        byte = max(0, min(255, byte))
        mm_equiv = (byte / 255.0) * AXIS_LENGTH_MM
        self._ser.write(bytes([byte]))
        log.info("→ byte %d  (≈ %.1f mm on %.0f mm axis)", byte, mm_equiv, AXIS_LENGTH_MM)

    def close(self):
        self._ser.close()


# ── demo / integration test ────────────────────────────────────────────────────
if __name__ == "__main__":
    gk = GoalkeeperSerial()
    try:
        # Sweep end-to-end as a quick sanity check
        for target_mm in [0, 70, 140, 250, 500, 250, 0]:
            gk.send_position_mm(target_mm)
            time.sleep(1.5)
    finally:
        gk.close()
