# carcount.py
# ─────────────────────────────────────────────────────────────
# ATMS — Autonomous Traffic Monitoring System
# Main entry point that ties together all four pillars:
#
#   1. The Eye    — YOLOv8 detects vehicles, ByteTrack assigns
#                   each one a persistent ID across frames
#   2. The Nerve  — MQTT sends live traffic state to the broker
#   3. The Muscle — ESP32 receives the state and lights up LEDs
#   4. The Brain  — Offline chart + HTML dashboard auto-generated
#                   when a stall is detected
#
# How it works in plain English:
#   The camera captures 30 frames per second. For each frame,
#   we ask YOLOv8 "what vehicles are in this image?" and get
#   back bounding boxes. We track each vehicle's position over
#   time. When a vehicle crosses a horizontal line we drew on
#   screen (the ROI line), we increment a counter. Every 2
#   seconds we publish the traffic state to MQTT so the ESP32
#   can update its LEDs. If traffic stays congested for 30+
#   seconds, we generate a dashboard report automatically.
# ─────────────────────────────────────────────────────────────

import cv2      # OpenCV — reads camera frames and draws on them
import time     # Standard Python time library for timestamps
from ultralytics import YOLO           # YOLOv8 object detection
from publisher import TrafficPublisher  # Our MQTT publisher
from reporter import generate_report, log_data  # Our analytics module


# ── Step 1: Load the AI model ─────────────────────────────────
# YOLOv8 "nano" is the smallest and fastest version of the model.
# It was already trained by Ultralytics on 80 object categories
# including cars, trucks, buses, and motorcycles — so we don't
# need to do any training ourselves. We just download and use it.
# First run: automatically downloads yolov8n.pt (~6MB) from the web.
model = YOLO("yolov8n.pt")


# ── Step 2: Define which object types we care about ───────────
# The COCO dataset (what YOLO was trained on) has 80 categories,
# each with a numeric ID. We only want to detect vehicles, so we
# create a dictionary mapping the 4 vehicle IDs to their names.
# Every other object type (person, dog, chair...) will be ignored.
#   2 = car
#   3 = motorcycle
#   5 = bus
#   7 = truck
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


# ── Step 3: Set the ROI counting line position ────────────────
# ROI stands for "Region of Interest."
# ROI_Y is a horizontal line drawn across the video frame at
# pixel row 300 (300 pixels from the top of the frame).
# Any vehicle whose center point crosses this line gets counted.
# You can change this number to move the line up or down
# depending on where your camera is positioned.
ROI_Y = 300


# ── Step 4: Set up all tracking variables ────────────────────
# These variables keep track of the system's state across frames.

count = 0
# The total number of vehicles that have crossed the ROI line
# since the program started. This is the main output metric.

prev_y = {}
# A dictionary that remembers each vehicle's vertical position
# (y-coordinate of its center point) from the PREVIOUS frame.
# Key   = track_id (a unique number assigned to each vehicle)
# Value = cy (the center y-coordinate in the last frame)
# We need this to detect when a vehicle crosses the ROI line,
# because crossing means: last frame above the line, this frame below.

crossed_ids = set()
# A set of track IDs that have already been counted.
# Without this, a slow vehicle whose center hovers near the ROI
# line could be counted 5 or 10 times across multiple frames.
# Once an ID is in this set, it won't be counted again.

last_publish = 0
# Unix timestamp of the last time we sent an MQTT message.
# We compare this to the current time to throttle publishing
# to once every 2 seconds — no need to flood the broker at 30fps.

stall_start = 0
# Unix timestamp of when the current traffic stall began.
# Set to 0 when there is no stall (traffic is moving normally).
# We start the timer when 5+ vehicles appear in the frame.

report_generated = False
# A True/False flag that prevents us from generating multiple
# reports for the same stall event. Once a report is generated,
# this becomes True and stays True until the stall clears.
# When traffic clears, it resets to False so the next stall
# can trigger a fresh report.

n = 0
# Number of vehicles detected in the CURRENT frame.
# This changes every frame — it's a snapshot, not cumulative.

stall_s = 0
# How many seconds the current stall has been going on.
# Calculated as: current time - stall_start.
# Resets to 0 whenever traffic clears.


# ── Step 5: Connect to camera and MQTT broker ─────────────────
# TrafficPublisher() immediately connects to the MQTT broker.
# If the broker isn't running, this line will throw an error.
publisher = TrafficPublisher()

# VideoCapture(0) opens the default camera on this computer.
# 0 = built-in webcam (Mac FaceTime camera or iPhone Continuity Camera)
# 1 = first external USB camera
# "video.mp4" = read from a saved video file instead
cap = cv2.VideoCapture(0)


# ── Step 6: Main processing loop ─────────────────────────────
# This loop is the heartbeat of the entire system.
# It runs continuously — one full iteration per camera frame.
# At 30 FPS, this loop executes about 30 times every second.
# The loop only exits when the user presses 'q'.
while True:

    # Ask the camera for the next frame.
    # ret = True if the frame was read successfully, False if not.
    # frame = the actual image as a NumPy array of pixel values.
    ret, frame = cap.read()

    # If the frame couldn't be read (camera glitch, brief disconnect),
    # skip this iteration and try again on the next frame.
    # Using "continue" instead of "break" means we don't crash —
    # the system keeps running through temporary camera issues.
    if not ret:
        continue

    # Get the height and width of the frame in pixels.
    # We need the width (w) to draw the ROI line across the full frame.
    h, w = frame.shape[:2]


    # ── Step 7: Run AI detection and tracking ─────────────────
    # model.track() is the core AI call. It does two things:
    #
    #   Detection (YOLO):
    #     Scans the entire frame and finds every vehicle.
    #     Returns bounding boxes (x1,y1,x2,y2) and confidence scores.
    #
    #   Tracking (ByteTrack):
    #     Matches each detected vehicle to the same vehicle in the
    #     previous frame using a Kalman filter + Hungarian algorithm.
    #     Assigns each vehicle a persistent integer ID (track_id)
    #     that stays the same across frames even if the vehicle is
    #     briefly occluded or the detection confidence dips.
    #
    # persist=True  → keep the ByteTrack state between frames
    # verbose=False → don't print detection logs to the terminal
    # classes=      → only detect our 4 vehicle categories
    results = model.track(frame, persist=True, verbose=False,
                          classes=list(VEHICLE_CLASSES.keys()))

    # Draw the ROI counting line across the full width of the frame.
    # We draw it BEFORE the bounding boxes so it appears underneath them.
    # Color is bright green (0, 255, 0) in BGR format, 2 pixels thick.
    cv2.line(frame, (0, ROI_Y), (w, ROI_Y), (0, 255, 0), 2)


    # ── Step 8: Process each detected vehicle ─────────────────
    # results[0].boxes contains all detections for this frame.
    # boxes.id is None for the first 1-2 frames while ByteTrack
    # initializes — we skip processing until IDs are available.
    boxes = results[0].boxes

    if boxes is not None and boxes.id is not None:
        for i in range(len(boxes)):

            # Pull out the class ID and unique track ID for this vehicle
            cls_id   = int(boxes.cls[i])   # e.g. 2 = "car"
            track_id = int(boxes.id[i])    # e.g. 7 = vehicle number 7

            # Get the bounding box corners
            # xyxy format: (left, top, right, bottom) in pixels
            x1, y1, x2, y2 = map(int, boxes.xyxy[i])

            # Calculate the centroid — the exact center of the bounding box.
            # We use the centroid (not the full box) as our tracking point
            # because it's a single stable coordinate to compare against ROI_Y.
            cx = (x1 + x2) // 2   # horizontal center
            cy = (y1 + y2) // 2   # vertical center

            # Draw a green rectangle around the vehicle
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 80), 2)

            # Draw a red dot at the centroid so we can see what's being tracked
            cv2.circle(frame, (cx, cy), 5, (0, 60, 255), -1)

            # Label the vehicle with its type and track ID
            cv2.putText(frame, f"{VEHICLE_CLASSES[cls_id]} #{track_id}",
                        (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 80), 1)


            # ── Step 9: Detect ROI line crossing ──────────────
            # We check if this vehicle just crossed the ROI line
            # by comparing its current y-position to its previous one.
            #
            # The crossing condition (top → bottom):
            #   Previous frame: cy was ABOVE the line (prev_y < ROI_Y)
            #   Current frame:  cy is ON or BELOW the line (cy >= ROI_Y)
            #
            # This direction-specific check means we only count vehicles
            # moving downward in the frame (one direction of travel).
            # If you want to count both directions, you'd add a second
            # condition for bottom → top crossings.
            if track_id in prev_y:
                if prev_y[track_id] < ROI_Y <= cy:
                    # Only count if this vehicle hasn't been counted before
                    if track_id not in crossed_ids:
                        count += 1
                        crossed_ids.add(track_id)

            # Save this frame's y-position so we can compare next frame
            prev_y[track_id] = cy

        # After processing all vehicles, record how many are visible now
        n = len(boxes.id)

    else:
        # No vehicles detected in this frame
        n = 0


    # ── Step 10: Calculate how long traffic has been stalled ──
    # We define a "stall" as 5 or more vehicles visible in the frame.
    # In a real system you'd also verify the vehicles aren't moving,
    # but for this MVP, high vehicle count is a good proxy for congestion.
    #
    # Logic:
    #   - If n >= 5 and no stall was already recorded → start the timer
    #   - If n >= 5 and a stall is already active → calculate its duration
    #   - If n < 5 → reset everything (traffic has cleared)
    if n >= 5:
        if stall_start == 0:
            stall_start = time.time()       # Mark when stall began
        stall_s = int(time.time() - stall_start)  # Seconds since stall began
    else:
        stall_start = 0   # Reset — no stall currently active
        stall_s = 0


    # ── Step 11: Classify the traffic flow state ──────────────
    # This maps the raw sensor data into one of 4 named states.
    # The ESP32 firmware reads this exact string and decides which
    # LED to turn on — so the string values must match exactly.
    #
    #   "CLEAR"     → green LED   (fewer than 5 vehicles)
    #   "MODERATE"  → yellow LED  (5-9 vehicles, no long stall)
    #   "CONGESTED" → red + yellow (10+ vehicles, no long stall)
    #   "STOPPED"   → red LED     (5+ vehicles stalled for 30+ seconds)
    #
    # STOPPED is checked FIRST because a long stall is more serious
    # than a high instantaneous count — even if only 6 cars are stuck
    # for 30 seconds, that's a STOPPED situation.
    flow = "STOPPED"   if stall_s >= 30 else \
           "CONGESTED" if n >= 10       else \
           "MODERATE"  if n >= 5        else "CLEAR"


    # ── Step 12: Record data for the analytics chart ──────────
    # log_data() appends (current_timestamp, vehicle_count) to a list
    # in reporter.py. When a report is triggered, that list becomes
    # the data for the traffic flow chart in the HTML dashboard.
    log_data(n)


    # ── Step 13: Publish MQTT message every 2 seconds ─────────
    # We only publish every 2 seconds to avoid flooding the broker.
    # The ESP32 processes messages fast enough that 0.5 Hz is plenty
    # for keeping the LEDs up to date with traffic conditions.
    if time.time() - last_publish >= 2.0:
        publisher.publish(count, flow, stall_s=stall_s)
        last_publish = time.time()
        print(f"[INFO] vehicles={n} | flow={flow} | stall={stall_s}s")


    # ── Step 14: Trigger the analytics report ─────────────────
    # If traffic has been stalled for 30+ seconds and we haven't
    # already generated a report for this stall, generate one now.
    # generate_report() creates a matplotlib chart and an HTML
    # dashboard, then opens it automatically in the browser.
    #
    # report_generated makes sure we only fire this ONCE per stall.
    # When the stall clears (stall_s resets to 0), report_generated
    # resets to False so the next stall can trigger a new report.
    if stall_s >= 30 and not report_generated:
        generate_report(n, stall_s, "cam_node_01")
        report_generated = True

    if stall_s == 0:
        report_generated = False


    # ── Step 15: Draw the HUD on the video frame ──────────────
    # HUD = Heads-Up Display. We overlay key metrics on the video
    # so anyone watching the monitor can see the system status
    # without needing to look at the terminal.
    cv2.putText(frame, f"Count: {count} | Flow: {flow} | Stall: {stall_s}s",
                (12, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)


    # ── Step 16: Show the annotated frame ─────────────────────
    # Display the frame (with bounding boxes, ROI line, and HUD)
    # in a window called "Traffic Monitor".
    cv2.imshow("Traffic Monitor", frame)

    # waitKey(1) pauses for 1 millisecond — required for imshow to
    # actually render the window. It also checks for keyboard input.
    # If the user presses 'q', we exit the loop gracefully.
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


# ── Step 17: Release resources ────────────────────────────────
# Always clean up when the loop exits.
# cap.release() unlocks the camera so other apps can use it.
# destroyAllWindows() closes the "Traffic Monitor" display window.
cap.release()
cv2.destroyAllWindows()
print(f"[DONE] Session ended. Total vehicles counted: {count}")