import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "EcoWatt AI - Campus Energy Optimizer"
    VERSION: str = "1.0.0"
    
    # Security & Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "ecowatt-hackathon-super-secret-key-2026-campus-energy-jwt")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    METER_API_KEY: str = os.getenv("METER_API_KEY", "campus-meter-secret-key-2026")
    
    # Default users
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@campus.edu")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "AdminCampus#2026")
    VIEWER_EMAIL: str = os.getenv("VIEWER_EMAIL", "viewer@campus.edu")
    VIEWER_PASSWORD: str = os.getenv("VIEWER_PASSWORD", "ViewerCampus#2026")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ecowatt.db")
    
    # Tariff & Emission
    DEFAULT_TARIFF_INR: float = float(os.getenv("DEFAULT_TARIFF_INR", "8.0"))
    DEFAULT_EMISSION_FACTOR: float = float(os.getenv("DEFAULT_EMISSION_FACTOR", "0.82")) # kg CO2 / kWh
    
    # LLM Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    KIMI_API_KEY: str = os.getenv("KIMI_API_KEY", "")
    SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # SMTP Alerting (Optional)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    ALERT_EMAIL: str = os.getenv("ALERT_EMAIL", "facility.manager@campus.edu")

settings = Settings()
