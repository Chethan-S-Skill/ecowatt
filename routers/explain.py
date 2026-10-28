from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from services.llm import explain_anomaly

router = APIRouter(prefix="/api/explain", tags=["AI Explainability"])

@router.post("/{anomaly_id}", response_model=schemas.ExplainResponse)
def get_ai_explanation(
    anomaly_id: int,
    db: Session = Depends(get_db)
):
    """
    Generates a 3-sentence plain English explanation + actionable fix for campus facility managers.
    Queries Gemini / Kimi / Claude / Sarvam with short timeout; falls back gracefully to
    domain template so this endpoint NEVER raises a 500 error.
    """
    anomaly = db.query(models.Anomaly).filter(models.Anomaly.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly record not found")

    b_name = anomaly.building.name if anomaly.building else "Campus Facility"
    start_str = anomaly.start_ts.strftime("%Y-%m-%d %H:%M")
    end_str = anomaly.end_ts.strftime("%Y-%m-%d %H:%M")

    res = explain_anomaly(
        building_name=b_name,
        rule=anomaly.rule,
        wasted_kwh=anomaly.wasted_kwh,
        start_ts=start_str,
        end_ts=end_str,
        evidence_json=anomaly.evidence
    )

    return schemas.ExplainResponse(
        anomaly_id=anomaly.id,
        rule=anomaly.rule,
        building_name=b_name,
        wasted_kwh=round(anomaly.wasted_kwh, 1),
        explanation=res["explanation"],
        recommended_action=res["recommended_action"],
        source=res["source"]
    )
