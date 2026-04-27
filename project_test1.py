from OpenGL.GL   import *
from OpenGL.GLUT import *
from OpenGL.GLU  import *
import math, random, time, sys, os

# ─────────────────────────── WINDOW / WORLD CONSTANTS ────────────
WIN_W, WIN_H = 1000, 800

LANES        = [-2.0, 0.0, 2.0]   # X positions of the 3 lanes
GRAVITY      = 28.0
JUMP_VEL     = 11.0
SPRING_VEL   = 19.0
BASE_SPEED   = 7.0
SPEED_INC    = 0.0012              # added per metre of distance
ZONE_DIST    = 300.0               # metres between zone changes
TILE_LEN     = 10.0                # ground tile length (Z)

# Camera
fovY         = 65

# ─────────────────────────── ZONE DEFINITIONS ────────────────────
# Each tuple: sky_top, sky_bot, ground_col, fog_col, name, rain, snow
ZONES = [
    ((0.53,0.81,0.98),(0.78,0.93,1.00),(0.20,0.55,0.10),(0.78,0.93,1.00),"Meadow",         False, False),
    ((0.10,0.10,0.24),(0.20,0.20,0.40),(0.10,0.28,0.10),(0.15,0.15,0.30),"Night Forest",   False, False),
    ((0.35,0.47,0.60),(0.55,0.65,0.75),(0.15,0.40,0.10),(0.45,0.55,0.65),"Rainy Valley",   True,  False),
    ((0.78,0.88,0.95),(0.90,0.95,1.00),(0.85,0.92,0.98),(0.85,0.90,0.95),"Snowfield",      False, True ),
    ((0.30,0.10,0.35),(0.55,0.25,0.60),(0.18,0.10,0.20),(0.40,0.20,0.45),"Twilight Hills", False, False),
    ((0.05,0.05,0.15),(0.10,0.05,0.20),(0.05,0.18,0.05),(0.05,0.05,0.12),"The Void",       False, False),
]

# ─────────────────────────── GLOBAL GAME STATE ───────────────────
game_state    = "menu"   # "menu" | "playing" | "dead"
distance      = 0.0
carrots       = 0
game_speed    = BASE_SPEED
zone_idx      = 0
last_zone     = 0
invisible_gnd = False
screen_shake  = 0.0
shake_amp     = 0.0
last_time     = 0.0
spawn_timer   = 0.0
ground_far_z  = 0.0

player = {
    "lane": 1, "x": 0.0, "y": 0.0, "vy": 0.0,
    "jumping": False, "jump_count": 0,
    "ducking": False, "duck_timer": 0.0,
    "invincible": False, "inv_timer": 0.0,
    "double_jump": False, "dj_timer": 0.0,
    "kick_timer": 0.0, "hop_anim": 0.0, "blink_t": 0.0,
}

objects      = []   # obstacle / collectible dicts
particles    = []   # particle dicts
ground_tiles = []   # ground tile dicts
weather      = []   # rain / snow drop dicts

# ─────────────────────────── UTILS ───────────────────────────────

def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ─────────────────────────── draw_text (same as template) ────────

def draw_text(x, y, text, r=1.0, g=1.0, b=1.0,
              font=GLUT_BITMAP_HELVETICA_18): # type: ignore
    glColor3f(r, g, b)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, WIN_W, 0, WIN_H)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

# ─────────────────────────── GEOMETRY HELPERS ────────────────────

def _unit_cube():
    verts = [(-0.5,-0.5,-0.5),(0.5,-0.5,-0.5),(0.5,0.5,-0.5),(-0.5,0.5,-0.5),
             (-0.5,-0.5, 0.5),(0.5,-0.5, 0.5),(0.5,0.5, 0.5),(-0.5,0.5, 0.5)]
    faces   = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
    glBegin(GL_QUADS)
    for face in faces:
        for vi in face:
            glVertex3f(*verts[vi])
    glEnd()

def draw_box(cx, cy, cz, sx, sy, sz, col):
    glColor3f(*col)
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glScalef(sx, sy, sz)
    _unit_cube()
    glPopMatrix()

def draw_sphere(cx, cy, cz, r, col, sl=10, st=8):
    glColor3f(*col)
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glutSolidSphere(r, sl, st)
    glPopMatrix()

def draw_cylinder(cx, cy, cz, r, h, col, sl=8):
    glColor3f(*col)
    glPushMatrix()
    glTranslatef(cx, cy + h * 0.5, cz)
    glScalef(r * 2.0, h, r * 2.0)
    glutSolidCube(1.0)
    glPopMatrix()

def draw_screen_rect(x, y, w, h, r, g, b, a=1.0):
    """Screen-space filled rectangle (for HUD bars / overlays)."""
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
    gluOrtho2D(0, WIN_W, 0, WIN_H)
    glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
    glColor3f(r, g, b)
    glBegin(GL_QUADS)
    glVertex3f(x,   y,   0); glVertex3f(x+w, y,   0)
    glVertex3f(x+w, y+h, 0); glVertex3f(x,   y+h, 0)
    glEnd()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION); glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

# ─────────────────────────── SKYBOX ──────────────────────────────

def draw_skybox():
    top = ZONES[zone_idx][0]
    bot = ZONES[zone_idx][1]
    glBegin(GL_QUADS)
    # back wall
    glColor3f(*top); glVertex3f(-200, 80,-150)
    glColor3f(*top); glVertex3f( 200, 80,-150)
    glColor3f(*bot); glVertex3f( 200, -2,-150)
    glColor3f(*bot); glVertex3f(-200, -2,-150)
    # left wall
    glColor3f(*top); glVertex3f(-200, 80,  20)
    glColor3f(*top); glVertex3f(-200, 80,-150)
    glColor3f(*bot); glVertex3f(-200, -2,-150)
    glColor3f(*bot); glVertex3f(-200, -2,  20)
    # right wall
    glColor3f(*top); glVertex3f( 200, 80,-150)
    glColor3f(*top); glVertex3f( 200, 80,  20)
    glColor3f(*bot); glVertex3f( 200, -2,  20)
    glColor3f(*bot); glVertex3f( 200, -2,-150)
    # ceiling
    glColor3f(*top); glVertex3f(-200, 80,  20)
    glColor3f(*top); glVertex3f( 200, 80,  20)
    glColor3f(*top); glVertex3f( 200, 80,-150)
    glColor3f(*top); glVertex3f(-200, 80,-150)
    glEnd()

# ─────────────────────────── GROUND TILES ────────────────────────

def push_ground_tile():
    global ground_far_z
    z_pos = ground_tiles[-1]["z"] - TILE_LEN if ground_tiles else 0.0
    ground_tiles.append({
        "z":           z_pos,
        "col":         ZONES[zone_idx][2],
        "transparent": invisible_gnd,
    })

def draw_ground_tiles():
    for tile in ground_tiles:
        base_col = tile["col"]
        if tile["transparent"] and tile["z"] < -30:
            base_col = (base_col[0] * 0.55, base_col[1] * 0.55, base_col[2] * 0.55)
        z0 = tile["z"]
        z1 = z0 - TILE_LEN
        glColor3f(*base_col)
        glBegin(GL_QUADS)
        glVertex3f(-3.5, 0, z0); glVertex3f( 3.5, 0, z0)
        glVertex3f( 3.5, 0, z1); glVertex3f(-3.5, 0, z1)
        glEnd()
        # Lane dividers
        glColor3f(0.92, 0.92, 0.92)
        for lx in (-1.0, 1.0):
            glBegin(GL_QUADS)
            glVertex3f(lx-0.03, 0.002, z0); glVertex3f(lx+0.03, 0.002, z0)
            glVertex3f(lx+0.03, 0.002, z1); glVertex3f(lx-0.03, 0.002, z1)
            glEnd()

        # Side shoulders so roadside props (trees) look grounded
        shoulder_col = (base_col[0] * 0.82, base_col[1] * 0.82, base_col[2] * 0.82)
        glColor3f(*shoulder_col)
        glBegin(GL_QUADS)
        glVertex3f(-12.0, -0.01, z0); glVertex3f(-3.5, -0.01, z0)
        glVertex3f(-3.5, -0.01, z1); glVertex3f(-12.0, -0.01, z1)
        glEnd()
        glBegin(GL_QUADS)
        glVertex3f(3.5, -0.01, z0); glVertex3f(12.0, -0.01, z0)
        glVertex3f(12.0, -0.01, z1); glVertex3f(3.5, -0.01, z1)
        glEnd()

# ─────────────────────────── BACKGROUND TREES ────────────────────

def draw_background_trees():
    if zone_idx == 3:
        leaf = (0.85, 0.92, 0.98)
    elif zone_idx >= 4:
        leaf = (0.30, 0.15, 0.35)
    else:
        leaf = (0.12, 0.50, 0.08)
    trunk = (0.45, 0.28, 0.10)
    drift = distance % 20.0
    for i in range(8):
        bz = 10.0 - i * 20.0 + drift
        for side in (-1, 1):
            bx = side * (6.5 + (i % 3) * 1.5)
            # Soil mound to better ground the tree on the roadside
            draw_box(bx, 0.1, bz, 2.0, 0.2, 2.0, (0.20, 0.15, 0.08))
            # Taller trunk so the leaves aren't at road height
            draw_box(bx, 2.5, bz, 0.8, 5.0, 0.8, trunk)
            # Tiered leaves for a fuller tree
            draw_sphere(bx, 5.5, bz, 2.2, leaf)
            draw_sphere(bx, 7.0, bz, 1.6, leaf)

# ─────────────────────────── WEATHER ─────────────────────────────

def init_weather():
    global weather
    weather = []
    rain = ZONES[zone_idx][5]
    snow = ZONES[zone_idx][6]
    n = 130 if (rain or snow) else 0
    for _ in range(n):
        weather.append({
            "x":  random.uniform(-5, 5),
            "y":  random.uniform(0.5, 9),
            "z":  random.uniform(-2, -30),
            "vx": random.uniform(-0.3, 0.3) if snow else random.uniform(-0.05, 0.05),
            "vy": random.uniform(-0.6, -1.2) if snow else random.uniform(-9, -13),
            "snow": snow,
        })

def update_weather(dt):
    for w in weather:
        w["x"] += w["vx"] * dt
        w["y"] += w["vy"] * dt
        if w["y"] < 0:
            w["x"] = random.uniform(-5, 5)
            w["y"] = random.uniform(7, 10)
            w["z"] = random.uniform(-2, -30)

def draw_weather():
    for w in weather:
        if w["snow"]:
            glColor3f(0.95, 0.97, 1.0)
            glPushMatrix()
            glTranslatef(w["x"], w["y"], w["z"])
            glutSolidSphere(0.04, 5, 4)
            glPopMatrix()
        else:
            glColor3f(0.55, 0.72, 0.9)
            glBegin(GL_QUADS)
            glVertex3f(w["x"] - 0.015, w["y"],      w["z"])
            glVertex3f(w["x"] + 0.015, w["y"],      w["z"])
            glVertex3f(w["x"] + 0.005, w["y"]+0.4,  w["z"])
            glVertex3f(w["x"] - 0.005, w["y"]+0.4,  w["z"])
            glEnd()

# ─────────────────────────── PARTICLES ───────────────────────────

def spawn_particles(x, y, z, col, n=8):
    for _ in range(n):
        a  = random.uniform(0, math.tau)
        sp = random.uniform(1.5, 5.0)
        particles.append({
            "x": x, "y": y, "z": z,
            "vx": math.cos(a)*sp,
            "vy": random.uniform(2, 6),
            "vz": math.sin(a)*sp,
            "life": random.uniform(0.4, 0.9),
            "col": col,
            "r":   random.uniform(0.05, 0.14),
        })

def update_particles(dt):
    for p in particles:
        p["x"] += p["vx"]*dt
        p["y"] += p["vy"]*dt
        p["z"] += p["vz"]*dt
        p["vy"] -= 12*dt
        p["life"] -= dt

def draw_particles():
    for p in particles:
        if p["life"] <= 0: continue
        t = clamp(p["life"]*2, 0, 1)
        glColor3f(p["col"][0] * t, p["col"][1] * t, p["col"][2] * t)
        glPushMatrix()
        glTranslatef(p["x"], p["y"], p["z"])
        glutSolidSphere(p["r"], 6, 4)
        glPopMatrix()

# ─────────────────────────── OBJECT SIZES / CENTRE-Y ─────────────

OBJ_SIZES = {
    "carrot":    (0.25, 0.50, 0.25),
    "potion":    (0.22, 0.40, 0.22),
    "rock":      (0.55, 0.55, 0.55),
    "fence":     (0.40, 0.80, 0.20),
    "cactus":    (0.30, 0.90, 0.30),
    "bird_low":  (0.50, 0.30, 0.50),
    "bird_high": (0.50, 0.30, 0.50),
    "spring":    (0.60, 0.20, 0.60),
    "log":       (0.55, 0.40, 0.55),
}
OBJ_CY_OVERRIDE = {"bird_high": 2.5, "bird_low": 1.3, "spring": 0.2}

def obj_cy(o):
    return OBJ_CY_OVERRIDE.get(o["kind"], OBJ_SIZES[o["kind"]][1])

# ─────────────────────────── SPAWN OBJECT ────────────────────────

def spawn_object():
    lane = random.randint(0, 2)
    r    = random.random()
    if   r < 0.28: kind = "carrot"
    elif r < 0.40: kind = "potion"
    elif r < 0.52: kind = "bird_low"
    elif r < 0.60: kind = "bird_high"
    elif r < 0.68: kind = "spring"
    elif r < 0.76: kind = "rock"
    elif r < 0.84: kind = "fence"
    elif r < 0.92: kind = "cactus"
    else:           kind = "log"
    objects.append({
        "lane": lane, "x": LANES[lane],
        "z": -32.0, "kind": kind,
        "alive": True, "anim": 0.0,
    })

# ─────────────────────────── DRAW OBJECT ─────────────────────────

def draw_object(o):
    k = o["kind"]
    x, z = o["x"], o["z"]
    cy   = obj_cy(o)
    bob  = math.sin(o["anim"] * 3) * 0.08
    a    = o["anim"]

    if k == "carrot":
        draw_box(x, cy+bob, z, 0.22, 0.55, 0.22, (1.0, 0.40, 0.0))
        draw_box(x, cy+bob+0.38, z, 0.10, 0.22, 0.10, (0.20, 0.80, 0.10))
        draw_box(x-0.08, cy+bob+0.36, z, 0.06, 0.18, 0.06, (0.20, 0.80, 0.10))
        draw_box(x+0.08, cy+bob+0.36, z, 0.06, 0.18, 0.06, (0.20, 0.80, 0.10))

    elif k == "potion":
        draw_box(x, cy+bob, z, 0.22, 0.38, 0.22, (0.0, 0.75, 1.0))
        draw_box(x, cy+bob+0.30, z, 0.12, 0.14, 0.12, (0.0, 0.55, 0.80))
        draw_box(x, cy+bob+0.44, z, 0.10, 0.08, 0.10, (0.75, 0.55, 0.30))
        for i in range(4):
            ang = a*2 + i*math.pi/2
            draw_sphere(x+math.cos(ang)*0.28, cy+bob+0.10,
                        z+math.sin(ang)*0.28, 0.06, (0.6, 1.0, 1.0))

    elif k == "rock":
        draw_sphere(x, cy, z, 0.55, (0.50, 0.50, 0.50))
        draw_sphere(x-0.22, cy+0.18, z+0.10, 0.28, (0.42, 0.42, 0.42))

    elif k == "fence":
        draw_box(x-0.35, cy, z, 0.10, 0.80, 0.10, (0.60, 0.38, 0.15))
        draw_box(x+0.35, cy, z, 0.10, 0.80, 0.10, (0.60, 0.38, 0.15))
        draw_box(x, cy+0.20, z, 0.80, 0.08, 0.08, (0.70, 0.45, 0.20))
        draw_box(x, cy-0.20, z, 0.80, 0.08, 0.08, (0.70, 0.45, 0.20))

    elif k == "cactus":
        draw_box(x, cy, z, 0.22, 0.90, 0.22, (0.15, 0.60, 0.15))
        draw_box(x-0.30, cy+0.25, z, 0.22, 0.12, 0.16, (0.15, 0.60, 0.15))
        draw_box(x+0.30, cy+0.10, z, 0.22, 0.12, 0.16, (0.15, 0.60, 0.15))

    elif k in ("bird_low", "bird_high"):
        col  = (0.75, 0.20, 0.20)
        flap = math.sin(a*6)*0.4
        draw_box(x, cy, z, 0.42, 0.26, 0.55, col)
        draw_sphere(x, cy+0.22, z-0.22, 0.18, col)
        draw_box(x, cy+0.20, z-0.42, 0.06, 0.06, 0.12, (1.0, 0.70, 0.0))
        draw_box(x-0.50, cy+flap*0.3, z, 0.30, 0.08, 0.35, (0.85, 0.30, 0.30))
        draw_box(x+0.50, cy-flap*0.3, z, 0.30, 0.08, 0.35, (0.85, 0.30, 0.30))

    elif k == "spring":
        draw_box(x, 0.10, z, 1.10, 0.12, 1.10, (0.20, 0.20, 0.20))
        for i in range(4):
            draw_box(x, 0.14+i*0.06, z, 0.55, 0.04, 0.55, (1.0, 0.30, 0.65))
        draw_box(x, 0.42, z, 0.16, 0.16, 0.16, (1.0, 1.0, 0.0))

    elif k == "log":
        draw_cylinder(x, 0.0, z-0.45, 0.45, 0.90, (0.55, 0.32, 0.10))
        draw_sphere(x, 0.45, z-0.45, 0.46, (0.65, 0.40, 0.15))

# ─────────────────────────── DRAW BUNNY ──────────────────────────

def draw_bunny():
    p  = player
    x  = p["x"]
    y  = p["y"]
    a  = p["hop_anim"]
    bt = p["blink_t"]

    # Invincibility blink
    if p["invincible"] and int(bt*10) % 2 == 0:
        return

    has_pu = p["invincible"] or p["double_jump"]
    if has_pu:
        t = math.sin(bt*8)*0.5 + 0.5
        body_col = (0.4+t*0.3, 0.90, 1.0)
    else:
        body_col = (0.96, 0.96, 0.92)

    sy   = 1.0 + (math.sin(a)*0.18 if p["jumping"] else 0.0)
    duck = p["ducking"]
    
    # Resize bunny to run horizontally like a rabbit (4 feet on the ground)
    bh   = 0.25 if duck else 0.35
    bw   = 0.40
    bd   = 0.65
    b_cy = y + (0.15 if duck else 0.25)

    # Body
    glColor3f(*body_col)
    glPushMatrix()
    glTranslatef(x, b_cy, 0)
    glScalef(bw, bh*sy, bd)
    glutSolidCube(1.0)
    glPopMatrix()

    if not duck:
        # Head (forward, lowered so it's not standing upright)
        draw_sphere(x, y+0.55, -0.35, 0.22, body_col)
        # Ears (rotated back slightly)
        draw_box(x-0.10, y+0.85, -0.28, 0.06, 0.30, 0.06, body_col)
        draw_box(x+0.10, y+0.85, -0.28, 0.06, 0.30, 0.06, body_col)
        draw_box(x-0.10, y+0.85, -0.28, 0.04, 0.24, 0.04, (1.0, 0.75, 0.82))
        draw_box(x+0.10, y+0.85, -0.28, 0.04, 0.24, 0.04, (1.0, 0.75, 0.82))
        # Eyes
        draw_sphere(x-0.10, y+0.60, -0.52, 0.04, (0.1, 0.1, 0.1))
        draw_sphere(x+0.10, y+0.60, -0.52, 0.04, (0.1, 0.1, 0.1))
        # Nose
        draw_sphere(x, y+0.52, -0.55, 0.03, (1.0, 0.5, 0.6))
        # Tail
        draw_sphere(x, y+0.35, 0.35, 0.12, (1.0, 1.0, 1.0))
        
        # Legs (four-leg hop animation)
        lp = math.sin(a)
        # rear legs (under tail)
        draw_box(x-0.14, y+0.10+lp*0.06, 0.20, 0.12, 0.20, 0.12, body_col)
        draw_box(x+0.14, y+0.10-lp*0.06, 0.20, 0.12, 0.20, 0.12, body_col)
        # front legs (under head)
        draw_box(x-0.14, y+0.10-lp*0.06, -0.20, 0.10, 0.18, 0.10, body_col)
        draw_box(x+0.14, y+0.10+lp*0.06, -0.20, 0.10, 0.18, 0.10, body_col)

    # Kick flash
    if p["kick_timer"] > 0.15:
        kt = p["kick_timer"]
        pulse = clamp(kt * 2.0, 0, 1)
        glColor3f(1.0, 1.0, 0.2 + 0.8 * pulse)
        glPushMatrix()
        glTranslatef(x+0.6, y+0.4, -0.5)
        glutSolidSphere(0.35+kt*0.2, 8, 6)
        glPopMatrix()

# ─────────────────────────── CAMERA (same as template) ───────────

def setupCamera():
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(fovY, WIN_W/WIN_H, 0.1, 500)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    t  = time.time()
    sx = math.sin(t*40) * screen_shake * shake_amp
    sy = math.cos(t*35) * screen_shake * shake_amp

    gluLookAt(
        sx,     4.5+sy, 9.5,   # Camera position
        0,      1.5,   -8,     # Look-at target
        0,      1,      0      # Up vector
    )

# ─────────────────────────── HUD ─────────────────────────────────

def draw_hud():
    sp = game_speed / BASE_SPEED

    if game_state == "playing":
        draw_text(16, WIN_H-28,  f"Distance : {int(distance)} m",              1.0, 1.0, 0.4)
        draw_text(16, WIN_H-54,  f"Carrots  : {carrots}",                       1.0, 0.6, 0.2)
        draw_text(16, WIN_H-80,  f"Speed    : {sp:.1f}x",                       0.4, 1.0, 0.4)
        draw_text(16, WIN_H-106, f"Zone {zone_idx+1}   : {ZONES[zone_idx][4]}", 0.7, 0.7, 1.0)

        if player["invincible"] or player["double_jump"]:
            t = max(player["inv_timer"], player["dj_timer"])
            lbl = []
            if player["double_jump"]: lbl.append("DBL JUMP")
            if player["invincible"]:  lbl.append("SHIELD")
            draw_text(16, WIN_H-136, f"  {' + '.join(lbl)}  {t:.1f}s", 0.2, 1.0, 1.0)
            draw_screen_rect(16, WIN_H-152, 180, 10, 0.1, 0.1, 0.1, 0.6)
            draw_screen_rect(16, WIN_H-152, int(180*clamp(t/12,0,1)), 10, 0.0, 0.85, 1.0, 0.9)

        if invisible_gnd:
            blink = 0.55 + 0.45*math.sin(time.time()*5)
            draw_text(WIN_W//2-110, WIN_H-30, "! INVISIBLE GROUND !", blink, 0.2, 0.2)

        draw_text(WIN_W-340, 14, "A/D:lane  W:jump  S:duck  F:kick", 0.5, 0.5, 0.5)

    elif game_state == "menu":
        cx = WIN_W//2 - 160
        draw_text(cx+10, WIN_H//2+130, "BUNNY HOP RUNNER  3D",           1.0, 0.9, 0.1, GLUT_BITMAP_HELVETICA_18) # type: ignore
        draw_text(cx+30, WIN_H//2+ 90, "Press ENTER to Start",           0.7, 0.9, 1.0)
        draw_text(cx,    WIN_H//2+ 55, "A / LEFT   -- change lane",      0.8, 0.8, 0.8)
        draw_text(cx,    WIN_H//2+ 28, "W / UP     -- jump",             0.8, 0.8, 0.8)
        draw_text(cx,    WIN_H//2+  2, "S / DOWN   -- duck / slide",     0.8, 0.8, 0.8)
        draw_text(cx,    WIN_H//2- 24, "F          -- kick attack",      0.8, 0.8, 0.8)
        draw_text(cx+10, WIN_H//2- 60, "Collect potions for:",           0.2, 0.9, 1.0)
        draw_text(cx+10, WIN_H//2- 84, "  Double Jump + Shield (12 s)",  0.2, 0.9, 1.0)
        draw_text(cx+10, WIN_H//2-108, "Land on SPRING for mega jump!",  1.0, 0.4, 0.8)

    elif game_state == "dead":
        cx = WIN_W//2 - 160
        draw_text(cx+40, WIN_H//2+100, "GAME OVER",                      1.0, 0.2, 0.2, GLUT_BITMAP_HELVETICA_18) # type: ignore
        draw_text(cx+20, WIN_H//2+ 60, f"Distance : {int(distance)} m",  1.0, 0.9, 0.4)
        draw_text(cx+20, WIN_H//2+ 32, f"Carrots  : {carrots}",          1.0, 0.6, 0.2)
        draw_text(cx+20, WIN_H//2+  4, f"Zone     : {zone_idx+1}  {ZONES[zone_idx][4]}", 0.7,0.7,1.0)
        draw_text(cx+20, WIN_H//2- 34, "Press ENTER to Retry",           0.4, 1.0, 0.4)
        draw_text(cx+20, WIN_H//2- 60, "Press ESC   to Quit",            0.6, 0.6, 0.6)

# ─────────────────────────── GAME LOGIC ──────────────────────────

def reset_game():
    global distance, carrots, game_speed, zone_idx, last_zone
    global invisible_gnd, screen_shake, shake_amp
    global spawn_timer, ground_far_z
    distance = 0.0; carrots = 0; game_speed = BASE_SPEED
    zone_idx = 0; last_zone = 0
    invisible_gnd = False; screen_shake = 0.0; shake_amp = 0.0
    spawn_timer = 0.0; ground_far_z = 0.0
    objects.clear(); particles.clear()
    ground_tiles.clear()
    player.update({
        "lane": 1, "x": 0.0, "y": 0.0, "vy": 0.0,
        "jumping": False, "jump_count": 0,
        "ducking": False, "duck_timer": 0.0,
        "invincible": False, "inv_timer": 0.0,
        "double_jump": False, "dj_timer": 0.0,
        "kick_timer": 0.0, "hop_anim": 0.0, "blink_t": 0.0,
    })
    for _ in range(14):
        push_ground_tile()
    init_weather()

def do_jump():
    global screen_shake, shake_amp
    p = player
    if not p["jumping"]:
        p["jumping"] = True; p["vy"] = JUMP_VEL; p["jump_count"] = 1
        p["ducking"] = False; p["duck_timer"] = 0
    elif p["double_jump"] and p["jump_count"] < 2:
        p["vy"] = JUMP_VEL * 0.9; p["jump_count"] = 2
        screen_shake = 0.25; shake_amp = 0.07
        spawn_particles(p["x"], p["y"]+0.5, 0, (0.0, 1.0, 1.0), 8)

def do_duck():
    p = player
    if p["jumping"]: p["vy"] -= 6; return
    p["ducking"] = True; p["duck_timer"] = 0.75

def do_kick():
    global screen_shake, shake_amp
    p = player
    if p["kick_timer"] > 0: return
    p["kick_timer"] = 0.45
    screen_shake = 0.3; shake_amp = 0.09
    hit = False
    for o in objects:
        if o["kind"] in ("carrot","potion","spring"): continue
        if (abs(o["x"]-p["x"]) < 1.4 and -5 < o["z"] < 1.0
                and abs(obj_cy(o)-p["y"]) < 2.0):
            o["alive"] = False
            spawn_particles(o["x"], obj_cy(o), o["z"], (1.0,0.85,0.1), 10)
            hit = True
    if hit:
        screen_shake = 0.45; shake_amp = 0.14

def collides_with_player(o):
    hw, hh, hd = OBJ_SIZES[o["kind"]]
    cy   = obj_cy(o)
    p    = player
    phh  = 0.28 if p["ducking"] else 0.50
    p_cy = p["y"] + phh
    if abs(o["x"] - p["x"]) > hw  + 0.28: return False
    if abs(cy     - p_cy)   > hh  + phh:  return False
    if abs(o["z"] - 0.0)    > hd  + 0.6:  return False
    return True

def collect_object(o):
    global carrots, screen_shake, shake_amp
    if o["kind"] == "carrot":
        carrots += 1
        spawn_particles(o["x"], obj_cy(o), o["z"], (1.0, 0.5, 0.0), 8)
    elif o["kind"] == "potion":
        player["invincible"] = True; player["inv_timer"]  = 12.0
        player["double_jump"]= True; player["dj_timer"]   = 12.0
        spawn_particles(o["x"], obj_cy(o), o["z"], (0.0,0.9,1.0), 14)
    elif o["kind"] == "spring":
        player["jumping"] = True; player["vy"] = SPRING_VEL; player["jump_count"] = 1
        screen_shake = 0.35; shake_amp = 0.12
        spawn_particles(o["x"], 0.4, o["z"], (1.0,0.3,0.8), 12)

def check_collisions():
    global game_state
    for o in objects:
        if not o["alive"]: continue
        if collides_with_player(o):
            if o["kind"] in ("carrot","potion","spring"):
                collect_object(o); o["alive"] = False
            else:
                if player["invincible"]:
                    o["alive"] = False
                    spawn_particles(o["x"], obj_cy(o), o["z"], (0.0,1.0,1.0), 8)
                else:
                    game_state = "dead"

def set_zone(idx):
    global zone_idx
    idx = min(idx, len(ZONES)-1)
    if idx == zone_idx: return
    zone_idx = idx
    for tile in ground_tiles:
        tile["col"] = ZONES[zone_idx][2]
    init_weather()

def update_game(dt):
    global distance, game_speed, last_zone
    global invisible_gnd, screen_shake, spawn_timer

    game_speed = BASE_SPEED + distance * SPEED_INC
    distance  += game_speed * dt

    km = int(distance / ZONE_DIST)
    if km != last_zone:
        last_zone = km
        set_zone(km % len(ZONES))

    # Keep road visible for gameplay clarity
    invisible_gnd = False

    p = player
    p["x"] = lerp(p["x"], LANES[p["lane"]], 0.18)

    if p["jumping"]:
        p["y"]  += p["vy"] * dt
        p["vy"] -= GRAVITY * dt
        if p["y"] <= 0.0:
            p["y"] = 0.0; p["jumping"] = False
            p["vy"] = 0.0; p["jump_count"] = 0

    if p["ducking"]:
        p["duck_timer"] -= dt
        if p["duck_timer"] <= 0: p["ducking"] = False

    if p["invincible"]:
        p["inv_timer"] -= dt
        if p["inv_timer"] <= 0: p["invincible"] = False
    if p["double_jump"]:
        p["dj_timer"] -= dt
        if p["dj_timer"] <= 0: p["double_jump"] = False

    if p["kick_timer"] > 0: p["kick_timer"] -= dt
    p["hop_anim"] += dt * (6 if p["jumping"] else 4)
    p["blink_t"]  += dt

    spawn_timer -= dt
    if spawn_timer <= 0:
        spawn_object()
        spawn_timer = max(0.50, 1.6 - game_speed*0.055)

    for o in objects:
        o["z"]    += game_speed * dt
        o["anim"] += dt

    check_collisions()

    for o in objects:
        if o["z"] > 4.0: o["alive"] = False
    objects[:] = [o for o in objects if o["alive"]]

    for tile in ground_tiles:
        tile["z"]           += game_speed * dt
        tile["col"]          = ZONES[zone_idx][2]
        tile["transparent"]  = invisible_gnd

    # Keep deterministic ordering even with frame spikes
    ground_tiles.sort(key=lambda t: t["z"], reverse=True)

    while ground_tiles and ground_tiles[0]["z"] > TILE_LEN:
        ground_tiles.pop(0)
    while not ground_tiles or ground_tiles[-1]["z"] > -260:
        push_ground_tile()

    update_particles(dt)
    update_weather(dt)

    if screen_shake > 0:
        screen_shake -= dt * 2

# ─────────────────────────── INPUT (matches template exactly) ─────

def keyboardListener(key, x, y):
    global game_state
    if key == b'\x1b':
        os._exit(0)
    if game_state == "menu" and key in (b'\r', b'\n', b' '):
        reset_game(); game_state = "playing"
    elif game_state == "dead" and key in (b'\r', b'\n', b' '):
        reset_game(); game_state = "playing"
    elif game_state == "playing":
        if key in (b'a', b'A', b'j', b'J'):
            player["lane"] = clamp(player["lane"]-1, 0, 2)
        elif key in (b'd', b'D', b'l', b'L'):
            player["lane"] = clamp(player["lane"]+1, 0, 2)
        elif key in (b'w', b'W', b'i', b'I', b' '):
            do_jump()
        elif key in (b's', b'S', b'k', b'K'):
            do_duck()
        elif key in (b'f', b'F'):
            do_kick()
        elif key in (b'r', b'R'):
            reset_game()
    glutPostRedisplay()

def specialKeyListener(key, x, y):
    if game_state != "playing": return
    if key == GLUT_KEY_LEFT:  player["lane"] = clamp(player["lane"]-1, 0, 2)
    if key == GLUT_KEY_RIGHT: player["lane"] = clamp(player["lane"]+1, 0, 2)
    if key == GLUT_KEY_UP:    do_jump()
    if key == GLUT_KEY_DOWN:  do_duck()

def mouseListener(button, state, x, y):
    pass   # reserved

# ─────────────────────────── IDLE (same as template) ─────────────

def idle():
    global last_time
    now = time.time()
    dt  = min(now - last_time, 0.05)
    last_time = now
    if game_state == "playing":
        update_game(dt)
    glutPostRedisplay()

# ─────────────────────────── DISPLAY (same as template) ──────────

def showScreen():
    fog = ZONES[zone_idx][3]
    glClearColor(*fog, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()
    glViewport(0, 0, WIN_W, WIN_H)

    setupCamera()

    draw_skybox()
    draw_background_trees()
    draw_ground_tiles()

    for o in objects:
        if o["alive"]: draw_object(o)

    draw_bunny()
    draw_particles()
    draw_weather()

    # Dark vignette for later zones (blurry-vision effect)
    if zone_idx >= 2:
        shade = min(0.35, (zone_idx-1)*0.10)
        draw_screen_rect(0, 0, WIN_W, WIN_H, shade * 0.2, shade * 0.2, shade * 0.25)

    draw_hud()
    glutSwapBuffers()

# ─────────────────────────── MAIN (matches template exactly) ─────

def main():
    global last_time
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(WIN_W, WIN_H)
    glutInitWindowPosition(0, 0)
    glutCreateWindow(b"Bunny Hop Runner 3D")

    # Seed ground tiles for menu backdrop
    for _ in range(14):
        push_ground_tile()
    init_weather()

    last_time = time.time()

    glutDisplayFunc(showScreen)
    glutKeyboardFunc(keyboardListener)
    glutSpecialFunc(specialKeyListener)
    glutMouseFunc(mouseListener)
    glutIdleFunc(idle)

    glutMainLoop()

if __name__ == "__main__":
    main()