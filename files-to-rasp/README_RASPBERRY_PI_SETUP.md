# Goalkeeper Vision — Raspberry Pi Setup (dispatcher architecture)

The Pi runs a **dispatcher** that owns the serial port and launches the vision
script as a subprocess. The vision script never touches serial — it only prints
`VISION:XX` lines, which the dispatcher turns into bytes for the Arduino.

```
systemd
  └─ goalkeeper_dispatcher.py        owns /dev/goalkeeper_serial
       └─ vision_raw.py (subprocess) prints  VISION:XX / VISION:FIRE  to stdout
            dispatcher parses those lines and writes the byte to the Arduino
```

Why: only ONE process opens the port (no conflicts), the vision script stays
simple, and a vision crash can't take serial down — the dispatcher just relaunches it.

### Files in this folder

```
files-to-rasp/
├── goalkeeper_dispatcher.py     # serial owner + vision supervisor (systemd runs THIS)
├── vision_raw.py                # headless detector; prints VISION:XX (no serial)
├── vision_debug.py              # GUI tuner; same detection + sliders; saves config.json
├── config.json                  # all tuning + serial + dispatcher settings
├── requirements.txt             # optional venv route
├── goalkeeper-vision.service    # systemd unit -> runs the dispatcher
├── 99-goalkeeper-serial.rules   # udev -> /dev/goalkeeper_serial  (1a86:7523)
└── README_RASPBERRY_PI_SETUP.md # this file
```

### Your specifics (already baked in)

- User: **`username`**, project dir: **`/home/username/goalkeeper-vision`**
- Board: **CH340** (`lsusb` → `1a86:7523`) → shows up as **`/dev/ttyUSB0`**, not ttyACM0
- Stable symlink: **`/dev/goalkeeper_serial`**  (always use this; never hardcode ttyUSB0)
- Baud: **115200** (matches firmware `SERIAL_BAUD`)

---

## VISION protocol

Vision script → dispatcher (stdout, one per output tick):

```
VISION:00     position, hex 0..FF  (00 = left, 7F = center, FF = right)
VISION:7F
VISION:FF
VISION:FIRE   fire the solenoid
```

Dispatcher → Arduino (bytes on the wire):

```
0x00..0xFD    position  (logical 255 is clamped to 0xFD)
0xFF          FIRE
```

> The clamp matters: the firmware treats `0xFE` as reserved and `0xFF` as FIRE,
> so a *position* byte is never allowed to reach `0xFE/0xFF`. `VISION:FF`
> (rightmost) becomes wire `0xFD`; only `VISION:FIRE` produces `0xFF`.

---

## 1. Install dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-opencv python3-numpy python3-serial v4l-utils
```

(apt OpenCV is the reliable route on a Pi. The service uses system `python3`.)

---

## 2. Copy the files onto the Pi

```bash
mkdir -p ~/goalkeeper-vision
# from your laptop:
#   scp -r files-to-rasp/* username@<PI_IP>:~/goalkeeper-vision/
# or, already on the Pi inside the repo:
cp -r files-to-rasp/* ~/goalkeeper-vision/
cd ~/goalkeeper-vision
ls -l
```

---

## 3. Stable serial port (udev)

Your IDs are already in the rule. Install it:

```bash
sudo cp ~/goalkeeper-vision/99-goalkeeper-serial.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug/replug the Arduino, then check:

```bash
ls -l /dev/goalkeeper_serial
```

You should see it point at `ttyUSB0` (CH340). If you ever need to edit it:

```bash
sudo nano /etc/udev/rules.d/99-goalkeeper-serial.rules
```

Confirm the IDs udev sees (sanity check):

```bash
lsusb | grep -i 1a86
udevadm info -a -n /dev/ttyUSB0 | grep -E 'idVendor|idProduct' | head
```

---

## 4. Tune the vision (GUI), save to config.json

Run the debug tool (needs a display — do this on the Pi desktop or over VNC/X):

```bash
cd ~/goalkeeper-vision
python3 vision_debug.py --config config.json
```

- Adjust HSV until only the ball is masked.
- Set **X Min Range** (green line = output 0) and **X Max Range** (red line = 255)
  to your goalkeeper's real left/right limits inside the frame.
- Read **Raw Ball X / Mapped X** live.
- Press **S** to save into `config.json`. Press **Q** to quit.

`vision_raw.py` and the dispatcher read the same `config.json`.

---

## 5. Test manually BEFORE enabling the service

**5a. See the raw VISION stream (no serial):**

```bash
cd ~/goalkeeper-vision
python3 vision_raw.py --config config.json
# stdout shows clean lines:  VISION:7F  VISION:80 ...   (Ctrl-C to stop)
```

**5b. Run the full dispatcher by hand (opens serial, drives the Arduino):**

```bash
cd ~/goalkeeper-vision
python3 goalkeeper_dispatcher.py --config config.json --verbose
```

Expected log lines:
- `Serial connected: /dev/goalkeeper_serial @ 115200`
- `Launching vision: ... vision_raw.py`
- `[vision] ... ball_x=... mapped=...`
- `[ARD] CAL_MM:...` / `[ARD] axis=...` (replies from the Arduino)

Move the ball → the carriage should track (Arduino must be in VISION mode and
calibrated). Ctrl-C stops the dispatcher and its child cleanly.

---

## 6. Install + enable the systemd service

The service is preset for `username`. (If your user differs:
`sed -i "s/username/$(whoami)/g" ~/goalkeeper-vision/goalkeeper-vision.service`.)

```bash
sudo cp ~/goalkeeper-vision/goalkeeper-vision.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable goalkeeper-vision.service
sudo systemctl start goalkeeper-vision.service
sudo systemctl status goalkeeper-vision.service
journalctl -u goalkeeper-vision.service -f
```

---

## 7. Day-to-day commands

```bash
# after editing code or config.json:
sudo systemctl restart goalkeeper-vision.service

# stop / disable:
sudo systemctl stop goalkeeper-vision.service
sudo systemctl disable goalkeeper-vision.service

# logs:
journalctl -u goalkeeper-vision.service -f
```

---

## 8. Robustness (what the dispatcher already handles)

- **Arduino not plugged in at boot** → keeps retrying `/dev/goalkeeper_serial`
  every 2 s, logs the outage once (no spam).
- **Arduino unplugged mid-run** → write fails, port closes, bytes are dropped
  (logged once), reconnects automatically when it returns.
- **Vision script crashes** → dispatcher logs it and relaunches after 2 s. Fast,
  repeated crashes back off (×2 up to 30 s); a healthy run resets the delay.
- **Invalid `VISION:` lines** → ignored, warned at a throttled rate.
- **No ball** → `vision_raw` holds the last known position (config
  `no_ball_behavior`: `hold` | `neutral` | `silent`); it does NOT jump.
- **Clean shutdown** → Ctrl-C / `systemctl stop` terminates the child
  (SIGTERM → SIGKILL fallback) and closes serial.
- **No port conflict** → only the dispatcher opens serial; the vision scripts
  never call `serial.Serial()`.

---

## 9. Optional: virtual environment

```bash
cd ~/goalkeeper-vision
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt        # only if NOT using apt OpenCV
# then point the service ExecStart python at .venv/bin/python and restart.
```

---

## 10. Troubleshooting

- **`/dev/goalkeeper_serial` missing** → `lsusb` shows `1a86:7523`? re-run the
  udev reload/trigger, replug the board.
- **`Permission denied`** on the port → the rule sets `MODE="0666"`. If you
  changed it: `sudo usermod -aG dialout username` then re-login.
- **`serial=DOWN` / `Serial ... down`** in logs → board not enumerated; check USB.
- **No movement but serial up** → Arduino must be in **VISION mode** and
  **calibrated** (`[ARD] CAL_MM:` should appear). Check HSV/range tuning.
- **Left/right reversed** → fix on the Arduino (`handlePositionByte`), so it's
  independent of the Pi.
- **Camera index wrong** → `v4l2-ctl --list-devices`, set `camera_index`.

---

## 11. Assumptions & TODOs

Assumptions (change in `config.json` / service if needed):
- user `username`, dir `/home/username/goalkeeper-vision`, camera index `0`,
  baud `115200`, one camera + one Arduino.

TODO (manual):
- [ ] Tune HSV + `x_min_range`/`x_max_range` with `vision_debug.py`, press `S` (§4).
- [ ] Confirm `/dev/goalkeeper_serial` appears after the udev step (§3).
- [ ] Run the dispatcher by hand once (§5b) before enabling the service.
- [ ] (If kicking via vision) set `kick_zone_h` > 0 in `config.json`.
