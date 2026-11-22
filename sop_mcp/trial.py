"""30-day trial gate. Soft local enforcement: the production/managed
version is the paid tier; this gate marks the evaluation boundary."""
import json
import os
import time
import datetime

TRIAL_DAYS = 30


def _data_dir(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "license.json")


def get_license(data_dir):
    path = _data_dir(data_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    now = time.time()
    lic = {
        "installed_at": datetime.datetime.utcfromtimestamp(now).strftime("%Y-%m-%d"),
        "expires_at": datetime.datetime.utcfromtimestamp(
            now + TRIAL_DAYS * 86400).strftime("%Y-%m-%d"),
        "type": "free-evaluation",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lic, f, indent=2)
    return lic


def check_trial(data_dir):
    lic = get_license(data_dir)
    expires = datetime.datetime.strptime(lic["expires_at"], "%Y-%m-%d")
    days_left = (expires - datetime.datetime.utcnow()).days
    return {
        "ok": days_left >= 0,
        "days_left": max(days_left, 0),
        "expires_at": lic["expires_at"],
        "message": ("Trial active: %d days left (until %s). "
                    "Contact us to upgrade to the managed production version."
                    % (max(days_left, 0), lic["expires_at"])
                    if days_left >= 0 else
                    "Trial expired on %s. Contact us to upgrade to the "
                    "managed production version." % lic["expires_at"]),
    }
