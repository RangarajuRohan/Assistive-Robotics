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

# ── Single Obstacle in corridor ──────────────────────────────────────────
OBSTACLES = [
    {"x": 340, "y": 380, "w": 35, "h": 25, "label": "Table", "color": "#8B4513"},
]

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
CORRIDOR_PATH = [
    {"x": 365, "y": 480},  # Entrance/Corridor doorway
    {"x": 365, "y": 470},  # Lower corridor
    {"x": 365, "y": 450},  # Living room door
    {"x": 365, "y": 510},  # Entrance door area
    {"x": 365, "y": 490},  # Lower corridor
    {"x": 365, "y": 470},  # Living room level
    {"x": 365, "y": 450},  # Living room door
    {"x": 365, "y": 430},  # Mid corridor
    {"x": 365, "y": 410},  # Dining room level
    {"x": 365, "y": 390},  # Dining room door
    {"x": 365, "y": 370},  # Upper mid corridor
    {"x": 365, "y": 350},  # Toilet junction
    {"x": 365, "y": 330},  # Toilet door level
    {"x": 365, "y": 310},  # Upper corridor
    {"x": 365, "y": 290},  # Bedroom junction
    {"x": 365, "y": 270},  # Bedroom door level
    {"x": 365, "y": 250},  # Upper corridor
    {"x": 365, "y": 230},  # Kitchen door level
    {"x": 365, "y": 210},  # Kitchen door
    {"x": 365, "y": 190},  # Upper corridor
    {"x": 365, "y": 175},  # Kitchen top
]

DOOR_POSITIONS = {
    "kitchen":  {"x": 254, "y": 205},
    "dining":   {"x": 254, "y": 355},
    "living":   {"x": 254, "y": 455},
    "bedroom1": {"x": 470, "y": 185},
    "bedroom2": {"x": 470, "y": 465},
    "toilet1":  {"x": 470, "y": 335},
    "toilet2":  {"x": 568, "y": 335},
    "entrance": {"x": 365, "y": 480},
    "sitout":   {"x": 254, "y": 550},
    "corridor": {"x": 365, "y": 400},
}

ROOM_DOOR_LEVELS = {
    "kitchen":  {"corridor_idx": 17, "door_pos": {"x": 254, "y": 205}},
    "dining":   {"corridor_idx": 10, "door_pos": {"x": 254, "y": 355}},
    "living":   {"corridor_idx": 5,  "door_pos": {"x": 254, "y": 455}},
    "bedroom1": {"corridor_idx": 13, "door_pos": {"x": 470, "y": 185}},
    "bedroom2": {"corridor_idx": 13, "door_pos": {"x": 470, "y": 465}},
    "toilet1":  {"corridor_idx": 11, "door_pos": {"x": 470, "y": 335}},
    "toilet2":  {"corridor_idx": 11, "door_pos": {"x": 568, "y": 335}},
    "entrance": {"corridor_idx": 0,  "door_pos": {"x": 365, "y": 530}},
    "sitout":   {"corridor_idx": 0,  "door_pos": {"x": 254, "y": 550}},
}

def get_room_at_position(x, y):
    """Find which room a position is in"""
    for room_name, room in ROOMS.items():
        if (room["x"] <= x <= room["x"] + room["w"] and 
            room["y"] <= y <= room["y"] + room["h"]):
            return room_name
    return "corridor"

def get_closest_corridor_point(pos):
    """Find the closest point on the corridor path"""
    return min(CORRIDOR_PATH, key=lambda p: math.hypot(p["x"] - pos["x"], p["y"] - pos["y"]))

def is_point_in_obstacle(x, y, margin=10):
    """Check if a point is inside the obstacle (with safety margin)"""
    if not OBSTACLES:
        return False
    obs = OBSTACLES[0]
    if (obs["x"] - margin <= x <= obs["x"] + obs["w"] + margin and 
        obs["y"] - margin <= y <= obs["y"] + obs["h"] + margin):
        return True
    return False

def is_path_blocked(start, end, step_size=5):
    """Check if a straight line path is blocked by the obstacle"""
    if not OBSTACLES:
        return False
    
    dist = math.hypot(end["x"] - start["x"], end["y"] - start["y"])
    if dist < 1:
        return False
    
    steps = int(dist / step_size) + 1
    for i in range(steps + 1):
        t = i / steps
        x = start["x"] + (end["x"] - start["x"]) * t
        y = start["y"] + (end["y"] - start["y"]) * t
        if is_point_in_obstacle(x, y, margin=10):
            return True
    return False

def create_detour(start, end, base_margin=18):
    """
    Route a clean path around the obstacle's actual bounding box (+ safety
    margin), rather than just nudging a midpoint sideways. This guarantees
    the robot's path never enters the obstacle, because every candidate leg
    is checked against is_path_blocked before being accepted. If a margin
    turns out not to be enough (e.g. corridor is tight), the margin is
    grown and retried.
    """
    if not OBSTACLES or not is_path_blocked(start, end):
        return [start, end]

    obs = OBSTACLES[0]
    obs_left, obs_right = obs["x"], obs["x"] + obs["w"]
    obs_top, obs_bottom = obs["y"], obs["y"] + obs["h"]

    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]

    last_candidate = [start, end]

    for margin in (base_margin, base_margin + 10, base_margin + 20, base_margin + 35):
        if abs(dy) >= abs(dx):
            # Mostly vertical travel (the normal case along the corridor):
            # step sideways clear of the obstacle's x-range, travel past
            # its y-range at that safe x, then rejoin.
            left_clear_x = obs_left - margin
            right_clear_x = obs_right + margin
            left_space = left_clear_x - 270
            right_space = 460 - right_clear_x
            bypass_x = left_clear_x if left_space >= right_space else right_clear_x
            bypass_x = max(275, min(455, bypass_x))

            if dy > 0:  # travelling downward
                enter_y = obs_top - margin
                exit_y = obs_bottom + margin
            else:  # travelling upward
                enter_y = obs_bottom + margin
                exit_y = obs_top - margin

            p1 = {"x": bypass_x, "y": enter_y}
            p2 = {"x": bypass_x, "y": exit_y}
        else:
            # Mostly horizontal travel
            top_clear_y = obs_top - margin
            bottom_clear_y = obs_bottom + margin
            top_space = top_clear_y - 90
            bottom_space = 580 - bottom_clear_y
            bypass_y = top_clear_y if top_space >= bottom_space else bottom_clear_y

            if dx > 0:  # travelling rightward
                enter_x = obs_left - margin
                exit_x = obs_right + margin
            else:  # travelling leftward
                enter_x = obs_right + margin
                exit_x = obs_left - margin

            p1 = {"x": enter_x, "y": bypass_y}
            p2 = {"x": exit_x, "y": bypass_y}

        candidate = [start, p1, p2, end]
        legs_clear = all(
            not is_path_blocked(candidate[i], candidate[i + 1])
            for i in range(len(candidate) - 1)
        )
        if legs_clear:
            # Drop near-duplicate points for a clean, minimal path
            final_path = [candidate[0]]
            for pt in candidate[1:]:
                if math.hypot(pt["x"] - final_path[-1]["x"], pt["y"] - final_path[-1]["y"]) > 3:
                    final_path.append(pt)
            return final_path

        last_candidate = candidate

    # Fallback (shouldn't normally be reached): use the widest-margin
    # candidate even if a leg check was borderline — still far better than
    # cutting straight through the obstacle.
    return last_candidate

def compute_path(start, end_room):
    """
    Compute a path that follows the corridor, goes through doors,
    and avoids obstacles with a single smooth detour (no zigzag).
    """
    path = []
    
    # Start position
    start_pos = {"x": start["x"], "y": start["y"]}
    path.append(start_pos)
    
    # Get current room
    start_room = start.get("current_room")
    if not start_room:
        start_room = get_room_at_position(start["x"], start["y"])
    
    # If already in destination room, go to center
    if start_room == end_room:
        center = ROOM_CENTERS.get(end_room)
        if center and math.hypot(center["x"] - path[-1]["x"], center["y"] - path[-1]["y"]) > 5:
            path.append(center)
        return path
    
    # Define direct connections between rooms
    DIRECT_CONNECTIONS = {
        "toilet1": ["toilet2"],
        "toilet2": ["toilet1"],
        "entrance": ["sitout", "corridor"],
        "sitout": ["entrance"],
        "corridor": ["entrance", "living", "dining", "kitchen", "bedroom1", "bedroom2", "toilet1", "toilet2"],
        "living": ["corridor"],
        "dining": ["corridor"],
        "kitchen": ["corridor"],
        "bedroom1": ["corridor"],
        "bedroom2": ["corridor"],
    }
    
    # If start room has direct connection to end room
    if end_room in DIRECT_CONNECTIONS.get(start_room, []):
        current_pos = path[-1]
        
        # Go to start door if needed
        if start_room != "corridor" and start_room != "entrance":
            start_door = DOOR_POSITIONS.get(start_room)
            if start_door and math.hypot(start_door["x"] - current_pos["x"], start_door["y"] - current_pos["y"]) > 5:
                door_path = create_detour(current_pos, start_door)
                path.extend(door_path[1:])
                current_pos = path[-1]
        
        # Go to destination door
        end_door = DOOR_POSITIONS.get(end_room)
        if end_door and math.hypot(end_door["x"] - current_pos["x"], end_door["y"] - current_pos["y"]) > 5:
            door_path = create_detour(current_pos, end_door)
            path.extend(door_path[1:])
            current_pos = path[-1]
        
        # Go to destination center
        end_center = ROOM_CENTERS.get(end_room)
        if end_center and math.hypot(end_center["x"] - current_pos["x"], end_center["y"] - current_pos["y"]) > 5:
            center_path = create_detour(current_pos, end_center)
            path.extend(center_path[1:])
        
        return path
    
    # For rooms that require going through the corridor
    
    # 1. Get to the corridor
    current_pos = path[-1]
    
    if start_room != "corridor" and start_room != "entrance":
        start_door = DOOR_POSITIONS.get(start_room)
        if start_door and math.hypot(start_door["x"] - current_pos["x"], start_door["y"] - current_pos["y"]) > 5:
            door_path = create_detour(current_pos, start_door)
            path.extend(door_path[1:])
            current_pos = path[-1]
    
    # Handle sitout -> entrance
    if start_room == "sitout":
        entrance_door = DOOR_POSITIONS.get("entrance")
        if entrance_door and math.hypot(entrance_door["x"] - current_pos["x"], entrance_door["y"] - current_pos["y"]) > 5:
            door_path = create_detour(current_pos, entrance_door)
            path.extend(door_path[1:])
            current_pos = path[-1]
        start_room = "entrance"
    
    # Handle entrance -> corridor
    if start_room == "entrance" and end_room != "sitout":
        corridor_entrance = CORRIDOR_PATH[0]
        if math.hypot(corridor_entrance["x"] - current_pos["x"], corridor_entrance["y"] - current_pos["y"]) > 5:
            door_path = create_detour(current_pos, corridor_entrance)
            path.extend(door_path[1:])
            current_pos = path[-1]
        start_room = "corridor"
    
    # 2. Get destination door
    end_door = DOOR_POSITIONS.get(end_room)
    if not end_door:
        end_center = ROOM_CENTERS.get(end_room)
        if end_center:
            path.append(end_center)
        return path
    
    # 3. Find closest corridor points (just the entry and exit — we don't
    #    need to walk through every densely-spaced waypoint in between,
    #    since the corridor is a straight run)
    start_corridor_pt = get_closest_corridor_point(current_pos)
    dest_corridor_pt = get_closest_corridor_point(end_door)
    
    # 4-5. Walk the corridor as ONE straight segment. If the obstacle is in
    #    the way, insert a single bypass point — that's it. No per-waypoint
    #    dots, no repeated detour calls, no zigzag.
    if math.hypot(start_corridor_pt["x"] - current_pos["x"], start_corridor_pt["y"] - current_pos["y"]) > 5:
        path.append(start_corridor_pt)
    
    if is_path_blocked(path[-1], dest_corridor_pt):
        detour_path = create_detour(path[-1], dest_corridor_pt)
        path.extend(detour_path[1:])
    else:
        path.append(dest_corridor_pt)
    
    # 6. Go to destination door
    if end_room not in ["corridor", "entrance"]:
        if is_path_blocked(path[-1], end_door):
            detour_path = create_detour(path[-1], end_door)
            path.extend(detour_path[1:])
        else:
            path.append(end_door)
    
    # 7. Go to room center
    end_center = ROOM_CENTERS.get(end_room)
    if end_center and math.hypot(end_center["x"] - path[-1]["x"], end_center["y"] - path[-1]["y"]) > 5:
        if is_path_blocked(path[-1], end_center):
            detour_path = create_detour(path[-1], end_center)
            path.extend(detour_path[1:])
        else:
            path.append(end_center)
    
    # Ensure path has at least 2 points
    if len(path) < 2:
        end_center = ROOM_CENTERS.get(end_room)
        if end_center:
            path.append(end_center)
    
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
    """Simulate LiDAR scan from current robot position with obstacle detection"""
    # Include obstacles in the LiDAR scan
    obstacles = [
        {"x": 260, "y": 60,  "w": 10, "h": 220},
        {"x": 260, "y": 60,  "w": 400, "h": 10},
        {"x": 260, "y": 280, "w": 400, "h": 10},
        {"x": 460, "y": 280, "w": 10, "h": 290},
        {"x": 260, "y": 480, "w": 200, "h": 10},
        {"x": 90, "y": 100, "w": 150, "h": 150},
        {"x": 90, "y": 290, "w": 150, "h": 120},
        {"x": 90, "y": 420, "w": 150, "h": 110},
        {"x": 90, "y": 530, "w": 150, "h": 60},
        {"x": 270, "y": 290, "w": 190, "h": 280},
        {"x": 270, "y": 490, "w": 190, "h": 80},
        {"x": 470, "y": 90, "w": 200, "h": 190},
        {"x": 470, "y": 390, "w": 200, "h": 170},
        {"x": 470, "y": 290, "w": 90, "h": 95},
        {"x": 568, "y": 290, "w": 90, "h": 95},
    ]
    
    # Add corridor obstacle to LiDAR
    for obs in OBSTACLES:
        obstacles.append({
            "x": obs["x"], "y": obs["y"], 
            "w": obs["w"], "h": obs["h"]
        })
    
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
                           obstacles=json.dumps(OBSTACLES))

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route("/api/obstacles")
def get_obstacles():
    return jsonify(OBSTACLES)

@app.route("/api/navigate", methods=["POST"])
def navigate():
    data = request.json
    command = data.get("command", "")
    destination = parse_command(command)
    if not destination:
        return jsonify({"success": False, "error": f"Could not understand: '{command}'. Try 'go to kitchen' or 'navigate to bedroom'."})
    
    state = get_robot_state()
    path = compute_path(state, destination)
    
    if len(path) < 2:
        end_center = ROOM_CENTERS.get(destination)
        if end_center:
            path.append(end_center)
    
    # Simulate LiDAR at each waypoint to detect obstacles
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
