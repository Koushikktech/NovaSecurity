import json
import os
import re
import threading
import time
from openai import OpenAI

NOVA_LITE_4B = os.getenv("NOVA_MODEL", "nova-2-lite-v1")


def _get_api_key() -> str:
    return os.getenv("NOVA_API_KEY") or os.getenv("OPENAI_API_KEY", "")


def _get_base_url() -> str:
    return os.getenv("NOVA_BASE_URL", "https://api.nova.amazon.com/v1")


def get_client() -> OpenAI:
    api_key = _get_api_key()
    if not api_key:
        api_key = "unconfigured-nova-key"
    return OpenAI(
        api_key=api_key,
        base_url=_get_base_url(),
    )


# Module-level default client
client = get_client()


_call_log = threading.local()


def reset_call_log() -> None:

    _call_log.entries = []


def get_call_log() -> list[dict]:

    return getattr(_call_log, "entries", [])


def _log_call(entry: dict) -> None:
    if not hasattr(_call_log, "entries"):
        _call_log.entries = []
    _call_log.entries.append(entry)


def _fix_json_escapes(text: str) -> str:
    """Fix invalid backslash escape sequences in JSON strings from LLM output.
    
    LLMs often return file paths like bad\db_init.py in JSON strings,
    which produces invalid escapes like \d. This fixes them by doubling
    lone backslashes that aren't valid JSON escapes.
    """
    # Valid JSON escape chars: " \ / b f n r t u
    return re.sub(r'\\(?!["\\bfnrtu/])', r'\\\\', text)


def nova_call(
    prompt: str,
    nova_model: str = "nova-2-lite-v1",
    max_tokens: int = 4096,
    retries: int = 2,
) -> dict | None:
    for attempt in range(retries + 1):
        t0 = time.time()
        raw_text = None
        parsed = None
        error_msg = None
        try:
            active_client = get_client()
            response = active_client.chat.completions.create(
                model=nova_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a security analysis assistant. Always respond with valid JSON only, no extra text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
                stream=False,
            )

            raw_text = response.choices[0].message.content
            if not raw_text:
                print(f"Empty response on attempt {attempt + 1}")
                continue

            text = raw_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                # Try fixing invalid backslash escapes (e.g. \d from file paths)
                try:
                    parsed = json.loads(_fix_json_escapes(text))
                except json.JSONDecodeError:
                    match = re.search(r"\{[\s\S]*\}", text)
                    if match:
                        try:
                            parsed = json.loads(match.group())
                        except json.JSONDecodeError:
                            parsed = json.loads(_fix_json_escapes(match.group()))
                    else:
                        raise json.JSONDecodeError(
                            "No JSON object found in response", text, 0
                        )

            _log_call(
                {
                    "model": nova_model,
                    "prompt": prompt[:500],
                    "raw_response": raw_text[:2000] if raw_text else None,
                    "parsed_response": parsed,
                    "duration_s": round(time.time() - t0, 2),
                    "attempt": attempt + 1,
                    "success": True,
                }
            )
            return parsed

        except json.JSONDecodeError as e:
            error_msg = str(e)
            print(f"JSON parse failed attempt {attempt + 1}: {e}")
            _log_call(
                {
                    "model": nova_model,
                    "prompt": prompt[:500],
                    "raw_response": raw_text[:2000] if raw_text else None,
                    "parsed_response": None,
                    "duration_s": round(time.time() - t0, 2),
                    "attempt": attempt + 1,
                    "success": False,
                    "error": error_msg,
                }
            )
            if attempt < retries:
                time.sleep(1)
            continue

        except Exception as e:
            error_msg = str(e)
            print(f"Nova call failed attempt {attempt + 1}: {e}")
            _log_call(
                {
                    "model": nova_model,
                    "prompt": prompt[:500],
                    "raw_response": raw_text[:2000] if raw_text else None,
                    "parsed_response": None,
                    "duration_s": round(time.time() - t0, 2),
                    "attempt": attempt + 1,
                    "success": False,
                    "error": error_msg,
                }
            )
            if attempt < retries:
                time.sleep(2)
            continue

    return None


def nova_call_reasoning(
    prompt: str,
    nova_model: str = NOVA_LITE_4B,
    max_tokens: int = 40000,
    reasoning_effort: str = "medium",
    retries: int = 2,
) -> dict | None:

    for attempt in range(retries + 1):
        t0 = time.time()
        raw_text = None
        parsed = None
        error_msg = None
        try:
            active_client = get_client()
            response = active_client.chat.completions.create(
                model=nova_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a security analysis assistant. Always respond with valid JSON only, no extra text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0,
                stream=False,
                extra_body={
                    "reasoningConfig": {
                        "type": "enabled",
                        "maxReasoningEffort": reasoning_effort,
                    }
                },
            )

            raw_text = response.choices[0].message.content
            if not raw_text:
                print(f"Empty response on attempt {attempt + 1}")
                continue

            text = raw_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                # Try fixing invalid backslash escapes (e.g. \d from file paths)
                try:
                    parsed = json.loads(_fix_json_escapes(text))
                except json.JSONDecodeError:
                    match = re.search(r"\{[\s\S]*\}", text)
                    if match:
                        try:
                            parsed = json.loads(match.group())
                        except json.JSONDecodeError:
                            parsed = json.loads(_fix_json_escapes(match.group()))
                    else:
                        raise json.JSONDecodeError(
                            "No JSON object found in response", text, 0
                        )

            _log_call(
                {
                    "model": nova_model,
                    "prompt": prompt[:500],
                    "raw_response": raw_text[:2000] if raw_text else None,
                    "parsed_response": parsed,
                    "duration_s": round(time.time() - t0, 2),
                    "attempt": attempt + 1,
                    "success": True,
                    "reasoning_effort": reasoning_effort,
                }
            )
            return parsed

        except json.JSONDecodeError as e:
            error_msg = str(e)
            print(f"JSON parse failed attempt {attempt + 1}: {e}")
            _log_call(
                {
                    "model": nova_model,
                    "prompt": prompt[:500],
                    "raw_response": raw_text[:2000] if raw_text else None,
                    "parsed_response": None,
                    "duration_s": round(time.time() - t0, 2),
                    "attempt": attempt + 1,
                    "success": False,
                    "error": error_msg,
                }
            )
            if attempt < retries:
                time.sleep(1)
            continue

        except Exception as e:
            error_msg = str(e)
            print(f"Nova reasoning call failed attempt {attempt + 1}: {e}")
            _log_call(
                {
                    "model": nova_model,
                    "prompt": prompt[:500],
                    "raw_response": raw_text[:2000] if raw_text else None,
                    "parsed_response": None,
                    "duration_s": round(time.time() - t0, 2),
                    "attempt": attempt + 1,
                    "success": False,
                    "error": error_msg,
                }
            )
            if attempt < retries:
                time.sleep(2)
            continue

    return None


def nova_call_text(
    prompt: str,
    nova_model: str = "nova-2-lite-v1",
    max_tokens: int = 4096,
    retries: int = 2,
) -> str | None:

    for attempt in range(retries + 1):
        try:
            active_client = get_client()
            response = active_client.chat.completions.create(
                model=nova_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.1,
                stream=False,
                extra_body={
                    "reasoningConfig": {
                        "type": "enabled",
                        "maxReasoningEffort": "medium",
                    }
                },
            )

            text = response.choices[0].message.content
            if not text:
                print(f"Empty response on attempt {attempt + 1}")
                continue

            return text.strip()

        except Exception as e:
            print(f"Nova call failed attempt {attempt + 1}: {e}")
            if attempt < retries:
                time.sleep(2)
            continue

    return None
