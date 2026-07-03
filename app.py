from flask import Flask, render_template, jsonify, request, send_from_directory
import sqlite3
import json
import math
import os

app = Flask(__name__)
DB_PATH = "robot_nav.db"

# ── Room definitions (pixels on a 780×600 canvas) ──────────────────────────
ROOMS = {
    "sitout":    {"x": 90,  "y": 530, "label": "SITOUT",    "color": "#FF6B6B", "w": 150, "h": 60},
    "living":    {"x": 90,  "y": 420, "label": "LIVING",    "color": "#4ECDC4", "w": 150, "h": 110},
    "dining":    {"x": 90,  "y": 290, "label": "DINING",    "color": "#45B7D1", "w": 150, "h": 120},
    "kitchen":   {"x": 90,  "y": 100, "label": "KITCHEN",   "color": "#96CEB4", "w": 150, "h": 150},
    "bedroom1":  {"x": 470, "y": 90,  "label": "BEDROOM 1", "color": "#FFEAA7", "w": 200, "h": 190},
    "bedroom2":  {"x": 470, "y": 390, "label": "BEDROOM 2", "color": "#DDA0DD", "w": 200, "h": 170},
    "toilet1":   {"x": 470, "y": 290, "label": "TOILET 1",  "color": "#98FB98", "w": 90,  "h": 95},
    "toilet2":   {"x": 568, "y": 290, "label": "TOILET 2",  "color": "#87CEEB", "w": 90,  "h": 95},
    "corridor":  {"x": 270, "y": 290, "label": "CORRIDOR",  "color": "#F0E68C", "w": 190, "h": 280},
    "entrance":  {"x": 270, "y": 490, "label": "ENTRANCE",  "color": "#FFB347", "w": 190, "h": 80},
}

# Room centers for each room (where robot stops)
ROOM_CENTERS = {
    "kitchen": {"x": 165, "y": 175},
    "dining": {"x": 165, "y": 350},
    "living": {"x": 165, "y": 470},
    "sitout": {"x": 165, "y": 545},
    "entrance": {"x": 365, "y": 530},
    "corridor": {"x": 365, "y": 400},
    "bedroom1": {"x": 570, "y": 185},
    "bedroom2": {"x": 570, "y": 475},
    "toilet1": {"x": 515, "y": 337},
    "toilet2": {"x": 613, "y": 337},
}

# Central corridor waypoints (the main path through the house)
CENTRAL_PATH = [
    {"x": 365, "y": 530},  # Entrance
    {"x": 365, "y": 490},  # Entrance/Corridor junction
    {"x": 365, "y": 455},  # Living room door level
    {"x": 365, "y": 420},  # Mid corridor
    {"x": 365, "y": 385},  # Dining room door level
    {"x": 365, "y": 350},  # Upper mid corridor
    {"x": 365, "y": 315},  # Toilet junction
    {"x": 365, "y": 280},  # Bedroom junction
    {"x": 365, "y": 245},  # Upper corridor
    {"x": 365, "y": 210},  # Kitchen door level
    {"x": 365, "y": 175},  # Kitchen top
]

# Door positions for each room (where robot enters from corridor)
# These are the connection points between rooms and the corridor
DOOR_POSITIONS = {
    "sitout":   {"x": 165, "y": 545},  # Door from entrance to sitout
    "living":   {"x": 165, "y": 455},  # Door from corridor to living room
    "dining":   {"x": 165, "y": 385},  # Door from corridor to dining room
    "kitchen":  {"x": 165, "y": 210},  # Door from corridor to kitchen
    "bedroom1": {"x": 560, "y": 185},  # Door from corridor to bedroom1
    "bedroom2": {"x": 560, "y": 475},  # Door from corridor to bedroom2
    "toilet1":  {"x": 510, "y": 335},  # Door from corridor to toilet1
    "toilet2":  {"x": 610, "y": 335},  # Door from corridor to toilet2
    "entrance": {"x": 365, "y": 530},  # Entrance is on the corridor
    "corridor": {"x": 365, "y": 400},  # Center of corridor
}

# Direct connections between rooms (for adjacent rooms)
# This allows direct movement between rooms that share a wall
DIRECT_CONNECTIONS = {
    "toilet1": ["toilet2", "bedroom1"],  # Toilet1 connects to Toilet2 and Bedroom1
    "toilet2": ["toilet1", "bedroom2"],  # Toilet2 connects to Toilet1 and Bedroom2
    "bedroom1": ["toilet1"],              # Bedroom1 connects to Toilet1
    "bedroom2": ["toilet2"],              # Bedroom2 connects to Toilet2
    "entrance": ["sitout"],               # Entrance connects to Sitout
    "sitout": ["entrance"],               # Sitout connects to Entrance
}

def compute_path(start, end_room):
    """
    Compute a path that follows corridors and goes through doors.
    This ensures the robot never goes through walls.
    """
    path = [{"x": start["x"], "y": start["y"]}]
    
    # Get the current room (where the robot is)
    start_room = start.get("current_room", None)
    
    # If start_room is not provided, find it from position
    if not start_room:
        for room_name, room in ROOMS.items():
            if (room["x"] <= start["x"] <= room["x"] + room["w"] and 
                room["y"] <= start["y"] <= room["y"] + room["h"]):
                start_room = room_name
                break
    
    # If still no room found, default to corridor
    if not start_room:
        start_room = "corridor"
    
    # If already in destination, go to room center
    if start_room == end_room:
        center = ROOM_CENTERS.get(end_room)
        if center:
            path.append(center)
        return path
    
    # Check if rooms are directly connected (adjacent)
    if (start_room in DIRECT_CONNECTIONS and end_room in DIRECT_CONNECTIONS[start_room]) or \
       (end_room in DIRECT_CONNECTIONS and start_room in DIRECT_CONNECTIONS[end_room]):
        # Take direct path between adjacent rooms
        end_center = ROOM_CENTERS.get(end_room)
        if end_center:
            path.append(end_center)
        return path
    
    # For non-adjacent rooms, go through the corridor
    
    # 1. Get door position for destination
    door_pos = DOOR_POSITIONS.get(end_room)
    if not door_pos:
        # If no door defined, just go to room center
        center = ROOM_CENTERS.get(end_room)
        if center:
            path.append(center)
        return path
    
    # 2. Find closest central path point to start position
    start_on_path = min(CENTRAL_PATH, key=lambda p: math.hypot(p["x"] - start["x"], p["y"] - start["y"]))
    
    # 3. Find closest central path point to destination door
    dest_on_path = min(CENTRAL_PATH, key=lambda p: math.hypot(p["x"] - door_pos["x"], p["y"] - door_pos["y"]))
    
    # 4. Get indices on the central path
    start_idx = CENTRAL_PATH.index(start_on_path)
    dest_idx = CENTRAL_PATH.index(dest_on_path)
    
    # 5. Build path along central corridor
    if start_idx <= dest_idx:
        corridor_segment = CENTRAL_PATH[start_idx:dest_idx + 1]
    else:
        corridor_segment = list(reversed(CENTRAL_PATH[dest_idx:start_idx + 1]))
    
    # Add corridor waypoints (skip if already at start)
    for wp in corridor_segment:
        if math.hypot(wp["x"] - path[-1]["x"], wp["y"] - path[-1]["y"]) > 5:
            path.append(wp)
    
    # 6. Add door position (if not already at door)
    if end_room not in ["entrance", "corridor"]:
        if math.hypot(door_pos["x"] - path[-1]["x"], door_pos["y"] - path[-1]["y"]) > 5:
            path.append(door_pos)
    
    # 7. Add room center (final destination)
    room_center = ROOM_CENTERS.get(end_room)
    if room_center and math.hypot(room_center["x"] - path[-1]["x"], room_center["y"] - path[-1]["y"]) > 10:
        path.append(room_center)
    
    return path

# ── DB init ────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS navigation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        command TEXT,
        destination TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        path TEXT,
        status TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS robot_state (
        id INTEGER PRIMARY KEY,
        x REAL, y REAL, angle REAL, current_room TEXT
    )""")
    c.execute("INSERT OR IGNORE INTO robot_state VALUES (1, 365, 530, 0, 'entrance')")
    c.execute("""CREATE TABLE IF NOT EXISTS lidar_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        scan_data TEXT,
        obstacles_detected INTEGER
    )""")
    conn.commit()
    conn.close()

def get_robot_state():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT x,y,angle,current_room FROM robot_state WHERE id=1").fetchone()
    conn.close()
    if row:
        return {"x": row[0], "y": row[1], "angle": row[2], "current_room": row[3]}
    return {"x": 365, "y": 530, "angle": 0, "current_room": "entrance"}

def save_robot_state(x, y, angle, room):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE robot_state SET x=?,y=?,angle=?,current_room=? WHERE id=1",
                 (x, y, angle, room))
    conn.commit()
    conn.close()

def log_navigation(command, destination, path, status):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO navigation_log(command,destination,path,status) VALUES(?,?,?,?)",
                 (command, destination, json.dumps(path), status))
    conn.commit()
    conn.close()

def save_lidar(scan_data, count):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO lidar_data(scan_data,obstacles_detected) VALUES(?,?)",
                 (json.dumps(scan_data), count))
    conn.commit()
    conn.close()

def parse_command(text):
    text = text.lower().strip()
    keywords = {
        "kitchen":  ["kitchen","cook","cooking"],
        "bedroom1": ["bedroom 1","bedroom1","first bedroom","master bedroom","master"],
        "bedroom2": ["bedroom 2","bedroom2","second bedroom","guest bedroom","guest"],
        "living":   ["living","living room","hall","lounge"],
        "dining":   ["dining","dining room","dining hall","eat","eating"],
        "toilet1":  ["toilet 1","toilet1","bathroom 1","bathroom1","first toilet","washroom 1"],
        "toilet2":  ["toilet 2","toilet2","bathroom 2","bathroom2","second toilet","washroom 2"],
        "corridor": ["corridor","hallway","passage","passageway"],
        "entrance": ["entrance","entry","front door","door","main door"],
        "sitout":   ["sitout","sit out","sit-out","porch","veranda","verandah","outside"],
    }
    for room, keys in keywords.items():
        for k in keys:
            if k in text:
                return room
    return None

def simulate_lidar(robot_x, robot_y, angle, num_beams=36):
    """Simulate LiDAR scan from current robot position"""
    obstacles = [
        {"x": 260, "y": 60,  "w": 10, "h": 220},
        {"x": 260, "y": 60,  "w": 400, "h": 10},
        {"x": 260, "y": 280, "w": 400, "h": 10},
        {"x": 460, "y": 280, "w": 10, "h": 290},
        {"x": 260, "y": 480, "w": 200, "h": 10},
        # Room walls as obstacles
        {"x": 90, "y": 100, "w": 150, "h": 150},  # Kitchen
        {"x": 90, "y": 290, "w": 150, "h": 120},  # Dining
        {"x": 90, "y": 420, "w": 150, "h": 110},  # Living
        {"x": 90, "y": 530, "w": 150, "h": 60},   # Sitout
        {"x": 270, "y": 290, "w": 190, "h": 280}, # Corridor
        {"x": 270, "y": 490, "w": 190, "h": 80},  # Entrance
        {"x": 470, "y": 90, "w": 200, "h": 190},  # Bedroom1
        {"x": 470, "y": 390, "w": 200, "h": 170}, # Bedroom2
        {"x": 470, "y": 290, "w": 90, "h": 95},   # Toilet1
        {"x": 568, "y": 290, "w": 90, "h": 95},   # Toilet2
    ]
    
    scans = []
    for i in range(num_beams):
        beam_angle = angle + (i * (360/num_beams))
        rad = math.radians(beam_angle)
        max_dist = 200
        dist = max_dist
        
        for obs in obstacles:
            if (obs["x"] <= robot_x <= obs["x"]+obs["w"] and 
                obs["y"] <= robot_y <= obs["y"]+obs["h"]):
                continue
                
            for d in range(5, max_dist + 1, 5):
                bx = robot_x + d * math.cos(rad)
                by = robot_y + d * math.sin(rad)
                if (obs["x"] <= bx <= obs["x"]+obs["w"] and 
                    obs["y"] <= by <= obs["y"]+obs["h"]):
                    dist = min(dist, d)
                    break
        
        hit = dist < max_dist
        scans.append({
            "angle": beam_angle % 360,
            "distance": dist,
            "hit": hit,
            "ex": robot_x + dist * math.cos(rad),
            "ey": robot_y + dist * math.sin(rad)
        })
    
    save_lidar(scans, sum(1 for s in scans if s["hit"]))
    return scans

# ── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html",
                           rooms=json.dumps(ROOMS),
                           obstacles=json.dumps([]))

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route("/api/navigate", methods=["POST"])
def navigate():
    data = request.json
    command = data.get("command", "")
    destination = parse_command(command)
    if not destination:
        return jsonify({"success": False, "error": f"Could not understand: '{command}'. Try 'go to kitchen' or 'navigate to bedroom'."})
    
    state = get_robot_state()
    path = compute_path(state, destination)
    
    # Ensure path has at least 2 points
    if len(path) < 2:
        end_center = ROOM_CENTERS.get(destination)
        if end_center:
            path.append(end_center)
    
    lidar = simulate_lidar(state["x"], state["y"], state["angle"])
    
    end = path[-1]
    angle = math.degrees(math.atan2(end["y"]-state["y"], end["x"]-state["x"]))
    save_robot_state(end["x"], end["y"], angle, destination)
    log_navigation(command, destination, path, "completed")
    
    return jsonify({
        "success": True,
        "destination": destination,
        "destination_label": ROOMS[destination]["label"],
        "path": path,
        "lidar": lidar,
        "robot_state": {"x": end["x"], "y": end["y"], "angle": angle, "current_room": destination}
    })

@app.route("/api/robot_state")
def robot_state():
    return jsonify(get_robot_state())

@app.route("/api/rooms")
def rooms():
    return jsonify(ROOMS)

@app.route("/api/history")
def history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT command,destination,timestamp,status FROM navigation_log ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return jsonify([{"command":r[0],"destination":r[1],"timestamp":r[2],"status":r[3]} for r in rows])

@app.route("/api/lidar_latest")
def lidar_latest():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT scan_data,obstacles_detected,timestamp FROM lidar_data ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return jsonify({})
    return jsonify({"scan_data": json.loads(row[0]), "obstacles_detected": row[1], "timestamp": row[2]})

@app.route("/api/lidar_current")
def lidar_current():
    state = get_robot_state()
    lidar = simulate_lidar(state["x"], state["y"], state["angle"])
    return jsonify({"lidar": lidar})

@app.route("/api/reset", methods=["POST"])
def reset():
    save_robot_state(365, 530, 0, "entrance")
    return jsonify({"success": True, "message": "Robot reset to entrance"})

if __name__ == "__main__":
    init_db()
    os.makedirs("static/css", exist_ok=True)
    os.makedirs("static/js", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)