import logging, json
from ..config import settings
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

log = logging.getLogger(__name__)

def weekly_patch(summary_json: dict) -> dict:
    if not settings.OPENAI_API_KEY or OpenAI is None:
        log.info("OpenAI disabled; returning empty patch.")
        return {}
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = (
        "You are a balance advisor for a household gamified bot. "
        "Given the weekly aggregate JSON, propose adjustments within corridors: "
        "increase/decrease task points within provided min/max; propose one-day booster events; "
        "and short motivation text. Respond JSON with keys: increase_points, decrease_points, events, message."
    )
    messages = [
        {"role": "system", "content": "Be concise and safe. Do not include PII."},
        {"role": "user", "content": prompt},
        {"role": "user", "content": json.dumps(summary_json)}
    ]
    try:
        res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.4)
        txt = res.choices[0].message.content
        patch = json.loads(txt)
        return patch
    except Exception as e:
        log.exception("OpenAI advisor failed: %s", e)
        return {}
