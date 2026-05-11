import cv2 as cv
import numpy as np

# ============================================================
#  TRACKING BEHAVIOR
# ============================================================
BUFFER_SIZE = 2
# How many consecutive frames a circle must appear before
# it's accepted as a real detection.
# Lower  = faster response, more jitter
# Higher = smoother but slower to lock on

# ============================================================
#  KALMAN FILTER SETUP
# ============================================================
# Tracks state: [x, y, radius, vx, vy, vr]
#   x, y    = center position
#   radius  = circle radius
#   vx, vy  = velocity in x and y
#   vr      = rate of radius change
#
# The Kalman filter does two things every frame:
#   1. PREDICT — where should the ball be based on its last velocity?
#   2. CORRECT — a detection came in, blend prediction with measurement

def make_kalman():
    kf = cv.KalmanFilter(6, 3)
    # --- Transition matrix (physics model) ---
    # Describes how state evolves frame to frame:
    #   new_x      = x  + vx    (position += velocity)
    #   new_y      = y  + vy
    #   new_radius = r  + vr
    #   new_vx     = vx          (velocity unchanged unless corrected)
    #   new_vy     = vy
    #   new_vr     = vr
    kf.transitionMatrix = np.array([
        [1, 0, 0, 1, 0, 0],   # x      depends on x and vx
        [0, 1, 0, 0, 1, 0],   # y      depends on y and vy
        [0, 0, 1, 0, 0, 1],   # radius depends on r and vr
        [0, 0, 0, 1, 0, 0],   # vx     stays the same
        [0, 0, 0, 0, 1, 0],   # vy     stays the same
        [0, 0, 0, 0, 0, 1],   # vr     stays the same
    ], dtype=np.float32)

    # --- Measurement matrix ---
    # We only observe x, y, radius (not velocity directly)
    kf.measurementMatrix = np.array([
        [1, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 1, 0, 0, 0],
    ], dtype=np.float32)

    # --- Process noise covariance (Q) ---
    # How much we trust the physics model.
    # Higher values = filter assumes the ball can change speed/direction quickly
    # Lower  values = filter assumes smooth, predictable motion
    # Tune these if the prediction arrow overshoots or lags on fast direction changes
    q_pos    = 0.05   # uncertainty in position evolution  (increase for erratic movement)
    q_vel    = 0.1    # uncertainty in velocity evolution  (increase if ball accelerates a lot)
    q_radius = 0.01   # uncertainty in radius change       (increase if ball zooms in/out fast)
    kf.processNoiseCov = np.diag([
        q_pos, q_pos, q_radius, q_vel, q_vel, q_radius
    ]).astype(np.float32)

    # --- Measurement noise covariance (R) ---
    # How much we trust the raw detector output.
    # Higher = detector is noisy, trust the prediction more
    # Lower  = detector is accurate, trust measurements more
    r_pos    = 5.0    # position measurement noise    (increase if detections jitter a lot)
    r_radius = 2.0    # radius measurement noise      (increase if radius jumps around)
    kf.measurementNoiseCov = np.diag([
        r_pos, r_pos, r_radius
    ]).astype(np.float32)

    # --- Error covariance (P) ---
    # Initial uncertainty in the state estimate.
    # A large value means "we don't know where it is yet"
    kf.errorCovPost = np.eye(6, dtype=np.float32) * 1.0

    return kf


def reset_tracking(kf):
    """Clears all tracking state and resets the Kalman filter."""
    kf = make_kalman()
    return kf, None, [], 0, 0, 0


# ============================================================
#  HSV COLOR RANGE  (orange golf ball defaults)
# ============================================================
# Hue in OpenCV is 0–179 (half of standard 360°)
# Orange typically sits around H=5–25
# Use the "HSV Tuning" trackbar window to dial these in live
HSV_H_MIN_DEFAULT = 5
HSV_H_MAX_DEFAULT = 25
HSV_S_MIN_DEFAULT = 100   # Saturation: 0=grey, 255=vivid color
HSV_S_MAX_DEFAULT = 255
HSV_V_MIN_DEFAULT = 100   # Value (brightness): 0=black, 255=white
HSV_V_MAX_DEFAULT = 255

# ============================================================
#  HOUGH CIRCLES PARAMETERS
# ============================================================
HOUGH_DP        = 1   # Accumulator resolution ratio.
                        # 1.0 = same as image, higher = faster but less precise
HOUGH_MIN_DIST  = 50    # Minimum distance between two detected circle centers (pixels)
                        # Prevents double-detections on the same ball
HOUGH_PARAM1    = 70   # Canny upper threshold — higher = only very strong edges
                        # Lower if ball edges are weak (dim lighting, similar colors)
HOUGH_PARAM2    = 30    # Accumulator threshold — lower = more circles detected
                        # Raise if you get too many false circles
HOUGH_MIN_R     = 10    # Minimum radius to detect (pixels)
                        # Set to roughly half the smallest expected ball size
HOUGH_MAX_R     = 100    # Maximum radius to detect (pixels)
                        # Set to slightly larger than the biggest expected ball size

# ============================================================
#  ROI (search window) PARAMETERS
# ============================================================
ROI_BASE_MARGIN = 120   # Minimum search margin around predicted position (pixels)
                        # Increase if ball moves faster than the window can follow
ROI_SPEED_SCALE = 3     # Margin grows by this factor times current speed
                        # Higher = bigger window at high speed (safer but more noise)
ROI_RADIUS_SCALE = 1.5  # Margin also scales with circle radius
                        # Useful when ball is close (large radius = fast pixel movement)

# ============================================================
#  VELOCITY DECAY (used only when Kalman loses the ball)
# ============================================================
VEL_DECAY = 0.8         # Multiplied against velocity each frame when no detection
                        # 1.0 = no decay (drifts forever), 0.0 = stops immediately

# ============================================================
#  PREDICTION ARROW DISPLAY
# ============================================================
ARROW_SCALE     = 5     # How many frames ahead the arrow tip represents
                        # Higher = longer arrow, easier to see trajectory
ARROW_COLOR     = (0, 255, 255)   # BGR — default cyan
ARROW_THICKNESS = 2

# ============================================================
#  BLUR KERNEL SIZE
# ============================================================
# Must be odd. Larger = more smoothing (less noise) but softer edges
# Too large blurs the ball edge and hurts detection
BLUR_KERNEL = 15

# ============================================================
#  MORPHOLOGY (mask cleanup)
# ============================================================
MORPH_KERNEL_SIZE = 5   # Size of ellipse used for open/close
                        # Larger removes bigger noise blobs and fills bigger holes
MORPH_ITERATIONS  = 2   # How many times to apply each operation
                        # More iterations = more aggressive cleanup


dist = lambda x1, y1, x2, y2: (x1 - x2)**2 + (y1 - y2)**2

cap = cv.VideoCapture(0)
kf = make_kalman()

prevCircle     = None
candidate_buffer = []
vel_x, vel_y, vel_r = 0, 0, 0
kalman_initialized = False   # True once we've fed the first real detection in

reset_flag = False
def on_mouse(event, x, y, flags, param):
    global reset_flag
    if event == cv.EVENT_LBUTTONDOWN:
        if 10 <= x <= 160 and 10 <= y <= 45:
            reset_flag = True

cv.namedWindow("circles")
cv.setMouseCallback("circles", on_mouse)

def nothing(x): pass
cv.namedWindow("HSV Tuning")
cv.createTrackbar("H Min", "HSV Tuning", HSV_H_MIN_DEFAULT, 179, nothing)
cv.createTrackbar("H Max", "HSV Tuning", HSV_H_MAX_DEFAULT, 179, nothing)
cv.createTrackbar("S Min", "HSV Tuning", HSV_S_MIN_DEFAULT, 255, nothing)
cv.createTrackbar("S Max", "HSV Tuning", HSV_S_MAX_DEFAULT, 255, nothing)
cv.createTrackbar("V Min", "HSV Tuning", HSV_V_MIN_DEFAULT, 255, nothing)
cv.createTrackbar("V Max", "HSV Tuning", HSV_V_MAX_DEFAULT, 255, nothing)


while True:

    ret, frame = cap.read()
    if not ret:
        print("Can't receive frame (stream end?). Exiting ...")
        break

    if reset_flag:
        kf, prevCircle, candidate_buffer, vel_x, vel_y, vel_r = reset_tracking(kf)
        kalman_initialized = False
        reset_flag = False

    # --------------------------------------------------------
    #  COLOR MASKING
    # --------------------------------------------------------
    hsv = cv.cvtColor(frame, cv.COLOR_BGR2HSV)

    h_min = cv.getTrackbarPos("H Min", "HSV Tuning")
    h_max = cv.getTrackbarPos("H Max", "HSV Tuning")
    s_min = cv.getTrackbarPos("S Min", "HSV Tuning")
    s_max = cv.getTrackbarPos("S Max", "HSV Tuning")
    v_min = cv.getTrackbarPos("V Min", "HSV Tuning")
    v_max = cv.getTrackbarPos("V Max", "HSV Tuning")

    mask = cv.inRange(hsv,
                      np.array([h_min, s_min, v_min]),
                      np.array([h_max, s_max, v_max]))

    kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE,
                                      (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    mask = cv.morphologyEx(mask, cv.MORPH_OPEN,  kernel, iterations=MORPH_ITERATIONS)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=MORPH_ITERATIONS)

    blurframe = cv.GaussianBlur(mask, (BLUR_KERNEL, BLUR_KERNEL), 0)
    cv.imshow("mask", blurframe)

    # --------------------------------------------------------
    #  KALMAN PREDICT — always run every frame
    # --------------------------------------------------------
    # Even with no detection, the filter advances its internal
    # state estimate using the transition matrix (position += velocity)
    if kalman_initialized:
        predicted = kf.predict()
        # predicted = [x, y, radius, vx, vy, vr]
        kx  = int(predicted[0])
        ky  = int(predicted[1])
        kr  = int(max(1, predicted[2]))
        kvx = float(predicted[3])
        kvy = float(predicted[4])
    else:
        kx, ky, kr, kvx, kvy = 0, 0, 0, 0, 0

    # --------------------------------------------------------
    #  ROI CROP
    # --------------------------------------------------------
    offset_x, offset_y = 0, 0
    search_area = blurframe

    ref = prevCircle  # use last known position to build the search window
    if ref is not None:
        x, y, r = int(ref[0]), int(ref[1]), int(ref[2])

        if kalman_initialized:
            # Use Kalman-predicted position as ROI center
            # Much better than raw last position when ball is moving fast
            px, py = kx, ky
        else:
            px, py = x, y

        speed  = np.sqrt(kvx**2 + kvy**2)
        margin = int(max(ROI_BASE_MARGIN,
                         speed * ROI_SPEED_SCALE,
                         r     * ROI_RADIUS_SCALE))

        x1 = max(0, px - r - margin)
        y1 = max(0, py - r - margin)
        x2 = min(frame.shape[1], px + r + margin)
        y2 = min(frame.shape[0], py + r + margin)

        if x2 > x1 and y2 > y1:
            crop = blurframe[y1:y2, x1:x2]
            if crop is not None and crop.size > 0:
                search_area = crop
                offset_x, offset_y = x1, y1
        else:
            kf, prevCircle, candidate_buffer, vel_x, vel_y, vel_r = reset_tracking(kf)
            kalman_initialized = False

    # --------------------------------------------------------
    #  HOUGH CIRCLE DETECTION
    # --------------------------------------------------------
    circles = None
    if search_area is not None and search_area.size > 0:
        try:
            circles = cv.HoughCircles(
                search_area,
                cv.HOUGH_GRADIENT,
                dp        = HOUGH_DP,
                minDist   = HOUGH_MIN_DIST,
                param1    = HOUGH_PARAM1,
                param2    = HOUGH_PARAM2,
                minRadius = HOUGH_MIN_R,
                maxRadius = HOUGH_MAX_R,
            )
        except cv.error as e:
            print(f"HoughCircles error (skipping frame): {e}")

    # --------------------------------------------------------
    #  DETECTION → BUFFER → KALMAN CORRECT
    # --------------------------------------------------------
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for c in circles[0]:
            c[0] += offset_x
            c[1] += offset_y

        chosen = (circles[0][0] if prevCircle is None
                  else min(circles[0],
                           key=lambda c: dist(c[0], c[1], prevCircle[0], prevCircle[1])))

        candidate_buffer.append(chosen)
        if len(candidate_buffer) > BUFFER_SIZE:
            candidate_buffer = candidate_buffer[-BUFFER_SIZE:]
    else:
        if candidate_buffer:
            candidate_buffer.pop(0)

    if len(candidate_buffer) >= BUFFER_SIZE:
        avg = np.mean(candidate_buffer[-BUFFER_SIZE:], axis=0).astype(np.float32)

        # Feed measurement into Kalman filter
        measurement = np.array([[avg[0]], [avg[1]], [avg[2]]], dtype=np.float32)

        if not kalman_initialized:
            # First detection — seed the filter state directly
            kf.statePre  = np.array([[avg[0]], [avg[1]], [avg[2]],
                                     [0], [0], [0]], dtype=np.float32)
            kf.statePost = kf.statePre.copy()
            kalman_initialized = True

        # CORRECT step — blends prediction with measurement
        # The blend ratio is determined automatically by the filter
        # based on Q (process noise) and R (measurement noise)
        corrected = kf.correct(measurement)

        cx = int(corrected[0])
        cy = int(corrected[1])
        cr = int(max(1, corrected[2]))

        # Update legacy prevCircle so ROI logic still works
        prevCircle = [cx, cy, cr]
        vel_x = float(corrected[3])
        vel_y = float(corrected[4])
        vel_r = float(corrected[5])

        # ---- Draw detected circle ----
        cv.circle(frame, (cx, cy), cr, (0, 165, 255), 2)       # orange outline
        cv.circle(frame, (cx, cy), 1,  (0, 255, 0),  3)        # green center dot

        # ---- Draw Kalman prediction arrow ----
        # Arrow tip = where the filter predicts the ball will be
        # ARROW_SCALE frames from now
        tip_x = int(cx + vel_x * ARROW_SCALE)
        tip_y = int(cy + vel_y * ARROW_SCALE)
        cv.arrowedLine(frame, (cx, cy), (tip_x, tip_y),
                       ARROW_COLOR, ARROW_THICKNESS, tipLength=0.3)

        spd = int(np.sqrt(vel_x**2 + vel_y**2))
        cv.putText(frame,
                   f"x:{cx} y:{cy} r:{cr} spd:{spd}",
                   (cx + cr + 5, cy),
                   cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

    elif kalman_initialized:
        # No detection — show Kalman's pure prediction (ghost circle)
        # The filter keeps estimating position using velocity
        cv.circle(frame, (kx, ky), kr, (80, 80, 80), 1)        # grey ghost
        tip_x = int(kx + kvx * ARROW_SCALE)
        tip_y = int(ky + kvy * ARROW_SCALE)
        cv.arrowedLine(frame, (kx, ky), (tip_x, tip_y),
                       (80, 80, 80), 1, tipLength=0.3)

        # Update prevCircle so ROI keeps following the prediction
        prevCircle = [kx, ky, kr]

    # --------------------------------------------------------
    #  RESET BUTTON
    # --------------------------------------------------------
    cv.rectangle(frame, (10, 10), (160, 45), (60, 60, 60), -1)
    cv.rectangle(frame, (10, 10), (160, 45), (180, 180, 180),  1)
    cv.putText(frame, "RESET TRACKING", (18, 33),
               cv.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv.putText(frame, "or press R", (10, 58),
               cv.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

    cv.imshow("circles", frame)

    key = cv.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("r"):
        kf, prevCircle, candidate_buffer, vel_x, vel_y, vel_r = reset_tracking(kf)
        kalman_initialized = False


cap.release()
cv.destroyAllWindows()