#!/usr/bin/env python3
"""
visao_debug.py — Single-ball tracking debug viewer + UART sender
===================================================================
Tracks ONE ball, predicts its position, maps to real-world distance (mm),
and streams a 0–253 byte over UART to the Arduino. A red KICK ZONE grows
from the BOTTOM of the result panel upward (controlled by a slider); when
the ball touches the zone we send a 0xFF byte (= FIRE) to the Arduino.

4-panel layout (all rendered inside the perspective-warped ROI):
  1. CONTOURS      — raw + filtered contour blobs
  2. COLOR FILTER  — what the camera "sees" (HSV masks visualized)
  3. GATE DIAG     — gradient / saturation filter view
  4. RESULT        — final result with predicted arrow + 0–255 bars + mm readout
                     + red KICK ZONE at the bottom

Perspective ROI:
  Press W to open the 4-corner selector window.
  Click the 4 corners of the playing area (any order — sorted automatically).
  Enter to confirm. The image is warped to a rectangle before all processing.

Distance calibration:
  "Goal left mm" / "Goal right mm" trackbars define the real-world extent
  of the left and right edges of the warped frame. Ball position is shown in mm.

Wire protocol to Arduino (single-byte stream):
  0x00..0xFD  — ball X position (0..253), mapped to axis travel.
  0xFE        — reserved (not used yet).
  0xFF        — FIRE the solenoid (kick zone trigger).

Keys:
  W        = open 4-corner perspective ROI selector
  C        = clear perspective ROI
  S        = save config
  U        = toggle UART output on/off
  P        = toggle "send predicted X" vs "send current X"
  SPACE    = manual test fire (sends 0xFF)
  R        = re-arm the kick trigger (clears the "already inside" latch)
  Q / ESC  = quit
"""

import cv2
import numpy as np
import sys
import json
import os
import time

try:
    import serial
    import serial.tools.list_ports
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False
    print("[Serial] pyserial not installed — UART output disabled. Run: pip install pyserial")

import glob

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
SERIAL_PORT     = None
SERIAL_BAUD     = 115200
SERIAL_ENABLED  = True
SEND_PREDICTED  = False
RECONNECT_EVERY = 2.0

# ── single-byte wire protocol ────────────────
FIRE_BYTE       = 0xFF          # reserved byte = "fire the kick"
POS_BYTE_MAX    = 253           # position bytes clamped to 0..253 so 0xFE/0xFF stay reserved

# ── kick trigger behavior ────────────────────
KICK_REARM_MS   = 1200          # min ms between fires on Python side (Arduino still
                                # enforces its own SOL_COOLDOWN_MS; this just stops
                                # spamming the line when the ball lingers in the zone)

_ser            = None
_last_reconnect = 0.0

def _autodetect_port():
    patterns = [
        '/dev/cu.usbserial-*',
        '/dev/cu.usbmodem*',
        '/dev/cu.wchusbserial*',
        '/dev/ttyUSB*',
        '/dev/ttyACM*',
    ]
    for pat in patterns:
        matches = sorted(glob.glob(pat))
        if matches:
            return matches[0]
    try:
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if any(s in (p.device or '').lower()
                   for s in ('usbserial','usbmodem','ttyusb','ttyacm','wchusb')):
                return p.device
    except Exception:
        pass
    return None

def _serial_open():
    global _ser, _last_reconnect, SERIAL_PORT
    if not _SERIAL_AVAILABLE or not SERIAL_ENABLED:
        return
    now = time.time()
    if now - _last_reconnect < RECONNECT_EVERY:
        return
    _last_reconnect = now
    if SERIAL_PORT is None:
        SERIAL_PORT = _autodetect_port()
        if SERIAL_PORT is None:
            print("[Serial] no Arduino-like port found (will retry)")
            return
        print(f"[Serial] auto-detected: {SERIAL_PORT}")
    try:
        _ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0, write_timeout=0.05)
        time.sleep(2.0)
        print(f"[Serial] opened {SERIAL_PORT} @ {SERIAL_BAUD}")
    except Exception as e:
        _ser = None
        if not os.path.exists(SERIAL_PORT or ''):
            SERIAL_PORT = None
        print(f"[Serial] open failed: {e}  (will retry)")

def _serial_send_byte(b: int):
    """Send a single position byte. Clamped to 0..POS_BYTE_MAX so it
    never collides with the reserved FIRE byte (0xFF)."""
    global _ser
    if not _SERIAL_AVAILABLE or not SERIAL_ENABLED:
        return
    if _ser is None:
        _serial_open()
        return
    try:
        val = max(0, min(POS_BYTE_MAX, int(b)))
        _ser.write(bytes([val]))
    except Exception as e:
        print(f"[Serial] write error: {e} — closing, will reconnect")
        try: _ser.close()
        except Exception: pass
        _ser = None

def _serial_send_fire():
    """Send the FIRE marker byte. Arduino reads 0xFF -> kicker.fire()."""
    global _ser
    if not _SERIAL_AVAILABLE or not SERIAL_ENABLED:
        print("[KICK] (serial disabled)")
        return
    if _ser is None:
        _serial_open()
        return
    try:
        _ser.write(bytes([FIRE_BYTE]))
        print("[KICK] -> 0xFF")
    except Exception as e:
        print(f"[Serial] fire write error: {e}")

# ─────────────────────────────────────────────
#  Arduino telemetry state (populated by serial parser)
# ─────────────────────────────────────────────
_arduino = dict(
    calibrated   = False,   # True once CAL_MM received
    measured_mm  = 0.0,     # axis length from Arduino calibration
    pos_mm       = 0.0,     # current stepper position
    target_mm    = 0.0,     # current stepper target
    state_str    = "---",   # axis state string (HOMED, RUNNING, etc.)
    trackbar_synced = False,  # have we pushed measured_mm to the trackbar yet?
)

_rx_line_buf = [""]   # accumulate incomplete UART lines between reads

def _parse_arduino_line(line: str):
    """Extract structured data from a single text line sent by the Arduino."""
    # CAL_MM:140.0  → calibration complete, real axis length known
    if line.startswith("CAL_MM:"):
        try:
            mm = float(line[7:].strip())
            _arduino['measured_mm']  = mm
            _arduino['calibrated']   = True
            _arduino['trackbar_synced'] = False   # trigger trackbar update
            print(f"[ARD] Calibration complete — axis = {mm:.1f} mm")
        except ValueError:
            pass
        return

    # Periodic status: axis=HOMED pos=70.0/140.0 tgt=70.0 ...
    if line.startswith("axis="):
        import re
        m_state = re.search(r'axis=(\S+)', line)
        m_pos   = re.search(r'pos=([\d.]+)/([\d.]+)', line)
        m_tgt   = re.search(r'tgt=([\d.-]+)', line)
        if m_state: _arduino['state_str']  = m_state.group(1)
        if m_pos:
            _arduino['pos_mm']       = float(m_pos.group(1))
            reported_len = float(m_pos.group(2))
            if reported_len > 0 and _arduino['measured_mm'] == 0.0:
                _arduino['measured_mm'] = reported_len
        if m_tgt: _arduino['target_mm']  = float(m_tgt.group(1))
        return

    # Axis state-change line: [AXIS] -> HOMED
    if line.startswith("[AXIS]"):
        print(f"[ARD] {line}")

def _serial_drain_rx():
    if _ser is None:
        return
    try:
        if not _ser.in_waiting:
            return
        data = _ser.read(_ser.in_waiting)
        _rx_line_buf[0] += data.decode(errors='ignore')
        parts = _rx_line_buf[0].split('\n')
        _rx_line_buf[0] = parts[-1]
        for raw in parts[:-1]:
            line = raw.strip()
            if not line:
                continue
            _parse_arduino_line(line)
            if not (line.startswith("axis=") or line.startswith("CAL_MM:")):
                print(f"[ARD] {line}")
    except Exception:
        pass

# ─────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ball_debug_config.json")
CAM_PORT    = 0
FRAME_W     = 1280
FRAME_H     = 720
DS          = 2

PANEL_W     = 640
PANEL_H     = 360
FONT        = cv2.FONT_HERSHEY_SIMPLEX
MAIN_WIN    = "Ball Tracker Debug  [W=persp ROI  C=clear  S=save  Q=quit]"
CTRL_WIN    = "Controls"

GHOST_FRAMES = 6

# ─────────────────────────────────────────────
#  PERSPECTIVE WARP state (4-corner ROI)
# ─────────────────────────────────────────────
_perspective = dict(
    pts=[],        # list of up to 4 (x, y) in raw frame coords
    matrix=None,   # 3×3 perspective transform matrix
    set=False,     # True when confirmed with 4 corners
)

def _order_corners(pts):
    arr = np.array(pts, dtype="float32")
    s   = arr.sum(axis=1)
    d   = np.diff(arr, axis=1).ravel()
    return np.array([
        arr[np.argmin(s)],   # TL
        arr[np.argmin(d)],   # TR
        arr[np.argmax(s)],   # BR
        arr[np.argmax(d)],   # BL
    ], dtype="float32")

def _compute_perspective_matrix(pts, dst_w, dst_h):
    ordered = _order_corners(pts)
    dst = np.array([
        [0,         0        ],
        [dst_w - 1, 0        ],
        [dst_w - 1, dst_h - 1],
        [0,         dst_h - 1],
    ], dtype="float32")
    return cv2.getPerspectiveTransform(ordered, dst)

def apply_perspective_warp(frame):
    if not _perspective['set'] or _perspective['matrix'] is None:
        return frame, None
    h, w = frame.shape[:2]
    warped = cv2.warpPerspective(frame, _perspective['matrix'], (w, h))
    return warped, list(_perspective['pts'])

# ─────────────────────────────────────────────
#  Kalman tracker (single ball)
# ─────────────────────────────────────────────
def _make_kalman():
    kf = cv2.KalmanFilter(4, 2)
    kf.measurementMatrix   = np.array([[1,0,0,0],[0,1,0,0]], np.float32)
    kf.transitionMatrix    = np.array([[1,0,1,0],[0,1,0,1],
                                        [0,0,1,0],[0,0,0,1]], np.float32)
    kf.processNoiseCov     = np.eye(4, dtype=np.float32) * 0.05
    kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 2.0
    kf.errorCovPost        = np.eye(4, dtype=np.float32) * 10
    kf.statePost           = np.zeros((4,1), np.float32)
    return kf

_tracker = dict(
    kf=_make_kalman(),
    ttl=0,
    pos=(0, 0),
    vel=(0, 0),
    r=10,
    initialized=False,
    history=[],
)

MAX_HISTORY = 20

# ─────────────────────────────────────────────
#  Kick-zone trigger state
# ─────────────────────────────────────────────
_kick = dict(
    was_in=False,        # edge detect: was the ball inside the zone last frame?
    last_fire_ms=0,      # last time we sent FIRE (ms since epoch)
    flash_until_ms=0,    # show "KICK!" flash until this time
)

def _now_ms():
    return int(time.time() * 1000)

# ─────────────────────────────────────────────
#  Config load/save
# ─────────────────────────────────────────────
def load_cfg() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
            print(f"[Config] Loaded {CONFIG_FILE}")
            return saved
    return {}

def save_cfg_file(cfg: dict):
    raw = dict(
        h_lo=cfg['h_lo'],         h_hi=cfg['h_hi'],
        s_min=cfg['s_min'],       s_max=cfg['s_max'],
        v_min=cfg['v_min'],       v_max=cfg['v_max'],
        area_min=cfg['area_min']//10,
        area_max=cfg['area_max']//10,
        rad_min=cfg['rad_min'],   rad_max=cfg['rad_max'],
        circ_min=int(cfg['circ_min']*100),
        morph_k=cfg['morph_k'],   morph_iter=cfg['morph_iter'],
        grad_std_min=cfg['grad_std_min'],
        grad_mean_min=cfg['grad_mean_min'],
        blur_k=cfg['blur_k'],
        goal_left_mm=cfg['goal_left_mm'],
        goal_right_mm=cfg['goal_right_mm'],
        kick_zone_h=cfg['kick_zone_h'],
        x_min_range=cfg['x_min_range'],
        x_max_range=cfg['x_max_range'],
        out_min=cfg['out_min'],
        out_max=cfg['out_max'],
    )
    if _perspective['set']:
        raw['perspective_pts'] = _perspective['pts']
    with open(CONFIG_FILE, 'w') as f:
        json.dump(raw, f, indent=2)
    print(f"[Config] Saved → {CONFIG_FILE}")

# ─────────────────────────────────────────────
#  Trackbars
# ─────────────────────────────────────────────
TB = dict(
    h_lo="H low",      h_hi="H high",
    s_min="S min",     s_max="S max",
    v_min="V min",     v_max="V max",
    area_min="Area min x10",  area_max="Area max x10",
    rad_min="Radius min",     rad_max="Radius max",
    circ_min="Circ min x.01",
    morph_k="Morph K",        morph_iter="Morph iter",
    grad_std_min="Grad STD min",
    grad_mean_min="Grad MEAN min",
    blur_k="Blur K",
    goal_left_mm="Goal left mm",
    goal_right_mm="Goal right mm",
    kick_zone_h="Kick Zone H",
    x_min_range="X Min Range",
    x_max_range="X Max Range",
    out_min="Limit Lo 0-255",
    out_max="Limit Hi 0-255",
)

def make_trackbars():
    saved = load_cfg()
    def d(k, default): return saved.get(k, default)

    if 'perspective_pts' in saved:
        pts = saved['perspective_pts']
        if len(pts) == 4:
            _perspective['pts'] = pts
            _perspective['set'] = True
            _perspective['matrix'] = _compute_perspective_matrix(pts, FRAME_W, FRAME_H)
            print(f"[Perspective] Restored from config: {pts}")

    cv2.namedWindow(CTRL_WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(CTRL_WIN, 420, 900)

    def mk(k, default, maxv):
        cv2.createTrackbar(TB[k], CTRL_WIN,
                           min(d(k, default), maxv), maxv, lambda v: None)

    mk("h_lo",   0,   179)
    mk("h_hi",  30,   179)
    mk("s_min",  80,  255)
    mk("s_max", 255,  255)
    mk("v_min",  80,  255)
    mk("v_max", 255,  255)
    mk("area_min",  40,  5000)
    mk("area_max", 300,  8000)
    mk("rad_min",  10,   200)
    mk("rad_max",  80,   200)
    mk("circ_min", 50,   100)
    mk("morph_k",    5,  21)
    mk("morph_iter", 2,   8)
    mk("grad_std_min",  5, 100)
    mk("grad_mean_min", 5, 100)
    mk("blur_k", 5, 21)
    # distance calibration
    mk("goal_left_mm",   0,    5000)
    mk("goal_right_mm", 1830,  5000)
    # KICK ZONE — height of the red band at the bottom of the frame.
    # 0 = no zone, max = full proc height. Ball touching this band -> FIRE.
    mk("kick_zone_h", 80, FRAME_H // DS)
    # HORIZONTAL GOALKEEPER RANGE — screen x (proc px) that map to output 0..253.
    # The camera still sees outside this range; the output just clamps.
    mk("x_min_range", 120, FRAME_W // DS)
    mk("x_max_range", 520, FRAME_W // DS)
    # SOFTWARE LIMIT SWITCHES — clamp the OUTPUT (0..255) so the stepper never
    # reaches the physical ends. Ball is still tracked everywhere; the output
    # stops at these limits (green line = lo, red line = hi).
    mk("out_min", 20,  255)
    mk("out_max", 235, 255)

def get_cfg() -> dict:
    def tb(k): return cv2.getTrackbarPos(TB[k], CTRL_WIN)
    return dict(
        h_lo=tb("h_lo"),         h_hi=tb("h_hi"),
        s_min=tb("s_min"),       s_max=tb("s_max"),
        v_min=tb("v_min"),       v_max=tb("v_max"),
        area_min=tb("area_min")*10,
        area_max=tb("area_max")*10,
        rad_min=tb("rad_min"),   rad_max=tb("rad_max"),
        circ_min=tb("circ_min")*0.01,
        morph_k=max(1, tb("morph_k") | 1),
        morph_iter=max(1, tb("morph_iter")),
        grad_std_min=tb("grad_std_min"),
        grad_mean_min=tb("grad_mean_min"),
        blur_k=max(1, tb("blur_k") | 1),
        goal_left_mm=tb("goal_left_mm"),
        goal_right_mm=tb("goal_right_mm"),
        kick_zone_h=tb("kick_zone_h"),
        x_min_range=tb("x_min_range"),
        x_max_range=tb("x_max_range"),
        out_min=tb("out_min"),
        out_max=tb("out_max"),
    )

# ─────────────────────────────────────────────
#  Processing pipeline
# ─────────────────────────────────────────────
def build_masks(img, cfg):
    bk = cfg['blur_k']
    blurred = cv2.GaussianBlur(img, (bk, bk), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    lo = np.array([cfg['h_lo'], cfg['s_min'], cfg['v_min']], np.uint8)
    hi = np.array([cfg['h_hi'], cfg['s_max'], cfg['v_max']], np.uint8)

    if cfg['h_lo'] <= cfg['h_hi']:
        color_mask = cv2.inRange(hsv, lo, hi)
    else:
        lo2 = np.array([0,           cfg['s_min'], cfg['v_min']], np.uint8)
        hi2 = np.array([cfg['h_hi'], cfg['s_max'], cfg['v_max']], np.uint8)
        lo3 = np.array([cfg['h_lo'], cfg['s_min'], cfg['v_min']], np.uint8)
        hi3 = np.array([179,         cfg['s_max'], cfg['v_max']], np.uint8)
        color_mask = cv2.bitwise_or(cv2.inRange(hsv, lo2, hi2),
                                    cv2.inRange(hsv, lo3, hi3))

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                   (cfg['morph_k'], cfg['morph_k']))
    cleaned = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN,  k, iterations=cfg['morph_iter'])
    cleaned = cv2.morphologyEx(cleaned,    cv2.MORPH_CLOSE, k, iterations=cfg['morph_iter'])

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gx   = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy   = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)

    return dict(hsv=hsv, color_mask=color_mask, cleaned=cleaned,
                grad_mag=grad_mag, gray=gray)

def gate_gradient(grad_mag, cx, cy, ri, cfg):
    h, w = grad_mag.shape
    r    = max(2, ri)
    x0,x1 = max(0,cx-r), min(w,cx+r+1)
    y0,y1 = max(0,cy-r), min(h,cy+r+1)
    if x1<=x0 or y1<=y0: return False, 0.0, 0.0
    yy, xx = np.ogrid[y0:y1, x0:x1]
    disk = (xx-cx)**2 + (yy-cy)**2 <= r*r
    vals = grad_mag[y0:y1, x0:x1][disk]
    if vals.size < 4: return False, 0.0, 0.0
    g_mean, g_std = float(vals.mean()), float(vals.std())
    ok = (g_std >= cfg['grad_std_min']) and (g_mean >= cfg['grad_mean_min'])
    return ok, g_mean, g_std

def find_ball(img, masks, cfg):
    contours, _ = cv2.findContours(masks['cleaned'], cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for cnt in contours:
        area  = cv2.contourArea(cnt)
        perim = cv2.arcLength(cnt, True)
        if perim == 0: continue
        circ = 4 * np.pi * area / (perim**2)
        (x,y), r = cv2.minEnclosingCircle(cnt)
        cx, cy, ri = int(x), int(y), int(r)

        pr = cfg['rad_min'] <= ri <= cfg['rad_max']
        pa = cfg['area_min'] <= area <= cfg['area_max']
        pc = circ >= cfg['circ_min']
        shape_ok = pr and pa and pc

        g_ok, g_mean, g_std = gate_gradient(masks['grad_mag'], cx, cy, ri, cfg)
        passed = shape_ok and g_ok

        candidates.append((cx, cy, ri, area, circ, passed, g_ok, g_mean, g_std,
                            pr, pa, pc, cnt))
    # Prefer PASSING candidates, then the one CLOSEST TO THE GOAL (lowest on
    # screen = largest cy = e[1]). With several balls, track the most urgent.
    candidates.sort(key=lambda e: (not e[5], -e[1]))
    return candidates

# ─────────────────────────────────────────────
#  Horizontal range mapping (calibrated goalkeeper range -> 0..POS_BYTE_MAX)
# ─────────────────────────────────────────────
def map_and_clamp(x, in_min, in_max, out_min=0, out_max=POS_BYTE_MAX):
    """Map screen-x in [in_min,in_max] to [out_min,out_max], clamped at the ends.

    Ball left of in_min  -> out_min.   Ball right of in_max -> out_max.
    The camera can still see the ball outside the range; the output just clamps.
    """
    if in_max == in_min:
        return (out_min + out_max) // 2        # calibration not set -> center
    mapped = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    mapped = max(out_min, min(out_max, mapped))
    return int(round(mapped))

def clamp_output(value, lo, hi):
    """SOFTWARE LIMIT SWITCHES — keep the mapped 0..255 output within [lo, hi]
    so the stepper never reaches the physical ends. Order-safe."""
    if lo > hi:
        lo, hi = hi, lo
    return max(lo, min(hi, value))

# ─────────────────────────────────────────────
#  Kalman update + distance mapping
# ─────────────────────────────────────────────
def update_tracker(candidates, frame_w, cfg):
    t = _tracker
    best = next((c for c in candidates if c[5]), None)

    if best:
        cx, cy, ri = best[0], best[1], best[2]
        if not t['initialized']:
            t['kf'].statePost[:2, 0] = [cx, cy]
            t['initialized'] = True
        t['kf'].correct(np.array([[np.float32(cx)],
                                   [np.float32(cy)]]))
        t['ttl'] = GHOST_FRAMES
        t['r']   = ri
    else:
        t['ttl'] = max(0, t['ttl'] - 1)

    pred = t['kf'].predict()
    px, py = int(pred[0]), int(pred[1])
    vx, vy = float(pred[2]), float(pred[3])
    t['pos'] = (px, py)
    t['vel'] = (vx, vy)

    if t['ttl'] > 0 or best:
        t['history'].append((px, py))
        if len(t['history']) > MAX_HISTORY:
            t['history'].pop(0)

    if t['ttl'] > 0:
        x_norm = float(np.clip(px, 0, frame_w)) / frame_w
        # Output uses the CALIBRATED horizontal range (clamps outside it),
        # then the software limit switches clamp it to the stepper's safe zone.
        x_out  = clamp_output(map_and_clamp(px, cfg['x_min_range'], cfg['x_max_range']),
                              cfg['out_min'], cfg['out_max'])
        if _arduino['calibrated'] and _arduino['measured_mm'] > 0:
            x_mm = x_norm * _arduino['measured_mm']
        else:
            x_mm = cfg['goal_left_mm'] + x_norm * (cfg['goal_right_mm'] - cfg['goal_left_mm'])
    else:
        x_out = -1
        x_mm  = -1.0

    return x_out, x_mm

# ─────────────────────────────────────────────
#  Kick-zone touch test
# ─────────────────────────────────────────────
def ball_in_kick_zone(proc_h, zone_h):
    """Returns True if the Kalman-tracked ball is touching the bottom red band.
    Band occupies y ∈ [proc_h - zone_h, proc_h]. Ball touches when the bottom
    of the ball circle crosses the band's top edge."""
    t = _tracker
    if zone_h <= 0 or t['ttl'] <= 0:
        return False
    _, cy = t['pos']
    r     = t['r']
    band_top = proc_h - zone_h
    return (cy + r) >= band_top

# ─────────────────────────────────────────────
#  Panels
# ─────────────────────────────────────────────
def panel_contours(img, masks, candidates, cfg):
    vis = cv2.resize(img, (PANEL_W, PANEL_H)).copy()
    vis = (vis * 0.45).astype(np.uint8)
    sx  = PANEL_W / img.shape[1]
    sy  = PANEL_H / img.shape[0]

    for c in candidates:
        cx,cy,ri,area,circ,passed,g_ok,g_mean,g_std,pr,pa,pc,cnt = c
        dcx,dcy = int(cx*sx), int(cy*sy)
        dr = max(1, int(ri*(sx+sy)/2))

        if passed:
            col = (0, 230, 255)
            cv2.circle(vis,(dcx,dcy),dr,col,2)
            cv2.circle(vis,(dcx,dcy),3,(255,255,255),-1)
            cv2.putText(vis,f"r:{ri} c:{circ:.2f}",
                        (max(0,dcx-dr),max(14,dcy-dr-10)),FONT,0.30,col,1)
        else:
            col = (50,50,160)
            for ang in range(0,360,18):
                a0=np.radians(ang); a1=np.radians(ang+9)
                p0=(int(dcx+dr*np.cos(a0)),int(dcy+dr*np.sin(a0)))
                p1=(int(dcx+dr*np.cos(a1)),int(dcy+dr*np.sin(a1)))
                cv2.line(vis,p0,p1,col,1)
            if not pr: reason=f"r:{ri}({'lo' if ri<cfg['rad_min'] else 'hi'})"
            elif not pa: reason=f"a:{int(area)}({'lo' if area<cfg['area_min'] else 'hi'})"
            elif not pc: reason=f"circ:{circ:.2f}lo"
            elif not g_ok: reason=f"grad(m{g_mean:.0f}s{g_std:.0f})"
            else: reason="?"
            cv2.putText(vis,reason,(max(0,dcx-dr),max(14,dcy-dr-2)),
                        FONT,0.27,(80,80,180),1)

    n_pass = sum(1 for c in candidates if c[5])
    cv2.putText(vis,f"blobs:{len(candidates)}  pass:{n_pass}",
                (6,PANEL_H-8),FONT,0.36,(150,150,150),1)
    _stamp(vis,"1 CONTOURS",(40,0,50),(210,100,255))
    return vis

def panel_color_filter(img, masks):
    h, w = img.shape[:2]
    vis  = np.zeros((h, w, 3), np.uint8)

    hsv = masks['hsv']
    S   = hsv[:,:,1]

    col_on = masks['color_mask'] > 0
    vis[col_on]  = img[col_on]
    vis[~col_on] = (img[~col_on] * 0.15).astype(np.uint8)

    sat_vis = np.zeros_like(img)
    sat_vis[:,:,1] = S // 2
    vis = cv2.addWeighted(vis, 0.85, sat_vis, 0.15, 0)

    edge = cv2.Canny(masks['cleaned'], 40, 120)
    vis[edge>0] = (220,220,0)

    out = cv2.resize(vis, (PANEL_W, PANEL_H))
    pct = int(np.count_nonzero(masks['color_mask'])*100 / (h*w))
    cv2.putText(out,f"color match: {pct}%  | yellow=edge",
                (6,PANEL_H-8),FONT,0.34,(160,160,160),1)
    _stamp(out,"2 COLOR FILTER",(0,45,45),(0,220,200))
    return out

def panel_gate_diag(img, masks, candidates, cfg):
    mag_u8 = cv2.normalize(masks['grad_mag'],None,0,255,cv2.NORM_MINMAX).astype(np.uint8)
    base   = cv2.cvtColor(mag_u8, cv2.COLOR_GRAY2BGR)
    base   = cv2.resize(base, (PANEL_W, PANEL_H))
    sx     = PANEL_W / img.shape[1]
    sy     = PANEL_H / img.shape[0]

    for c in candidates:
        cx,cy,ri,area,circ,passed,g_ok,g_mean,g_std,pr,pa,pc,cnt = c
        dcx,dcy = int(cx*sx), int(cy*sy)
        dr      = max(1, int(ri*(sx+sy)/2))

        if passed:         col=(0,220,0)
        elif g_ok:         col=(0,190,255)
        else:              col=(0,60,220)

        cv2.circle(base,(dcx,dcy),dr,col,1)
        cv2.circle(base,(dcx,dcy),3,col,-1)
        lbl = f"m{g_mean:.0f} s{g_std:.0f}"
        cv2.putText(base,lbl,(max(0,dcx-dr),max(14,dcy-dr-3)),FONT,0.28,col,1)

    cv2.putText(base,
        f"grad_mean>={cfg['grad_mean_min']}  grad_std>={cfg['grad_std_min']}",
        (6,PANEL_H-8),FONT,0.32,(200,200,200),1)
    _stamp(base,"3 GATE DIAG",(40,25,0),(255,180,60))
    return base

def panel_result(img, masks, candidates, cfg, x_out, x_mm, persp_pts,
                 in_zone, flashing):
    vis = cv2.resize(img, (PANEL_W, PANEL_H)).copy()
    sx  = PANEL_W / img.shape[1]
    sy  = PANEL_H / img.shape[0]
    t   = _tracker

    # ─── RED KICK ZONE (bottom-anchored, grows upward) ──────────────────
    zone_h = cfg['kick_zone_h']
    # zone is defined in proc/img coords; img and panel share aspect, so
    # scaling y by sy gives us the panel-space band height.
    panel_zone_h = int(zone_h * sy)
    if panel_zone_h > 0:
        band_top = PANEL_H - panel_zone_h
        overlay  = vis.copy()
        # Red normally; flashes yellow on a fresh kick.
        color = (0, 255, 255) if flashing else (0, 0, 255)
        alpha = 0.70 if flashing else 0.40
        cv2.rectangle(overlay, (0, band_top), (PANEL_W, PANEL_H), color, -1)
        cv2.addWeighted(overlay, alpha, vis, 1 - alpha, 0, vis)
        cv2.line(vis, (0, band_top), (PANEL_W, band_top), (0, 0, 255), 2)
        cv2.putText(vis, f"KICK ZONE  h={zone_h}px",
                    (8, band_top + 16), FONT, 0.42, (255, 255, 255), 1)

    # ─── FIELD calibration (cyan): which screen px map to output 0 / 255 ───
    xr_min = cfg['x_min_range']
    xr_max = cfg['x_max_range']
    lx_min = int(np.clip(xr_min * sx, 0, PANEL_W - 1))
    lx_max = int(np.clip(xr_max * sx, 0, PANEL_W - 1))
    cv2.line(vis, (lx_min, 0), (lx_min, PANEL_H), (255, 255, 0), 1)   # cyan
    cv2.line(vis, (lx_max, 0), (lx_max, PANEL_H), (255, 255, 0), 1)   # cyan
    cv2.putText(vis, "field 0",   (lx_min + 2, 14), FONT, 0.34, (255, 255, 0), 1)
    cv2.putText(vis, "field 255", (max(0, lx_max - 64), 14), FONT, 0.34, (255, 255, 0), 1)

    # ─── SOFTWARE LIMIT SWITCHES (green=lo, red=hi): output clamp 0..255 ────
    out_lo = cfg['out_min']
    out_hi = cfg['out_max']
    span = (xr_max - xr_min)
    lo_px = xr_min + (out_lo / 255.0) * span
    hi_px = xr_min + (out_hi / 255.0) * span
    glx = int(np.clip(lo_px * sx, 0, PANEL_W - 1))
    grx = int(np.clip(hi_px * sx, 0, PANEL_W - 1))
    cv2.line(vis, (glx, 0), (glx, PANEL_H), (0, 255, 0), 2)   # green = limit lo
    cv2.line(vis, (grx, 0), (grx, PANEL_H), (0, 0, 255), 2)   # red   = limit hi
    cv2.putText(vis, f"LIM {out_lo}", (glx + 3, PANEL_H - 78), FONT, 0.42, (0, 255, 0), 1)
    cv2.putText(vis, f"LIM {out_hi}", (max(0, grx - 64), PANEL_H - 78), FONT, 0.42, (0, 0, 255), 1)

    raw_bx = t['pos'][0] if (t['ttl'] > 0 or len(t['history']) > 2) else -1
    info = [
        f"Mapped X: {x_out if x_out >= 0 else '--'}/{POS_BYTE_MAX} (clamp {out_lo}..{out_hi})",
        f"Raw Ball X: {raw_bx if raw_bx >= 0 else '--'} px",
        f"Field: {xr_min}..{xr_max} px -> 0..255",
        f"Limits: {out_lo}..{out_hi}",
    ]
    for i, txt in enumerate(info):
        yy = 44 + i * 16
        cv2.putText(vis, txt, (8, yy), FONT, 0.40, (0, 0, 0), 3)
        cv2.putText(vis, txt, (8, yy), FONT, 0.40, (255, 255, 255), 1)

    # trail
    for i in range(1, len(t['history'])):
        alpha = i / len(t['history'])
        tc    = (0, int(180*alpha), int(255*alpha))
        p1    = (int(t['history'][i-1][0]*sx), int(t['history'][i-1][1]*sy))
        p2    = (int(t['history'][i][0]*sx),   int(t['history'][i][1]*sy))
        cv2.line(vis, p1, p2, tc, 2)

    for c in candidates:
        cx,cy,ri,_,_,passed,_,_,_,_,_,_,cnt = c
        if not passed: continue
        dcx,dcy = int(cx*sx), int(cy*sy)
        dr      = max(1, int(ri*(sx+sy)/2))
        ball_col = (0, 255, 0) if in_zone else (0, 200, 0)
        cv2.circle(vis,(dcx,dcy),dr,ball_col,2)
        cv2.circle(vis,(dcx,dcy),4,(255,255,255),-1)

    # Kalman predicted position + arrow
    if t['ttl'] > 0 or len(t['history']) > 2:
        px, py = t['pos']
        vx, vy = t['vel']
        dpx, dpy = int(px*sx), int(py*sy)
        fut_x = int(np.clip((px + vx*6)*sx, 0, PANEL_W-1))
        fut_y = int(np.clip((py + vy*6)*sy, 0, PANEL_H-1))

        cv2.arrowedLine(vis,(dpx,dpy),(fut_x,fut_y),(0,230,255),2,tipLength=0.35)
        cv2.circle(vis,(dpx,dpy),6,(0,230,255),2)

        speed = (vx**2+vy**2)**0.5
        cv2.putText(vis,f"vel:{speed:.1f}px/f",
                    (max(0,dpx-30),max(14,dpy-12)),FONT,0.32,(0,230,255),1)

    # ── bars ──────────────────────────────────
    bar_h  = 18
    bar_gap = 2
    bar1_y = PANEL_H - bar_h*2 - bar_gap - 4
    bar2_y = PANEL_H - bar_h - 2

    if t['ttl'] > 0 or len(t['history']) > 2:
        fut_px     = t['pos'][0] + t['vel'][0] * 6
        x_norm_pred = float(np.clip(fut_px, 0, img.shape[1])) / img.shape[1]
        pred_x_out  = clamp_output(map_and_clamp(fut_px, cfg['x_min_range'], cfg['x_max_range']),
                                   cfg['out_min'], cfg['out_max'])
        pred_x_mm   = cfg['goal_left_mm'] + x_norm_pred * (cfg['goal_right_mm'] - cfg['goal_left_mm'])
    else:
        pred_x_out = -1
        pred_x_mm  = -1.0

    cv2.rectangle(vis,(0,bar1_y),(PANEL_W,bar1_y+bar_h),(25,25,25),-1)
    if x_out >= 0:
        bx1 = int(x_out * PANEL_W / POS_BYTE_MAX)
        cv2.rectangle(vis,(0,bar1_y),(bx1,bar1_y+bar_h),(0,220,255),-1)
        lbl1 = f"now {x_out}/{POS_BYTE_MAX}  {x_mm:.0f}mm"
        cv2.putText(vis,lbl1,(min(bx1+4,PANEL_W-145),bar1_y+bar_h-4),FONT,0.34,(0,0,0),2)
        cv2.putText(vis,lbl1,(min(bx1+4,PANEL_W-145),bar1_y+bar_h-4),FONT,0.34,(255,255,255),1)
    else:
        cv2.putText(vis,"NO BALL",(PANEL_W//2-35,bar1_y+bar_h-3),FONT,0.36,(60,60,200),1)

    cv2.rectangle(vis,(0,bar2_y),(PANEL_W,bar2_y+bar_h),(20,20,20),-1)
    if pred_x_out >= 0:
        bx2 = int(pred_x_out * PANEL_W / POS_BYTE_MAX)
        cv2.rectangle(vis,(0,bar2_y),(bx2,bar2_y+bar_h),(0,230,255),-1)
        lbl2 = f"pred {pred_x_out}/{POS_BYTE_MAX}  {pred_x_mm:.0f}mm"
        cv2.putText(vis,lbl2,(min(bx2+4,PANEL_W-160),bar2_y+bar_h-4),FONT,0.34,(0,0,0),2)
        cv2.putText(vis,lbl2,(min(bx2+4,PANEL_W-160),bar2_y+bar_h-4),FONT,0.34,(0,0,0),1)
    else:
        cv2.putText(vis,"NO PRED",(PANEL_W//2-35,bar2_y+bar_h-3),FONT,0.36,(60,60,60),1)

    cv2.putText(vis,"NOW",(2,bar1_y+bar_h-4),FONT,0.28,(0,180,220),1)
    cv2.putText(vis,"PRD",(2,bar2_y+bar_h-4),FONT,0.28,(30,180,255),1)

    # ── kick-zone state badge ──────────────────────────────────────────
    if flashing:
        badge_txt, badge_col = "KICK!", (0, 255, 255)
    elif in_zone:
        badge_txt, badge_col = "IN ZONE", (0, 255, 0)
    elif zone_h > 0:
        badge_txt, badge_col = "armed", (180, 180, 180)
    else:
        badge_txt, badge_col = "zone off", (90, 90, 90)
    cv2.putText(vis, badge_txt, (PANEL_W // 2 - 30, 20), FONT, 0.55, badge_col, 2)

    if t['ttl'] > 0:
        ghost_alpha = t['ttl'] / GHOST_FRAMES
        cv2.putText(vis,f"ghost:{t['ttl']}f",
                    (PANEL_W-90,14),FONT,0.32,(0,int(220*ghost_alpha),int(220*ghost_alpha)),1)

    if persp_pts:
        cv2.putText(vis,"[PERSP]",(PANEL_W-70,PANEL_H-8),FONT,0.30,(200,200,0),1)

    _draw_arduino_telemetry(vis)
    _stamp(vis,"4 RESULT",(0,45,10),(0,230,100))
    return vis

def _draw_arduino_telemetry(panel):
    a = _arduino
    lines = []
    if a['calibrated']:
        lines.append(f"ARD axis: {a['measured_mm']:.0f} mm")
        lines.append(f"ARD pos:  {a['pos_mm']:.1f} mm")
        lines.append(f"ARD tgt:  {a['target_mm']:.1f} mm")
        lines.append(f"ARD st:   {a['state_str']}")
        box_col = (0, 180, 80)
        txt_col = (180, 255, 200)
    else:
        lines.append("ARD: CALIBRATING...")
        lines.append(f"ARD st:   {a['state_str']}")
        box_col = (40, 40, 0)
        txt_col = (0, 200, 255)

    fh = 14
    pad = 4
    box_w = 175
    box_h = len(lines) * fh + pad * 2
    bx = PANEL_W - box_w - 4
    by = 20
    cv2.rectangle(panel, (bx, by), (bx + box_w, by + box_h), box_col, -1)
    for i, ln in enumerate(lines):
        cv2.putText(panel, ln, (bx + pad, by + pad + fh * (i + 1) - 2),
                    FONT, 0.30, txt_col, 1)

def _calibration_overlay(panel):
    overlay = panel.copy()
    cv2.rectangle(overlay, (0, PANEL_H//2 - 22), (PANEL_W, PANEL_H//2 + 22),
                  (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.65, panel, 0.35, 0, panel)
    cv2.putText(panel, "WAITING FOR ARDUINO CALIBRATION",
                (12, PANEL_H//2 + 7), FONT, 0.50, (0, 200, 255), 1)

def _stamp(panel, title, bg_col, fg_col):
    (tw,th),_ = cv2.getTextSize(title, FONT, 0.40, 1)
    cv2.rectangle(panel,(0,0),(tw+14,th+8),bg_col,-1)
    cv2.putText(panel,title,(7,th+3),FONT,0.40,fg_col,1)

# ─────────────────────────────────────────────
#  4-Corner Perspective Selector window
# ─────────────────────────────────────────────
PERSP_WIN = "Perspective ROI — click 4 corners  |  Enter=confirm  C=clear  Esc=cancel"

_persp_sel = dict(active=False, pts=[], frame=None)

_CORNER_COLORS = [(0,230,255),(0,160,255),(0,80,255),(80,200,0)]
_CORNER_LABELS = ["1","2","3","4"]

def _persp_mouse_cb(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        pts = _persp_sel['pts']
        if len(pts) < 4:
            pts.append((x, y))
        else:
            dists = [(abs(p[0]-x)+abs(p[1]-y), i) for i, p in enumerate(pts)]
            _, idx = min(dists)
            pts[idx] = (x, y)

def _persp_draw(frame, pts):
    vis = frame.copy()
    if len(pts) >= 2:
        for i in range(len(pts)-1):
            cv2.line(vis, pts[i], pts[i+1], (200,200,0), 1)
        if len(pts) == 4:
            cv2.line(vis, pts[3], pts[0], (200,200,0), 1)
            poly = np.array(pts, dtype=np.int32)
            overlay = vis.copy()
            cv2.fillPoly(overlay, [poly], (50,50,0))
            cv2.addWeighted(overlay, 0.35, vis, 0.65, 0, vis)
            cv2.polylines(vis, [poly], True, (0,230,255), 2)

    for i, p in enumerate(pts):
        col = _CORNER_COLORS[i]
        cv2.circle(vis, p, 10, col, -1)
        cv2.circle(vis, p, 11, (255,255,255), 1)
        cv2.putText(vis, _CORNER_LABELS[i], (p[0]+13, p[1]+5), FONT, 0.6, col, 2)

    h, w = vis.shape[:2]
    if len(pts) < 4:
        msg = f"Click corner {len(pts)+1}/4  |  Enter=confirm  C=clear  Esc=cancel"
        col = (200,200,0)
    else:
        msg = "4 corners set — Enter to confirm  |  click near a point to reposition  |  C=clear"
        col = (0,230,255)
    cv2.putText(vis, msg, (10, h-12), FONT, 0.45, (0,0,0), 3)
    cv2.putText(vis, msg, (10, h-12), FONT, 0.45, col, 1)
    return vis

def enter_persp_mode(frame):
    _persp_sel['active'] = True
    _persp_sel['frame']  = frame.copy()
    _persp_sel['pts']    = list(_perspective['pts']) if _perspective['set'] else []
    cv2.namedWindow(PERSP_WIN, cv2.WINDOW_NORMAL)
    fw = min(frame.shape[1], 1280)
    fh = min(frame.shape[0], 720)
    cv2.resizeWindow(PERSP_WIN, fw, fh)
    cv2.setMouseCallback(PERSP_WIN, _persp_mouse_cb)

def handle_persp_mode():
    if not _persp_sel['active']:
        return False
    frame = _persp_sel['frame']
    pts   = _persp_sel['pts']
    vis   = _persp_draw(frame, pts)
    cv2.imshow(PERSP_WIN, vis)

    k = cv2.waitKey(1) & 0xFF
    if k in (13, ord('\r')):
        if len(pts) == 4:
            _perspective['pts']    = list(pts)
            _perspective['set']    = True
            _perspective['matrix'] = _compute_perspective_matrix(pts, FRAME_W, FRAME_H)
            print(f"[Perspective] Confirmed: {pts}")
        else:
            print(f"[Perspective] Need 4 corners, only {len(pts)} placed — cancelled")
        _persp_sel['active'] = False
        cv2.destroyWindow(PERSP_WIN)
    elif k in (ord('c'), ord('C')):
        _perspective.update(pts=[], matrix=None, set=False)
        _persp_sel['pts'] = []
        print("[Perspective] Cleared")
        _persp_sel['active'] = False
        cv2.destroyWindow(PERSP_WIN)
    elif k == 27:
        _persp_sel['active'] = False
        cv2.destroyWindow(PERSP_WIN)
    return True

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    global SERIAL_ENABLED, SEND_PREDICTED, _ser

    cap = cv2.VideoCapture(CAM_PORT)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    if not cap.isOpened():
        sys.exit(f"[ERROR] Cannot open camera {CAM_PORT}")

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    proc_w   = actual_w // DS
    proc_h   = actual_h // DS
    print(f"[Camera] {actual_w}x{actual_h}  proc={proc_w}x{proc_h}  DS={DS}")
    print("[Keys]  W=persp ROI  C=clear  S=save  U=toggle UART  P=toggle pred/now")
    print("        SPACE=test fire  R=re-arm trigger  Q/ESC=quit")
    print(f"[Proto] pos bytes 0..{POS_BYTE_MAX}, FIRE = 0x{FIRE_BYTE:02X}")

    make_trackbars()
    _serial_open()

    cv2.namedWindow(MAIN_WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(MAIN_WIN, PANEL_W*2, PANEL_H*2)
    cv2.moveWindow(MAIN_WIN, 0, 30)
    cv2.moveWindow(CTRL_WIN, PANEL_W*2 + 10, 30)

    prev_x_out = -1

    while True:
        if handle_persp_mode():
            continue

        ret, frame = cap.read()
        if not ret:
            continue

        warped, persp_pts = apply_perspective_warp(frame)
        proc = cv2.resize(warped, (proc_w, proc_h), interpolation=cv2.INTER_LINEAR)

        cfg = get_cfg()

        masks      = build_masks(proc, cfg)
        candidates = find_ball(proc, masks, cfg)
        x_out, x_mm = update_tracker(candidates, proc_w, cfg)

        # predicted values
        t = _tracker
        if t['ttl'] > 0 or len(t['history']) > 2:
            fut_px      = t['pos'][0] + t['vel'][0] * 6
            x_pred      = clamp_output(map_and_clamp(fut_px, cfg['x_min_range'], cfg['x_max_range']),
                                       cfg['out_min'], cfg['out_max'])
        else:
            x_pred = -1

        # ── sync goal_right_mm trackbar once calibration arrives ──────
        if _arduino['calibrated'] and not _arduino['trackbar_synced']:
            try:
                cv2.setTrackbarPos(TB['goal_right_mm'], CTRL_WIN,
                                   int(np.clip(_arduino['measured_mm'], 0, 5000)))
                _arduino['trackbar_synced'] = True
                print(f"[Cal] Trackbar synced to Arduino measured length: "
                      f"{_arduino['measured_mm']:.0f} mm")
            except Exception:
                pass

        # ── KICK ZONE trigger ────────────────────────────────────────
        in_zone = ball_in_kick_zone(proc_h, cfg['kick_zone_h'])
        now     = _now_ms()
        flashing = now < _kick['flash_until_ms']
        if (in_zone and not _kick['was_in']
                and (now - _kick['last_fire_ms']) >= KICK_REARM_MS
                and _arduino['calibrated']):
            _serial_send_fire()
            _kick['last_fire_ms']   = now
            _kick['flash_until_ms'] = now + 250
            flashing = True
        _kick['was_in'] = in_zone

        # ── send position to Arduino ─────────────────────────────────
        send_val = x_pred if SEND_PREDICTED else x_out
        if send_val >= 0 and _arduino['calibrated']:
            _serial_send_byte(send_val)
        _serial_drain_rx()

        if x_out != prev_x_out:
            if x_out >= 0:
                tag  = "PRED" if SEND_PREDICTED else "NOW "
                gate = "" if _arduino['calibrated'] else " [BLOCKED-no cal]"
                print(f"[Ball] now={x_out:3d} pred={x_pred:3d}  TX[{tag}]={send_val:3d}  "
                      f"dist={x_mm:.0f}mm{gate}", end='\r')
            else:
                print("[Ball] ---     ", end='\r')
            prev_x_out = x_out

        # ── build panels ──────────────────────
        p1 = panel_contours(proc, masks, candidates, cfg)
        p2 = panel_color_filter(proc, masks)
        p3 = panel_gate_diag(proc, masks, candidates, cfg)
        p4 = panel_result(proc, masks, candidates, cfg, x_out, x_mm, persp_pts,
                          in_zone, flashing)

        if not _arduino['calibrated']:
            for p in (p1, p2, p3, p4):
                _calibration_overlay(p)

        top    = np.hstack([p1, p2])
        bottom = np.hstack([p3, p4])
        grid   = np.vstack([top, bottom])
        cv2.imshow(MAIN_WIN, grid)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key in (ord('w'), ord('W')):
            ret2, raw = cap.read()
            if ret2:
                enter_persp_mode(raw)
        elif key in (ord('c'), ord('C')):
            _perspective.update(pts=[], matrix=None, set=False)
            print("\n[Perspective] Cleared")
        elif key in (ord('s'), ord('S')):
            save_cfg_file(cfg)
            _print_cfg(cfg)
        elif key in (ord('u'), ord('U')):
            SERIAL_ENABLED = not SERIAL_ENABLED
            print(f"\n[Serial] {'ENABLED' if SERIAL_ENABLED else 'DISABLED'}")
            if not SERIAL_ENABLED and _ser:
                try: _ser.close()
                except Exception: pass
                _ser = None
            elif SERIAL_ENABLED:
                _serial_open()
        elif key in (ord('p'), ord('P')):
            SEND_PREDICTED = not SEND_PREDICTED
            print(f"\n[TX  ] sending {'PREDICTED (yellow)' if SEND_PREDICTED else 'CURRENT (cyan)'} X")
        elif key == ord(' '):
            _serial_send_fire()
            _kick['last_fire_ms']   = _now_ms()
            _kick['flash_until_ms'] = _kick['last_fire_ms'] + 250
        elif key in (ord('r'), ord('R')):
            _kick['was_in']       = False
            _kick['last_fire_ms'] = 0
            print("\n[Kick] trigger re-armed")

    cap.release()
    cv2.destroyAllWindows()
    if _ser:
        try: _ser.close()
        except Exception: pass
    print()

def _print_cfg(cfg):
    print("\n# ── visao_debug config (full-res 1280×720) ──")
    print(f"H_RANGE       = ({cfg['h_lo']}, {cfg['h_hi']})")
    print(f"S_RANGE       = ({cfg['s_min']}, {cfg['s_max']})")
    print(f"V_RANGE       = ({cfg['v_min']}, {cfg['v_max']})")
    print(f"AREA          = ({cfg['area_min']}, {cfg['area_max']})")
    print(f"RADIUS        = ({cfg['rad_min']}, {cfg['rad_max']})")
    print(f"CIRC_MIN      = {cfg['circ_min']:.2f}")
    print(f"MORPH         = k={cfg['morph_k']} iter={cfg['morph_iter']}")
    print(f"GRAD_STD_MIN  = {cfg['grad_std_min']}")
    print(f"GRAD_MEAN_MIN = {cfg['grad_mean_min']}")
    print(f"BLUR_K        = {cfg['blur_k']}")
    print(f"GOAL_LEFT_MM  = {cfg['goal_left_mm']}")
    print(f"GOAL_RIGHT_MM = {cfg['goal_right_mm']}")
    print(f"KICK_ZONE_H   = {cfg['kick_zone_h']}")
    print(f"X_MIN_RANGE   = {cfg['x_min_range']}")
    print(f"X_MAX_RANGE   = {cfg['x_max_range']}")
    print(f"OUT_MIN       = {cfg['out_min']}")
    print(f"OUT_MAX       = {cfg['out_max']}")
    if _perspective['set']:
        print(f"PERSP_PTS     = {_perspective['pts']}")
    print(f"# ── DS={DS}x for Pi: spatial values / {DS} ──\n")

if __name__ == "__main__":
    main()
