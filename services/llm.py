import json
import logging
from typing import Dict, Any, Tuple
import httpx
from config import settings

logger = logging.getLogger("ecowatt.llm")

def generate_template_explanation(
    building_name: str,
    rule: str,
    wasted_kwh: float,
    start_ts_str: str,
    end_ts_str: str,
    evidence_data: Dict[str, Any]
) -> Tuple[str, str]:
    """
    Deterministic rule-based energy audit template.
    Generates a high-quality 3-sentence plain-English explanation + fix for facility managers.
    Guaranteed to execute in <1ms without internet connectivity.
    """
    mean_load = evidence_data.get("mean_load_kw", round(wasted_kwh / max(1, evidence_data.get("duration_hours", 1)), 1))
    idle_target = evidence_data.get("idle_target_kw", 40.0)
    duration = evidence_data.get("duration_hours", 1)

    if rule == "after_hours":
        exp = (
            f"Between {start_ts_str} and {end_ts_str}, {building_name} sustained an average draw of {mean_load} kW, "
            f"exceeding its permissible idle baseload of {idle_target} kW over {duration} consecutive hours. "
            f"This persistent nocturnal power draw indicates laboratory workstations, classroom lighting, or auxiliary HVAC systems "
            f"were left running without student occupancy, dissipating {wasted_kwh:.1f} kWh of grid power."
        )
        fix = "Deploy automated timer setbacks on lighting contactors and install smart sub-meter relays to cut inactive circuits from 22:00 to 05:00."

    elif rule == "weekend_waste":
        exp = (
            f"During standard weekend closure ({start_ts_str} to {end_ts_str}), {building_name} operated at {mean_load} kW "
            f"instead of dropping to its inactive threshold of {idle_target} kW. "
            f"Central ventilation systems and administrative peripherals remained energized in weekday mode across {duration} hours. "
            f"This operational oversight resulted in {wasted_kwh:.1f} kWh of entirely avoidable weekend consumption."
        )
        fix = "Enforce weekend BMS scheduling lockouts and install PIR motion sensors on lecture hall air distribution dampers."

    elif rule == "daylight_lighting":
        exp = (
            f"{building_name} consumed {wasted_kwh:.1f} kWh after sunrise between {start_ts_str} and {end_ts_str} at an average of {mean_load} kW. "
            f"Exterior and pathway luminaires remained fully energized despite ample ambient daylight. "
            f"This failure to de-energize daytime circuits represents 100% preventable energy waste."
        )
        fix = "Clean and recalibrate optical lux photocells and integrate an astronomical clock controller on the lighting distribution board."

    elif rule == "spike":
        z_score = evidence_data.get("max_spike_z", 3.2)
        exp = (
            f"A demand surge of {mean_load} kW was captured at {building_name} on {start_ts_str}, registering a robust z-score of {z_score}. "
            f"This sudden surge significantly exceeded the historical hour-of-week median, pointing to concurrent compressor staging or uncoordinated machinery startup. "
            f"The transient spike added {wasted_kwh:.1f} kWh of peak load and risks campus tariff demand penalties."
        )
        fix = "Implement staggered sequence delays on high-tonnage HVAC compressors and establish real-time peak demand shaving alerts."

    else:
        exp = (
            f"An unusual consumption pattern was detected in {building_name} from {start_ts_str} to {end_ts_str}. "
            f"The system recorded {wasted_kwh:.1f} kWh of anomalous consumption deviating from historical baselines. "
            f"Continued unaddressed operation will inflate quarterly utility expenditures."
        )
        fix = "Inspect electrical sub-panel metering and review equipment operational hours with facility maintenance."

    return exp, fix

def explain_anomaly(
    building_name: str,
    rule: str,
    wasted_kwh: float,
    start_ts: str,
    end_ts: str,
    evidence_json: str
) -> Dict[str, str]:
    """
    Explains an energy anomaly in plain English with a 3-sentence summary and actionable fix.
    Tries AI LLM APIs (Gemini, Kimi/Moonshot, Anthropic) if configured.
    Falls back gracefully to deterministic domain templates so it NEVER returns 500!
    """
    evidence_data = {}
    try:
        evidence_data = json.loads(evidence_json) if evidence_json else {}
    except Exception:
        evidence_data = {}

    prompt = (
        f"You are EcoWatt AI, an expert energy auditor for a university campus.\n"
        f"Analyze this detected electrical anomaly:\n"
        f"- Building: {building_name} ({evidence_data.get('building_type', 'campus')} type)\n"
        f"- Rule Triggered: {rule}\n"
        f"- Period: {start_ts} to {end_ts}\n"
        f"- Wasted Energy: {wasted_kwh:.1f} kWh\n"
        f"- Metrics: Peak={evidence_data.get('peak_kw', 'N/A')} kW, Idle Target={evidence_data.get('idle_target_kw', 'N/A')} kW, Mean Load={evidence_data.get('mean_load_kw', 'N/A')} kW\n\n"
        f"Respond in EXACTLY this JSON format:\n"
        f'{{"explanation": "Exactly three plain-English sentences explaining the root cause and why it wastes energy.", '
        f'"recommended_action": "One actionable, practical fix for campus facility administrators."}}'
    )

    # 1. Try Kimi (Moonshot / OpenAI compatible format)
    if settings.KIMI_API_KEY and settings.KIMI_API_KEY.startswith("sk-"):
        try:
            with httpx.Client(timeout=3.5) as client:
                res = client.post(
                    "https://api.moonshot.cn/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.KIMI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "moonshot-v1-8k",
                        "messages": [
                            {"role": "system", "content": "You are a professional energy auditor. Respond only with JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    parsed = json.loads(content)
                    return {
                        "explanation": parsed["explanation"],
                        "recommended_action": parsed["recommended_action"],
                        "source": "kimi"
                    }
        except Exception as e:
            logger.info(f"Kimi LLM call bypassed: {e}")

    # 2. Try Google Gemini API
    if settings.GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
            with httpx.Client(timeout=3.5) as client:
                res = client.post(
                    url,
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw_text)
                    return {
                        "explanation": parsed["explanation"],
                        "recommended_action": parsed["recommended_action"],
                        "source": "gemini"
                    }
        except Exception as e:
            logger.info(f"Gemini API call bypassed: {e}")

    # 3. Try Anthropic Claude API
    if settings.ANTHROPIC_API_KEY:
        try:
            with httpx.Client(timeout=3.5) as client:
                res = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 300,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    text = data["content"][0]["text"]
                    parsed = json.loads(text)
                    return {
                        "explanation": parsed["explanation"],
                        "recommended_action": parsed["recommended_action"],
                        "source": "claude"
                    }
        except Exception as e:
            logger.info(f"Anthropic Claude call bypassed: {e}")

    # Guaranteed Deterministic Template Fallback (Offline safe, hackathon ready)
    exp, fix = generate_template_explanation(
        building_name=building_name,
        rule=rule,
        wasted_kwh=wasted_kwh,
        start_ts_str=start_ts,
        end_ts_str=end_ts,
        evidence_data=evidence_data
    )
    return {
        "explanation": exp,
        "recommended_action": fix,
        "source": "deterministic_template"
    }
