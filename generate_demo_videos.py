"""
generate_demo_videos.py
Creates 10 synthetic demo videos (no internet needed).
Each video demonstrates one or more system features.

Run: python generate_demo_videos.py
Output: demo_videos/ directory (10 × .mp4 files)
"""

import cv2
import numpy as np
import os, math, random

OUT_DIR = "demo_videos"
os.makedirs(OUT_DIR, exist_ok=True)

W, H   = 1280, 720
FPS    = 25
FOUR   = cv2.VideoWriter_fourcc(*"mp4v")

# ── helpers ───────────────────────────────────────────────────────────────────
def writer(name, seconds=10):
    path = os.path.join(OUT_DIR, name)
    return cv2.VideoWriter(path, FOUR, FPS, (W, H)), path

def blank(bg=(20, 20, 30)):
    f = np.full((H, W, 3), bg, dtype=np.uint8)
    # Road markings
    cv2.rectangle(f, (340, 0), (940, H), (35, 35, 45), -1)
    for y in range(0, H, 80):
        cv2.line(f, (638, y), (638, y+40), (200, 200, 80), 3)
    return f

def draw_car(frame, x, y, color=(0,200,0), label="", w=64, h=32):
    x, y = int(x), int(y)
    cv2.rectangle(frame, (x-w//2, y-h//2), (x+w//2, y+h//2), color, -1)
    cv2.rectangle(frame, (x-w//4, y-h//2-8), (x+w//4, y-h//2), (150,200,255), -1)
    cv2.circle(frame, (x-w//3, y+h//2), 6, (30,30,30), -1)
    cv2.circle(frame, (x+w//3, y+h//2), 6, (30,30,30), -1)
    if label:
        cv2.putText(frame, label, (x-20, y-h//2-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255,255,255), 1)

def hud_text(frame, texts):
    overlay = frame.copy()
    cv2.rectangle(overlay, (0,0),(W,36),(10,10,10),-1)
    cv2.addWeighted(overlay,0.7,frame,0.3,0,frame)
    for i, (txt, color) in enumerate(texts):
        cv2.putText(frame, txt, (10+i*280, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)

def zone_lines(frame):
    for y, label, limit in [(240,"highway→main",60),(480,"main→school",30)]:
        cv2.line(frame,(0,y),(W,y),(100,100,100),1)
        cv2.putText(frame,f"{label} | {limit}km/h",(5,y-4),
                    cv2.FONT_HERSHEY_SIMPLEX,0.38,(150,150,150),1)

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 1 — Normal Traffic Flow
# ══════════════════════════════════════════════════════════════════════════════
def v1_normal_flow():
    vw, path = writer("01_normal_traffic_flow.mp4", 10)
    cars = [{"x": random.randint(380,600), "y": random.randint(-200,0),
             "speed": random.uniform(3,6), "color": (random.randint(0,255),
             random.randint(0,255), random.randint(0,255)), "id": i}
            for i in range(6)]
    for frame_n in range(FPS*10):
        f = blank()
        zone_lines(f)
        for c in cars:
            c["y"] += c["speed"]
            if c["y"] > H+60: c["y"] = -60
            draw_car(f, c["x"], c["y"], c["color"], f'#{c["id"]} {c["speed"]*FPS/8:.0f}km/h')
        hud_text(f, [("Vehicles: 6",(0,220,0)),
                     ("Avg Speed: 42 km/h",(0,200,255)),
                     ("01 — Normal Flow",(200,200,200))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 2 — Speeding Violation
# ══════════════════════════════════════════════════════════════════════════════
def v2_speeding():
    vw, path = writer("02_speeding_violation.mp4", 10)
    y = 0.0
    for frame_n in range(FPS*10):
        f = blank()
        zone_lines(f)
        # Normal car
        draw_car(f, 520, (frame_n * 4) % (H+60) - 30, (0,200,0), "#1 48km/h")
        # Speeding car
        y = (frame_n * 18) % (H + 60) - 30
        spd = 18*FPS/8
        color = (0,0,255) if spd > 60 else (0,200,0)
        draw_car(f, 720, y, color, f'#2 {spd:.0f}km/h SPEEDING')
        if spd > 60:
            cv2.putText(f,"⚠ SPEEDING VIOLATION",(420,H-40),
                        cv2.FONT_HERSHEY_SIMPLEX,1.1,(0,0,255),3)
        hud_text(f,[("02 — Speeding Detection",(200,200,200)),
                    ("Limit: 60 km/h",(0,200,255))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 3 — Wrong-Way Detection
# ══════════════════════════════════════════════════════════════════════════════
def v3_wrong_way():
    vw, path = writer("03_wrong_way_detection.mp4", 10)
    for frame_n in range(FPS*10):
        f = blank()
        zone_lines(f)
        # Normal (going down)
        draw_car(f, 500, (frame_n*5)%(H+60)-30, (0,200,0), "#1 correct ↓")
        # Wrong-way (going up)
        wy = H - (frame_n*7)%(H+60)
        draw_car(f, 720, wy, (0,0,255), "#2 WRONG WAY ↑")
        cv2.arrowedLine(f,(720,int(wy)+20),(720,int(wy)-30),(0,0,255),3,tipLength=0.4)
        if frame_n > 20:
            cv2.putText(f,"⚠ WRONG-WAY VEHICLE DETECTED",(320,H-40),
                        cv2.FONT_HERSHEY_SIMPLEX,1.0,(0,0,255),3)
        hud_text(f,[("03 — Wrong-Way Detection",(200,200,200)),
                    ("Allowed direction: DOWN",(0,200,255))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 4 — Congestion Detection
# ══════════════════════════════════════════════════════════════════════════════
def v4_congestion():
    vw, path = writer("04_congestion_detection.mp4", 12)
    positions = [(420+i*55, 200+j*70) for i in range(5) for j in range(4)]
    congestion_start = FPS*4
    for frame_n in range(FPS*12):
        f = blank()
        zone_lines(f)
        congest = frame_n >= congestion_start
        n_cars  = min(int(frame_n / FPS * 3), len(positions))
        for i in range(n_cars):
            x, y = positions[i]
            jitter_x = math.sin(frame_n*0.05+i)*2 if congest else 0
            jitter_y = (frame_n * (0.5 if congest else 4)) % (H+60) - 30
            if not congest:
                jitter_y = y + (frame_n*2)%(H-y+60)
            else:
                jitter_y = positions[i][1] + math.sin(frame_n*0.03+i)*3
            draw_car(f, positions[i][0]+jitter_x, jitter_y if not congest else positions[i][1],
                     (0,100,255) if congest else (0,200,0))
        if congest:
            cv2.rectangle(f,(0,H-36),(W,H),(0,0,180),-1)
            cv2.putText(f,"⚠ CONGESTION DETECTED — Avg Speed < 20 km/h",
                        (20,H-10),cv2.FONT_HERSHEY_SIMPLEX,0.8,(255,255,0),2)
        hud_text(f,[("04 — Congestion Detection",(200,200,200)),
                    (f"Vehicles: {n_cars}",(0,220,0))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 5 — Dwell / Obstruction
# ══════════════════════════════════════════════════════════════════════════════
def v5_dwell():
    vw, path = writer("05_dwell_obstruction.mp4", 12)
    timer_start = FPS*3
    for frame_n in range(FPS*12):
        f = blank()
        zone_lines(f)
        # Moving car
        draw_car(f, 500, (frame_n*5)%(H+60)-30, (0,200,0), "#1 moving")
        # Stationary car
        dwell_sec = max(0, (frame_n - timer_start)/FPS)
        color = (0,0,255) if dwell_sec>5 else (0,200,255)
        draw_car(f, 720, 360, color, f'#2 stopped {dwell_sec:.0f}s')
        if dwell_sec > 5:
            cv2.putText(f,"⚠ OBSTRUCTION — Vehicle Stationary > 30s",
                        (250,H-40),cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,255),2)
        # Timer bar
        pct = min(dwell_sec/30, 1.0)
        cv2.rectangle(f,(700,340),(700+int(100*pct),348),(0,0,255),-1)
        cv2.rectangle(f,(700,340),(800,348),(200,200,200),1)
        hud_text(f,[("05 — Dwell/Obstruction",(200,200,200)),
                    (f"Dwell time: {dwell_sec:.1f}s",(0,200,255))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 6 — Tailgating Detection
# ══════════════════════════════════════════════════════════════════════════════
def v6_tailgating():
    vw, path = writer("06_tailgating_detection.mp4", 10)
    for frame_n in range(FPS*10):
        f = blank()
        zone_lines(f)
        base_y = (frame_n*7)%(H+60) - 30
        # Leader
        draw_car(f, 640, base_y, (0,200,0), "#1 leader 85km/h")
        # Follower too close
        gap    = max(20, 90 - frame_n//5)
        follow_y = base_y + 50 + gap
        color  = (0,0,255) if gap < 60 else (0,200,255)
        draw_car(f, 640, follow_y, color, f'#2 gap:{gap}px')
        if gap < 60:
            cv2.line(f,(640,int(base_y)+16),(640,int(follow_y)-16),(0,0,255),2)
            cv2.putText(f,"⚠ TAILGATING — Following too closely",
                        (310,H-40),cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,255),2)
        hud_text(f,[("06 — Tailgating Detection",(200,200,200)),
                    (f"Gap: {gap} px (min:60)",(0,200,255))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 7 — Multi-Lane Multi-Violation
# ══════════════════════════════════════════════════════════════════════════════
def v7_multi():
    vw, path = writer("07_multi_lane_multi_violation.mp4", 12)
    for frame_n in range(FPS*12):
        f = blank()
        zone_lines(f)
        # Lane 1 — speeding
        y1 = (frame_n*16)%(H+60)-30
        draw_car(f,480,y1,(0,0,255),"#1 SPEEDING 95km/h")
        # Lane 2 — normal
        y2 = (frame_n*5)%(H+60)-30
        draw_car(f,640,y2,(0,200,0),"#2 55km/h OK")
        # Lane 3 — wrong way
        y3 = H-(frame_n*8)%(H+60)
        draw_car(f,800,y3,(200,0,200),"#3 WRONG WAY ↑")
        cv2.arrowedLine(f,(800,int(y3)+20),(800,int(y3)-30),(200,0,200),2,tipLength=0.4)

        cv2.putText(f,"SPEEDING",(430,int(y1)-30),
                    cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,0,255),1)
        if frame_n>15:
            cv2.putText(f,"WRONG WAY",(740,int(y3)-30),
                        cv2.FONT_HERSHEY_SIMPLEX,0.5,(200,0,200),1)
        hud_text(f,[("07 — Multi Violation",(200,200,200)),
                    ("2 violations active",(0,0,255))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 8 — Zone-Aware Speed Limits
# ══════════════════════════════════════════════════════════════════════════════
def v8_zones():
    vw, path = writer("08_zone_aware_speed_limits.mp4", 12)
    for frame_n in range(FPS*12):
        f = blank()
        zone_lines(f)
        y = (frame_n*6)%(H+60)-30
        if y < 240:
            zone, limit, ok = "HIGHWAY", 100, True
        elif y < 480:
            zone, limit, ok = "MAIN ROAD", 60, True
        else:
            zone, limit, ok = "SCHOOL ZONE", 30, False  # always flag in school zone at 72
        speed = 72
        color = (0,200,0) if (speed<=limit) else (0,0,255)
        draw_car(f, 640, y, color, f'#{1} {speed}km/h')
        cv2.putText(f,f"Zone: {zone}  Limit:{limit}km/h  Speed:{speed}km/h",
                    (300,H-40),cv2.FONT_HERSHEY_SIMPLEX,0.75,color,2)
        hud_text(f,[("08 — Zone-Aware Speed",(200,200,200)),
                    (f"Current: {zone} limit {limit}",(0,200,255))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 9 — License Plate OCR Snapshot
# ══════════════════════════════════════════════════════════════════════════════
def v9_plate():
    vw, path = writer("09_license_plate_ocr.mp4", 10)
    plates = ["MH12AB1234","DL8CAF3399","KA05MG7777","TN09ZZ0001"]
    for frame_n in range(FPS*10):
        f = blank()
        zone_lines(f)
        idx   = (frame_n//(FPS*2)) % len(plates)
        plate = plates[idx]
        y     = (frame_n*5)%(H+60)-30
        draw_car(f,640,y,(0,0,255),"Speeding Vehicle")
        # Plate box
        if 0 < y < H:
            cv2.rectangle(f,(600,int(y)+10),(680,int(y)+28),(255,255,255),-1)
            cv2.rectangle(f,(600,int(y)+10),(680,int(y)+28),(0,0,0),1)
            cv2.putText(f,plate,(604,int(y)+24),
                        cv2.FONT_HERSHEY_SIMPLEX,0.38,(0,0,180),1)
        # OCR result panel
        cv2.rectangle(f,(20,60),(420,140),(30,30,30),-1)
        cv2.rectangle(f,(20,60),(420,140),(0,200,255),2)
        cv2.putText(f,"OCR Result:",(30,85),cv2.FONT_HERSHEY_SIMPLEX,0.6,(200,200,200),1)
        cv2.putText(f,plate,(30,120),cv2.FONT_HERSHEY_SIMPLEX,1.2,(0,255,0),2)
        hud_text(f,[("09 — Plate OCR",(200,200,200)),
                    (f"Plate: {plate}",(0,220,0))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO 10 — Full System Demo (all features together)
# ══════════════════════════════════════════════════════════════════════════════
def v10_full():
    vw, path = writer("10_full_system_demo.mp4", 15)
    cars = [
        {"id":1,"x":480,"y":0,  "dy":14,"color":(0,0,255),  "label":"SPEEDING 95km/h"},
        {"id":2,"x":580,"y":200,"dy":5, "color":(0,200,0),  "label":"Normal 52km/h"},
        {"id":3,"x":700,"y":H,  "dy":-8,"color":(200,0,200),"label":"WRONG WAY ↑"},
        {"id":4,"x":800,"y":350,"dy":0, "color":(0,200,255),"label":"STOPPED"},
        {"id":5,"x":640,"y":100,"dy":7, "color":(0,150,255),"label":"Tailgating"},
        {"id":6,"x":640,"y":50, "dy":7, "color":(0,0,255),  "label":"Leader"},
    ]
    violations_log = []
    for frame_n in range(FPS*15):
        f = blank()
        zone_lines(f)

        for c in cars:
            c["y"] = (c["y"] + c["dy"])
            if c["y"] > H + 60: c["y"] = -60
            if c["y"] < -60:    c["y"] = H + 60
            y_disp = c["y"] % (H + 120) - 60
            draw_car(f, c["x"], y_disp, c["color"], f'#{c["id"]} {c["label"]}')

        # Violations ticker
        viol_types = ["SPEEDING","WRONG-WAY","OBSTRUCTION","TAILGATING"]
        if frame_n % 40 == 0:
            violations_log.append(
                f"[{frame_n//FPS:02d}s] {random.choice(viol_types)} — "
                f"Plate: MH{random.randint(10,99)}AB{random.randint(1000,9999)}"
            )
        # Show last 4
        for i, v in enumerate(violations_log[-4:]):
            cv2.putText(f, v, (10, H-120+i*25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0,200,255), 1)

        cv2.rectangle(f,(0,H-36),(W,H),(20,20,80),-1)
        cv2.putText(f,f"LIVE — {len(violations_log)} violations logged | "
                      f"Challans generated automatically",
                    (20,H-10),cv2.FONT_HERSHEY_SIMPLEX,0.65,(255,220,0),2)

        hud_text(f,[("10 — Full System Demo",(200,200,200)),
                    (f"Active tracks: 6  |  Violations: {len(violations_log)}",(0,0,255))])
        vw.write(f)
    vw.release(); print(f"  ✓ {path}")


# ── Run all ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating 10 demo videos …")
    v1_normal_flow()
    v2_speeding()
    v3_wrong_way()
    v4_congestion()
    v5_dwell()
    v6_tailgating()
    v7_multi()
    v8_zones()
    v9_plate()
    v10_full()
    print(f"\nAll done! Videos saved to: {OUT_DIR}/")
    print("Test any video: python main.py --source demo_videos/02_speeding_violation.mp4")
