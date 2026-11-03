"""
THUNDER — PUBG Mobile Highlight Automation Studio
Hardware ID (HWID) Device Locking & Security Shield
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import subprocess
# Suppress any popup CMD / console windows for all spawned child processes (FFmpeg, FFprobe, etc.)
if os.name == "nt":
    _orig_popen = subprocess.Popen
    def _hidden_popen(*args, **kwargs):
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        si = kwargs.get('startupinfo')
        if si is None:
            si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = si
        return _orig_popen(*args, **kwargs)
    subprocess.Popen = _hidden_popen

import platform

_SHIELD_SALT = b"THUNDER_ESPORTS_MAAKTHUNDER_STUDIO_SECURE_2026_HWID_BIND"
_CACHED_HWID = None

def _get_hwid_cache_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.expanduser("~")
    vault_dir = os.path.join(appdata, "THUNDER_Studio")
    os.makedirs(vault_dir, exist_ok=True)
    return os.path.join(vault_dir, "hwid.cache")

def get_system_hwid():
    """Generates a reproducible, tamper-resistant Hardware ID for the local PC (cached in memory and disk for 0ms access)."""
    global _CACHED_HWID
    if _CACHED_HWID:
        return _CACHED_HWID

    cache_path = _get_hwid_cache_path()
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val.startswith("THUNDER-HWID-") and len(val) >= 20:
                    _CACHED_HWID = val
                    return _CACHED_HWID
        except Exception:
            pass

    components = []
    
    # 1. Motherboard UUID
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if out and len(out) > 5:
            components.append(out)
    except Exception:
        pass

    # 2. Processor ID
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).ProcessorId"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if out and len(out) > 3:
            components.append(out)
    except Exception:
        pass

    # 3. System Drive Serial Number (C:)
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\").VolumeSerialNumber"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if out and len(out) > 2:
            components.append(out)
    except Exception:
        pass

    if not components:
        components.append(platform.node())
        components.append(platform.machine())

    raw_signature = "|".join(components)
    hwid_hash = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()[:20].upper()
    _CACHED_HWID = f"THUNDER-HWID-{hwid_hash}"

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(_CACHED_HWID)
    except Exception:
        pass

    return _CACHED_HWID


def _get_vault_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.expanduser("~")
    vault_dir = os.path.join(appdata, "THUNDER_Studio")
    os.makedirs(vault_dir, exist_ok=True)
    return os.path.join(vault_dir, "thunder_license.vault")


def compute_signature(license_key, hwid, expires_at, plan=""):
    """Generates an HMAC-SHA256 signature binding the key, plan, and expiry to this machine's HWID."""
    if plan:
        norm_plan = str(plan).strip().upper()
        msg = f"{license_key.strip().upper()}::{hwid.strip().upper()}::{expires_at}::{norm_plan}".encode("utf-8")
    else:
        msg = f"{license_key.strip().upper()}::{hwid.strip().upper()}::{expires_at}".encode("utf-8")
    return hmac.new(_SHIELD_SALT, msg, hashlib.sha256).hexdigest()


def _cipher_data(raw_bytes, hwid_str):
    """Symmetric hardware-bound stream cipher to prevent offline Notepad editing."""
    key_stream = hashlib.sha256(_SHIELD_SALT + hwid_str.encode("utf-8")).digest()
    return bytes(b ^ key_stream[i % len(key_stream)] for i, b in enumerate(raw_bytes))


def save_vault(license_key, plan, email, expires_at, days_left):
    """Cryptographically seals and hardware-encrypts license vault to the local PC."""
    current_hwid = get_system_hwid()
    norm_plan = str(plan).strip()
    sig = compute_signature(license_key, current_hwid, expires_at, norm_plan)
    
    vault_data = {
        "license_key": license_key.strip().upper(),
        "hwid": current_hwid,
        "plan": norm_plan,
        "email": email,
        "expires_at": expires_at,
        "days_left": days_left,
        "signature": sig,
        "timestamp": int(time.time())
    }
    
    vault_path = _get_vault_path()
    try:
        raw_json = json.dumps(vault_data, indent=2, ensure_ascii=False).encode("utf-8")
        encrypted_bytes = _cipher_data(raw_json, current_hwid)
        encoded_b64 = base64.b64encode(encrypted_bytes).decode("ascii")
        vault_payload = "--- THUNDER SECURE ENCRYPTED VAULT (DO NOT EDIT) ---\n" + encoded_b64 + "\n"
        with open(vault_path, "w", encoding="utf-8") as f:
            f.write(vault_payload)
        return True
    except Exception as e:
        print(f"[HWID_SHIELD] Failed to save encrypted vault: {e}")
        return False


def load_and_verify_vault():
    """
    Loads license vault, decrypts hardware ciphertext, and strictly verifies against this machine's HWID and HMAC seal.
    Returns (is_valid, data_dict, error_message).
    """
    vault_path = _get_vault_path()
    if not os.path.exists(vault_path):
        return False, None, "No license vault found. Please activate your THUNDER license key."

    current_hwid = get_system_hwid()
    data = None
    try:
        with open(vault_path, "r", encoding="utf-8") as f:
            raw_content = f.read().strip()
            
        if raw_content.startswith("--- THUNDER SECURE ENCRYPTED VAULT"):
            # Decrypt hardware cipher
            lines = raw_content.splitlines()
            b64_str = "".join([l.strip() for l in lines if not l.startswith("---")])
            encrypted_bytes = base64.b64decode(b64_str)
            decrypted_json = _cipher_data(encrypted_bytes, current_hwid).decode("utf-8")
            data = json.loads(decrypted_json)
        elif raw_content.startswith("{"):
            # Legacy plaintext format support
            data = json.loads(raw_content)
        else:
            return False, None, "Corrupted or tampered license vault file."
    except Exception as e:
        return False, None, f"License vault decrypt failed (file was modified or corrupted): {e}"

    if not isinstance(data, dict):
        return False, None, "Invalid license vault structure."

    lic_key = data.get("license_key", "")
    stored_hwid = data.get("hwid", "")
    sig = data.get("signature", "")
    expires_at = data.get("expires_at", 0)
    plan = data.get("plan", "Basic")
    
    # 1. Anti-Tamper: Check Hardware ID match
    if stored_hwid != current_hwid:
        return False, data, "License Key is locked to a different computer (HWID mismatch). Each license is bound to one PC."

    # 2. Anti-Tamper: Cryptographic signature verification (including plan seal)
    expected_sig = compute_signature(lic_key, current_hwid, expires_at, plan)
    legacy_sig = compute_signature(lic_key, current_hwid, expires_at, "")
    
    if hmac.compare_digest(sig, expected_sig):
        pass  # 100% verified with plan seal
    elif hmac.compare_digest(sig, legacy_sig):
        # Legacy vault verified: auto-upgrade seamlessly to plan-sealed encrypted vault
        days_val = data.get("days_left", 14)
        email_val = data.get("email", "")
        save_vault(lic_key, plan, email_val, expires_at, days_val)
    else:
        return False, data, "Security alert: License vault signature has been tampered with or modified."

    # 3. Expiration check
    if expires_at and expires_at > 0:
        now_ts = int(time.time())
        if now_ts > expires_at:
            return False, data, "Your license period has expired. Please upgrade or renew on the official portal."
        # Update remaining days dynamically
        days_left = max(1, int((expires_at - now_ts) // 86400))
        data["days_left"] = days_left
    else:
        data["days_left"] = "Lifetime"

    return True, data, ""


def revoke_vault():
    """Removes stored vault to force re-activation."""
    vault_path = _get_vault_path()
    if os.path.exists(vault_path):
        try:
            os.remove(vault_path)
            return True
        except Exception:
            return False
    return True
