import cv2

cam_index = 1
cap = cv2.VideoCapture(cam_index)

if not cap.isOpened():
    print("Camera not found on port", cam_index)
    exit()

width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
fps = cap.get(cv2.CAP_PROP_FPS)

print("Camera opened on port:", cam_index)
print("Resolution:", int(width), "x", int(height))
print("FPS:", fps)

ret, frame = cap.read()

if ret:
    print("Frame captured successfully")
else:
    print("Failed to capture frame")

cap.release()
