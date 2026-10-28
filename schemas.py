from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict

# User & Auth
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

# Buildings
class BuildingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(academic|lab|library|hostel|cafeteria|admin|lighting)$")
    is_24h: bool = False
    peak_kw: float = Field(..., gt=0)
    idle_pct: float = Field(0.15, ge=0.0, le=1.0)

class BuildingOut(BaseModel):
    id: int
    name: str
    type: str
    is_24h: bool
    peak_kw: float
    idle_pct: float
    current_kw: Optional[float] = None
    energy_score: Optional[float] = None
    anomaly_count: Optional[int] = 0
    model_config = ConfigDict(from_attributes=True)

# Meter Readings
class MeterReadingCreate(BaseModel):
    building: str
    timestamp: datetime
    kwh: float = Field(..., ge=0)

class MeterReadingBatch(BaseModel):
    readings: List[MeterReadingCreate]

class MeterReadingOut(BaseModel):
    id: int
    building_id: int
    ts: datetime
    kwh: float
    model_config = ConfigDict(from_attributes=True)

class CsvUploadSummary(BaseModel):
    total_rows: int
    rows_loaded: int
    rows_skipped: int
    skipped_reasons: List[str]

# Analytics Summary & KPI
class SummaryOut(BaseModel):
    building_name: Optional[str] = "Campus Total"
    days_analyzed: int
    total_kwh: float
    wasted_kwh: float
    wasted_pct: float
    projected_savings_rupees_year: float
    co2_reduction_tons_year: float
    energy_score_baseline: float
    energy_score_optimized: float
    open_anomalies_count: int
    applied_recommendations_count: int
    total_recommendations_count: int
    tariff_inr: float
    emission_factor: float

# Series & Heatmap
class SeriesPoint(BaseModel):
    ts: datetime
    kwh: float
    is_anomaly: bool = False
    wasted_kwh: float = 0.0
    baseline_kwh: float
    optimized_kwh: float
    anomaly_rule: Optional[str] = None
    ml_anomaly_score: Optional[float] = None

class SeriesResponse(BaseModel):
    building: str
    days: int
    points: List[SeriesPoint]

class HeatmapCell(BaseModel):
    weekday: int  # 0=Monday ... 6=Sunday
    hour: int     # 0..23
    avg_kwh: float
    is_wasted_zone: bool = False

class HeatmapResponse(BaseModel):
    building: str
    cells: List[HeatmapCell]

# Forecast
class ForecastPoint(BaseModel):
    ts: datetime
    predicted_kwh: float
    lower_bound_kwh: float
    upper_bound_kwh: float

class ForecastResponse(BaseModel):
    building: str
    horizon: str
    status: str
    message: Optional[str] = None
    points: List[ForecastPoint] = []

# Anomalies
class AnomalyOut(BaseModel):
    id: int
    building_id: int
    building_name: str
    rule: str
    start_ts: datetime
    end_ts: datetime
    wasted_kwh: float
    severity: str
    evidence: str
    created_at: datetime
    status: str
    model_config = ConfigDict(from_attributes=True)

class AnomalyResolve(BaseModel):
    status: str = Field(..., pattern="^(open|resolved)$")

# Recommendations
class RecommendationOut(BaseModel):
    id: int
    building_id: int
    building_name: str
    anomaly_rule: str
    fix_text: str
    capture_rate: float
    kwh_week: float
    rupees_year: float
    co2_t_year: float
    applied: bool
    model_config = ConfigDict(from_attributes=True)

class RecommendationToggle(BaseModel):
    applied: bool

# Weather
class WeatherPoint(BaseModel):
    ts: datetime
    temp_c: float

class WeatherResponse(BaseModel):
    current_temp_c: Optional[float] = None
    weather_correlation_pct: Optional[float] = None
    correlation_message: str
    days_data: int
    series: List[WeatherPoint] = []

# AI Explanation
class ExplainResponse(BaseModel):
    anomaly_id: int
    rule: str
    building_name: str
    wasted_kwh: float
    explanation: str
    recommended_action: str
    source: str  # "gemini", "kimi", "claude", "sarvam", or "deterministic_template"
