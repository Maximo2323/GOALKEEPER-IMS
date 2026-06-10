#!/usr/bin/env python3
"""
vision_raw.py — headless goalkeeper ball tracker.

ARCHITECTURE: this script does NOT open the serial port. It only DETECTS the
ball and prints tagged lines to STDOUT:

    VISION:7F        position 0..255 as 2 hex digits (00=left .. FF=right)
    VISION:FIRE      request a solenoid kick (kick-zone trigger)

The goalkeeper_dispatcher.py process captures this stdout, parses the lines,
and is the ONLY thing that writes bytes to /dev/goalkeeper_serial.

  * STDOUT = VISION lines ONLY (clean, machine-readable, one per output tick).
  * STDERR = all human logs (so they never pollute the VISION stream).

No-ball behavior (configurable via config "no_ball_behavior"):
    "hold"    (default) keep printing the last known position — no jumping
    "neutral" print VISION:7F (center)
    "silent"  print nothing until the ball is seen again

Run standalone (for debugging the stream):
    python3 vision_raw.py --config config.json
"""

import argparse
import json
import logging
import os
import sys
import time

import cv2
import numpy as np

# Logs go to STDERR so STDOUT stays a clean VISION stream.
log = logging.getLogger("vision_raw")

OUT_MIN = 0
OUT_MAX = 255       # logical range; the DISPATCHER clamps to the wire protocol


# ─────────────────────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "camera_index": 0,
    "frame_w": 1280, "frame_h": 720, "ds": 2,

    "h_lo": 0,  "h_hi": 30,
    "s_min": 80, "s_max": 255,
    "v_min": 80, "v_max": 255,
    "area_min": 40,  "area_max": 300,   # x10
    "rad_min": 10,   "rad_max": 80,
    "circ_min": 50,                     # x100
    "morph_k": 5,    "morph_iter": 2,
    "blur_k": 5,
    "grad_std_min": 5, "grad_mean_min": 5,

    "x_min_range": 120,                 # proc-px that maps to output 0
    "x_max_range": 520,                 # proc-px that maps to output 255

    # SOFTWARE LIMIT SWITCHES: clamp the 0..255 output to this safe sub-range
    # so the stepper never reaches the physical limits.
    "out_min": 20,
    "out_max": 235,

    "kick_zone_h": 0,                   # 0 disables auto-fire
    "kick_rearm_ms": 1200,

    "perspective_pts": [],

    "no_ball_behavior": "hold",         # hold | neutral | silent
    "neutral_value": 127,
    "output_rate_hz": 30,               # max VISION lines per second
    "status_period_s": 2.0,             # stderr status log cadence
}


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                cfg.update(json.load(f))
            log.info("Loaded config: %s", path)
        except Exception as e:
            log.error("Bad config %s: %s — using defaults", path, e)
    else:
        log.warning("Config %s missing — using defaults", path)
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
#  Mapping
# ─────────────────────────────────────────────────────────────────────────────
def map_and_clamp(x, in_min, in_max, out_min=OUT_MIN, out_max=OUT_MAX):
    """Map x in [in_min,in_max] to [out_min,out_max], clamped outside the range.

    Ball left of in_min -> out_min, right of in_max -> out_max. The camera can
    still see the ball outside the range; we just clamp the output.
    """
    if in_max == in_min:
        return (out_min + out_max) // 2
    mapped = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    return int(round(max(out_min, min(out_max, mapped))))


def clamp_output(value, lo, hi):
    """Software limit switches: keep the 0..255 output within [lo, hi] so the
    stepper never reaches the physical ends. Order-safe."""
    if lo > hi:
        lo, hi = hi, lo
    return max(lo, min(hi, value))


# ─────────────────────────────────────────────────────────────────────────────
#  Perspective warp (optional)
# ─────────────────────────────────────────────────────────────────────────────
def _order_corners(pts):
    arr = np.array(pts, dtype="float32")
    s = arr.sum(axis=1); d = np.diff(arr, axis=1).ravel()
    return np.array([arr[np.argmin(s)], arr[np.argmin(d)],
                     arr[np.argmax(s)], arr[np.argmax(d)]], dtype="float32")


def make_perspective(pts, cal_w, cal_h, w, h):
    """Build the warp matrix.

    pts are in the CALIBRATION resolution (cal_w x cal_h, e.g. 1280x720 from the
    Mac debug tool). They're scaled to THIS camera's actual frame (w x h) so the
    same saved corners work regardless of the camera's resolution.
    """
    if not pts or len(pts) != 4:
        return None
    sx, sy = w / float(cal_w), h / float(cal_h)
    spts = [(p[0] * sx, p[1] * sy) for p in pts]
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")
    return cv2.getPerspectiveTransform(_order_corners(spts), dst)


# ─────────────────────────────────────────────────────────────────────────────
#  Ball detector (HSV + shape + gradient gate)
# ─────────────────────────────────────────────────────────────────────────────
class Detector:
    def __init__(self, cfg):
        self.h_lo, self.h_hi = cfg["h_lo"], cfg["h_hi"]
        self.s_min, self.s_max = cfg["s_min"], cfg["s_max"]
        self.v_min, self.v_max = cfg["v_min"], cfg["v_max"]
        self.area_min = cfg["area_min"] * 10
        self.area_max = cfg["area_max"] * 10
        self.rad_min, self.rad_max = cfg["rad_min"], cfg["rad_max"]
        self.circ_min = cfg["circ_min"] * 0.01
        self.morph_k = max(1, int(cfg["morph_k"]) | 1)
        self.morph_iter = max(1, int(cfg["morph_iter"]))
        self.blur_k = max(1, int(cfg["blur_k"]) | 1)
        self.grad_std_min = cfg["grad_std_min"]
        self.grad_mean_min = cfg["grad_mean_min"]
        self._kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (self.morph_k, self.morph_k))

    def _mask(self, img):
        blur = cv2.GaussianBlur(img, (self.blur_k, self.blur_k), 0)
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
        if self.h_lo <= self.h_hi:
            mask = cv2.inRange(hsv, (self.h_lo, self.s_min, self.v_min),
                               (self.h_hi, self.s_max, self.v_max))
        else:
            m1 = cv2.inRange(hsv, (0, self.s_min, self.v_min),
                             (self.h_hi, self.s_max, self.v_max))
            m2 = cv2.inRange(hsv, (self.h_lo, self.s_min, self.v_min),
                             (179, self.s_max, self.v_max))
            mask = cv2.bitwise_or(m1, m2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel, iterations=self.morph_iter)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel, iterations=self.morph_iter)
        return mask

    def _grad_ok(self, grad_mag, cx, cy, r):
        h, w = grad_mag.shape
        rr = max(2, r)
        x0, x1 = max(0, cx - rr), min(w, cx + rr + 1)
        y0, y1 = max(0, cy - rr), min(h, cy + rr + 1)
        if x1 <= x0 or y1 <= y0:
            return False
        patch = grad_mag[y0:y1, x0:x1]
        return patch.size >= 4 and patch.std() >= self.grad_std_min and patch.mean() >= self.grad_mean_min

    def detect(self, img):
        """Return (cx, cy, r) of the ball CLOSEST TO THE GOAL, or None.

        With several balls on the track we want the most urgent one — the one
        nearest the goalkeeper, i.e. lowest on the screen (largest y / nearest
        the bottom / kick line). Among all valid candidates we keep the one with
        the greatest cy.
        """
        mask = self._mask(img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.magnitude(gx, gy)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best, best_cy = None, -1            # pick the LOWEST ball (closest to goal)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.area_min or area > self.area_max:
                continue
            perim = cv2.arcLength(cnt, True)
            if perim == 0:
                continue
            if (4 * np.pi * area / (perim * perim)) < self.circ_min:
                continue
            (x, y), r = cv2.minEnclosingCircle(cnt)
            cx, cy, ri = int(x), int(y), int(r)
            if not (self.rad_min <= ri <= self.rad_max):
                continue
            if not self._grad_ok(grad_mag, cx, cy, ri):
                continue
            if cy > best_cy:                # lower on screen = closer to the goal
                best, best_cy = (cx, cy, ri), cy
        return best


def open_camera(cfg):
    while True:
        cap = cv2.VideoCapture(cfg["camera_index"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["frame_w"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["frame_h"])
        if cap.isOpened():
            aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            log.info("Camera %s opened %dx%d", cfg["camera_index"], aw, ah)
            return cap, aw, ah
        log.warning("Camera %s unavailable — retry in 3s", cfg["camera_index"])
        cap.release()
        time.sleep(3.0)


def emit(line):
    """Print a VISION line to STDOUT (the dispatcher reads this)."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────────────────────────────────────
def run(cfg):
    detector = Detector(cfg)
    cap, aw, ah = open_camera(cfg)
    ds = max(1, int(cfg["ds"]))
    proc_w, proc_h = aw // ds, ah // ds
    persp = make_perspective(cfg.get("perspective_pts"),
                             cfg["frame_w"], cfg["frame_h"], aw, ah)

    # Loud diagnostic so we can SEE the warp is correct for this resolution.
    # If perspective is ON, every "corner(cam)" must fall inside 0..aw / 0..ah;
    # if they exceed the camera size, the warp grabs a sub-region (the classic
    # "top-left corner" bug) and this script is the OLD un-scaled version.
    _pp = cfg.get("perspective_pts") or []
    if persp is not None and len(_pp) == 4:
        _sx, _sy = aw / float(cfg["frame_w"]), ah / float(cfg["frame_h"])
        _scaled = [(int(p[0] * _sx), int(p[1] * _sy)) for p in _pp]
        log.info("PERSPECTIVE ON  calib=%dx%d -> camera=%dx%d  corners(cam)=%s",
                 cfg["frame_w"], cfg["frame_h"], aw, ah, _scaled)
    else:
        log.info("PERSPECTIVE OFF (perspective_pts empty or not 4 points)")

    x_min, x_max = int(cfg["x_min_range"]), int(cfg["x_max_range"])
    out_lo, out_hi = int(cfg["out_min"]), int(cfg["out_max"])
    # x_min_range/x_max_range are PIXELS in the "reference" processing width =
    # frame_w/ds — the width the Mac debug tool calibrates in. This camera may
    # give a different resolution, so we scale ball-x into the reference width
    # below. Result: the SAME x_min/x_max (and ball_debug_config.json values)
    # behave identically no matter what resolution the camera actually delivers.
    ref_w = max(1, int(cfg["frame_w"]) // ds)
    ref_h = max(1, int(cfg["frame_h"]) // ds)      # reference height for kick zone
    kick_zone_h = int(cfg["kick_zone_h"])
    rearm_ms = int(cfg["kick_rearm_ms"])
    behavior = str(cfg["no_ball_behavior"]).lower()
    neutral = int(cfg["neutral_value"])
    out_interval = 1.0 / max(1, int(cfg["output_rate_hz"]))
    status_period = float(cfg["status_period_s"])

    log.info("Range %d..%d px (ref_w=%d) -> 0..255 clamp %d..%d | no_ball=%s | %d Hz | kick_zone_h=%d",
             x_min, x_max, ref_w, out_lo, out_hi, behavior, int(cfg["output_rate_hz"]), kick_zone_h)
    log.info("camera proc=%dx%d  ball-x scaled by ref_w/proc_w=%.3f", proc_w, proc_h, ref_w / proc_w)

    last_mapped = None
    last_print = 0.0
    last_status = 0.0
    last_fire_ms = 0

    last_cx_ref = None
    PREDICT_FRAMES = 3.5

    while True:
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                log.warning("Camera read failed — reopening")
                cap.release()
                cap, aw, ah = open_camera(cfg)
                proc_w, proc_h = aw // ds, ah // ds
                persp = make_perspective(cfg.get("perspective_pts"),
                                         cfg["frame_w"], cfg["frame_h"], aw, ah)
                continue

            if persp is not None:
                frame = cv2.warpPerspective(frame, persp, (aw, ah))
            proc = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_LINEAR)

            found = detector.detect(proc)
            have_ball = found is not None
            if have_ball:
                cx, cy, r = found
                # Scale ball-x from this camera's actual proc width into the reference width.
                cx_ref = cx * ref_w / proc_w
                # Prediction:
                # dx_ref = how much the ball moved since last frame.
                # PREDICT_FRAMES controls how aggressive the prediction is.
                if last_cx_ref is not None:
                    dx_ref = cx_ref - last_cx_ref
                    cx_send = cx_ref + dx_ref * PREDICT_FRAMES
                else:
                    cx_send = cx_ref
                last_cx_ref = cx_ref
                last_mapped = clamp_output(map_and_clamp(cx_send, x_min, x_max), out_lo, out_hi)
            now = time.monotonic()

            # ── emit position at the controlled rate ───────────────────────
            if now - last_print >= out_interval:
                if have_ball or behavior == "hold":
                    if last_mapped is not None:
                        emit(f"VISION:{last_mapped:02X}")
                        last_print = now
                elif behavior == "neutral":
                    emit(f"VISION:{neutral:02X}")
                    last_print = now
                # "silent": print nothing when no ball

            # ── kick zone -> FIRE ──────────────────────────────────────────
            if have_ball and kick_zone_h > 0:
                _, cy, r = found
                kz_proc = kick_zone_h * proc_h / ref_h   # scale to this resolution
                if (cy + r) >= (proc_h - kz_proc):
                    now_ms = int(time.time() * 1000)
                    if now_ms - last_fire_ms >= rearm_ms:
                        emit("VISION:FIRE")
                        last_fire_ms = now_ms
                        log.info("kick-zone FIRE")

            # ── throttled status (stderr) ──────────────────────────────────
            if now - last_status >= status_period:
                last_status = now
                if have_ball:
                    log.info("ball_x=%d mapped=%d (0x%02X)", found[0], last_mapped, last_mapped)
                else:
                    log.info("no ball (behavior=%s, last=%s)", behavior, last_mapped)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log.exception("loop error (continuing): %s", e)
            time.sleep(0.3)

    cap.release()


def main():
    ap = argparse.ArgumentParser(description="Headless goalkeeper vision (prints VISION lines)")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "config.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [vision_raw %(levelname)s] %(message)s",
        stream=sys.stderr,          # keep STDOUT clean for VISION lines
    )
    cfg = load_config(args.config)
    log.info("vision_raw starting (no serial; printing VISION:XX to stdout)")
    run(cfg)


if __name__ == "__main__":
    main()
