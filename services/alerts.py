import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings

logger = logging.getLogger("ecowatt.alerts")

def send_high_severity_alert(
    building_name: str,
    rule: str,
    start_ts: str,
    end_ts: str,
    wasted_kwh: float,
    evidence: str
) -> bool:
    """
    Sends an email alert for High severity anomalies if SMTP is configured.
    Gracefully logs warning and continues if SMTP is unconfigured or fails.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASS:
        logger.info(
            f"[ALERT LOG ONLY - SMTP Unconfigured] High Severity Anomaly in {building_name}: "
            f"Rule={rule}, Wasted={wasted_kwh:.1f} kWh, From={start_ts} to {end_ts}"
        )
        return False

    try:
        subject = f"🚨 [EcoWatt AI ALERT] High Energy Anomaly Detected in {building_name}"
        body = f"""
Campus Energy Alert - EcoWatt AI Optimizer

A High Severity energy waste pattern has been detected:
--------------------------------------------------------
Building:     {building_name}
Anomaly Rule: {rule}
Period:       {start_ts} to {end_ts}
Wasted Load:  {wasted_kwh:.1f} kWh
Evidence:     {evidence}

Action Required:
Inspect sub-meter controls, HVAC setpoints, or after-hours equipment schedules.
Login to the EcoWatt dashboard to review AI explanations and apply savings fixes:
http://localhost:8000
--------------------------------------------------------
EcoWatt AI - Automated Campus Guardian
"""
        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_USER
        msg["To"] = settings.ALERT_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=4) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)

        logger.info(f"Successfully sent High severity alert email to {settings.ALERT_EMAIL} for {building_name}")
        return True
    except Exception as e:
        logger.warning(f"Could not send email alert for {building_name} ({e}). Continuing safely.")
        return False
