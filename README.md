# 🌿 EcoWatt AI – Campus Energy Optimizer
> **IEEE EcoTech Hackathon Solution** &bull; High-Reliability Full-Stack Campus Sub-Meter Intelligence & Measurable Carbon Reduction

EcoWatt AI converts university campus sub-meter telemetry into measurable operational savings. It identifies after-hours vampire baseloads, weekend scheduling misconfigurations, daytime lighting oversights, and inductive demand surges using explainable physics-based rules and an unsupervised IsolationForest ML detector. Facility administrators can simulate what-if interventions with iOS-style toggles to immediately observe projected rupee savings, CO₂ reductions, and Energy Score improvements.

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.11+
- Git

### 2. Installation
```bash
# Clone or navigate to the project directory
cd ecowatt

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install strictly verified dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### 3. Initialize & Seed Database
Seeds 7 campus facilities, default Admin and Viewer accounts, 28 days of hourly weather cache, and 4,704 hourly readings with planted realistic anomaly patterns:
```bash
python seed.py
```

### 4. Run the Full-Stack Application
Start the FastAPI server (serves both API and high-performance Vanilla JS / SVG frontend):
```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Open your browser to: **[http://localhost:8000](http://localhost:8000)**

### 5. Launch Live Telemetry Simulator (Demo Mode)
In a second terminal window, run the meter simulator to stream live readings every 5 seconds:
```bash
python simulator.py
```
Watch the EcoWatt dashboard's live pulsing indicator, load curves, and KPI counters update in real time!

---

## 🌐 Demo Credentials & Roles

| Role | Email | Password | Access Rights |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@campus.edu` | `AdminCampus#2026` | Full access: Resolve anomalies, upload CSVs, add facilities |
| **Viewer** | `viewer@campus.edu` | `ViewerCampus#2026` | Audit access: View dashboards, toggle what-if simulations |

---

## 🏛️ Project Structure

```
ecowatt/
├── .env                  # Live environment secrets & API keys
├── .env.example          # Template environment configuration
├── requirements.txt      # Pinned, tested dependencies
├── README.md             # Architecture, demo script, and documentation
├── main.py               # FastAPI application, static mounting & middleware
├── config.py             # Typed Pydantic/dotenv configuration
├── database.py           # SQLAlchemy 2.x engine and session manager
├── models.py             # Declarative database models (7 tables)
├── schemas.py            # Pydantic v2 validation models & DTOs
├── auth.py               # Passlib bcrypt hashing, JWT & meter key guards
├── seed.py               # 28-day data generator with planted anomalies
├── simulator.py          # 5-second live telemetry ingestion daemon
├── routers/
│   ├── __init__.py
│   ├── auth.py           # /api/auth/login, /api/auth/me (rate-limited)
│   ├── buildings.py      # /api/buildings
│   ├── readings.py       # /api/readings (X-Meter-Key), /api/upload-csv
│   ├── analytics.py      # /api/summary, /api/series, /api/heatmap, /api/forecast, /api/export-report
│   ├── anomalies.py      # /api/anomalies, /api/anomalies/{id} (resolve)
│   ├── recommendations.py# /api/recommendations, /api/recommendations/{id} (what-if toggle)
│   ├── weather.py        # /api/weather (Open-Meteo caching & correlation)
│   └── explain.py        # /api/explain/{id} (Gemini/Kimi/Claude/Template AI)
├── services/
│   ├── __init__.py
│   ├── analytics.py      # Rule engine, consecutive clustering, savings maths, Energy Score
│   ├── forecast.py       # 4-week hour-of-week moving average forecaster
│   ├── ml.py             # Scikit-learn IsolationForest unsupervised scorer
│   ├── weather.py        # Open-Meteo client & 14-day climate correlation
│   ├── llm.py            # Multi-provider LLM caller + offline template fallback
│   └── alerts.py         # SMTP email notifications for High severity anomalies
├── static/
│   ├── index.html        # Semantic HTML5 dashboard layout
│   ├── style.css         # Custom design system (light/dark themes, glassmorphism)
│   └── app.js            # Hand-crafted SVG charts, 24x7 heatmap, 5s polling engine
└── tests/
    ├── __init__.py
    ├── test_auth.py            # JWT token & authentication tests
    ├── test_csv_validation.py  # CSV ingestion & edge-case skipping tests
    ├── test_analytics_rules.py # Core physics rules & Energy Score tests
    ├── test_forecast.py        # Forecasting logic & 14-day history guards
    └── test_savings.py         # Capture rates & what-if toggle simulation tests
```

---

## 🔌 Complete API Reference

All endpoints return strictly validated JSON with standard HTTP status codes:

| Method | Endpoint | Description | Auth / Headers |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Authenticate user & issue JWT | Public (Rate-limited) |
| `GET` | `/api/auth/me` | Fetch authenticated user profile | Bearer JWT |
| `GET` | `/api/buildings` | List all 7 buildings with live kW & Energy Scores | Public |
| `POST` | `/api/buildings` | Register a new campus facility | Admin Bearer JWT |
| `POST` | `/api/readings` | Ingest single or batch telemetry readings | `X-Meter-Key` or Admin |
| `POST` | `/api/upload-csv` | Upload meter CSV (max 10MB, max 200,000 rows) | Public / User |
| `GET` | `/api/summary` | Top-level KPIs: Total, Wasted, ₹ Savings, CO₂, Score | Public |
| `GET` | `/api/series` | Hourly time series with baseline, waste, & ML score | Public |
| `GET` | `/api/heatmap` | 7×24 hourly load matrix with waste zones | Public |
| `GET` | `/api/forecast` | Hour-of-week 4-week moving average (24h or 7d) | Public |
| `GET` | `/api/anomalies` | Query detected anomalies filtered by facility/severity| Public |
| `PATCH`| `/api/anomalies/{id}` | Resolve open anomaly | User / Admin |
| `GET` | `/api/recommendations` | List actionable fixes with annual savings | Public |
| `PATCH`| `/api/recommendations/{id}` | Toggle applied intervention (updates what-if) | User / Admin |
| `GET` | `/api/weather` | Current temperature, Open-Meteo cache & correlation | Public |
| `POST` | `/api/explain/{id}` | AI 3-sentence root cause explanation & fix | Public (Never 500s) |
| `GET` | `/api/export-report` | Printable executive campus audit report | Public (HTML) |
| `GET` | `/health` | Server health check and version status | Public |

---

## 🛡️ Hackathon Reliability & Offline Demo Mode

EcoWatt AI is architected with **Demo-Safety First** principles:
1. **Zero External Breakages:**
   - **Open-Meteo:** Uses a 3.0s timeout. If internet is severed, it transparently returns cached weather from the SQLite `weather` table.
   - **AI Explanations:** The LLM client calls Gemini / Kimi / Claude with a short timeout. If offline or if API keys are exhausted, it instantaneously falls back to deterministic energy engineering templates. It **never returns a 500**.
   - **Email Alerts:** If SMTP is unconfigured or unreachable, it logs a clean structured warning and continues execution without blocking ingestion.
2. **Frontend Zero-Glitch Guarantee:**
   - All numerical renderers use `safeNum()` to ensure that `NaN`, `undefined`, or `Infinity` never display on the dashboard.
   - Pure vanilla JavaScript with hand-crafted inline SVG: Zero CDN dependencies, zero NPM bundle failures, zero chart library version conflicts.

---

## 🧪 Automated Test Suite

Run the full pytest suite:
```bash
pytest -v
```
All 16 tests cover:
- Admin & viewer JWT token validation & unauthenticated rejection
- CSV upload schema validation, negative/non-numeric skips, and date parsing
- Analytics rules: After-hours baseload, weekend waste, daylight lighting, and MAD robust z-score spikes
- 14-day history requirement for hour-of-week forecasting
- Capture rate savings maths and dynamic what-if recalculation

---

## ⏱️ 3-Minute Hackathon Demo Script

### **Minute 1: The Campus Problem & Live Dashboard (0:00 - 1:00)**
1. **Hook:** *"Judges, university campuses waste 15% to 30% of their utility budgets on 'vampire' loads—empty computer labs running overnight, HVACs conditioning unoccupied academic blocks on weekends, and outdoor lighting burning long after sunrise. Meet EcoWatt AI."*
2. **Dashboard Walkthrough:** 
   - Point out the **Gradient Header Banner** with the pulsing **● Live Feed** badge and **Campus Energy Score (57.3/100)**.
   - Show the **KPI Cards**: Over the last 28 days, EcoWatt flagged **67,640 kWh of preventable waste (10.7%)**, equating to **₹55.9 Lakhs** in potential annual savings and **573 tons of CO₂**.
   - Show the **Hand-Crafted SVG Chart**: Explain the green actual load curve, the red wasted-hour dots, and the distinct shaded **Forecast Zone**.

### **Minute 2: Live Simulator & Telemetry Ingestion (1:00 - 2:00)**
1. **Live Simulator:** Start `python simulator.py` in the terminal. Show judges that every 5 seconds, real-time meter readings push to `/api/readings` with the `X-Meter-Key` header.
2. **Live Auto-Refresh:** Point to the dashboard refreshing smoothly every 5 seconds without full page reloads.
3. **Building Isolation:** Click on **Computer Labs** in the Facilities list. Notice the Energy Score drops to 0/100 because the lab baseload never drops below 160 kW at night!
4. **24x7 Heatmap:** Point to the 24×7 matrix showing persistent bright load squares between 22:00 and 05:00 on weekdays.

### **Minute 3: AI Explanation, What-If Simulation & Audit Export (2:00 - 3:00)**
1. **AI Root-Cause Explanation:** Click **"✨ Explain with AI"** on the Computer Labs after-hours anomaly. 
   - Show the modal pop up with an instant 3-sentence root cause and recommended operational fix (automated night setbacks on sub-meter contactors).
2. **What-If Savings Engine:** 
   - Toggle the iOS switch for *"Computer Labs: Implement automated night setbacks..."*
   - Watch the **Projected Savings** and **Energy Score** dynamically increase in real time, and observe the dashed green "Optimized (Post-Fix)" line drop on the chart!
3. **Ingest CSV & Export Report:**
   - Drop a sample CSV onto the drag-and-drop zone to demonstrate batch validation and row filtering.
   - Click **"Export Report"** to reveal the printable, executive-ready Campus Energy Audit summary.

