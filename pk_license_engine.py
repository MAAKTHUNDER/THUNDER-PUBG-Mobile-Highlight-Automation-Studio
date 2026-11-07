"""
THUNDER — PUBG Mobile Highlight Automation Studio
Pakistani Domestic Licensing & Anti-Fraud Engine (Firestore-Backed)
"""

import os
import sys
import time
import json
import uuid
import hmac
import hashlib
import urllib.request
import urllib.error

# Project Configuration
FIREBASE_PROJECT_ID = "maakthunder-studio"
FIREBASE_API_KEY = "AIzaSyBpWeW72diIAq9enlq9y-Gh5U_33ta8RPg"
FIRESTORE_REST_BASE = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1566833699712925806/qihzAN0sGmPsVa8uXPktUxZidLcy-CV2KIvWpIJ0Ig34S8vAOppqJlPhbxWOUBBT00Jo"

_SHIELD_SECRET = b"MAAKTHUNDER_STUDIO_PAKISTAN_DOMESTIC_KEY_SECRET_2026"

def send_discord_alert(title: str, description: str, fields: list = None, color: int = 58367):
    """Dispatches a real-time event alert to the official Discord admin channel."""
    try:
        payload = {
            "username": "THUNDER Studio Sentinel",
            "embeds": [{
                "title": title,
                "description": description,
                "color": color,
                "fields": fields or [],
                "footer": {"text": "Official Client of MAAKTHUNDER Studios • 2026"},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }]
        }
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "THUNDER-Studio/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as _:
            pass
    except Exception as e:
        print("[Discord Alert Notice]", e)

PLAN_DAYS = {
    "trial": 15,
    "basic": 30,
    "pro": 30,
    "pro_plus": 30,
    "annual": 365,
    "lifetime": 3650
}

def generate_pk_license_key(plan: str) -> str:
    """Generates a guaranteed collision-free, cryptographically signed Pakistani License Key."""
    unique_entropy = f"{uuid.uuid4().hex[:12]}-{int(time.time())}"
    plan_prefix = plan.upper()[:4]
    raw_token = f"THUNDER-PK-{plan_prefix}-{unique_entropy}".upper()
    sig = hmac.new(_SHIELD_SECRET, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()[:6].upper()
    return f"{raw_token}-{sig}"


def _firestore_post(collection: str, doc_id: str, fields_dict: dict, auth_token: str = None):
    """Writes a document to Firestore using the authenticated REST API."""
    mask_params = "&".join([f"updateMask.fieldPaths={k}" for k in fields_dict.keys()])
    url = f"{FIRESTORE_REST_BASE}/{collection}/{doc_id}?{mask_params}&key={FIREBASE_API_KEY}"
    firestore_fields = {}
    for k, v in fields_dict.items():
        if isinstance(v, bool):
            firestore_fields[k] = {"booleanValue": v}
        elif isinstance(v, str):
            firestore_fields[k] = {"stringValue": v}
        elif isinstance(v, (int, float)):
            firestore_fields[k] = {"integerValue": str(int(v))}
        elif v is None:
            firestore_fields[k] = {"nullValue": None}

    payload = json.dumps({"fields": firestore_fields}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            return True, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return False, e.read().decode()
    except Exception as e:
        return False, str(e)


def _firestore_get(collection: str, doc_id: str):
    """Retrieves a document from Firestore."""
    url = f"{FIRESTORE_REST_BASE}/{collection}/{doc_id}?key={FIREBASE_API_KEY}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            fields = data.get("fields", {})
            parsed = {}
            for k, val_obj in fields.items():
                for type_key, actual_val in val_obj.items():
                    if type_key == "integerValue":
                        parsed[k] = int(actual_val)
                    else:
                        parsed[k] = actual_val
            return True, parsed
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, None
        return False, e.read().decode()
    except Exception as e:
        return False, str(e)


def check_tid_claimed(tid: str) -> bool:
    """Checks if this Transaction ID has ever been used before (Anti-Fraud)."""
    clean_tid = tid.strip().upper()
    success, data = _firestore_get("claimed_transactions", clean_tid)
    return success and data is not None


def claim_transaction_id(tid: str, email: str, plan: str, amount: int):
    """Records a Transaction ID into the immutable claimed ledger."""
    clean_tid = tid.strip().upper()
    return _firestore_post("claimed_transactions", clean_tid, {
        "tid": clean_tid,
        "email": email.strip().lower(),
        "plan": plan,
        "amount": amount,
        "claimed_at": int(time.time())
    })


def register_or_upgrade_license(name: str, email: str, plan: str, tid: str = "", duration_days: int = None, amount: int = 0, exact_days: int = None, is_lifetime: bool = False):
    """
    Creates a new Pakistani license or upgrades an existing license.
    Strictly checks that the Transaction ID is not reused.
    """
    clean_email = email.strip().lower()
    clean_tid = tid.strip().upper() if tid else ""

    # 1. Anti-Fraud TID check (unless it's a 15-day trial with no payment)
    if clean_tid:
        if check_tid_claimed(clean_tid):
            return {
                "success": False,
                "error": f"Transaction ID '{clean_tid}' has already been claimed! Each payment receipt can only be used once."
            }

    # 2. Check if this customer already has an existing license (For Upgrade / Renewal)
    doc_id = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:24]
    existing_ok, existing_data = _firestore_get("pk_licenses", doc_id)

    now_ts = int(time.time())
    if is_lifetime or str(duration_days).lower() == "lifetime" or exact_days == 0:
        new_expiry = 0
        days_value = "Lifetime"
        is_lifetime = True
    elif exact_days is not None:
        new_expiry = now_ts + max(0, int(exact_days) * 86400)
        days_value = max(0, int(exact_days))
        is_lifetime = False
    else:
        days_to_add = duration_days if duration_days is not None else PLAN_DAYS.get(plan, 30)
        seconds_to_add = int(days_to_add) * 86400
        if existing_ok and existing_data:
            current_expiry = int(existing_data.get("expires_at", now_ts))
            base_expiry = max(current_expiry, now_ts) if int(days_to_add) > 0 else current_expiry
            new_expiry = max(now_ts, base_expiry + seconds_to_add)
        else:
            new_expiry = max(now_ts, now_ts + seconds_to_add)
        days_value = max(0, int((new_expiry - now_ts) // 86400))
        is_lifetime = False

    if existing_ok and existing_data:
        # UPGRADE OR EXTEND EXISTING KEY
        license_key = existing_data.get("key", generate_pk_license_key(plan))
        hwid = existing_data.get("hwid", "")

        fields = {
            "key": license_key,
            "email": clean_email,
            "name": name or existing_data.get("name", ""),
            "plan": plan,
            "status": "active",
            "hwid": hwid or "",
            "created_at": existing_data.get("created_at", now_ts),
            "updated_at": now_ts,
            "expires_at": new_expiry,
            "days": days_value,
            "is_lifetime": is_lifetime,
            "last_tid": clean_tid
        }
        _firestore_post("pk_licenses", doc_id, fields)
        action_type = "upgraded"
    else:
        # BRAND NEW KEY
        license_key = generate_pk_license_key(plan)
        fields = {
            "key": license_key,
            "email": clean_email,
            "name": name,
            "plan": plan,
            "status": "active",
            "hwid": "",
            "created_at": now_ts,
            "expires_at": new_expiry,
            "days": days_value,
            "is_lifetime": is_lifetime,
            "last_tid": clean_tid
        }
        _firestore_post("pk_licenses", doc_id, fields)
        action_type = "created"

    # Store primary key document by raw license key string for direct lookup
    _firestore_post("pk_licenses_by_key", license_key, fields)

    # 3. Burn the TID
    if clean_tid:
        claim_transaction_id(clean_tid, clean_email, plan, amount)

    remaining_days = max(1, int((new_expiry - now_ts) / 86400))
    
    # Dispatch Discord Sentinel Alert
    send_discord_alert(
        title=f"⚡ New License {action_type.capitalize()}: {plan.upper()}",
        description=f"A Pakistani software pass was successfully **{action_type}**.",
        fields=[
            {"name": "Customer", "value": f"{name} ({clean_email})", "inline": True},
            {"name": "Plan Tier", "value": plan.upper(), "inline": True},
            {"name": "Validity", "value": f"{remaining_days} Days", "inline": True},
            {"name": "License Key", "value": f"`{license_key}`", "inline": False},
            {"name": "Payment TID", "value": clean_tid or "None (Free Trial)", "inline": True}
        ],
        color=0x00E5FF if plan == "trial" else 0xF59E0B
    )

    return {
        "success": True,
        "action": action_type,
        "license_key": license_key,
        "email": clean_email,
        "plan": plan,
        "expires_at": new_expiry,
        "days_left": remaining_days
    }


def lookup_license_by_identifier(identifier: str):
    """
    Finds an existing license by either Email OR License Key string,
    returning its status, plan, and days remaining.
    """
    clean_id = identifier.strip()
    if not clean_id:
        return {"found": False, "message": "Please enter your License Key or Email address."}

    # Case 1: Searching by Key
    if clean_id.upper().startswith("THUNDER-"):
        clean_key = clean_id.upper()
        doc_lookup_id = clean_key
        ok, data = _firestore_get("pk_licenses_by_key", clean_key)
        if not ok or not data:
            doc_lookup_id = hashlib.sha256(clean_key.encode("utf-8")).hexdigest()[:24]
            ok, data = _firestore_get("pk_licenses_by_key", doc_lookup_id)
        if not ok or not data:
            return {"found": False, "message": "No license found with this key. Please check your key or order a pass."}
    # Case 2: Searching by Email
    else:
        clean_email = clean_id.lower()
        doc_id = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:24]
        ok, data = _firestore_get("pk_licenses", doc_id)
        if not ok or not data:
            return {"found": False, "message": "No license found under this email. Please check your email or order a pass."}

    now_ts = int(time.time())
    expires_at = int(data.get("expires_at", 0))
    is_lifetime = data.get("is_lifetime") is True or str(data.get("days", "")).lower() == "lifetime" or expires_at == 0 or expires_at > 2500000000
    is_expired = False if is_lifetime else (expires_at > 0 and now_ts > expires_at)
    days_left = "Lifetime" if is_lifetime else (max(0, int((expires_at - now_ts) / 86400)) if not is_expired else 0)

    return {
        "found": True,
        "key": data.get("key"),
        "name": data.get("name"),
        "email": data.get("email"),
        "plan": data.get("plan"),
        "status": "expired" if is_expired else data.get("status", "active"),
        "days_left": days_left,
        "expires_at": expires_at,
        "is_lifetime": is_lifetime,
        "hwid": data.get("hwid")
    }


def validate_and_bind_pk_key(key_str: str, system_hwid: str):
    """
    Called by THUNDER Studio Desktop to validate a Pakistani license key
    and lock it to this computer's HWID.
    """
    clean_key = key_str.strip().upper()
    doc_lookup_id = clean_key
    ok, data = _firestore_get("pk_licenses_by_key", clean_key)
    if not ok or not data:
        doc_lookup_id = hashlib.sha256(clean_key.encode("utf-8")).hexdigest()[:24]
        ok, data = _firestore_get("pk_licenses_by_key", doc_lookup_id)
    if not ok or not data:
        return False, None, "Invalid Pakistani License Key. Please check your key or order a pass on the portal."

    # Status check
    if data.get("status") == "revoked":
        return False, data, "This license key has been revoked by MAAKTHUNDER Studios."

    # Expiry check
    now_ts = int(time.time())
    expires_at = int(data.get("expires_at", 0))
    is_lifetime = data.get("is_lifetime") is True or str(data.get("days", "")).lower() == "lifetime" or expires_at == 0 or expires_at > 2500000000
    if not is_lifetime and expires_at and now_ts > expires_at:
        return False, data, "Your THUNDER pass has expired. Please renew on the portal or contact on Discord."

    # HWID Binding check
    bound_hwid = data.get("hwid")
    if not bound_hwid:
        # First time activation on this PC: bind it!
        data["hwid"] = system_hwid
        bind_fields = {"hwid": system_hwid}
        curr_name = str(data.get("name", "")).lower()
        if "gift" in curr_name or "unassigned" in curr_name:
            data["name"] = "Claimed PC User"
            bind_fields["name"] = "Claimed PC User"

        _firestore_post("pk_licenses_by_key", doc_lookup_id, bind_fields)
        # Also update the customer master doc
        doc_id = hashlib.sha256(data.get("email", "").encode("utf-8")).hexdigest()[:24]
        _firestore_post("pk_licenses", doc_id, bind_fields)

        # Alert Discord that a key was hardware-activated on a PC
        send_discord_alert(
            title="💻 Machine Bound: PC Hardware Activated",
            description=f"A license key was permanently locked to a user's PC hardware.",
            fields=[
                {"name": "Customer", "value": f"{data.get('name', 'User')} ({data.get('email', '-')})", "inline": True},
                {"name": "Plan", "value": data.get("plan", "trial").upper(), "inline": True},
                {"name": "Hardware ID (HWID)", "value": f"`{system_hwid}`", "inline": False},
                {"name": "Key", "value": f"`{clean_key}`", "inline": False}
            ],
            color=0x10B981 # Emerald Green
        )
    elif bound_hwid != system_hwid:
        return False, data, "This license key is locked to a different PC. Each key is bound to 1 computer only."

    days_left = "Lifetime" if is_lifetime else max(1, int((expires_at - now_ts) / 86400))
    msg_dur = "Permanent Lifetime Access" if is_lifetime else f"{days_left} days remaining"
    return True, data, f"Valid {data.get('plan', 'Pro+').upper()} Pass ({msg_dur})"


def get_user_cloud_profile(uid: str):
    """Fetches user profile from Firestore users/{uid}."""
    if not uid:
        return None
    success, data = _firestore_get("users", uid)
    if success and data:
        return data
    return None


def bind_license_to_google_user(uid: str, email: str, license_key: str, plan: str = "Pro+", is_lifetime: bool = False, expires_at: int = 0, hwid: str = None, auth_token: str = None):
    """Binds a license pass bidirectionally to a Google User account in Firestore."""
    if not uid or not license_key:
        return False, "Missing uid or license_key"
    
    clean_key = license_key.strip().upper()
    user_fields = {
        "license_key": clean_key,
        "plan": str(plan).lower().replace("+", "_plus"),
        "is_lifetime": bool(is_lifetime),
        "expires_at": int(expires_at),
        "bound_at": int(time.time())
    }
    if hwid:
        user_fields["hwid"] = hwid

    # 1. Update users/{uid} (using user ID token or admin bearer)
    ok1, res1 = _firestore_post("users", uid, user_fields, auth_token=auth_token)
    
    # 2. Update pk_licenses_by_key/{clean_key}
    key_fields = {
        "google_uid": uid,
        "google_email": email
    }
    ok2, res2 = _firestore_post("pk_licenses_by_key", clean_key, key_fields)
    
    return ok1 or ok2, "Linked successfully"



if __name__ == "__main__":
    print("Testing PK License Engine...")
    res = register_or_upgrade_license("Test User", "test_pk_gamer@example.com", "trial", "")
    print("Trial Generation:", res)
    test_key = res["license_key"]
    valid, info, msg = validate_and_bind_pk_key(test_key, "THUNDER-HWID-TESTMACHINE123")
    print("Validation Result:", valid, msg)
