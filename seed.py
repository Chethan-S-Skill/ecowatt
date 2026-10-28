import random
import math
from datetime import datetime, timedelta
import numpy as np
from sqlalchemy.orm import Session

from database import engine, Base, SessionLocal
import models
from config import settings
from auth import get_password_hash
from services.analytics import run_analytics_for_buildings

import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def seed_database():
    print("[*] EcoWatt AI - Initializing & Seeding Database...")
    # 1. Create tables
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    # Clear existing data for clean demo seed
    db.query(models.Anomaly).delete()
    db.query(models.Recommendation).delete()
    db.query(models.MeterReading).delete()
    db.query(models.Building).delete()
    db.query(models.User).delete()
    db.query(models.Weather).delete()
    db.query(models.Setting).delete()
    db.commit()

    # 2. Seed Users
    admin_user = models.User(
        email=settings.ADMIN_EMAIL,
        password_hash=get_password_hash(settings.ADMIN_PASSWORD),
        role="admin"
    )
    viewer_user = models.User(
        email=settings.VIEWER_EMAIL,
        password_hash=get_password_hash(settings.VIEWER_PASSWORD),
        role="viewer"
    )
    db.add_all([admin_user, viewer_user])
    print(f"[+] Seeded Admin ({settings.ADMIN_EMAIL}) and Viewer ({settings.VIEWER_EMAIL})")

    # 3. Seed Settings
    db.add_all([
        models.Setting(key="tariff_inr", value=str(settings.DEFAULT_TARIFF_INR)),
        models.Setting(key="emission_factor", value=str(settings.DEFAULT_EMISSION_FACTOR)),
        models.Setting(key="ml_enabled", value="true")
    ])
    print(f"[+] Seeded Settings: Tariff=INR {settings.DEFAULT_TARIFF_INR}/kWh, Emission={settings.DEFAULT_EMISSION_FACTOR} kg CO2/kWh")

    # 4. Seed 7 Campus Buildings
    buildings_meta = [
        {"name": "Academic Block", "type": "academic", "peak_kw": 350.0, "is_24h": False, "idle_pct": 0.15},
        {"name": "Computer Labs", "type": "lab", "peak_kw": 280.0, "is_24h": False, "idle_pct": 0.15},
        {"name": "Library", "type": "library", "peak_kw": 200.0, "is_24h": False, "idle_pct": 0.15},
        {"name": "Hostel Block", "type": "hostel", "peak_kw": 400.0, "is_24h": True, "idle_pct": 0.20},
        {"name": "Cafeteria", "type": "cafeteria", "peak_kw": 180.0, "is_24h": True, "idle_pct": 0.20},
        {"name": "Admin Block", "type": "admin", "peak_kw": 220.0, "is_24h": False, "idle_pct": 0.15},
        {"name": "Outdoor Lighting", "type": "lighting", "peak_kw": 85.0, "is_24h": False, "idle_pct": 0.05},
    ]

    building_objs = {}
    for b_data in buildings_meta:
        b = models.Building(**b_data)
        db.add(b)
        db.flush()
        building_objs[b.name] = b
    print(f"[+] Seeded 7 Campus Buildings")

    # 5. Fixed Random Seed for 28 Days Simulation
    np.random.seed(42)
    random.seed(42)

    # 28 days of hourly readings up to current hour
    end_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    total_hours = 28 * 24
    start_time = end_time - timedelta(hours=total_hours - 1)

    readings_to_add = []
    weather_to_add = []

    # Pre-generate weather for 28 days: diurnal cycle 20°C at 5AM to 34°C at 2PM
    current_ts = start_time
    for h in range(total_hours):
        hour = current_ts.hour
        # Diurnal temperature curve
        diurnal = math.sin((hour - 8) * math.pi / 12)
        temp_c = 26.0 + 7.0 * diurnal + np.random.normal(0, 0.8)
        weather_to_add.append(models.Weather(ts=current_ts, temp_c=round(temp_c, 1)))
        current_ts += timedelta(hours=1)
    db.add_all(weather_to_add)
    db.flush()
    print("[+] Seeded 28 days of hourly campus weather records (Open-Meteo cache)")

    # 6. Generate Readings for each building with planted anomalies
    spike_target_time = start_time + timedelta(days=16, hours=14) # Tuesday 14:00

    for b_name, b in building_objs.items():
        peak = b.peak_kw
        idle_target = b.idle_pct * peak
        current_ts = start_time

        for h in range(total_hours):
            hour = current_ts.hour
            weekday = current_ts.weekday() # 0=Mon ... 6=Sun
            is_weekend = weekday in [5, 6]

            # Base diurnal profile
            day_fraction = math.sin((hour - 6) * math.pi / 12) if (6 <= hour <= 20) else 0.0
            day_fraction = max(0.0, day_fraction)

            # Planted patterns per building
            if b_name == "Computer Labs":
                # Plant: Labs never switch off at night!
                # Draws ~150-170 kW even from 22:00 to 05:00 (idle target is 42 kW)
                if hour >= 22 or hour <= 4:
                    kwh = 160.0 + np.random.normal(0, 4.0)
                else:
                    kwh = 190.0 + (peak - 190.0) * day_fraction + np.random.normal(0, 6.0)

            elif b_name == "Academic Block":
                # Plant: Runs on weekends (09:00 - 16:59) at full occupancy load
                if is_weekend and (9 <= hour <= 16):
                    kwh = 220.0 + np.random.normal(0, 8.0)
                elif is_weekend or (hour >= 21 or hour <= 5):
                    kwh = idle_target * 0.85 + np.random.normal(0, 2.0)
                else:
                    kwh = idle_target + (peak - idle_target) * (0.4 + 0.5 * day_fraction) + np.random.normal(0, 7.0)

            elif b_name == "Outdoor Lighting":
                # Plant: Outdoor lights left on after sunrise (07:00-08:59 still drawing ~75 kW)
                if hour >= 18 or hour <= 6:
                    kwh = 80.0 + np.random.normal(0, 1.5)
                elif 7 <= hour <= 8:
                    kwh = 75.0 + np.random.normal(0, 2.0)  # Planted daylight waste!
                else:
                    kwh = 1.0 + np.random.normal(0, 0.3)

            elif b_name == "Admin Block":
                # Normal office schedule (09:00-18:00 weekdays), low night
                if (not is_weekend) and (8 <= hour <= 18):
                    kwh = idle_target + (peak * 0.6) * (0.3 + 0.7 * day_fraction) + np.random.normal(0, 5.0)
                else:
                    kwh = idle_target * 0.7 + np.random.normal(0, 1.5)

                # Plant: afternoon spike on Tuesday at 14:00 reaching 210 kW!
                if abs((current_ts - spike_target_time).total_seconds()) < 1800:
                    kwh = 210.0 + np.random.normal(0, 3.0)

            elif b_name == "Library":
                # Open on weekends (normal weekend load, not an anomaly)
                if 9 <= hour <= 21:
                    load_mult = 0.8 if is_weekend else 0.95
                    kwh = idle_target + (peak - idle_target) * 0.75 * load_mult + np.random.normal(0, 4.0)
                else:
                    kwh = idle_target * 0.8 + np.random.normal(0, 1.5)

            elif b_name in ["Hostel Block", "Cafeteria"]:
                # 24-hour building (peaks around evening 18:00-23:00, lunch, morning)
                activity = 0.35 + 0.45 * math.sin((hour - 12) * math.pi / 12)**2
                kwh = idle_target + (peak - idle_target) * activity + np.random.normal(0, 5.0)

            else:
                kwh = idle_target + (peak - idle_target) * day_fraction + np.random.normal(0, 3.0)

            kwh_final = max(0.5, round(kwh, 2))
            readings_to_add.append(models.MeterReading(
                building_id=b.id,
                ts=current_ts,
                kwh=kwh_final
            ))

            current_ts += timedelta(hours=1)

    db.bulk_save_objects(readings_to_add)
    db.commit()
    print(f"[+] Seeded {len(readings_to_add):,} meter readings across 28 days")

    # 7. Run Analytics to Populate Anomalies and Recommendations
    print("[*] Executing Analytics Engine on Seeded Data...")
    summary = run_analytics_for_buildings(db)
    print(f"[+] Detected {summary['new_anomalies']} anomalies across buildings")

    total_recs = db.query(models.Recommendation).count()
    print(f"[+] Generated {total_recs} savings recommendations with measurable capture rates")

    db.close()
    print("[OK] EcoWatt AI Seed Complete! System is demo-ready.")

if __name__ == "__main__":
    seed_database()
