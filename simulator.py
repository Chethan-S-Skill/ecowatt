import sys
import time
import math
import random
from datetime import datetime
import requests

from config import settings

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api/readings"

BUILDINGS = [
    {"name": "Academic Block", "base": 180.0, "peak": 350.0, "is_24h": False},
    {"name": "Computer Labs", "base": 160.0, "peak": 280.0, "is_24h": False},
    {"name": "Library", "base": 110.0, "peak": 200.0, "is_24h": False},
    {"name": "Hostel Block", "base": 240.0, "peak": 400.0, "is_24h": True},
    {"name": "Cafeteria", "base": 95.0, "peak": 180.0, "is_24h": True},
    {"name": "Admin Block", "base": 75.0, "peak": 220.0, "is_24h": False},
    {"name": "Outdoor Lighting", "base": 1.0, "peak": 85.0, "is_24h": False},
]

def generate_live_reading(b: dict, now: datetime) -> float:
    hour = now.hour
    is_weekend = now.weekday() in [5, 6]
    name = b["name"]

    if name == "Outdoor Lighting":
        if hour >= 18 or hour <= 6:
            val = 80.0 + random.uniform(-1.5, 1.5)
        elif 7 <= hour <= 8:
            val = 75.0 + random.uniform(-2.0, 2.0)  # Planted daylight anomaly!
        else:
            val = 1.0 + random.uniform(0.0, 0.4)
    elif name == "Computer Labs":
        # Continues night baseload waste
        if hour >= 22 or hour <= 4:
            val = 160.0 + random.uniform(-4.0, 4.0)
        else:
            val = 210.0 + random.uniform(-6.0, 6.0)
    elif name == "Academic Block":
        if is_weekend and (9 <= hour <= 16):
            val = 220.0 + random.uniform(-8.0, 8.0)
        elif is_weekend or (hour >= 21 or hour <= 5):
            val = 50.0 + random.uniform(-3.0, 3.0)
        else:
            val = 240.0 + random.uniform(-10.0, 10.0)
    else:
        # Generic diurnal curve
        day_frac = max(0.0, math.sin((hour - 6) * math.pi / 12)) if (6 <= hour <= 20) else 0.0
        val = b["base"] + (b["peak"] - b["base"]) * (0.3 + 0.6 * day_frac) + random.uniform(-5.0, 5.0)

    return max(0.5, round(val, 2))

def run_simulator(interval: int = 5):
    print("==================================================")
    print(" EcoWatt AI - Campus Meter Telemetry Simulator")
    print(f" Target: {API_URL}")
    print(f" Interval: Every {interval} seconds")
    print(f" Meter Key: {settings.METER_API_KEY[:8]}...")
    print(" Press Ctrl+C to terminate.")
    print("==================================================")

    step = 0
    headers = {
        "X-Meter-Key": settings.METER_API_KEY,
        "Content-Type": "application/json"
    }

    while True:
        step += 1
        now = datetime.utcnow()
        now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

        payload = []
        summary_items = []
        for b in BUILDINGS:
            kwh = generate_live_reading(b, now)
            payload.append({
                "building": b["name"],
                "timestamp": now_str,
                "kwh": kwh
            })
            summary_items.append(f"{b['name'][:6]}: {kwh:.0f}kW")

        try:
            resp = requests.post(
                API_URL,
                json=payload,
                headers=headers,
                timeout=4.0
            )
            if resp.status_code == 200:
                print(f"[#{step:04d} {now.strftime('%H:%M:%S')}] Pushed 7 meters -> {' | '.join(summary_items[:3])}...")
            else:
                print(f"[WARN] HTTP {resp.status_code}: {resp.text}")
        except requests.exceptions.ConnectionError:
            print(f"[WAIT] Waiting for EcoWatt server at {BASE_URL} (retrying in {interval}s)...")
        except Exception as e:
            print(f"[ERROR] Telemetry push error: {e}")

        time.sleep(interval)

if __name__ == "__main__":
    run_simulator(interval=5)
