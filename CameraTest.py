import cv2 as cv
import numpy as np

def reset_tracking():
    """Returns fresh tracking state centered on None"""
    return None, [], 0, 0, 0

cap = cv.VideoCapture(0)

prevCircle = None
candidate_buffer = []
BUFFER_SIZE = 2

dist = lambda x1, y1, x2, y2: (x1 - x2)**2 + (y1 - y2)**2
vel_x, vel_y, vel_r = 0, 0, 0

# Mouse click handler — clicking the reset button resets tracking
reset_flag = False
def on_mouse(event, x, y, flags, param):
    global reset_flag
    if event == cv.EVENT_LBUTTONDOWN:
        # Check if click is inside reset button area (drawn later)
        if 10 <= x <= 160 and 10 <= y <= 45:
            reset_flag = True

cv.namedWindow("circles")
cv.setMouseCallback("circles", on_mouse)


while True:

    ret, frame = cap.read()
    if not ret:
        print("Can't receive frame (stream end?). Exiting ...")
        break

    # Handle reset button click
    if reset_flag:
        prevCircle, candidate_buffer, vel_x, vel_y, vel_r = reset_tracking()
        reset_flag = False

    gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)

    # Skip equalizeHist — it amplifies golf ball dimples as noise,
    # breaking the circular edge the Hough transform relies on
    blurframe = cv.GaussianBlur(gray, (15, 15), 0)

    offset_x, offset_y = 0, 0
    search_area = blurframe

    if prevCircle is not None:
        x, y, r = int(prevCircle[0]), int(prevCircle[1]), int(prevCircle[2])

        predicted_x = int(x + vel_x)
        predicted_y = int(y + vel_y)
        predicted_r = int(r + vel_r)

        speed = np.sqrt(vel_x**2 + vel_y**2)
        margin = int(max(120, speed * 3, r * 1.5))

        x1 = max(0, predicted_x - predicted_r - margin)
        y1 = max(0, predicted_y - predicted_r - margin)
        x2 = min(frame.shape[1], predicted_x + predicted_r + margin)
        y2 = min(frame.shape[0], predicted_y + predicted_r + margin)

        if x2 > x1 and y2 > y1:
            search_area = blurframe[y1:y2, x1:x2]
            if search_area is None or search_area.size == 0:
                search_area = blurframe
                offset_x, offset_y = 0, 0
            else:
                offset_x, offset_y = x1, y1
        else:
            prevCircle, candidate_buffer, vel_x, vel_y, vel_r = reset_tracking()


    circles = None
    if search_area is not None and search_area.size > 0:
        try:
            circles = cv.HoughCircles(
                search_area,
                cv.HOUGH_GRADIENT,
                dp=1.2,
                minDist=50,

                param1=100,   # Lower — golf ball dimples weaken edges,
                              # so we need to accept softer edge responses

                param2=35,    # Lower — golf ball edge is less perfect than lens cap,
                              # needs a more lenient accumulator threshold

                minRadius=10, # Small enough to catch golf ball at distance
                maxRadius=80  # Golf balls don't get huge even up close
            )
        except cv.error as e:
            print(f"HoughCircles error (skipping frame): {e}")
            circles = None


    if circles is not None:
        circles = np.uint16(np.around(circles))

        for c in circles[0]:
            c[0] += offset_x
            c[1] += offset_y

        if prevCircle is None:
            chosen = circles[0][0]
        else:
            chosen = min(
                circles[0],
                key=lambda c: dist(c[0], c[1], prevCircle[0], prevCircle[1])
            )

        candidate_buffer.append(chosen)
        if len(candidate_buffer) > BUFFER_SIZE:
            candidate_buffer = candidate_buffer[-BUFFER_SIZE:]

    else:
        if candidate_buffer:
            candidate_buffer.pop(0)


    if len(candidate_buffer) >= BUFFER_SIZE:

        avg = np.mean(candidate_buffer[-BUFFER_SIZE:], axis=0).astype(int)

        if prevCircle is not None:
            vel_x = avg[0] - prevCircle[0]
            vel_y = avg[1] - prevCircle[1]
            vel_r = avg[2] - prevCircle[2]

        prevCircle = avg

        cv.circle(frame, (avg[0], avg[1]), avg[2], (0, 200, 255), 2)
        cv.circle(frame, (avg[0], avg[1]), 1, (0, 255, 0), 3)

        cv.putText(
            frame,
            f"x:{avg[0]} y:{avg[1]} r:{avg[2]} spd:{int(np.sqrt(vel_x**2 + vel_y**2))}",
            (avg[0] + avg[2] + 5, avg[1]),
            cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1
        )

    elif prevCircle is not None:
        prevCircle = [
            prevCircle[0] + vel_x,
            prevCircle[1] + vel_y,
            prevCircle[2] + vel_r
        ]
        vel_x *= 0.8
        vel_y *= 0.8
        vel_r *= 0.8

        cx, cy, cr = int(prevCircle[0]), int(prevCircle[1]), int(max(1, prevCircle[2]))
        h, w = frame.shape[:2]
        if 0 <= cx < w and 0 <= cy < h:
            cv.circle(frame, (cx, cy), cr, (50, 50, 50), 1)


    # --- Draw Reset Button ---
    btn_color  = (60, 60, 60)
    text_color = (255, 255, 255)
    cv.rectangle(frame, (10, 10), (160, 45), btn_color, -1)         # filled bg
    cv.rectangle(frame, (10, 10), (160, 45), (180, 180, 180), 1)    # border
    cv.putText(frame, "RESET TRACKING", (18, 33),
               cv.FONT_HERSHEY_SIMPLEX, 0.45, text_color, 1)

    # Show 'R' key hint
    cv.putText(frame, "or press R", (10, 58),
               cv.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)


    cv.imshow("circles", frame)

    key = cv.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("r"):
        # Also allow keyboard reset with R key
        prevCircle, candidate_buffer, vel_x, vel_y, vel_r = reset_tracking()


cap.release()
cv.destroyAllWindows()