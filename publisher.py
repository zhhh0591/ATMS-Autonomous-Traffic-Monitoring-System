# publisher.py
# ─────────────────────────────────────────────────────────────
# This module handles all MQTT communication from the Python
# edge vision system to the ESP32 microcontroller.
# It acts as the "nervous system" of ATMS — translating what
# the camera sees into messages the hardware can act on.
#
# MQTT (Message Queuing Telemetry Transport) is a lightweight
# messaging protocol designed for IoT devices. It uses a
# publish/subscribe model — Python publishes messages to a
# "topic", and the ESP32 subscribes to that same topic.
# This is the same protocol used in industrial SCADA systems.
# ─────────────────────────────────────────────────────────────

import json   # Used to convert Python dict → JSON string for transmission
import time   # Used to generate Unix timestamps for each message
import paho.mqtt.client as mqtt  # Official MQTT client library for Python


class TrafficPublisher:
    """
    Manages the MQTT connection and publishes traffic state payloads.

    We use a class here instead of standalone functions because:
    1. The MQTT client needs to stay connected between publishes
    2. A class keeps the connection state and topic organized
    3. It makes the code reusable if we add more camera nodes later
    """

    def __init__(self):
        # ── Step 1: Define the MQTT topic ─────────────────────
        # Topics work like addresses in MQTT.
        # Format: "traffic/node/{node_id}/state"
        # The ESP32 is subscribed to this exact same topic,
        # so it will receive every message we publish here.
        # Using a structured topic format makes it easy to scale —
        # a second camera would use "traffic/node/cam_node_02/state"
        self.topic = "traffic/node/cam_node_01/state"

        # ── Step 2: Create the MQTT client ────────────────────
        # client_id is a unique name for this publisher.
        # If two clients connect with the same ID, the broker
        # will disconnect the older one — so keep it unique.
        self.client = mqtt.Client(client_id="edge_vision")

        # ── Step 3: Connect to the Mosquitto broker ───────────
        # "broker.emqx.io" is a public MQTT broker we can use for testing.
        # Port 1883 is the standard unencrypted MQTT port.
        # keepalive=60 means the client sends a "ping" every 60 seconds
        # to tell the broker it's still alive and connected.
        self.client.connect("broker.emqx.io", 1883, keepalive=60)

        # ── Step 4: Start the background network loop ─────────
        # loop_start() runs the MQTT network loop in a separate thread.
        # This means MQTT handles incoming/outgoing messages in the
        # background without blocking the main camera loop in carcount.py.
        # If we used loop_forever() instead, the program would freeze here.
        self.client.loop_start()

        print("[MQTT] Connected to broker")

    def publish(self, vehicle_count, flow_state, density_pct=0, stall_s=0):
        """
        Publishes a traffic state message to the MQTT broker.

        This method is called every 2 seconds by carcount.py.
        The ESP32 receives this message and updates the LED state.

        Parameters:
            vehicle_count : number of vehicles in the current frame
            flow_state    : one of "CLEAR", "MODERATE", "CONGESTED", "STOPPED"
            density_pct   : estimated % of frame covered by vehicles (0-100)
            stall_s       : how long traffic has been stationary in seconds
        """

        # ── Step 5: Build the JSON payload ────────────────────
        # This is the "contract" between Python and the ESP32.
        # Both sides must agree on the exact field names.
        # We chose JSON because it's human-readable and easy to
        # parse on both Python and C++ (Arduino) sides.
        #
        # Field explanations:
        # schema_ver    → version number so we can update the format later
        #                 without breaking older ESP32 firmware
        # node_id       → identifies which camera sent this message
        #                 useful when scaling to multiple intersections
        # ts            → Unix timestamp (seconds since Jan 1 1970)
        #                 lets us log exactly when each reading was taken
        # vehicle_count → total vehicles that have crossed the ROI line
        # flow_state    → the key field the ESP32 FSM acts on directly
        # density_pct   → reserved for future dashboard visualization
        # stall_duration_s → how long the stall has lasted
        # incident_flag → True if stall > 120s, triggers alert on ESP32
        payload = {
            "schema_ver":       "1.0",
            "node_id":          "cam_node_01",
            "ts":               int(time.time()),
            "vehicle_count":    vehicle_count,
            "flow_state":       flow_state,
            "density_pct":      density_pct,
            "stall_duration_s": stall_s,
            "incident_flag":    stall_s >= 120  # boolean: True if major stall
        }

        # ── Step 6: Serialize and publish ─────────────────────
        # json.dumps() converts the Python dictionary into a JSON string.
        # Example output:
        # '{"schema_ver": "1.0", "flow_state": "CONGESTED", ...}'
        #
        # qos=1 means "at least once delivery" — the broker will
        # confirm the message was received and retry if it wasn't.
        # qos=0 would be "fire and forget" with no confirmation.
        # For a traffic system, qos=1 is safer — we don't want
        # the ESP32 to miss a STOPPED signal.
        self.client.publish(self.topic, json.dumps(payload), qos=1)

        # ── Step 7: Log to terminal ───────────────────────────
        # Print a confirmation every time we publish so we can
        # monitor the system in real-time from the terminal.
        print(f"[MQTT] Published: {flow_state} | Vehicles: {vehicle_count}")