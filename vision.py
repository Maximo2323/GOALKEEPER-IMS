#!/usr/bin/env python3
"""
Stereo Ball Detector with Kalman Tracking
==========================================
Splits the ZED stereo frame into left / right halves.
Each half gets its own independent Kalman tracker.

Detection strategy
------------------
Instead of defining every target colour (yellow, red, orange, black,
dark-blue), we define what we do NOT want — green (unripe seeds) — and
keep everything else.  Two pixel groups pass through to HoughCircles:
  1. Coloured non-green  (saturation >= S_MIN, hue outside green band)
  2. Very dark           (V < V_DARK, catches black / overmature seeds)

Classification (per detected circle)
-------------------------------------
  MADURO      — yellow, red, orange  (not dark, not blue-shifted)
  SOBREMADURO — black (V < V_DARK) or dark-blue (H in blue range)
  INCIERTO    — not enough saturation to decide

Kalman tracking
---------------
When a ball disappears the filter predicts its position and the next
search is constrained to a small window around that prediction.

Keys:  Q = quit
"""

import cv2
import numpy as np
import sys

# ══════════════════════════════════════════════════════════════════════
#  CAMERA
# ══════════════════════════════════════════════════════════════════════
CAM_PORT = 0        # index passed to VideoCapture (0 = first USB cam)
FRAME_W  = 1344     # full stereo frame width  (left eye + right eye)
FRAME_H  = 376      # full stereo frame height

# ══════════════════════════════════════════════════════════════════════
#  DISPLAY
# ══════════════════════════════════════════════════════════════════════
DISP_SCALE = 1.5    # multiply native half-frame size for the preview window
                    # (increase if the window is too small on your monitor)

# ══════════════════════════════════════════════════════════════════════
#  GREEN EXCLUSION  — pixels we want to REMOVE from the detection mask
#  Unripe (green) seeds are the only ones we skip.  Everything else
#  (yellow, red, orange, black, dark-blue) is kept as a candidate.
#
#  In OpenCV HSV: Hue is 0-179 (red≈0/179, yellow≈15-30, green≈35-85,
#  blue≈95-130), Saturation 0-255, Value (brightness) 0-255.
# ══════════════════════════════════════════════════════════════════════
GREEN_H_LO  = 30    # lower hue bound of "green" (OpenCV 0-179)
GREEN_H_HI  = 90    # upper hue bound of "green"
GREEN_S_MIN = 40    # only exclude a pixel as green if it has at least
                    # this much saturation (avoids masking grey shadows)

# ══════════════════════════════════════════════════════════════════════
#  CLASSIFICATION THRESHOLDS
#  Applied to the HSV statistics inside each detected circle.
# ══════════════════════════════════════════════════════════════════════
V_DARK    = 80      # mean brightness below this  → SOBREMADURO (black grain)
S_MIN     = 40      # mean saturation below this  → INCIERTO    (too grey)
H_BLUE_LO = 95      # hue lower bound for dark-blue → SOBREMADURO
H_BLUE_HI = 130     # hue upper bound for dark-blue → SOBREMADURO

# ══════════════════════════════════════════════════════════════════════
#  MORPHOLOGY  — cleans up the detection mask before HoughCircles
# ══════════════════════════════════════════════════════════════════════
MORPH_KERNEL     = 5    # side length of the structuring element (px)
MORPH_ITERATIONS = 2    # how many open + close passes to run

# ══════════════════════════════════════════════════════════════════════
#  GAUSSIAN BLUR  — smooths the mask so HoughCircles works better
# ══════════════════════════════════════════════════════════════════════
BLUR_KERNEL = 15    # must be an odd number

# ══════════════════════════════════════════════════════════════════════
#  HOUGH CIRCLES
# ══════════════════════════════════════════════════════════════════════
HOUGH_DP       = 1    # accumulator resolution vs image resolution ratio
HOUGH_MIN_DIST = 20   # minimum pixel distance between two circle centres
HOUGH_PARAM1   = 70   # Canny high threshold used internally
HOUGH_PARAM2   = 30   # accumulator votes needed (lower → more circles found)
BALL_MIN_R     = 10   # ignore circles smaller than this radius (px)
BALL_MAX_R     = 80   # ignore circles larger  than this radius (px)

# ══════════════════════════════════════════════════════════════════════
#  KALMAN TRACKER
# ══════════════════════════════════════════════════════════════════════
KALMAN_LOST_MAX   = 15  # frames without a detection before the track is dropped
KALMAN_SEARCH_PAD = 60  # px radius around the predicted centre used as the
                         # constrained search window when the ball is not visible

# ══════════════════════════════════════════════════════════════════════
#  DERIVED CONSTANTS  (do not edit these)
# ══════════════════════════════════════════════════════════════════════
HALF_W  = FRAME_W // 2
DISP_HW = int(HALF_W  * DISP_SCALE)
DISP_H  = int(FRAME_H * DISP_SCALE)
FONT    = cv2.FONT_HERSHEY_SIMPLEX


# ══════════════════════════════════════════════════════════════════════
#  KALMAN TRACKER CLASS
# ══════════════════════════════════════════════════════════════════════
class BallTracker:
    """
    Constant-velocity Kalman filter for a single ball.
    State  : [cx, cy, vx, vy]
    Measure: [cx, cy]
    """
    def __init__(self):
        kf = cv2.KalmanFilter(4, 2)   # 4 state vars, 2 measurement vars

        # Which state variables map to the measurements (cx, cy)
        kf.measurementMatrix = np.array(
            [[1, 0, 0, 0],
             [0, 1, 0, 0]], dtype=np.float32)

        # Next state = current state + velocity (simple constant-velocity)
        kf.transitionMatrix = np.array(
            [[1, 0, 1, 0],
             [0, 1, 0, 1],
             [0, 0, 1, 0],
             [0, 0, 0, 1]], dtype=np.float32)

        # How much we trust the process model (larger = reacts faster)
        kf.processNoiseCov     = np.eye(4, dtype=np.float32) * 0.03
        # How much we trust the sensor (larger = smoother but more lag)
        kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 1.0
        kf.errorCovPost        = np.eye(4, dtype=np.float32)

        self.kf         = kf
        self.active     = False   # True once the first detection arrives
        self.lost_count = 0       # frames since last confirmed detection
        self.radius     = 0       # last known ball radius (for drawing)

    def predict(self):
        """Advance the filter one frame; return (cx, cy) prediction or None."""
        if not self.active:
            return None
        p = self.kf.predict()
        return int(p[0]), int(p[1])

    def update(self, cx: int, cy: int, r: int):
        """Feed a confirmed measurement into the filter."""
        meas = np.array([[np.float32(cx)], [np.float32(cy)]])
        if not self.active:
            # Seed the state so the first correction lands in the right place
            self.kf.statePre  = np.array([cx, cy, 0, 0],
                                          dtype=np.float32).reshape(4, 1)
            self.kf.statePost = self.kf.statePre.copy()
            self.active = True
        self.kf.correct(meas)
        self.lost_count = 0
        self.radius     = r

    def mark_lost(self):
        """Call once per frame when no detection was found."""
        if not self.active:
            return
        self.lost_count += 1
        if self.lost_count > KALMAN_LOST_MAX:
            self.active     = False
            self.lost_count = 0


# ══════════════════════════════════════════════════════════════════════
#  DETECTION HELPERS
# ══════════════════════════════════════════════════════════════════════
def build_mask(half: np.ndarray) -> np.ndarray:
    """Convert a BGR half-frame to a cleaned binary mask via HSV thresholding."""
    lo   = np.array(HSV_LOWER, dtype=np.uint8)
    hi   = np.array(HSV_UPPER, dtype=np.uint8)
    hsv  = cv2.cvtColor(half, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lo, hi)

    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                     (MORPH_KERNEL, MORPH_KERNEL))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kern,
                            iterations=MORPH_ITERATIONS)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kern,
                            iterations=MORPH_ITERATIONS)
    mask = cv2.GaussianBlur(mask, (BLUR_KERNEL, BLUR_KERNEL), 0)
    return mask


def hough_circles(mask: np.ndarray,
                  min_r: int = BALL_MIN_R,
                  max_r: int = BALL_MAX_R):
    """Run HoughCircles on a mask; return array of (cx, cy, r) or None."""
    try:
        circles = cv2.HoughCircles(
            mask, cv2.HOUGH_GRADIENT,
            dp=HOUGH_DP, minDist=HOUGH_MIN_DIST,
            param1=HOUGH_PARAM1, param2=HOUGH_PARAM2,
            minRadius=min_r, maxRadius=max_r,
        )
    except cv2.error:
        return None
    if circles is None:
        return None
    return np.uint16(np.around(circles[0]))


def detect(half: np.ndarray, tracker: BallTracker):
    """
    Full detection + tracking step for one camera half.

    1. Build HSV mask over the whole half.
    2. If the tracker has an active prediction, cut the mask down to a small
       window around that prediction (ignores detections far away).
    3. Run HoughCircles on the (possibly constrained) mask.
    4. On hit  → update the Kalman filter.
       On miss → mark the tracker lost; if still within tolerance return
                 the predicted position so the caller can draw a ghost circle.

    Returns (found: bool, cx, cy, r)
      found=True  → real detection this frame
      found=False → Kalman prediction (ball recently lost)
      r=0         → no track at all
    """
    mask = build_mask(half)
    pred = tracker.predict()   # (cx, cy) or None

    # Restrict search to a padded bounding box around the prediction
    if pred is not None:
        px, py = pred
        h, w   = mask.shape
        x0 = max(0, px - KALMAN_SEARCH_PAD)
        x1 = min(w, px + KALMAN_SEARCH_PAD)
        y0 = max(0, py - KALMAN_SEARCH_PAD)
        y1 = min(h, py + KALMAN_SEARCH_PAD)
        search = np.zeros_like(mask)
        search[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    else:
        search = mask   # no prior → search everywhere

    circles = hough_circles(search)

    if circles is not None:
        # Choose the largest circle — most likely the real ball
        best = max(circles, key=lambda c: c[2])
        cx, cy, r = int(best[0]), int(best[1]), int(best[2])
        tracker.update(cx, cy, r)
        return True, cx, cy, r

    # No detection this frame
    tracker.mark_lost()
    if tracker.active and pred is not None:
        # Still within the lost tolerance — return ghost position
        return False, pred[0], pred[1], tracker.radius

    return False, 0, 0, 0


# ══════════════════════════════════════════════════════════════════════
#  DRAWING
# ══════════════════════════════════════════════════════════════════════
def draw_panel(panel: np.ndarray, title: str,
               found: bool, cx: int, cy: int, r: int,
               lost_count: int):
    """Annotate one display panel with title bar and ball overlay."""
    # Dark title bar
    cv2.rectangle(panel, (0, 0), (panel.shape[1], 36), (18, 18, 18), -1)
    cv2.putText(panel, title, (10, 26), FONT, 0.7, (220, 220, 220), 2)

    if r > 0:
        # Green = live detection, blue = Kalman prediction (ball hidden)
        colour = (0, 210, 0) if found else (0, 160, 220)
        label  = "DETECTED" if found else f"PREDICTED  (lost {lost_count}f)"
        cv2.circle(panel, (cx, cy), r, colour, 2)
        cv2.circle(panel, (cx, cy), 4, (255, 255, 255), -1)
        cv2.putText(panel, label,
                    (max(0, cx - r), max(50, cy - r - 6)),
                    FONT, 0.5, colour, 1)


def draw_divider(canvas: np.ndarray):
    cv2.line(canvas,
             (DISP_HW, 0), (DISP_HW, canvas.shape[0]),
             (70, 70, 70), 2)


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    cap = cv2.VideoCapture(CAM_PORT)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    if not cap.isOpened():
        sys.exit(f"[ERROR] Cannot open camera on port {CAM_PORT}")

    print(f"Camera: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))} x "
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
          f"@ {cap.get(cv2.CAP_PROP_FPS):.0f} fps")
    print("Q = quit")

    trackers = {"left": BallTracker(), "right": BallTracker()}

    cv2.namedWindow("Ball Detector", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Ball Detector", DISP_HW * 2, DISP_H)

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        halves = {
            "left":  frame[:, :HALF_W],
            "right": frame[:, HALF_W:],
        }

        canvas = np.zeros((DISP_H, DISP_HW * 2, 3), dtype=np.uint8)

        for i, (side, half) in enumerate(halves.items()):
            found, cx, cy, r = detect(half, trackers[side])

            # Scale detection coords to display size
            sx   = DISP_HW / HALF_W
            sy   = DISP_H  / FRAME_H
            disp = cv2.resize(half, (DISP_HW, DISP_H))

            draw_panel(
                disp,
                "LEFT  (lower intake)" if side == "left" else "RIGHT (upper intake)",
                found,
                int(cx * sx), int(cy * sy), max(1, int(r * sx)) if r > 0 else 0,
                trackers[side].lost_count,
            )

            canvas[:, i * DISP_HW:(i + 1) * DISP_HW] = disp

        draw_divider(canvas)
        cv2.imshow("Ball Detector", canvas)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
