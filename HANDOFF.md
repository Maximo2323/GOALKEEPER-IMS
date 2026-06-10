# Goalkeeper IMS — Handoff

**Last updated:** 2026-06-10

A robotic goalkeeper: an Arduino Uno drives a linear stepper carriage along a
goal line. A camera (on a Raspberry Pi) tracks the ball and tells the Arduino
where to go. A joystick allows manual control. A solenoid kicks.

The system **works as of this writing.** This document is the source of truth
for how it's wired, how the code is organised, and the gotchas already solved.

---

## 1. Big picture / architecture

```
            ┌─────────────────────── Raspberry Pi (Ubuntu) ───────────────────────┐
  camera ──▶│  goalkeeper_dispatcher.py   (systemd service, OWNS the serial port)  │
            │        └─ launches subprocess ─▶ vision_raw.py                        │
            │                                    prints "VISION:7F" / "VISION:FIRE" │
            │        dispatcher parses those lines ─▶ writes 1 byte ───────────────┼──▶ USB serial
            └──────────────────────────────────────────────────────────────────────┘   /dev/goalkeeper_serial
                                                                                            │
                                                                                            ▼
                                            ┌────────────── Arduino Uno (src/main.cpp) ──────────────┐
                                            │  MANUAL mode: joystick drives the carriage             │
                                            │  VISION mode: serial bytes drive the carriage          │
                                            │  MODE button toggles between them. Solenoid kicks.     │
                                            └─────────────────────────────────────────────────────────┘
```

Two independent halves:

- **Firmware** (`src/main.cpp`, the "full-test"): runs the stepper, joystick,
  solenoid, limit switches. Switches live between MANUAL and VISION with a button.
- **Pi vision** (`files-to-rasp/`): a **dispatcher** owns the serial port and
  supervises a headless **vision** subprocess that only prints `VISION:` lines.
  Only the dispatcher touches the serial port → no port conflicts, and a vision
  crash can't take serial down (the dispatcher just relaunches it).

The Pi connects to the Arduino over USB. The Arduino is a **CH340** board, so on
the Pi it enumerates as `/dev/ttyUSB0`; a udev rule pins it to the stable name
**`/dev/goalkeeper_serial`**.

---

## 2. Pin assignments (`include/pins.h`)

Current physical wiring (pin order). **Buttons & limit switches are wired
pull-DOWN** (external resistor to GND, switch other side to VCC) → `pinMode INPUT`,
pressed/triggered reads **HIGH**.

| Pin | Signal | Notes |
|-----|--------|-------|
| D2  | `GK_LIMIT_FAR`   | far limit switch (pull-down, HIGH=triggered) |
| D3  | `GK_LIMIT_HOME`  | home limit switch (pull-down, HIGH=triggered) |
| D4  | `BTN_FIRE`       | solenoid fire button (pull-down, HIGH=pressed) |
| D5  | `BTN_MODE`       | MANUAL/VISION toggle button (pull-down, HIGH=pressed) |
| D6  | `GK_DIR`         | stepper direction |
| D7  | `GK_STEP`        | stepper step pulse |
| D8  | `GK_ENA`         | stepper enable, **active-LOW** (LOW = enabled) |
| D9  | `SOL_MOSFET`     | solenoid gate, active-HIGH |
| A0  | `JOY_PIN`        | joystick X (analog) |

> **Why STEP/DIR/ENA are NOT on D2–D4:** the A4988/DRV8825 driver holds its
> STEP/DIR/ENA inputs HIGH through internal pullups. When the stepper driver was
> on D2/D3/D4 it pinned those lines HIGH and broke the button/limit reads. Moving
> the driver to D6/D7/D8 fixed it. **Don't move them back.**

> **Polarity (`constants.h`):** `LIMIT_TRIGGERED = HIGH`, `SOL_BUTTON_PRESSED = HIGH`,
> `MODE_PRESSED_LEVEL = HIGH`, all with `pinMode(..., INPUT)` (NOT `INPUT_PULLUP`,
> which fights the external pull-down resistor).

D10–D13 are free (the SPI display idea was abandoned — see §10).

---

## 3. Firmware (`src/main.cpp` = the "full-test")

On boot it runs the full calibration, then starts in **MANUAL**. A press of the
**MODE button (D5)** toggles MANUAL ⇄ VISION (debounced rising edge).

### MANUAL mode
- **Joystick = direct velocity, NO acceleration.** Deflection maps straight to
  stepper speed via `AccelStepper::runSpeed()` — push further, go faster; centre
  = instant stop. (`JoystickAxis` → `StepperAxis::setVelocity()`.)
- **Joystick left/right is inverted** in `JoystickAxis.cpp` (`-_maxSpeed * deflection`)
  because the physical stick was reversed relative to travel.
- Fire button (D4) kicks the solenoid. Limit switches hard-stop + latch.

### VISION mode
- Reads single bytes from USB serial:
  - `0x00..0xFD` = position. Mapped to travel, **left/right inverted on the
    Arduino side** (`handlePositionByte`: `targetMm = (POS_BYTE_MAX - b)/POS_BYTE_MAX * L`).
  - `0xFE` = reserved (no-op). `0xFF` = FIRE the solenoid.
- Position moves use an acceleration profile (`GK_RUNTIME_ACCELERATION`), unlike
  the joystick.

### Serial out (Arduino → Pi), 115200 baud
- `CAL_MM:<len>` once when calibration completes.
- `axis=<state> pos=<mm>/<len> tgt=<mm> kick=<state> mode=<MANUAL|VISION>` every 500 ms.
- `[AXIS] -> <state>` / `[MODE] -> <mode>` on transitions.

### StepperAxis state machine (`lib/steppers/`)
```
UNINIT → home() → HOMING_TO_HOME → (HOME hit, pos:=0) → HOMING_TO_FAR
       → (FAR hit, measure length) → MOVE_TO_CENTER → HOMED
HOMED ←→ RUNNING (position/vision moveTo, accel)   ENA auto-disabled in HOMED
HOMED ←→ VELOCITY (joystick, constant speed)        ENA auto-enabled on move
limit hit → hard stop + re-zero + latch → HOMED
```
Limit switches are the single source of truth; the digital position is re-zeroed
whenever a limit is hit.

### Flashing the firmware
Connect the Arduino **to the Mac** (it normally lives on the Pi), then:
```bash
cd /Users/username/GOALKEEPER-IMS
pio run -t upload
```
The CH340 may make PlatformIO auto-detect the wrong port (e.g. Bluetooth audio).
If so, force it: `pio run -t upload --upload-port /dev/cu.usbserialXXXX`
(or `…wchusbserial…`). Find it with `ls /dev/cu.*` before/after plugging in.

---

## 4. Vision protocol (Pi)

The vision script and the dispatcher speak a tiny text protocol over the pipe;
the dispatcher translates it to the firmware's wire bytes:

| `vision_raw.py` prints (stdout) | dispatcher writes to Arduino |
|---|---|
| `VISION:00` … `VISION:FF` (logical 0–255 position, hex) | byte `0x00..0xFD` (**clamped** so position never hits the reserved/fire bytes) |
| `VISION:FIRE` | byte `0xFF` (kick) |

- `VISION:FF` (rightmost) → wire `0xFD`. Only `VISION:FIRE` produces `0xFF`.
- Invalid lines are ignored (throttled warning).
- **STDOUT carries VISION lines only;** all human logs go to STDERR so the stream
  stays clean. The dispatcher re-logs the vision stderr and the Arduino's replies
  to journald.

---

## 5. Vision pipeline (`files-to-rasp/vision_raw.py`)

```
camera frame
  → (optional) perspective warp        ← currently OFF (perspective_pts: [])
  → resize to proc = (frame_w/ds) × (frame_h/ds)
  → HSV threshold + morphology
  → contour filter (area / radius / circularity / gradient gate)
  → pick the ball CLOSEST TO THE GOAL  ← lowest on screen (largest cy)
  → map ball-x → 0..255 via x_min_range/x_max_range, then clamp to out_min/out_max
  → print VISION:XX   (kick zone at the bottom → VISION:FIRE)
```

- **Closest-ball tracking:** with several balls, it keeps the one nearest the
  goal (largest `cy`). `vision-tracker.py` (Mac) does the same.
- **No-ball behaviour:** `hold` (default) keeps emitting the last known position
  so the carriage doesn't jump. (`neutral` = centre, `silent` = stop emitting.)

---

## 6. ⚠️ Resolution / dimensions — the #1 gotcha (READ THIS)

`x_min_range`, `x_max_range`, and `kick_zone_h` are **pixels in the processing
frame** (`frame_w/ds` × `frame_h/ds`). They are therefore **resolution-dependent**.
The Mac camera and the Pi camera are different resolutions, so the same numbers
do **not** mean the same thing on both — this caused a long "everything moves
only halfway / grabs a corner" saga.

**The working approach (what's deployed): calibrate at the camera's NATIVE
resolution and keep the config matching it.**

| | Mac debug tool | Raspberry Pi runtime |
|---|---|---|
| script | `visao/vision-tracker.py` / `vision_debug.py` | `vision_raw.py` (via dispatcher) |
| camera | 1280×720 | **640×480** (this camera's max) |
| config | `config_debug.json` (`frame_w:1280`) | **`config.json` (`frame_w:640, frame_h:480, ds:2`)** |
| proc width | 640 | 320 |
| example ranges | 62..520 (in 640) | **31..260 (in 320)** |

- `vision_raw.py` scales ball-x by `ref_w/proc_w` where `ref_w = frame_w/ds`.
  If `frame_w` matches the **actual** camera width, `ref_w == proc_w` → scale 1,
  and the range numbers are simply native pixels. That's the current setup.
- If you instead want to reuse Mac-tuned values directly on the Pi, set the Pi's
  `frame_w/frame_h` to the **calibration** resolution (1280×720) and the scaler
  will up-convert — but it's simpler and less error-prone to just re-tune the two
  range numbers in the Pi's native resolution.
- **Perspective is OFF** (`perspective_pts: []`) → the full camera frame is used.
  If you re-enable it, `make_perspective` scales the saved corners from the
  calibration resolution to the actual frame, but a mis-scaled / wrongly-sized
  warp is exactly what "grabs the top-left corner" looks like. Leave it off
  unless you re-calibrate carefully.

**Verify on the Pi log** (`journalctl -u goalkeeper-vision.service -n 20`):
```
Camera 0 opened 640x480
Range 31..260 px (ref_w=320) -> 0..255 clamp 0..255 ...
PERSPECTIVE OFF (perspective_pts empty or not 4 points)
```

---

## 7. Config reference (`files-to-rasp/config.json`)

| Key | Meaning |
|---|---|
| `serial_port` / `serial_baud` | `/dev/goalkeeper_serial` @ 115200 (dispatcher) |
| `vision_script` | which script the dispatcher launches (`vision_raw.py`) |
| `camera_index`, `frame_w`, `frame_h`, `ds` | camera + downscale. **Set frame_* to the camera's native res.** |
| `h_lo..v_max` | HSV ball colour |
| `area_min/max` (×10), `rad_min/max`, `circ_min` (×100), `morph_k`, `morph_iter`, `blur_k`, `grad_*` | shape/detection gates (same scaling convention as the debug tool's saved config) |
| `x_min_range`, `x_max_range` | proc-px that map to output 0 / 255 |
| `out_min`, `out_max` | **software limit switches** — clamp the 0–255 output so the carriage stops short of the physical ends. Currently `0/255` (no clamp). |
| `kick_zone_h` | bottom band height (proc-px); ball entering it → `VISION:FIRE`. 0 disables. |
| `perspective_pts` | 4 corners or `[]` (off) |
| `no_ball_behavior` | `hold` / `neutral` / `silent` |
| `output_rate_hz` | max VISION lines/sec |

`config.json` = runtime (dispatcher). `config_debug.json` = the `vision_debug.py`
GUI tuner. They share keys; deploy a tuning session with
`cp config_debug.json config.json` **(and re-check ranges if the resolutions differ)**.

---

## 8. Raspberry Pi deployment

Everything the Pi needs is in **`files-to-rasp/`** (the only folder you copy over).
Full step-by-step is in `files-to-rasp/README_RASPBERRY_PI_SETUP.md`. Summary:

- **User:** `username`, project dir `~/goalkeeper-vision`, IP seen as `10.xx.xxx.xx`.
- **Deps:** `sudo apt install -y python3-opencv python3-numpy python3-serial`.
- **Stable port (udev):** `99-goalkeeper-serial.rules` →
  `ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523"` → `/dev/goalkeeper_serial`.
  Install: `sudo cp … /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger`.
- **Service:** `goalkeeper-vision.service` runs the **dispatcher**
  (`After=network.target`, `Restart=always`, `Environment=PYTHONUNBUFFERED=1`).
  `sudo systemctl enable --now goalkeeper-vision.service`.
- **Logs:** `journalctl -u goalkeeper-vision.service -f` (use `-n 30` to see
  existing lines; `-f` only streams *new* ones).

### Push updated files from the Mac
```bash
cd /Users/username/GOALKEEPER-IMS
scp files-to-rasp/vision_raw.py files-to-rasp/goalkeeper_dispatcher.py \
    files-to-rasp/config.json username@10.xx.xxx.xx:~/goalkeeper-vision/
# on the Pi:
sudo systemctl restart goalkeeper-vision.service
```
Editing `config.json` does nothing until you **restart the service** (it reads
config once at launch).

### Remote desktop to the Pi
Use **xrdp (RDP)**, not VNC. `sudo apt install -y xrdp` (already done); connect
from the Mac with **Windows App / Microsoft Remote Desktop** to `10.xx.xxx.xx`,
user `username`. RealVNC Viewer will **not** connect to xrdp (different protocol).

---

## 9. Repo layout

```
src/main.cpp                  active sketch = test/full-test.cpp (MANUAL+VISION)
include/pins.h, constants.h   pins + tuning (current layout, see §2)
platformio.ini                Uno target, lib_deps = AccelStepper only

lib/steppers/                 StepperAxis — velocity + position, limits, calibration
lib/Sensors/Joystick/         JoystickAxis — direct velocity, L/R inverted
lib/solenoid/                 Solenoid — pulse + cooldown FSM

test/                         buildable alternative sketches (copy over src/main.cpp to flash):
  full-test.cpp               MANUAL+VISION w/ MODE toggle  (== src/main.cpp)
  manual-mode-test.cpp        scripted moves + joystick + fire + limits
  vision-test.cpp             vision-UART firmware only
  pin-test.cpp                raw input diagnostic (buttons/limits/joystick)
  solenoid-uart-pc.cpp        solenoid via serial commands
  stepper-move-test.cpp       bare back-and-forth
  archive/                    obsolete (maintest, solenoidburst)

visao/                        Mac/laptop vision tools:
  vision-tracker.py           full 4-panel GUI tracker (perspective, ranges, limit
                              switches, kick zone) — main CALIBRATION tool
  uart-test.py                PC byte sender (no camera)
  uart-sender.py              minimal serial helper
  camera-check.py             camera probe
  ball_debug_config.json      saved calibration (HSV/shape/ranges/perspective)
  archive/

files-to-rasp/                THE ONLY files copied to the Pi:
  goalkeeper_dispatcher.py    serial owner + vision supervisor (systemd runs this)
  vision_raw.py               headless detector → VISION lines
  vision_debug.py             GUI tuner (run over xrdp) → writes config_debug.json
  config.json                 runtime config (Pi native 640×480, perspective off)
  config_debug.json           debug/calibration config
  requirements.txt
  goalkeeper-vision.service    systemd unit (runs the dispatcher)
  99-goalkeeper-serial.rules   udev → /dev/goalkeeper_serial
  README_RASPBERRY_PI_SETUP.md exact copy-paste setup
```

---

## 10. Key constants (`include/constants.h`)

| Constant | Value | Controls |
|---|---|---|
| `SERIAL_BAUD` | 115200 | must match Pi side |
| `GK_STEPS_PER_MM` | 10.0 | geometry (verify on real axis) |
| `GK_MOTOR_MAX_SPEED` / `GK_MAX_SPEED` | 750 steps/s | motor ceiling; also joystick top speed |
| `GK_RUNTIME_ACCELERATION` | 3000 steps/s² | **vision moveTo only** — joystick has NO accel |
| `GK_CAL_HUNT_SPEED` | 130 | homing search speed |
| `JOY_MAX_SPEED` | = `GK_MAX_SPEED` | speed at full stick deflection |
| `JOY_DEADBAND` | 60 | ADC units around centre = stop |
| `LIMIT_TRIGGERED` | HIGH | pull-down switches |
| `SOL_BUTTON_PRESSED` / `MODE_PRESSED_LEVEL` | HIGH | pull-down buttons |
| `SOL_PULSE_MS` / `SOL_COOLDOWN_MS` | 50 / 500 | kick duration / lockout |

---

## 11. Resolved bugs & lessons (don't re-introduce)

1. **Button/limit wiring:** pull-DOWN (resistor to GND, switch to VCC, pressed=HIGH),
   `pinMode INPUT`. Using `INPUT_PULLUP` fought the external pulldown → pins stuck.
2. **Stepper driver off D2/D3/D4:** its STEP/DIR/ENA pullups held those lines HIGH
   and broke the buttons. Driver lives on D6/D7/D8 now.
3. **Joystick = direct velocity, no accel**, and **L/R inverted** in `JoystickAxis`.
4. **Vision L/R inverted on the Arduino** (`handlePositionByte`), independent of
   the joystick. Don't double-invert.
5. **SPI display (GMT130/ST7789) abandoned** — the module *burned*. It has an
   onboard 3.3V regulator and wants **5V on VCC**; feeding it 3.3V undervolted it.
   All display code/libs were removed.
6. **Resolution/dimension bug** (§6): ranges are proc-pixels. Calibrate at the
   deployment camera's native resolution. Pi config = 640×480 native, ranges in
   320-wide space, perspective OFF.
7. **Perspective corner scaling:** corners are saved at calibration resolution and
   scaled to the actual frame; a wrong scale "grabs a corner". Currently OFF.
8. **Pi serial:** dispatcher is the ONLY serial owner; vision scripts never open
   the port. Stable name via udev (`/dev/goalkeeper_serial`, CH340 = ttyUSB0).
9. **systemd:** `After=multi-user.target` (with `WantedBy=multi-user.target`) left
   the start job stuck → use `After=network.target`. Add `PYTHONUNBUFFERED=1` so
   logs reach journald immediately. `journalctl -f` only shows *new* lines.
10. **Remote desktop:** xrdp (RDP/3389) + Microsoft Remote Desktop, NOT RealVNC
    (protocol mismatch → "connection refused"/hang).
11. **PlatformIO upload** auto-grabbed a Bluetooth serial port; pass `--upload-port`.

---

## 12. Open items / TODO

- [ ] `out_min/out_max` are `0/255` (no software travel clamp). If the carriage
      slams a physical limit at the extremes, set e.g. `10/245` and redeploy.
- [ ] Detection filters are loose (`circ_min` low, `area_min` 0). Combined with
      closest-ball, a reflection low on the frame could steal tracking — tighten
      `circ_min`/`area_min` if it's jumpy.
- [ ] Copying values between `config_debug.json` (1280) and `config.json` (640)
      requires re-tuning the two range numbers (different proc widths).
- [ ] Verify `GK_STEPS_PER_MM` against the real axis with a ruler.
- [ ] Optional: firmware-side travel clamp (refuse `moveTo` beyond a safe mm
      window) as a belt-and-suspenders limit guard.
