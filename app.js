/* ═══════════════════════════════════════════════
   LIDAR NAV — Main Application Script
═══════════════════════════════════════════════ */

// ── Canvases ──────────────────────────────────
const floorCanvas  = document.getElementById('floorCanvas');
const lidarCanvas  = document.getElementById('lidarCanvas');
const robotCanvas  = document.getElementById('robotCanvas');
const lidarPolar   = document.getElementById('lidarPolar');
const canvas3d     = document.getElementById('canvas3d');

const floorCtx  = floorCanvas.getContext('2d');
const lidarCtx  = lidarCanvas.getContext('2d');
const robotCtx  = robotCanvas.getContext('2d');
const polarCtx  = lidarPolar.getContext('2d');
const ctx3d     = canvas3d.getContext('2d');

// ── State ─────────────────────────────────────
let robotState   = { x: 365, y: 530, angle: 0, current_room: 'entrance' };
let animating    = false;
let currentPath  = [];
let currentLidar = [];
let robotImg     = new Image();
robotImg.src     = '/static/robot.jpg';

// Room color map
const ROOM_COLORS = {
  sitout:   '#FF6B6B', living: '#4ECDC4', dining: '#45B7D1',
  kitchen:  '#96CEB4', bedroom1: '#FFEAA7', bedroom2: '#DDA0DD',
  toilet1:  '#98FB98', toilet2: '#87CEEB', corridor: '#F0E68C',
  entrance: '#FFB347'
};

const DOOR_POSITIONS = {
    "kitchen": { x: 254, y: 205 },
    "dining": { x: 254, y: 355 },
    "living": { x: 254, y: 455 },
    "bedroom1": { x: 470, y: 185 },
    "bedroom2": { x: 470, y: 465 },
    "toilet1": { x: 470, y: 335 },
    "toilet2": { x: 568, y: 335 },
    "entrance": { x: 365, y: 530 },
    "sitout": { x: 254, y: 550 },      // ← moved to sitout/entrance wall
    "corridor": { x: 365, y: 400 },
};

// ── Init ──────────────────────────────────────
window.addEventListener('load', () => {
    fetchRobotState();
    fetchObstacles();  // ADD THIS
    drawFloorPlan();
    drawRobot(robotState.x, robotState.y, robotState.angle);
    animatePolar([]);
    draw3D(robotState.current_room);
    loadHistory();
    setInterval(animatePolar3DBg, 50);
});


function drawFloorPlan() {
    const ctx = floorCtx;
    const W = floorCanvas.width, H = floorCanvas.height;

    // Background
    ctx.fillStyle = '#060e1c';
    ctx.fillRect(0, 0, W, H);

    // Grid
    ctx.strokeStyle = 'rgba(0,229,255,0.04)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x < W; x += 20) { 
        ctx.beginPath(); 
        ctx.moveTo(x,0); 
        ctx.lineTo(x,H); 
        ctx.stroke(); 
    }
    for (let y = 0; y < H; y += 20) { 
        ctx.beginPath(); 
        ctx.moveTo(0,y); 
        ctx.lineTo(W,y); 
        ctx.stroke(); 
    }

    // Outer wall
    ctx.strokeStyle = 'rgba(0,229,255,0.8)';
    ctx.lineWidth = 3;
    ctx.strokeRect(30, 30, 620, 540);

    // Draw rooms
    for (const [key, room] of Object.entries(ROOMS_DATA)) {
        drawRoom(ctx, key, room);
    }

    // Draw walls
    drawWalls(ctx);
    
    // Draw doors
    drawDoors(ctx);
    
    // Draw obstacles - ADD THIS LINE
    drawObstacles(ctx);

    // Dimension labels
    ctx.fillStyle = 'rgba(0,229,255,0.5)';
    ctx.font = '11px Orbitron';
    ctx.textAlign = 'center';
    ctx.fillText('26 ft', W/2 - 16, H - 8);
    ctx.save(); 
    ctx.translate(12, H/2); 
    ctx.rotate(-Math.PI/2);
    ctx.fillText('35 ft', -16, 0); 
    ctx.restore();
}

// ── Room Drawing ────────────────────────────────
function drawRoom(ctx, key, room) {
    const color = ROOM_COLORS[key] || '#aaa';
    const [r,g,b] = hexToRgb(color);

    // Fill with subtle gradient
    const grad = ctx.createLinearGradient(room.x, room.y, room.x+room.w, room.y+room.h);
    grad.addColorStop(0, `rgba(${r},${g},${b},0.12)`);
    grad.addColorStop(1, `rgba(${r},${g},${b},0.04)`);
    ctx.fillStyle = grad;
    ctx.fillRect(room.x, room.y, room.w, room.h);

    // Room border
    ctx.strokeStyle = `rgba(${r},${g},${b},0.5)`;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(room.x, room.y, room.w, room.h);

    // Corner accents
    const cs = 8;
    ctx.strokeStyle = `rgba(${r},${g},${b},0.9)`;
    ctx.lineWidth = 2;
    [[room.x, room.y],[room.x+room.w, room.y],[room.x, room.y+room.h],[room.x+room.w, room.y+room.h]]
        .forEach(([cx,cy], i) => {
            const dx = i%2===0?1:-1, dy = i<2?1:-1;
            ctx.beginPath(); 
            ctx.moveTo(cx+dx*cs, cy); 
            ctx.lineTo(cx,cy); 
            ctx.lineTo(cx,cy+dy*cs); 
            ctx.stroke();
        });

    // Label background
    const lx = room.x + room.w/2, ly = room.y + room.h/2;
    ctx.fillStyle = `rgba(${r},${g},${b},0.15)`;
    const tw = ctx.measureText(room.label).width + 10;
    ctx.fillRect(lx - tw/2, ly - 18, tw, 22);

    // Label text
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.font = 'bold 11px Orbitron';
    ctx.textAlign = 'center'; 
    ctx.textBaseline = 'middle';
    ctx.fillText(room.label, lx, ly - 6);

    // Add door icon ONLY for rooms that have doors and are NOT the wall between sitout and living
    // We skip adding door icons for sitout and living here since they'll be drawn in drawDoors()
    if (DOOR_POSITIONS[key] && key !== 'sitout' && key !== 'living') {
        const door = DOOR_POSITIONS[key];
        ctx.font = '14px sans-serif';
        ctx.fillStyle = 'rgba(255,170,0,0.6)';
        ctx.fillText('🚪', door.x - 10, door.y + 5);
    }

    // Dimension hint
    ctx.fillStyle = `rgba(${r},${g},${b},0.6)`;
    ctx.font = '9px Share Tech Mono';
    const dimLabel = `${(room.w/20).toFixed(1)}×${(room.h/20).toFixed(1)}ft`;
    ctx.fillText(dimLabel, lx, ly + 8);

    ctx.textAlign = 'left'; 
    ctx.textBaseline = 'alphabetic';
}

function drawWalls(ctx) {
    ctx.strokeStyle = 'rgba(0,229,255,0.7)';
    ctx.lineWidth = 3;
    
    // ── VERTICAL WALL: Left side (x=250) with door gaps ──
    // Kitchen door (y: 185-225) - centered
    ctx.beginPath(); ctx.moveTo(250, 30); ctx.lineTo(250, 180); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(250, 230); ctx.lineTo(250, 250); ctx.stroke();
    
    // Dining door (y: 335-375) - moved UP to avoid living room wall
    ctx.beginPath(); ctx.moveTo(250, 250); ctx.lineTo(250, 330); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(250, 380); ctx.lineTo(250, 410); ctx.stroke(); // Wall continues to living room boundary
    
    // Living door (y: 435-475) - centered
    ctx.beginPath(); ctx.moveTo(250, 420); ctx.lineTo(250, 430); ctx.stroke(); // Wall from dining boundary
    ctx.beginPath(); ctx.moveTo(250, 480); ctx.lineTo(250, 500); ctx.stroke();
    
    // ── HORIZONTAL WALLS: Left rooms ──
    ctx.beginPath(); ctx.moveTo(30, 250); ctx.lineTo(250, 250); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(30, 380); ctx.lineTo(250, 380); ctx.stroke();
    
    // ── SOLID WALL BETWEEN SITOUT AND LIVING ──
    // Complete wall from x=30 to x=250 at y=500 - NO DOOR
    ctx.beginPath(); ctx.moveTo(30, 500); ctx.lineTo(250, 500); ctx.stroke();
    
    // ── VERTICAL WALL: Between corridor and bedrooms/toilets (x=460) ──
    // Bedroom1 door (y: 165-205) - centered
    ctx.beginPath(); ctx.moveTo(460, 90); ctx.lineTo(460, 160); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(460, 210); ctx.lineTo(460, 280); ctx.stroke();
    
    // Toilet1 door (y: 315-355) - centered
    ctx.beginPath(); ctx.moveTo(460, 280); ctx.lineTo(460, 310); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(460, 360); ctx.lineTo(460, 380); ctx.stroke();
    
    // Toilet2 door (y: 315-355) - centered on wall at x=568
    ctx.beginPath(); ctx.moveTo(568, 280); ctx.lineTo(568, 310); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(568, 360); ctx.lineTo(568, 380); ctx.stroke();
    
    // Bedroom2 door (y: 445-485) - centered
    ctx.beginPath(); ctx.moveTo(460, 380); ctx.lineTo(460, 440); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(460, 490); ctx.lineTo(460, 570); ctx.stroke();
    
    // ── WALLS BETWEEN TOILETS ──
    ctx.beginPath(); ctx.moveTo(555, 280); ctx.lineTo(555, 380); ctx.stroke();
    
    // ── TOILET BOTTOM WALL ──
    ctx.beginPath(); ctx.moveTo(460, 380); ctx.lineTo(650, 380); ctx.stroke();
    
    // ── BEDROOM WALLS ──
    ctx.beginPath(); ctx.moveTo(650, 90); ctx.lineTo(650, 280); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(650, 390); ctx.lineTo(650, 570); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(460, 390); ctx.lineTo(650, 390); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(460, 560); ctx.lineTo(650, 560); ctx.stroke();
    
    // ── ENTRANCE/CORRIDOR DIVIDE ──
    // ── ENTRANCE/CORRIDOR DIVIDE (door gap centered on corridor, x:345-385) ──
    ctx.beginPath(); ctx.moveTo(250, 480); ctx.lineTo(345, 480); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(385, 480); ctx.lineTo(460, 480); ctx.stroke();
        
    // ── WALL AT x=250 BETWEEN LIVING AND SITOUT ──
    // This creates a solid wall separating living and sitout vertically
    ctx.beginPath(); ctx.moveTo(250, 500); ctx.lineTo(250, 530); ctx.stroke();
}

function drawDoors(ctx) {
    const doorColor = 'rgba(255,170,0,0.4)';
    
    const doors = [
        // Kitchen door (right wall of kitchen at x=250, facing corridor)
        { x: 248, y: 185, w: 6, h: 40, label: 'Kitchen' },
        // Dining door (right wall of dining at x=250, facing corridor) - MOVED UP
        { x: 248, y: 335, w: 6, h: 40, label: 'Dining' },
        // Living door (right wall of living at x=250, facing corridor) - CENTERED
        { x: 248, y: 435, w: 6, h: 40, label: 'Living' },
        // Bedroom1 door (left wall of bedroom1 at x=470, facing corridor)
        { x: 470, y: 165, w: 6, h: 40, label: 'Bedroom 1' },
        // Bedroom2 door (left wall of bedroom2 at x=470, facing corridor) - CENTERED
        { x: 470, y: 445, w: 6, h: 40, label: 'Bedroom 2' },
        // Toilet1 door (left wall of toilet1 at x=470, facing corridor)
        { x: 470, y: 315, w: 6, h: 40, label: 'Toilet 1' },
        // Toilet2 door (left wall of toilet2 at x=568, facing corridor)
        { x: 568, y: 315, w: 6, h: 40, label: 'Toilet 2' },
        // Entrance door (bottom wall of entrance) - THIS IS THE DOOR BETWEEN ENTRANCE AND SITOUT
        // Sitout ↔ Entrance door (vertical wall at x=250)
        { x: 248, y: 530, w: 6, h: 40, label: 'Sitout ↔ Entrance' },
        { x: 345, y: 477, w: 40, h: 6, label: 'Entrance ↔ Corridor' },
    ];
    
    doors.forEach(door => {
        ctx.save();
        
        // Door opening (gap in wall)
        ctx.fillStyle = '#060e1c';
        ctx.fillRect(door.x, door.y, door.w, door.h);
        
        // Door frame glow
        ctx.strokeStyle = doorColor;
        ctx.lineWidth = 2;
        ctx.shadowColor = 'rgba(255,170,0,0.3)';
        ctx.shadowBlur = 8;
        ctx.strokeRect(door.x, door.y, door.w, door.h);
        ctx.shadowBlur = 0;
        
        // Door arc (swing) - horizontal door
        ctx.strokeStyle = 'rgba(255,170,0,0.25)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        
        const cx = door.x + door.w/2;
        const cy = door.y + (door.h/2);
        const radius = Math.min(door.w, door.h) * 1.5;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, -Math.PI, 0);
        ctx.stroke();
        
        ctx.setLineDash([]);
        
        // Door label
        ctx.fillStyle = 'rgba(255,170,0,0.8)';
        ctx.font = 'bold 9px Orbitron';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        const labelX = door.x + door.w/2;
        const labelY = door.y - 4;
        ctx.fillText('🚪', labelX, labelY);
        
        ctx.restore();
    });
}
// ── Draw Obstacles ──────────────────────────────
// ── Draw Obstacles ──────────────────────────────
function drawObstacles(ctx) {
    if (typeof OBSTACLES_DATA === 'undefined' || !OBSTACLES_DATA || OBSTACLES_DATA.length === 0) return;
    
    OBSTACLES_DATA.forEach(obs => {
        // Shadow
        ctx.shadowColor = 'rgba(0,0,0,0.5)';
        ctx.shadowBlur = 20;
        
        // 3D effect
        const grad = ctx.createLinearGradient(obs.x, obs.y, obs.x + obs.w, obs.y + obs.h);
        grad.addColorStop(0, '#A0522D');
        grad.addColorStop(0.5, '#8B4513');
        grad.addColorStop(1, '#4A2508');
        
        ctx.fillStyle = grad;
        ctx.fillRect(obs.x, obs.y, obs.w, obs.h);
        
        ctx.shadowBlur = 0;
        ctx.strokeStyle = 'rgba(255,200,100,0.3)';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(obs.x, obs.y, obs.w, obs.h);
        
        // Label
        ctx.fillStyle = 'rgba(255,255,255,0.9)';
        ctx.font = 'bold 12px Orbitron';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🪑', obs.x + obs.w/2, obs.y + obs.h/2 - 2);
        
        ctx.font = 'bold 7px Orbitron';
        ctx.fillStyle = 'rgba(255,200,100,0.8)';
        ctx.fillText(obs.label, obs.x + obs.w/2, obs.y + obs.h/2 + 14);
    });
}

// ── Fetch Obstacles ──────────────────────────────
async function fetchObstacles() {
    try {
        const res = await fetch('/api/obstacles');
        window.OBSTACLES_DATA = await res.json();
    } catch(e) {
        window.OBSTACLES_DATA = [];
    }
}


function darkenColor(hex, amount) {
    let r = parseInt(hex.slice(1,3), 16);
    let g = parseInt(hex.slice(3,5), 16);
    let b = parseInt(hex.slice(5,7), 16);
    r = Math.max(0, r - amount);
    g = Math.max(0, g - amount);
    b = Math.max(0, b - amount);
    return `rgb(${r},${g},${b})`;
}
// Add this function to update LiDAR during movement
async function updateLidarDuringMovement(x, y, angle) {
    try {
        // Get current LiDAR scan
        const res = await fetch('/api/lidar_current');
        const data = await res.json();
        if (data.lidar) {
            currentLidar = data.lidar;
            drawLidarBeams(currentLidar, x, y);
            drawPolarLidar(currentLidar);
            document.getElementById('lidarHits').textContent = 
                currentLidar.filter(b=>b.hit).length;
        }
    } catch(e) {
        // Silent fail - use existing LiDAR data
    }
}

// ── Robot Drawing ─────────────────────────────
function drawRobot(x, y, angle) {
  const ctx = robotCtx;
  ctx.clearRect(0, 0, robotCanvas.width, robotCanvas.height);

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle * Math.PI / 180);

  // Glow effect
  ctx.shadowColor = '#00ff88';
  ctx.shadowBlur = 20;

  // Try to draw robot image, fallback to shape
  try {
    if (robotImg.complete && robotImg.naturalWidth) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(0, 0, 18, 0, Math.PI*2);
      ctx.clip();
      ctx.drawImage(robotImg, -18, -18, 36, 36);
      ctx.restore();
    } else {
      drawRobotShape(ctx);
    }
  } catch(e) { drawRobotShape(ctx); }

  // Direction arrow
  ctx.shadowBlur = 0;
  ctx.strokeStyle = '#00ff88';
  ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(0,0); ctx.lineTo(28, 0);
  ctx.stroke();
  ctx.fillStyle = '#00ff88';
  ctx.beginPath(); ctx.moveTo(28,0); ctx.lineTo(22,-4); ctx.lineTo(22,4); ctx.fill();

  // Outer ring
  ctx.strokeStyle = 'rgba(0,255,136,0.6)';
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(0, 0, 22, 0, Math.PI*2); ctx.stroke();

  ctx.restore();

  // Position pulse
  ctx.save();
  ctx.translate(x, y);
  const t = Date.now() / 500;
  const pulseR = 30 + 10*Math.sin(t);
  ctx.strokeStyle = `rgba(0,255,136,${0.2+0.1*Math.sin(t)})`;
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(0, 0, pulseR, 0, Math.PI*2); ctx.stroke();
  ctx.restore();
}

function drawRobotShape(ctx) {
  // Body
  ctx.fillStyle = '#1a3a5c';
  ctx.beginPath(); ctx.arc(0, 0, 16, 0, Math.PI*2); ctx.fill();
  ctx.strokeStyle = '#00ff88';
  ctx.lineWidth = 2;
  ctx.stroke();
  // Wheels
  [-1,1].forEach(s => {
    ctx.fillStyle = '#333';
    ctx.fillRect(-12, s*10-3, 8, 6);
    ctx.fillRect(4, s*10-3, 8, 6);
  });
  // Eye
  ctx.fillStyle = '#00ff88';
  ctx.beginPath(); ctx.arc(6, 0, 4, 0, Math.PI*2); ctx.fill();
}

// ── Path Drawing ──────────────────────────────
function drawPath(path) {
  const ctx = lidarCtx;
  if (!path || path.length < 2) return;

  ctx.save();
  ctx.strokeStyle = '#00e5ff';
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 4]);
  ctx.shadowColor = '#00e5ff';
  ctx.shadowBlur = 6;

  ctx.beginPath();
  ctx.moveTo(path[0].x, path[0].y);
  for (let i = 1; i < path.length; i++) {
    ctx.lineTo(path[i].x, path[i].y);
  }
  ctx.stroke();
  ctx.setLineDash([]);

  // Waypoint markers
  path.forEach((pt, i) => {
    if (i === 0) return;
    ctx.fillStyle = i === path.length-1 ? '#ffaa00' : '#00e5ff';
    ctx.shadowColor = ctx.fillStyle;
    ctx.shadowBlur = 10;
    ctx.beginPath(); ctx.arc(pt.x, pt.y, 5, 0, Math.PI*2); ctx.fill();
  });
  ctx.restore();
}

function drawLidarBeams(lidarData, rx, ry) {
  const ctx = lidarCtx;
  ctx.clearRect(0, 0, lidarCanvas.width, lidarCanvas.height);

  if (!lidarData || !lidarData.length) return;

  // Draw path
  drawPath(currentPath);

  lidarData.forEach(beam => {
    const rad = beam.angle * Math.PI / 180;
    const ex = rx + beam.distance * Math.cos(rad);
    const ey = ry + beam.distance * Math.sin(rad);

    ctx.strokeStyle = beam.hit
      ? 'rgba(255,51,85,0.35)'
      : 'rgba(0,229,255,0.08)';
    ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(ex, ey); ctx.stroke();

    if (beam.hit) {
      ctx.fillStyle = '#ff3355';
      ctx.shadowColor = '#ff3355'; ctx.shadowBlur = 4;
      ctx.beginPath(); ctx.arc(ex, ey, 2.5, 0, Math.PI*2); ctx.fill();
      ctx.shadowBlur = 0;
    }
  });
}

// ── Polar LiDAR ───────────────────────────────
let polarAngle = 0;
function animatePolar3DBg() {
  polarAngle += 2;
  if (currentLidar.length) drawPolarLidar(currentLidar);
  else drawPolarIdle();
  draw3D(robotState.current_room);
}

function drawPolarIdle() {
  const ctx = polarCtx;
  const cx = 110, cy = 110, maxR = 100;
  ctx.clearRect(0, 0, 220, 220);
  ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(0,0,220,220);

  // Rings
  [25,50,75,100].forEach(r => {
    ctx.strokeStyle = 'rgba(0,229,255,0.12)';
    ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.stroke();
  });
  // Cross
  ctx.strokeStyle = 'rgba(0,229,255,0.12)';
  [[cx-100,cy,cx+100,cy],[cx,cy-100,cx,cy+100]].forEach(([x1,y1,x2,y2])=>{
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  });

  // Spinning sweep
  const rad = polarAngle * Math.PI / 180;
  const grad = ctx.createLinearGradient(cx,cy,cx+100*Math.cos(rad),cy+100*Math.sin(rad));
  grad.addColorStop(0,'rgba(0,229,255,0.3)');
  grad.addColorStop(1,'rgba(0,229,255,0)');
  ctx.strokeStyle = grad;
  ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(cx,cy);
  ctx.lineTo(cx+100*Math.cos(rad),cy+100*Math.sin(rad)); ctx.stroke();

  // Center
  ctx.fillStyle = '#00ff88';
  ctx.beginPath(); ctx.arc(cx,cy,4,0,Math.PI*2); ctx.fill();
}

function drawPolarLidar(beams) {
  const ctx = polarCtx;
  const cx = 110, cy = 110, scale = 0.5;
  ctx.clearRect(0,0,220,220);
  ctx.fillStyle = 'rgba(0,0,0,0.85)'; ctx.fillRect(0,0,220,220);

  [25,50,75,100].forEach(r => {
    ctx.strokeStyle = 'rgba(0,229,255,0.12)'; ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.stroke();
  });
  [[cx-100,cy,cx+100,cy],[cx,cy-100,cx,cy+100]].forEach(([x1,y1,x2,y2])=>{
    ctx.strokeStyle='rgba(0,229,255,0.12)'; ctx.lineWidth=0.5;
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  });

  // Sweep overlay
  const rad = polarAngle * Math.PI / 180;
  ctx.save();
  ctx.globalAlpha = 0.15;
  ctx.fillStyle = '#00e5ff';
  ctx.beginPath(); ctx.moveTo(cx,cy);
  ctx.arc(cx,cy,100,rad-0.3,rad); ctx.closePath(); ctx.fill();
  ctx.restore();

  // Beams
  beams.forEach(b => {
    const r = b.angle * Math.PI / 180;
    const d = b.distance * scale;
    ctx.strokeStyle = b.hit ? 'rgba(255,51,85,0.6)' : 'rgba(0,229,255,0.15)';
    ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(cx,cy);
    ctx.lineTo(cx+d*Math.cos(r), cy+d*Math.sin(r)); ctx.stroke();
    if (b.hit) {
      ctx.fillStyle='#ff3355'; ctx.shadowColor='#ff3355'; ctx.shadowBlur=4;
      ctx.beginPath(); ctx.arc(cx+d*Math.cos(r),cy+d*Math.sin(r),2.5,0,Math.PI*2); ctx.fill();
      ctx.shadowBlur=0;
    }
  });

  ctx.fillStyle='#00ff88'; ctx.shadowColor='#00ff88'; ctx.shadowBlur=8;
  ctx.beginPath(); ctx.arc(cx,cy,5,0,Math.PI*2); ctx.fill();
  ctx.shadowBlur=0;
}

// ── 3D Room View ──────────────────────────────
function draw3D(roomKey) {
  const ctx = ctx3d;
  const W = 220, H = 160;
  ctx.clearRect(0,0,W,H);

  const color = ROOM_COLORS[roomKey] || '#aaa';
  const [r,g,b] = hexToRgb(color);
  const t = Date.now()/1000;

  // Sky
  const sky = ctx.createLinearGradient(0,0,0,H);
  sky.addColorStop(0,'#050a14');
  sky.addColorStop(1,`rgba(${r},${g},${b},0.08)`);
  ctx.fillStyle = sky; ctx.fillRect(0,0,W,H);

  // Floor perspective
  const vpx = W/2, vpy = 55;
  const floorPts = [[0,H],[W,H],[W*0.75,vpy+30],[W*0.25,vpy+30]];
  const floorGrad = ctx.createLinearGradient(0,vpy+30,0,H);
  floorGrad.addColorStop(0,`rgba(${r},${g},${b},0.25)`);
  floorGrad.addColorStop(1,`rgba(${r},${g},${b},0.08)`);
  ctx.fillStyle = floorGrad;
  ctx.beginPath(); floorPts.forEach(([px,py],i)=>i?ctx.lineTo(px,py):ctx.moveTo(px,py));
  ctx.closePath(); ctx.fill();

  // Floor grid
  ctx.strokeStyle = `rgba(${r},${g},${b},0.2)`; ctx.lineWidth = 0.5;
  for(let i=1;i<5;i++){
    const t=i/5;
    const y1=vpy+30+(H-vpy-30)*t;
    const x1=W*0.25+(0-W*0.25)*t, x2=W*0.75+(W-W*0.75)*t;
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2||y1); ctx.stroke();
  }
  for(let i=0;i<=4;i++){
    const t=i/4;
    const bx=W*t, fx=W*0.25+(W*0.5)*t;
    ctx.beginPath(); ctx.moveTo(fx,vpy+30); ctx.lineTo(bx,H); ctx.stroke();
  }

  // Walls
  // Left wall
  const leftWall = ctx.createLinearGradient(0,0,W*0.25,0);
  leftWall.addColorStop(0,'rgba(0,0,0,0.8)');
  leftWall.addColorStop(1,`rgba(${r},${g},${b},0.12)`);
  ctx.fillStyle = leftWall;
  ctx.beginPath(); ctx.moveTo(0,0); ctx.lineTo(W*0.25,vpy+30); ctx.lineTo(0,H); ctx.closePath(); ctx.fill();

  // Right wall
  const rightWall = ctx.createLinearGradient(W*0.75,0,W,0);
  rightWall.addColorStop(0,`rgba(${r},${g},${b},0.12)`);
  rightWall.addColorStop(1,'rgba(0,0,0,0.8)');
  ctx.fillStyle = rightWall;
  ctx.beginPath(); ctx.moveTo(W,0); ctx.lineTo(W*0.75,vpy+30); ctx.lineTo(W,H); ctx.closePath(); ctx.fill();

  // Ceiling
  const ceiling = ctx.createLinearGradient(0,0,0,vpy+30);
  ceiling.addColorStop(0,`rgba(${r},${g},${b},0.06)`);
  ceiling.addColorStop(1,`rgba(${r},${g},${b},0.2)`);
  ctx.fillStyle = ceiling;
  ctx.fillRect(0,0,W,vpy+30);

  // Vanishing point perspective lines
  ctx.strokeStyle=`rgba(${r},${g},${b},0.3)`; ctx.lineWidth=1;
  [[0,0],[W,0],[0,H],[W,H]].forEach(([px,py])=>{
    ctx.beginPath(); ctx.moveTo(px,py); ctx.lineTo(vpx,vpy); ctx.stroke();
  });

  // Room label
  ctx.fillStyle = `rgba(${r},${g},${b},0.9)`;
  ctx.font = 'bold 13px Orbitron';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.shadowColor = color; ctx.shadowBlur = 8;
  const label = ROOMS_DATA[roomKey]?.label || roomKey.toUpperCase();
  ctx.fillText(label, W/2, 25);
  ctx.shadowBlur=0; ctx.textAlign='left'; ctx.textBaseline='alphabetic';

  // Animated robot sprite in 3D
  const rx = W/2 + 20*Math.sin(t*0.8);
  const ry = H*0.65 + 5*Math.sin(t*1.2);
  ctx.fillStyle = '#00ff88'; ctx.shadowColor='#00ff88'; ctx.shadowBlur=6;
  ctx.beginPath(); ctx.arc(rx,ry,6,0,Math.PI*2); ctx.fill();
  ctx.shadowBlur=0;

  document.getElementById('ri3dRoom').textContent = label;
}

// ── Robot Animation ────────────────────────────
// Modify the animateRobot function to update LiDAR during movement
async function animateRobot(path) {
    if (animating || !path || path.length < 2) return;
    animating = true;

    for (let i = 0; i < path.length - 1; i++) {
        const from = path[i], to = path[i+1];
        const dist = Math.hypot(to.x-from.x, to.y-from.y);
        const steps = Math.max(30, Math.floor(dist/3));
        const angle = Math.atan2(to.y-from.y, to.x-from.x) * 180/Math.PI;

        for (let s = 0; s <= steps; s++) {
            const t = s/steps;
            const x = from.x + (to.x-from.x)*t;
            const y = from.y + (to.y-from.y)*t;
            robotState.x = x; robotState.y = y; robotState.angle = angle;
            drawRobot(x, y, angle);
            
            // Update LiDAR every few steps
            if (s % 3 === 0) {
                await updateLidarDuringMovement(x, y, angle);
            } else {
                drawLidarBeams(currentLidar, x, y);
            }
            
            updateStateDisplay();
            await sleep(16);
        }
    }
    animating = false;
}

// ── Navigation API ────────────────────────────
async function navigate(command) {
  if (animating) { showNotif('Robot is moving...', 'info'); return; }

  setStatus('NAVIGATING...', true);
  addLog(`► ${command}`, 'nav');

  try {
    const res = await fetch('/api/navigate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({command})
    });
    const data = await res.json();

    if (data.success) {
      currentPath = data.path;
      currentLidar = data.lidar;
      robotState = data.robot_state;

      // Update lidar display
      document.getElementById('lidarHits').textContent =
        data.lidar.filter(b=>b.hit).length;

      showNotif(`✓ Navigating to ${data.destination_label}`, 'success');
      addLog(`✓ → ${data.destination_label}`, 'success');
      setStatus('NAVIGATING — ' + data.destination_label.toUpperCase(), false);

      // Activate nav topic
      document.getElementById('topicNav').classList.add('active');

      // Animate
      await animateRobot(data.path);

      robotState = data.robot_state;
      drawRobot(robotState.x, robotState.y, robotState.angle);
      drawLidarBeams(currentLidar, robotState.x, robotState.y);
      draw3D(robotState.current_room);
      updateStateDisplay();
      setStatus('ARRIVED — ' + data.destination_label.toUpperCase(), false);
      addLog(`⬤ Arrived at ${data.destination_label}`, 'success');

      document.getElementById('topicNav').classList.remove('active');
      loadHistory();
    } else {
      showNotif(data.error, 'error');
      addLog(`✗ ${data.error}`, 'error');
      setStatus('SYSTEM READY', false);
    }
  } catch(e) {
    showNotif('Connection error', 'error');
    setStatus('ERROR', false);
  }
}

function sendCommand() {
  const input = document.getElementById('cmdInput');
  const cmd = input.value.trim();
  if (!cmd) return;
  input.value = '';
  navigate(cmd);
}

function quickNav(room) {
  navigate(`go to ${room}`);
}

// ── Voice Recognition ─────────────────────────
let recognition = null;
let voiceActive = false;

function startVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showNotif('Speech recognition not supported. Use Chrome.', 'error');
    return;
  }

  if (voiceActive) {
    if (recognition) recognition.stop();
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = true;
  recognition.maxAlternatives = 3;

  const btn = document.getElementById('voiceBtn');
  const visual = document.getElementById('voiceVisual');
  const transcript = document.getElementById('transcript');

  recognition.onstart = () => {
    voiceActive = true;
    btn.classList.add('recording');
    btn.querySelector('.btn-label').textContent = '● LISTENING...';
    visual.classList.add('recording');
    transcript.textContent = '🎙 Listening...';
    addLog('🎙 Voice activated', 'nav');
  };

  recognition.onresult = (e) => {
    let text = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      text += e.results[i][0].transcript;
    }
    transcript.textContent = text;
    if (e.results[e.results.length-1].isFinal) {
      navigate(text);
    }
  };

  recognition.onerror = (e) => {
    transcript.textContent = `Error: ${e.error}`;
    addLog(`Voice error: ${e.error}`, 'error');
  };

  recognition.onend = () => {
    voiceActive = false;
    btn.classList.remove('recording');
    btn.querySelector('.btn-label').textContent = 'HOLD TO SPEAK';
    visual.classList.remove('recording');
  };

  recognition.start();
}

// ── UI Helpers ────────────────────────────────
function setStatus(text, busy) {
  document.getElementById('statusText').textContent = text;
  const dot = document.getElementById('statusDot');
  dot.style.background = busy ? '#ffaa00' : '#00ff88';
  dot.style.boxShadow = busy ? '0 0 12px rgba(255,170,0,0.5)' : '0 0 12px rgba(0,255,136,0.5)';
}

function updateStateDisplay() {
  document.getElementById('posX').textContent = Math.round(robotState.x);
  document.getElementById('posY').textContent = Math.round(robotState.y);
  document.getElementById('posAngle').textContent = Math.round(robotState.angle) + '°';
  const label = ROOMS_DATA[robotState.current_room]?.label || robotState.current_room;
  document.getElementById('posRoom').textContent = label;
  document.getElementById('currentRoomDisplay').textContent = label.toUpperCase();
}

let logTimeout;
function addLog(msg, type='') {
  const list = document.getElementById('logList');
  const d = document.createElement('div');
  d.className = `log-item ${type}`;
  const now = new Date(); const t = now.toLocaleTimeString('en',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
  d.innerHTML = `<span class="log-time">[${t}]</span> ${msg}`;
  list.insertBefore(d, list.firstChild);
  while (list.children.length > 30) list.removeChild(list.lastChild);
}

let notifTimer;
function showNotif(msg, type='info') {
  const n = document.getElementById('notif');
  n.textContent = msg; n.className = `notif ${type} show`;
  clearTimeout(notifTimer);
  notifTimer = setTimeout(()=>n.classList.remove('show'), 3500);
}

async function fetchRobotState() {
  try {
    const res = await fetch('/api/robot_state');
    robotState = await res.json();
    updateStateDisplay();
    drawRobot(robotState.x, robotState.y, robotState.angle);
    draw3D(robotState.current_room);
  } catch(e) {}
}

async function resetRobot() {
  await fetch('/api/reset', {method:'POST'});
  robotState = {x:365, y:530, angle:0, current_room:'entrance'};
  currentPath = []; currentLidar = [];
  lidarCtx.clearRect(0,0,lidarCanvas.width,lidarCanvas.height);
  drawRobot(robotState.x, robotState.y, robotState.angle);
  updateStateDisplay(); draw3D('entrance');
  showNotif('Robot reset to entrance', 'info');
  addLog('⟳ Robot reset', 'nav');
}

async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    const list = document.getElementById('histList');
    list.innerHTML = data.map(h => `
      <div class="hist-entry">
        <span class="hist-cmd">${h.command}</span>
        <span class="hist-dest">→ ${(ROOMS_DATA[h.destination]?.label||h.destination)}</span>
        <div class="hist-time">${h.timestamp}</div>
      </div>`).join('') || '<div class="hist-entry" style="color:#4a7fa8">No history yet</div>';
  } catch(e) {}
}

// ── Utils ─────────────────────────────────────
function sleep(ms) { return new Promise(r=>setTimeout(r,ms)); }
function hexToRgb(hex) {
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  return [r,g,b];
}