#!/usr/bin/env python3
"""
vision_debug.py — GUI tuning tool for the goalkeeper vision.

Same detection + mapping as vision_raw.py, but WITH an OpenCV preview window and
trackbars so you can calibrate HSV + the horizontal goalkeeper range live. It
writes the SAME config.json that vision_raw.py reads, so: tune here, press 's',
then run vision_raw.py / the dispatcher.

Like vision_raw.py, it does NOT open serial. It also prints VISION:XX lines to
stdout, so you can even run it UNDER the dispatcher for live on-robot tuning:
    python3 goalkeeper_dispatcher.py --config config.json   # set vision_script=vision_debug.py

Keys:
    S = save current trackbar values into config.json
    Q / ESC = quit

On-screen it shows: Raw Ball X, Mapped X (0-255), X Min Range, X Max Range, and
draws vertical lines at the two range edges.
"""

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

# Reuse the exact detector + mapping from vision_raw (same folder).
from vision_raw import (Detector, map_and_clamp, clamp_output, make_perspective,
                        DEFAULT_CONFIG, OUT_MAX)

WIN = "Goalkeeper Vision Debug"
CTRL = "Controls"
FONT = cv2.FONT_HERSHEY_SIMPLEX

# (config-key, label, max-value) for the trackbars we expose.
TRACKBARS = [
    ("h_lo", "H low", 179), ("h_hi", "H high", 179),
    ("s_min", "S min", 255), ("s_max", "S max", 255),
    ("v_min", "V min", 255), ("v_max", "V max", 255),
    ("area_min", "Area min x10", 5000), ("area_max", "Area max x10", 8000),
    ("rad_min", "Radius min", 200), ("rad_max", "Radius max", 200),
    ("circ_min", "Circ min x100", 100),
    ("morph_k", "Morph K", 21), ("morph_iter", "Morph iter", 8),
    ("blur_k", "Blur K", 21),
    ("grad_std_min", "Grad STD min", 100), ("grad_mean_min", "Grad MEAN min", 100),
    ("kick_zone_h", "Kick Zone H", 720),
    ("x_min_range", "X Min Range", 1280),   # capped at proc width at runtime
    ("x_max_range", "X Max Range", 1280),
    ("out_min", "Limit Lo 0-255", 255),     # software limit switches (output clamp)
    ("out_max", "Limit Hi 0-255", 255),
]


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                cfg.update(json.load(f))
            print(f"[debug] loaded {path}", file=sys.stderr)
        except Exception as e:
            print(f"[debug] bad config {path}: {e}", file=sys.stderr)
    return cfg


def save_config(path, cfg):
    # merge over any existing file so we don't drop keys we don't expose
    existing = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(cfg)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"[debug] saved -> {path}", file=sys.stderr)


def make_trackbars(cfg, range_max):
    cv2.namedWindow(CTRL, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(CTRL, 420, 900)
    for key, label, maxv in TRACKBARS:
        if key in ("x_min_range", "x_max_range"):
            maxv = range_max          # ranges live in reference width (frame_w/ds)
        val = int(min(cfg.get(key, 0), maxv))
        cv2.createTrackbar(label, CTRL, val, maxv, lambda v: None)


def read_trackbars(cfg):
    out = dict(cfg)
    for key, label, _ in TRACKBARS:
        out[key] = cv2.getTrackbarPos(label, CTRL)
    # keep odd kernels valid
    out["morph_k"] = max(1, out["morph_k"] | 1)
    out["blur_k"] = max(1, out["blur_k"] | 1)
    out["morph_iter"] = max(1, out["morph_iter"])
    return out


def emit(line):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description="Goalkeeper vision debug/calibration GUI")
    here = os.path.dirname(os.path.abspath(__file__))
    # Tune into the DEBUG config so calibration never disturbs the running
    # runtime config.json. Deploy by copying config_debug.json -> config.json.
    ap.add_argument("--config", default=os.path.join(here, "config_debug.json"))
    ap.add_argument("--no-emit", action="store_true", help="don't print VISION lines")
    args = ap.parse_args()

    cfg = load_config(args.config)

    cap = cv2.VideoCapture(cfg["camera_index"])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["frame_w"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["frame_h"])
    if not cap.isOpened():
        sys.exit(f"[debug] cannot open camera {cfg['camera_index']}")

    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ds = max(1, int(cfg["ds"]))
    proc_w, proc_h = aw // ds, ah // ds
    ref_w = max(1, int(cfg["frame_w"]) // ds)   # ranges live in this width
    ref_h = max(1, int(cfg["frame_h"]) // ds)
    persp = make_perspective(cfg.get("perspective_pts"),
                             cfg["frame_w"], cfg["frame_h"], aw, ah)

    make_trackbars(cfg, ref_w)
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, proc_w, proc_h)

    out_interval = 1.0 / max(1, int(cfg["output_rate_hz"]))
    last_print = 0.0
    last_mapped = None

    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        if persp is not None:
            frame = cv2.warpPerspective(frame, persp, (aw, ah))
        proc = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_LINEAR)

        cfg = read_trackbars(cfg)
        detector = Detector(cfg)                  # cheap; rebuilt so slider edits apply live
        found = detector.detect(proc)

        x_min, x_max = int(cfg["x_min_range"]), int(cfg["x_max_range"])
        out_lo, out_hi = int(cfg["out_min"]), int(cfg["out_max"])
        vis = proc.copy()
        sf = proc_w / ref_w        # reference-px -> on-screen proc-px (for drawing)

        # field calibration lines (cyan) -> output 0 / 255
        cv2.line(vis, (int(x_min * sf), 0), (int(x_min * sf), proc_h), (255, 255, 0), 1)
        cv2.line(vis, (int(x_max * sf), 0), (int(x_max * sf), proc_h), (255, 255, 0), 1)
        cv2.putText(vis, "field 0",   (int(x_min * sf) + 3, 16), FONT, 0.45, (255, 255, 0), 1)
        cv2.putText(vis, "field 255", (max(0, int(x_max * sf) - 70), 16), FONT, 0.45, (255, 255, 0), 1)

        # software limit switches (green=lo, red=hi) -> output clamp [out_lo,out_hi]
        span = (x_max - x_min)
        lo_px = int((x_min + (out_lo / 255.0) * span) * sf)
        hi_px = int((x_min + (out_hi / 255.0) * span) * sf)
        cv2.line(vis, (lo_px, 0), (lo_px, proc_h), (0, 255, 0), 2)
        cv2.line(vis, (hi_px, 0), (hi_px, proc_h), (0, 0, 255), 2)
        cv2.putText(vis, f"LIM {out_lo}", (lo_px + 3, proc_h - 10), FONT, 0.5, (0, 255, 0), 1)
        cv2.putText(vis, f"LIM {out_hi}", (max(0, hi_px - 60), proc_h - 10), FONT, 0.5, (0, 0, 255), 1)

        raw_bx, mapped = -1, last_mapped
        if found is not None:
            cx, cy, r = found
            raw_bx = cx
            cx_ref = cx * ref_w / proc_w      # scale into reference width
            mapped = clamp_output(map_and_clamp(cx_ref, x_min, x_max), out_lo, out_hi)
            last_mapped = mapped
            cv2.circle(vis, (cx, cy), r, (0, 255, 0), 2)
            cv2.circle(vis, (cx, cy), 3, (255, 255, 255), -1)

        # kick zone band (scale calibrated height into this resolution)
        kz = int(cfg["kick_zone_h"])
        if kz > 0:
            kz_proc = int(kz * proc_h / ref_h)
            cv2.rectangle(vis, (0, proc_h - kz_proc), (proc_w, proc_h), (0, 0, 255), 1)

        # readout
        info = [
            f"Raw Ball X: {raw_bx if raw_bx >= 0 else '--'} px",
            f"Mapped X:   {mapped if mapped is not None else '--'} / {OUT_MAX} (clamp {out_lo}..{out_hi})",
            f"Field: {x_min}..{x_max} px",
            f"Limits: {out_lo}..{out_hi}",
            "S=save  Q=quit",
        ]
        for i, txt in enumerate(info):
            y = 22 + i * 20
            cv2.putText(vis, txt, (8, y), FONT, 0.5, (0, 0, 0), 3)
            cv2.putText(vis, txt, (8, y), FONT, 0.5, (255, 255, 255), 1)

        cv2.imshow(WIN, vis)

        # emit VISION line (so it can run under the dispatcher too)
        now = time.monotonic()
        if not args.no_emit and last_mapped is not None and now - last_print >= out_interval:
            emit(f"VISION:{last_mapped:02X}")
            last_print = now

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key in (ord('s'), ord('S')):
            save_config(args.config, cfg)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
