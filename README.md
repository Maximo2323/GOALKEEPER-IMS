# GOALKEEPER-IMS

> Autonomous goalkeeper robot — firmware, motion control & computer-vision ball tracking.
> Tecnológico de Monterrey · Implementation of Mechatronic Systems · 2026

A robotic goalkeeper that slides a solenoid-kicker carriage along the goal line to
block an incoming ball. An **Arduino Uno** runs the motion firmware; a **Raspberry Pi**
runs a camera-based vision pipeline that tracks the ball and streams target positions
to the Arduino over USB serial. A joystick allows manual control, and a push-button
toggles between manual play and autonomous (vision) play.

> 📋 **The full engineering handoff — exact wiring, tuning, deployment, and every
> hardware bug already solved — lives in [HANDOFF.md](HANDOFF.md). Read it before
> touching the hardware.**

---

## Status

| Subsystem | State |
|---|---|
| Firmware — motion, solenoid, mode switching (Arduino) | ✅ Working |
| Manual control (joystick) | ✅ Working |
| Vision pipeline (Raspberry Pi · OpenCV) | ✅ Working |
| Autonomous play (vision → Arduino over serial) | ✅ Working |

---

## Architecture

```
        ┌──────────────── Raspberry Pi ────────────────┐
camera ─▶│  goalkeeper_dispatcher.py  (owns serial)     │
        │      └─ supervises ─▶ vision_raw.py           │
        │                         prints VISION: lines  │
        │  dispatcher → 1 byte ─────────────────────────┼─▶ USB serial
        └───────────────────────────────────────────────┘   /dev/goalkeeper_serial
                                                                  │
                                                                  ▼
                              ┌────────── Arduino Uno (src/main.cpp) ──────────┐
                              │  MANUAL: joystick drives the carriage          │
                              │  VISION: serial bytes drive the carriage       │
                              │  MODE button toggles modes · solenoid kicks    │
                              └────────────────────────────────────────────────┘
```

Two independent halves:

- **Firmware (`src/main.cpp`)** — drives the stepper carriage, reads the joystick,
  fires the solenoid, and enforces the limit switches. It switches live between
  **MANUAL** and **VISION** with a button.
- **Pi vision (`files-to-rasp/`)** — a **dispatcher** owns the serial port and
  supervises a headless **vision** process that detects the ball and emits
  position/fire commands. Only the dispatcher touches serial, so a vision crash
  can't take the link down — the dispatcher just relaunches it.

The Arduino is a CH340 board; on the Pi a udev rule pins it to the stable name
`/dev/goalkeeper_serial`.

---

## Hardware — pin map (Arduino Uno)

| Pin | Signal | Notes |
|-----|--------|-------|
| D2  | `GK_LIMIT_FAR`  | far limit switch (pull-down, HIGH = triggered) |
| D3  | `GK_LIMIT_HOME` | home limit switch (pull-down, HIGH = triggered) |
| D4  | `BTN_FIRE`      | solenoid fire button (pull-down, HIGH = pressed) |
| D5  | `BTN_MODE`      | MANUAL/VISION toggle button (pull-down, HIGH = pressed) |
| D6  | `GK_DIR`        | stepper direction |
| D7  | `GK_STEP`       | stepper step pulse |
| D8  | `GK_ENA`        | stepper enable (**active-LOW**) |
| D9  | `SOL_MOSFET`    | solenoid gate (active-HIGH) |
| A0  | `JOY_PIN`       | joystick X (analog) |

**Wiring notes:** buttons and limit switches are wired **pull-DOWN** (external
resistor to GND), so pressed/triggered reads **HIGH**. The stepper STEP/DIR/ENA
deliberately live on **D6/D7/D8** — putting the driver on D2–D4 pins those lines
HIGH through its internal pull-ups and breaks the button/limit reads. See
[HANDOFF.md](HANDOFF.md) §2 and §11. All pin numbers are in
[`include/pins.h`](include/pins.h); tuning/geometry/timing in
[`include/constants.h`](include/constants.h).

---

## Operating modes

The firmware boots, runs a full limit-switch calibration (home → far → centre),
then starts in **MANUAL**. The **MODE button (D5)** toggles modes on each press.

- **MANUAL** — the joystick is *direct velocity, no acceleration*: push further →
  faster, centre = instant stop. The fire button (D4) kicks the solenoid. Limit
  switches hard-stop and re-zero the position.
- **VISION** — single bytes arrive over USB serial:
  - `0x00..0xFD` → ball X position, mapped to carriage travel (accelerated move)
  - `0xFE` → reserved (no-op)
  - `0xFF` → **FIRE** the solenoid

---

## Repo layout

```
src/main.cpp        firmware (MANUAL + VISION) — identical to test/full-test.cpp
include/            pins.h, constants.h
lib/                StepperAxis · JoystickAxis · Solenoid
platformio.ini      Arduino Uno target (lib_deps: AccelStepper)
test/               standalone reference sketches — copy one over src/main.cpp to flash
visao/              Mac/laptop vision + serial tools (calibration & bench testing)
files-to-rasp/      everything deployed to the Raspberry Pi (the only folder copied over)
HANDOFF.md          full engineering handoff — source of truth
```

### Firmware libraries (`lib/`)

| Library | Responsibility |
|---|---|
| **`StepperAxis`** (`lib/steppers`) | Limit-switch-authoritative motion: homing/calibration, accelerated position moves, constant-velocity (joystick) moves, end-stop latching |
| **`JoystickAxis`** (`lib/Sensors/Joystick`) | Analog joystick → direct velocity, with deadband; left/right inverted to match travel |
| **`Solenoid`** (`lib/solenoid`) | Non-blocking kicker FSM: timed pulse, cooldown lockout, hard safety cap, bundled fire-button edge detect |

External dependency: [AccelStepper](https://github.com/waspinator/AccelStepper)
(pulled in by PlatformIO via `lib_deps`).

---

## Build & flash (PlatformIO)

```bash
pio run              # compile the firmware
pio run -t upload    # flash (Arduino connected to the computer over USB)
pio device monitor   # 115200 baud serial monitor
```

The sketches in `test/` are standalone alternatives — copy one over `src/main.cpp`
to flash it (e.g. `pin-test.cpp` for raw input diagnostics, `manual-mode-test.cpp`
for joystick-only). The CH340 can make PlatformIO auto-pick the wrong port; if
upload fails, pass `--upload-port /dev/cu.usbserialXXXX` (see HANDOFF §3).

---

## Raspberry Pi deployment

Everything the Pi needs is in **`files-to-rasp/`** — the only folder you copy over.
The dispatcher runs as a `systemd` service and owns the serial port. Full
copy-paste setup is in
[`files-to-rasp/README_RASPBERRY_PI_SETUP.md`](files-to-rasp/README_RASPBERRY_PI_SETUP.md);
the deployment and vision-tuning gotchas (especially the resolution-dependent
detection ranges) are in [HANDOFF.md](HANDOFF.md) §4–§8.

---

## Team

| Name | ID |
|---|---|
| Favio Artea Bretado | A00842128 |
| Yael Guerrero | A00842246 |
| Eduardo Mateo Murillo Andrade | A00842099 |
| Maximo Javier Fajardo Cantú | A01384983 |

> **Course:** Implementation of Mechatronic Systems — Group 607
> **Professor:** Salvador Alejandro Leal Merlo
