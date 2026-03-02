import os
import time
import json
import socket
import urllib.request
import urllib.error
from datetime import datetime, timezone

# -----------------------------
# CONFIG (env overrides)
# -----------------------------
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "10"))
RE_ALERT_EVERY_SECONDS = int(os.getenv("RE_ALERT_EVERY_SECONDS", "300"))  # 5 mins
STATE_FILE = os.getenv("STATE_FILE", ".monitor_state.json")

DJANGO_HEALTH_URL = os.getenv("DJANGO_HEALTH_URL", "http://localhost:8000/api/health/")
FLOWER_URL = os.getenv("FLOWER_URL", "http://localhost:5555/")  # optional

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Optional redis TCP check (no deps)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
CHECK_REDIS = os.getenv("CHECK_REDIS", "1") in ["1", "true", "True"]

# -----------------------------
# Helpers
# -----------------------------
def utcnow():
    return datetime.now(timezone.utc).isoformat()

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def http_get_json(url: str, timeout=3):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        try:
            return resp.status, json.loads(body)
        except Exception:
            return resp.status, {"raw": body}

def http_head(url: str, timeout=3):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status

def redis_ping_tcp(host: str, port: int, timeout=2) -> bool:
    # Minimal Redis PING without external libs: send RESP "*1\r\n$4\r\nPING\r\n"
    payload = b"*1\r\n$4\r\nPING\r\n"
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(payload)
            data = s.recv(64)
            return data.startswith(b"+PONG")
    except Exception:
        return False

def log_line(msg: str):
    print(f"{utcnow()} | {msg}", flush=True)

def telegram_send(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "telegram not configured"
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return (resp.status == 200), f"status={resp.status}"
    except Exception as e:
        return False, str(e)

def should_alert(key: str, state: dict, now_ts: float) -> bool:
    last = state.get(key, {}).get("last_alert_ts")
    if last is None:
        return True
    return (now_ts - last) >= RE_ALERT_EVERY_SECONDS

def set_alerted(key: str, state: dict, now_ts: float):
    state.setdefault(key, {})
    state[key]["last_alert_ts"] = now_ts

def set_status(key: str, state: dict, up: bool):
    state.setdefault(key, {})
    state[key]["up"] = up
    state[key]["last_change_at"] = utcnow()

# -----------------------------
# Checks
# -----------------------------
def check_django_health():
    try:
        status, data = http_get_json(DJANGO_HEALTH_URL, timeout=3)
        ok = (status == 200) and (data.get("status") in ["ok", "degraded"])
        return ok, f"HTTP {status} status={data.get('status')} services={data.get('services')}"
    except urllib.error.URLError as e:
        return False, f"unreachable ({e})"
    except Exception as e:
        return False, f"error ({e})"

def check_flower():
    if not FLOWER_URL:
        return True, "skipped"
    try:
        status = http_head(FLOWER_URL, timeout=3)
        return (200 <= status < 500), f"HTTP {status}"
    except Exception as e:
        return False, f"unreachable ({e})"

def check_redis():
    if not CHECK_REDIS:
        return True, "skipped"
    ok = redis_ping_tcp(REDIS_HOST, REDIS_PORT, timeout=2)
    return ok, "PONG" if ok else "no PONG"

# -----------------------------
# Main loop
# -----------------------------
def main():
    state = load_state()
    log_line("🧭 monitor started")

    while True:
        now_ts = time.time()

        checks = [
            ("django", check_django_health),
            ("flower", check_flower),
            ("redis", check_redis),
        ]

        for key, fn in checks:
            ok, info = fn()

            prev_up = state.get(key, {}).get("up")
            if prev_up is None:
                prev_up = True  # assume up initially

            # Log every cycle (small)
            log_line(f"{'✅' if ok else '❌'} {key} | {info}")

            # Detect transition: UP -> DOWN
            if prev_up and not ok:
                set_status(key, state, False)
                if should_alert(key, state, now_ts):
                    msg = f"❌ {key.upper()} DOWN\n{info}\n{utcnow()}"
                    telegram_send(msg)
                    set_alerted(key, state, now_ts)

            # DOWN -> UP (recovery)
            if (not prev_up) and ok:
                set_status(key, state, True)
                msg = f"✅ {key.upper()} RECOVERED\n{info}\n{utcnow()}"
                telegram_send(msg)
                # reset alert timer so next outage alerts immediately
                state.setdefault(key, {})["last_alert_ts"] = None

            # Still down: re-alert every RE_ALERT_EVERY_SECONDS
            if (not ok) and should_alert(key, state, now_ts):
                msg = f"⚠️ {key.upper()} still DOWN\n{info}\n{utcnow()}"
                telegram_send(msg)
                set_alerted(key, state, now_ts)

        save_state(state)
        time.sleep(CHECK_EVERY_SECONDS)

if __name__ == "__main__":
    main()