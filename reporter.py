# reporter.py
# ─────────────────────────────────────────────────────────────
# Offline analytics reporter for ATMS.
# When a traffic stall is detected, this module:
#   1. Plots the real-time vehicle count history using matplotlib
#   2. Embeds the chart into an HTML dashboard
#   3. Opens the dashboard automatically in the browser
#
# No external API needed — runs 100% offline on the edge device./ I was Used externally for AI generate the graph, but the final output Its really required privative network and stable wifi connection so thats really depends on the environment

import time
import subprocess
import os
import matplotlib.pyplot as plt

# Global list that silently records vehicle count over time.
# Every frame, carcount.py calls log_data() to append a reading.
# This builds up a time-series dataset we can plot later.
traffic_log = []


def log_data(vehicle_count):
    """
    Called every frame by carcount.py to log traffic data.
    Stores a (timestamp, vehicle_count) tuple for chart generation.
    """
    traffic_log.append((time.time(), vehicle_count))


def generate_report(vehicle_count, stall_duration_s, node_id):
    """
    Triggered automatically when traffic stalls for 30+ seconds.
    Generates a local HTML analytics dashboard with a traffic chart.

    Parameters:
        vehicle_count   : vehicles detected in the current frame
        stall_duration_s: how long traffic has been stationary
        node_id         : camera node identifier (e.g. "cam_node_01")
    """

    print(f"[REPORTER] Stall detected! Generating dashboard for {node_id}...")

    # ── Step 1: Plot the vehicle count time series ────────────
    # We use matplotlib to draw a line chart of vehicle count over time.
    # The x-axis is seconds elapsed since the system started.
    # The y-axis is how many vehicles were in the frame at each moment.
    plt.figure(figsize=(10, 5))

    if len(traffic_log) > 1:
        # Convert raw Unix timestamps → seconds from start
        start_time = traffic_log[0][0]
        times  = [t[0] - start_time for t in traffic_log]
        counts = [t[1] for t in traffic_log]

        # Draw the line and shade the area below it
        plt.plot(times, counts, color='#2c3e50', linewidth=2.5, label='Vehicle Count')
        plt.fill_between(times, counts, color='#3498db', alpha=0.3)
    else:
        plt.text(0.5, 0.5, 'Insufficient Data', ha='center', va='center')

    plt.title(f"Traffic Density Analysis — Node: {node_id}", fontsize=14, pad=15)
    plt.xlabel("Seconds elapsed since system start", fontsize=12)
    plt.ylabel("Vehicles in Frame", fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.6)

    # Save chart as a local PNG file
    # We use a fixed filename so the HTML can always find it
    graph_filename = "traffic_plot.png"
    plt.savefig(graph_filename, bbox_inches='tight', dpi=150)
    plt.close()

    # ── Step 2: Build the HTML dashboard ─────────────────────
    # We embed the chart image using its absolute local file path.
    # This ensures the browser can load the image even without a server.
    timestamp  = time.strftime("%Y-%m-%d %H:%M:%S")
    html_filename = f"analytics_report_{int(time.time())}.html"
    img_path   = os.path.abspath(graph_filename)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>ATMS Dashboard</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background: #eef2f5;
            margin: 0;
            padding: 40px;
            color: #333;
        }}
        .card {{
            background: white;
            max-width: 900px;
            margin: auto;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}
        h1 {{
            color: #e74c3c;
            margin-top: 0;
            border-bottom: 2px solid #eee;
            padding-bottom: 15px;
        }}
        .stats {{
            display: flex;
            gap: 20px;
            margin: 30px 0;
        }}
        .stat {{
            flex: 1;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            text-align: center;
            border-left: 5px solid #3498db;
        }}
        .stat.alert {{
            border-left-color: #e74c3c;
            background: #fdf3f2;
        }}
        .stat b {{
            display: block;
            font-size: 32px;
            color: #2c3e50;
            margin-bottom: 5px;
        }}
        .stat.alert b {{ color: #e74c3c; }}
        img {{
            width: 100%;
            border-radius: 8px;
            margin-top: 10px;
            border: 1px solid #ddd;
        }}
        .footer {{
            color: #95a5a6;
            font-size: 12px;
            text-align: center;
            margin-top: 30px;
        }}
    </style>
</head>
<body>
<div class="card">
    <h1>ATMS — Incident Analytics Dashboard</h1>
    <p style="color:#7f8c8d"><b>Generated:</b> {timestamp}</p>

    <div class="stats">
        <div class="stat alert"><b>{stall_duration_s}s</b>Stall Duration</div>
        <div class="stat"><b>{vehicle_count}</b>Vehicles Detected</div>
        <div class="stat"><b>{node_id}</b>Node ID</div>
    </div>

    <h3>Live Traffic Flow Chart</h3>
    <img src="file://{img_path}" alt="Traffic Chart">

    <div class="footer">
        Generated offline by ATMS Edge Vision System · {timestamp}
    </div>
</div>
</body>
</html>"""

    # ── Step 3: Save and open the dashboard ──────────────────
    with open(html_filename, "w", encoding='utf-8') as f:
        f.write(html)

    # "open" is a Mac terminal command that opens a file
    # with its default application — HTML files open in the browser.
    subprocess.run(["open", html_filename])
    print(f"[REPORTER] Dashboard saved and opened: {html_filename}")