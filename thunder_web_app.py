import os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import time
import json
import datetime
import threading
import requests
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

import urllib.request
import webbrowser
import webview
import http.server
import socketserver
from thunder_core import RenderCancelledError, ThunderEngine
import hwid_shield
import pk_license_engine

def get_resource_path(rel_path):
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            cand = os.path.join(meipass, rel_path)
            if os.path.exists(cand):
                return cand
        cand2 = os.path.join(os.path.dirname(sys.executable), '_internal', rel_path)
        if os.path.exists(cand2):
            return cand2
        cand3 = os.path.join(os.path.dirname(sys.executable), rel_path)
        if os.path.exists(cand3):
            return cand3
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)

USER_DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "THUNDER_Studio")
try:
    os.makedirs(USER_DATA_DIR, exist_ok=True)
except Exception:
    pass

APP_VERSION = "1.1"
CONFIG_FILE = os.path.join(USER_DATA_DIR, "studio_config.json")
SCAN_CACHE_FILE = os.path.join(USER_DATA_DIR, "scan_cache.json")
STUDIO_PROJECT_FILE = os.path.join(USER_DATA_DIR, "studio_project.json")
LOCAL_VERSION_FILE = get_resource_path("version.json")
UPDATE_MANIFEST_URL = "https://maakthunder-studio.web.app/version.json"


_CURRENT_API_INSTANCE = None

def get_user_session_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    vault_dir = os.path.join(appdata, "THUNDER_Studio")
    os.makedirs(vault_dir, exist_ok=True)
    return os.path.join(vault_dir, "thunder_user_session.json")

def load_user_session():
    path = get_user_session_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_user_session(user_data):
    path = get_user_session_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, indent=2)
        return True
    except Exception:
        return False
def get_youtube_channel_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    studio_dir = os.path.join(appdata, "THUNDER_Studio")
    os.makedirs(studio_dir, exist_ok=True)
    return os.path.join(studio_dir, "thunder_youtube_channel.json")

def load_youtube_channel():
    path = get_youtube_channel_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_youtube_channel(channel_data):
    path = get_youtube_channel_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(channel_data, f, indent=2)
        return True
    except Exception:
        return False

def clear_youtube_channel():
    path = get_youtube_channel_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

def clear_user_session():
    path = get_user_session_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

class ThunderStudioAPI:
    def __init__(self):
        global _CURRENT_API_INSTANCE
        _CURRENT_API_INSTANCE = self
        self._window = None
        self.is_scanning = False
        self._stage = "idle"
        self._current_video_idx = 1
        self._total_videos = 1
        self.engine = ThunderEngine(log_callback=self._engine_log, progress_callback=self._progress)
        self.is_processing = False
        self.config = self._load_config()
        try:
            saved_mode = self.config.get("cpu_mode", "normal")
            self.set_cpu_mode(saved_mode)
        except Exception:
            pass


    def get_user_session(self):
        """Returns active Google user session if signed in."""
        session = load_user_session()
        if session and session.get("email"):
            return {"status": "authenticated", "user": session}
        return {"status": "unauthenticated", "user": None}

    def connect_youtube_channel(self):
        """Launches real YouTube OAuth & channel picker in default browser."""
        try:
            url = "https://maakthunder-studio.web.app/youtube_connect.html?port=54321&auto=1"
            webbrowser.open(url)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def disconnect_youtube_channel(self):
        """Disconnects the linked YouTube channel."""
        try:
            clear_youtube_channel()
            if self._window:
                self._window.evaluate_js("if (window.onYouTubeDisconnected) window.onYouTubeDisconnected();")
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def create_youtube_playlist(self, title, privacy="public"):
        """Creates a new playlist on the connected YouTube channel via YouTube Data API."""
        ch = load_youtube_channel()
        if not ch or not ch.get("token"):
            return {"status": "error", "message": "No YouTube channel connected. Please connect your channel first."}
        token = ch["token"]
        url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"
        payload = json.dumps({
            "snippet": {
                "title": title,
                "description": "Created by THUNDER Studio — Automated PUBG Montage Engine"
            },
            "status": {
                "privacyStatus": privacy
            }
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                new_pl = {
                    "id": data.get("id"),
                    "title": data.get("snippet", {}).get("title", title),
                    "itemCount": 0
                }
                pls = ch.get("playlists", [])
                pls.insert(0, new_pl)
                ch["playlists"] = pls
                save_youtube_channel(ch)
                return {"status": "ok", "playlist": new_pl}
        except urllib.error.HTTPError as e:
            return {"status": "error", "message": f"YouTube API Error ({e.code}): " + e.read().decode()[:200]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_connected_youtube_channel(self):
        """Returns the currently connected YouTube channel profile if any."""
        ch = load_youtube_channel()
        if ch and ch.get("channel_id"):
            return {"status": "connected", "channel": ch}
        return {"status": "disconnected", "channel": None}

    def start_google_login(self):
        """Launches Google OAuth login loopback in user's default browser."""
        try:
            auth_url = "https://maakthunder-studio.web.app/app_auth.html?port=54321"
            webbrowser.open(auth_url)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def logout_user(self):
        """Logs out active Google session and clears local session cache."""
        try:
            clear_user_session()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def set_cpu_mode(self, mode):
        """Sets Windows process priority, CPU affinity mask, and engine throttling across 3 tiers (Normal 25%, Balanced 50%, Turbo 75%)."""
        try:
            m_str = str(mode).lower().replace(" ", "").replace("_", "").replace("+", "plus").replace("%", "")
            if "turbo" in m_str or "75" in m_str or "max" in m_str:
                target_mode = "turbo"
            elif "balanced" in m_str or "50" in m_str or "medium" in m_str:
                target_mode = "balanced"
            else:
                target_mode = "normal"

            self.config["cpu_mode"] = target_mode
            self._save_config()

            if hasattr(self, 'engine'):
                self.engine.cpu_mode = target_mode

            total_cores = min(64, os.cpu_count() or 16)
            cores_25 = max(2, int(round(total_cores * 0.25)))  # e.g. 4 on 16-core
            cores_50 = max(2, int(round(total_cores * 0.50)))  # e.g. 8 on 16-core
            cores_75 = max(3, int(round(total_cores * 0.75)))  # e.g. 12 on 16-core (Strict ceiling)

            # All modes strictly run with BELOW_NORMAL_PRIORITY_CLASS so Windows and Chrome NEVER freeze
            priority_val = 0x00004000

            if target_mode == "turbo":
                allowed_cores = cores_75
                log_tag = f"🚀 Turbo Mode ({allowed_cores}/{total_cores} Cores • 75% Power - Fast & Safe Max)"
            elif target_mode == "balanced":
                allowed_cores = cores_50
                log_tag = f"⚡ Balanced Mode ({allowed_cores}/{total_cores} Cores • 50% Power - Smooth Multitasking)"
            else:
                allowed_cores = cores_25
                log_tag = f"🛡️ Normal Mode ({allowed_cores}/{total_cores} Cores • 25% Power - Safe & Zero Game Lag)"

            affinity_mask = (1 << allowed_cores) - 1

            # OpenCV threading control
            try:
                import cv2
                cv2.setNumThreads(allowed_cores)
            except Exception:
                pass

            # Windows Process Priority and Hardware Core Affinity
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.SetPriorityClass.restype = wintypes.BOOL
            kernel32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
            kernel32.SetProcessAffinityMask.restype = wintypes.BOOL

            h = kernel32.GetCurrentProcess()
            kernel32.SetPriorityClass(h, priority_val)
            kernel32.SetProcessAffinityMask(h, affinity_mask)

            self._ui_log(f"⚡ Performance Profile: {log_tag}")
            return {
                "status": "ok",
                "mode": target_mode,
                "affinity_cores": allowed_cores,
                "total_cores": total_cores,
                "cores_25": cores_25,
                "cores_50": cores_50,
                "cores_75": cores_75,
                "normal_cores": cores_25,
                "balanced_cores": cores_50,
                "turbo_cores": cores_75
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def export_diagnostic_report(self):
        """Generates a sanitized diagnostic report file on Desktop and opens it."""
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.exists(desktop):
                desktop = USER_DATA_DIR
            out_file = os.path.join(desktop, "THUNDER_Diagnostic_Report.txt")

            scan_cache = self._load_scan_cache()
            total_cached_clips = sum(len(v.get("clips", [])) for v in scan_cache.values() if isinstance(v, dict))

            import platform
            content = [
                "============================================================",
                "   THUNDER STUDIO - DIAGNOSTIC & ERROR REPORT",
                "============================================================",
                f"Generated At: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"App Version: {APP_VERSION}",
                f"Operating System: {platform.system()} {platform.release()} ({platform.version()})",
                f"Architecture: {platform.machine()}",
                f"CPU Cores (Logical): {os.cpu_count()}",
                f"Python Runtime: {platform.python_version()}",
                "------------------------------------------------------------",
                "FFMPEG / HARDWARE ENCODER STATUS:",
                f"FFmpeg Available: {bool(self.engine.ffmpeg_bin)}",
                f"FFmpeg Path: {self.engine.ffmpeg_bin}",
                f"Hardware NVENC Accelerated: True",
                "------------------------------------------------------------",
                "SCAN & CLIP CACHE METRICS:",
                f"Total Cached Videos: {len(scan_cache)}",
                f"Total Cached Clips: {total_cached_clips}",
                "------------------------------------------------------------",
                "SECURITY & PRIVACY NOTICE:",
                "This report contains ONLY hardware & error metrics.",
                "No passwords, license keys, or video contents are included.",
                "============================================================"
            ]

            with open(out_file, "w", encoding="utf-8") as f:
                f.write("\n".join(content))

            try:
                os.startfile(desktop)
            except Exception:
                pass

            return {"status": "ok", "path": out_file}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def open_discord_support(self):
        """Opens user Discord support link in browser."""
        url = self.config.get("discord_url") or "https://discord.gg/mudxsPXaCW"
        webbrowser.open(url)
        return {"status": "ok", "url": url}

    def set_window(self, window):
        self._window = window

    def _load_config(self):
        user_videos_dir = os.path.join(os.path.expanduser("~"), "Videos", "THUNDER Highlights")
        
        # Smart defaults for brand new users on any PC
        # Video folder and Export folder are compulsory, Music is optional (empty = pure game audio)
        default_cfg = {
            "player_ign": "",
            "channel_name": "",
            "yt": "",
            "tt": "",
            "fb": "",
            "music_offset": "00:55",
            "export_folder": user_videos_dir,
            "capture_folder": "",
            "music_file": "",
            "plan": "Pro+",
            "discord_url": "https://discord.gg/mudxsPXaCW",
            "license_status": "trial",
            "trial_start_date": datetime.datetime.now().isoformat(),
            "trial_days": 15,
            "license_key": "",
            "hide_ign_popup": False
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_cfg.update(data)
            except Exception as e:
                print("Error loading config:", e)
        return default_cfg

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Error saving config:", e)

    def _load_scan_cache(self):
        if os.path.exists(SCAN_CACHE_FILE):
            try:
                with open(SCAN_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print("Error loading scan cache:", e)
        return {}

    def _save_scan_cache(self, cache_data):
        try:
            with open(SCAN_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Error saving scan cache:", e)

    def save_studio_project(self, project_data):
        try:
            with open(STUDIO_PROJECT_FILE, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)
            return {"status": "ok", "message": "Project saved successfully"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def load_studio_project(self):
        if os.path.exists(STUDIO_PROJECT_FILE):
            try:
                with open(STUDIO_PROJECT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and data.get("scan_duration"):
                        self._last_scan_duration = float(data["scan_duration"])
                    return {"status": "ok", "project": data}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "empty", "project": None}

    def has_cached_scan(self, file_paths=None):
        """Checks if any of the specified video files have preserved scan results in cache."""
        try:
            cache = self._load_scan_cache()
            if not cache:
                return False
            if not file_paths:
                file_paths = getattr(self, "selected_videos", []) or []
            if not file_paths:
                scan_res = self.scan_capture_folder()
                file_paths = scan_res.get("files", [])
            for p in file_paths:
                name = os.path.basename(p)
                entry = cache.get(p) or cache.get(name)
                if entry and entry.get("clips"):
                    return True
            return False
        except Exception:
            return False

    def clear_scan_cache(self):
        try:
            if os.path.exists(SCAN_CACHE_FILE):
                os.remove(SCAN_CACHE_FILE)
            return {"status": "ok", "message": "Scan cache cleared"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def open_polar_trial_page(self):
        """Opens the official Polar checkout for the 15-Day Free Trial ($0)."""
        try:
            webbrowser.open("https://buy.polar.sh/polar_cl_d6GLSYIZRPoQLXgEQehOxevXfpAGBSfLzDYuR4C9V7i")
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def open_polar_store_page(self):
        """Opens the official Polar 15-Day Free Trial ($0) checkout during trial testing phase."""
        try:
            webbrowser.open("https://buy.polar.sh/polar_cl_d6GLSYIZRPoQLXgEQehOxevXfpAGBSfLzDYuR4C9V7i")
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # Backward compatibility aliases
    open_whop_trial_page = open_polar_trial_page
    open_whop_store_page = open_polar_store_page

    def open_pk_portal_page(self):
        """Opens the Pakistani Domestic Portal (Easypaisa / JazzCash / Raast)."""
        try:
            webbrowser.open("https://maakthunder-studio.web.app")
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def deactivate_license(self):
        """Clears local license vault so user can test the license activation gate."""
        try:
            hwid_shield.revoke_vault()
            self.config["license_key"] = ""
            self.config["license_status"] = "locked"
            self.config["plan"] = "Locked"
            self._save_config()
            return {"status": "ok", "message": "Machine license cleared."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _async_cloud_license_check(self, key, vault_data):
        """Runs cloud revocation and expiration checks in background thread to avoid freezing the UI thread."""
        def _worker():
            try:
                if not key.startswith("THUNDER-PK-"):
                    return
                ok, server_doc = pk_license_engine._firestore_get("pk_licenses_by_key", key)
                if not ok or not server_doc:
                    doc_id = key.replace("-", "_")
                    ok, server_doc = pk_license_engine._firestore_get("pk_licenses_by_key", doc_id)
                if not ok or not server_doc:
                    return

                status = str(server_doc.get("status", "active")).lower()
                if status in ["revoked", "canceled", "cancelled", "banned"]:
                    hwid_shield.revoke_vault()
                    self.config["license_key"] = ""
                    self.config["license_status"] = "locked"
                    self.config["plan"] = "Locked"
                    self._save_config()
                    self._ui_log(f"⚠️ License Key '{key}' was revoked by Administrator. Studio locked.")
                    if self._window:
                        self._window.evaluate_js("updateLicenseUI()")
                    return

                server_plan = server_doc.get("plan", vault_data.get("plan", "Pro+"))
                server_expiry = int(server_doc.get("expires_at", vault_data.get("expires_at", 0)))
                now_ts = int(time.time())
                is_lifetime = (
                    server_doc.get("is_lifetime") is True
                    or str(server_doc.get("days", "")).lower() == "lifetime"
                    or server_expiry == 0
                    or server_expiry > 2500000000
                )

                if not is_lifetime and server_expiry and now_ts > server_expiry:
                    hwid_shield.revoke_vault()
                    self.config["license_key"] = ""
                    self.config["license_status"] = "locked"
                    self.config["plan"] = "Locked"
                    self._save_config()
                    if self._window:
                        self._window.evaluate_js("updateLicenseUI()")
                    return

                if is_lifetime:
                    server_days = "Lifetime"
                    server_expiry = 0
                else:
                    server_days = max(1, int((server_expiry - now_ts) // 86400)) if server_expiry else vault_data.get("days_left", 14)

                p_clean = str(server_plan).lower().strip()
                if p_clean in ["pro+", "pro_plus", "trial", "lifetime"]:
                    mapped_plan = "Pro+"
                elif p_clean == "basic":
                    mapped_plan = "Basic"
                else:
                    mapped_plan = "Pro"

                if mapped_plan != vault_data.get("plan") or str(server_days) != str(vault_data.get("days_left")):
                    vault_data["plan"] = mapped_plan
                    vault_data["days_left"] = server_days
                    vault_data["expires_at"] = server_expiry
                    vault_data["is_lifetime"] = is_lifetime
                    hwid_shield.save_vault(key, mapped_plan, vault_data.get("email", ""), server_expiry, server_days)
                    if self._window:
                        self._window.evaluate_js("updateLicenseUI()")
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def sync_cloud_license(self):
        '''Immediately performs a live sync with Firestore for the active license.
        Updates the local cryptographically signed vault and returns fresh status & days.'''
        try:
            is_valid, vault_data, err_msg = hwid_shield.load_and_verify_vault()
            if not is_valid or not vault_data:
                return {"status": "error", "message": "No active license vault found locally."}

            key = vault_data.get("license_key", "").strip()
            if not key:
                return {"status": "error", "message": "No active license key found in vault."}


            # Cloud check
            ok, server_doc = pk_license_engine._firestore_get("pk_licenses_by_key", key)
            if not ok or not server_doc:
                doc_id = key.replace("-", "_")
                ok, server_doc = pk_license_engine._firestore_get("pk_licenses_by_key", doc_id)
            if not ok or not server_doc:
                import hashlib
                key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
                ok, server_doc = pk_license_engine._firestore_get("pk_licenses_by_key", key_hash)
            if not ok or not server_doc:
                info = pk_license_engine.lookup_license_by_identifier(key)
                if info.get("found"):
                    server_doc = {
                        "status": info.get("status", "active"),
                        "plan": info.get("plan", "pro_plus"),
                        "expires_at": info.get("expires_at", 0),
                        "email": info.get("email", "")
                    }
                    ok = True

            if not ok or not server_doc:
                return {"status": "error", "message": "Could not locate license on cloud server. Please check your internet connection."}

            status = str(server_doc.get("status", "active")).lower()
            if status in ["revoked", "canceled", "cancelled", "banned"]:
                hwid_shield.revoke_vault()
                self.config["license_key"] = ""
                self.config["license_status"] = "locked"
                self.config["plan"] = "Locked"
                self._save_config()
                if self._window:
                    self._window.evaluate_js("updateLicenseUI()")
                return {"status": "revoked", "message": "License was revoked by Administrator."}

            now_ts = int(time.time())
            server_expiry = int(server_doc.get("expires_at", 0))
            is_lifetime = (
                server_doc.get("is_lifetime") is True
                or str(server_doc.get("days", "")).lower() == "lifetime"
                or server_expiry == 0
                or server_expiry > 2500000000
            )

            if not is_lifetime and server_expiry and now_ts > server_expiry:
                hwid_shield.revoke_vault()
                self.config["license_key"] = ""
                self.config["license_status"] = "locked"
                self.config["plan"] = "Locked"
                self._save_config()
                if self._window:
                    self._window.evaluate_js("updateLicenseUI()")
                return {"status": "expired", "message": "License has expired. Please renew on portal."}

            server_plan = server_doc.get("plan", vault_data.get("plan", "Pro+"))
            if is_lifetime:
                server_days = "Lifetime"
                server_expiry = 0
            else:
                server_days = max(1, int((server_expiry - now_ts) // 86400)) if server_expiry else 15

            p_clean = str(server_plan).lower().strip()
            if p_clean in ["pro+", "pro_plus", "trial", "lifetime"]:
                mapped_plan = "Pro+"
            elif p_clean == "basic":
                mapped_plan = "Basic"
            else:
                mapped_plan = "Pro"

            email = server_doc.get("email") or vault_data.get("email", "")
            hwid_shield.save_vault(key, mapped_plan, email, server_expiry, server_days)

            # Update in-memory config
            self.config["license_key"] = key
            self.config["license_status"] = "active"
            self.config["plan"] = mapped_plan
            self._save_config()

            if self._window:
                self._window.evaluate_js("updateLicenseUI()")

            sync_msg = "Successfully synchronized! Permanent Lifetime Access Active." if is_lifetime else f"Successfully synchronized! {server_days} Days Remaining."

            return {
                "status": "ok",
                "message": sync_msg,
                "days_left": server_days,
                "is_lifetime": is_lifetime,
                "plan": mapped_plan,
                "license_key": key
            }
        except Exception as e:
            return {"status": "error", "message": f"Sync failed: {str(e)}"}

    def get_license_info(self):
        """Instantly queries local HWID vault (0ms - zero UI lag) and triggers background cloud check."""
        hwid = hwid_shield.get_system_hwid()
        is_valid, vault_data, err_msg = hwid_shield.load_and_verify_vault()
        
        if is_valid and vault_data:
            key = vault_data.get("license_key", "")
            
            # Non-blocking background verification (never blocks modal opening)
            if key and (key.startswith("THUNDER-PK-") or key.startswith("THUNDER-")):
                    self._async_cloud_license_check(key, vault_data)

            plan = vault_data.get("plan", "15-Day Creator Trial")
            days_left = vault_data.get("days_left", 15)
            email = vault_data.get("email", "")
            is_lifetime = (
                vault_data.get("is_lifetime") is True
                or str(days_left).lower() == "lifetime"
                or vault_data.get("expires_at") == 0
                or "LIFETIME" in key
            )
            return {
                "status": "active",
                "is_active": True,
                "is_locked": False,
                "plan": plan,
                "days_left": "Lifetime" if is_lifetime else days_left,
                "is_lifetime": is_lifetime,
                "is_trial": "trial" in plan.lower() and not is_lifetime,
                "is_expired": False,
                "license_key": key,
                "hwid": hwid,
                "email": email,
                "watermark_active": False
            }
        else:
            return {
                "status": "locked",
                "is_active": False,
                "is_locked": True,
                "error": err_msg or "License Key Required",
                "plan": "Locked",
                "days_left": 0,
                "is_trial": False,
                "is_expired": "expired" in str(err_msg).lower(),
                "license_key": "",
                "hwid": hwid,
                "watermark_active": True
            }

    def activate_license_key(self, key_str):
        """Validates key with Polar / Pakistan Domestic Licensing Engine and locks license to current machine HWID."""
        key = key_str.strip().upper() if key_str else ""
        if not key or len(key) < 6:
            return {"success": False, "error": "Invalid License Key format. Please enter a valid key (e.g. THUNDER-... or THUNDER-PK-...)."} 


        hwid = hwid_shield.get_system_hwid()

        # 1. PAKISTANI DOMESTIC LICENSE VALIDATION (Firestore-backed)
        if key.startswith("THUNDER-PK-"):
            try:
                valid, data, msg = pk_license_engine.validate_and_bind_pk_key(key, hwid)
                if not valid:
                    return {"success": False, "error": msg}

                tier_name = (data.get("plan") or "PRO+").upper()
                if tier_name == "TRIAL":
                    tier = "Pro+"  # 15-Day Free Trial activates full Pro+ features!
                elif tier_name == "BASIC":
                    tier = "Basic"
                elif tier_name in ["PRO+", "PRO_PLUS"]:
                    tier = "Pro+"
                else:
                    tier = "Pro"

                now_ts = int(time.time())
                expires_at = int(data.get("expires_at", 0))
                is_lifetime = (
                    data.get("is_lifetime") is True
                    or str(data.get("days", "")).lower() == "lifetime"
                    or expires_at == 0
                    or expires_at > 2500000000
                )
                if is_lifetime:
                    days_left = "Lifetime"
                    expires_at = 0
                else:
                    days_left = max(1, int((expires_at - now_ts) // 86400)) if expires_at else 15
                email = data.get("email", "pk_user@maakthunder.com")

                saved = hwid_shield.save_vault(key, tier, email, expires_at, days_left)
                if not saved:
                    return {"success": False, "error": "Failed to create secure HWID vault on system."}

                self.config["license_key"] = key
                self.config["license_status"] = "active"
                self.config["plan"] = tier
                self.config["user_email"] = email
                self.config["trial_days"] = days_left
                self._save_config()

                self._ui_log(f"Key Activated: {tier} ({days_left} Days Left) for {email}")
                # Auto-bind newly activated key to logged-in Google account in Firestore
                try:
                    user_sess = load_user_session()
                    if user_sess and user_sess.get("uid"):
                        pk_license_engine.bind_license_to_google_user(
                            uid=user_sess["uid"],
                            email=user_sess.get("email", email),
                            license_key=key,
                            plan=tier,
                            is_lifetime=is_lifetime,
                            expires_at=expires_at,
                            hwid=hwid,
                            auth_token=user_sess.get("token")
                        )
                except Exception as e_bind:
                    print("Auto-bind key to Google user note:", e_bind)

                return {
                    "success": True,
                    "plan": tier,
                    "days_left": days_left,
                    "message": f"Successfully activated {tier}! You have {days_left} days of full access. (Tip: Save your key to search or upgrade your plan anytime on the portal)."
                }
            except Exception as e:
                return {"success": False, "error": f"Error validating Pakistani license: {e}"}

        # 2. POLAR GLOBAL LICENSE VALIDATION (Polar API)
        POLAR_ORG_ID = "a2fd55ea-dac9-40df-9809-d6b739d4ceba"
        POLAR_TOKEN = "polar_oat_xhI1lGZChHbWx4zHayyNRtYcyisva6XxPiVjh2boOmw"
        try:
            val_url = "https://api.polar.sh/v1/license-keys/validate"
            val_payload = json.dumps({"key": key, "organization_id": POLAR_ORG_ID}).encode("utf-8")
            val_req = urllib.request.Request(
                val_url,
                data=val_payload,
                headers={
                    "Authorization": f"Bearer {POLAR_TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "THUNDER-Studio-Validator/1.0"
                },
                method="POST"
            )

            try:
                with urllib.request.urlopen(val_req, timeout=10) as resp:
                    lic_info = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as he:
                err_body = he.read().decode("utf-8")
                if "no longer active" in err_body or he.code == 404:
                    return {"success": False, "error": "This Polar license key is inactive, expired, or has been revoked."}
                return {"success": False, "error": f"Polar validation error ({he.code}): {he.reason}"}

            status = str(lic_info.get("status", "active")).lower()
            if status != "granted":
                return {"success": False, "error": f"License key is {status}. Please ensure your trial/subscription is active on Polar."}

            # Check expiry
            expires_at_str = lic_info.get("expires_at")
            days_left = 15
            now_ts = int(time.time())
            expires_at = now_ts + (15 * 86400)
            if expires_at_str:
                try:
                    from datetime import datetime
                    clean_iso = str(expires_at_str).replace('Z', '+00:00')
                    dt = datetime.fromisoformat(clean_iso)
                    expires_at = int(dt.timestamp())
                    days_left = max(1, int((expires_at - now_ts) // 86400))
                except Exception:
                    try:
                        import dateutil.parser
                        dt = dateutil.parser.isoparse(expires_at_str)
                        expires_at = int(dt.timestamp())
                        days_left = max(1, int((expires_at - now_ts) // 86400))
                    except Exception:
                        pass

            customer = lic_info.get("customer") or {}
            email = customer.get("email", "polar_customer@maakthunder.com")
            tier = "Pro+"

            saved = hwid_shield.save_vault(key, tier, email, expires_at, days_left)
            if not saved:
                return {"success": False, "error": "Failed to create secure HWID vault on system."}

            self.config["license_key"] = key
            self.config["license_status"] = "active"
            self.config["plan"] = tier
            self.config["user_email"] = email
            self.config["trial_days"] = days_left
            self._save_config()

            self._ui_log(f"Key Activated: {tier} ({days_left} Days Left) for {email}")
            return {
                "success": True,
                "plan": tier,
                "days_left": days_left,
                "message": f"Successfully activated {tier}! You have {days_left} days of full access. (Tip: Check your email for your Polar Customer Portal link to view or manage your plan)."
            }

        except Exception as e:
            return {"success": False, "error": f"Connection error: {e}"}

    def check_scan_cache(self, files=None):
        """Checks how many of the given video files have an existing cached scan."""
        try:
            if not files:
                files = self.config.get("selected_videos", [])
            scan_cache = self._load_scan_cache()
            cached_count = 0
            cached_names = []
            for f in files:
                f_name = os.path.basename(f)
                entry = scan_cache.get(f) or scan_cache.get(f_name)
                if entry and entry.get("clips") and os.path.exists(f):
                    curr_size = os.path.getsize(f)
                    curr_mtime = os.path.getmtime(f)
                    if entry.get("size") == curr_size and abs(entry.get("mtime", 0) - curr_mtime) < 5:
                        cached_count += 1
                        cached_names.append(f_name)
            return {"cached_count": cached_count, "total_files": len(files), "cached_names": cached_names}
        except Exception as e:
            return {"cached_count": 0, "total_files": len(files or []), "cached_names": [], "error": str(e)}

    def get_config(self):
        cfg = dict(self.config)
        total_cores = min(64, os.cpu_count() or 16)
        cores_25 = max(2, int(round(total_cores * 0.25)))
        cores_50 = max(2, int(round(total_cores * 0.50)))
        cores_75 = max(3, int(round(total_cores * 0.75)))
        cfg["total_cores"] = total_cores
        cfg["cores_25"] = cores_25
        cfg["cores_50"] = cores_50
        cfg["cores_75"] = cores_75
        cfg["normal_cores"] = cores_25
        cfg["balanced_cores"] = cores_50
        cfg["turbo_cores"] = cores_75
        cfg["cpu_mode"] = self.config.get("cpu_mode", "normal")
        return cfg

    def save_settings(self, cfg_data):
        self.config.update(cfg_data)
        self._save_config()
        return True

    def _engine_log(self, message):
        print(message)
        # Internal engine logs are strictly for backend diagnostics/stdout.
        # NEVER leak raw frame-by-frame candidates or internal fight detection spam into the user console.
        msg_str = str(message)
        if self.is_scanning or not self.is_processing:
            return
        if any(token in msg_str for token in ["[FIGHT DETECTED]", "[Step", "Frame", "OCR", "Candidate", "Cluster", "Activity:"]):
            return
        if self._window:
            safe_msg = json.dumps(msg_str)
            self._window.evaluate_js(f"addLog({safe_msg})")

    def _ui_log(self, message):
        print(message)
        if self._window:
            safe_msg = json.dumps(str(message))
            self._window.evaluate_js(f"addLog({safe_msg})")

    def _set_ui_progress(self, pct, status_text=""):
        if self._window:
            safe_txt = json.dumps(str(status_text))
            self._window.evaluate_js(f"setProgress({int(pct)}, {safe_txt})")

    def _progress(self, current, total):
        # Step-wise progress during frame-by-frame scan
        if self._stage == "scanning" and total > 0 and self._total_videos > 0:
            chunk = 60.0 / self._total_videos
            base = 5.0 + (self._current_video_idx - 1) * chunk
            curr_chunk = (float(current) / float(total)) * chunk
            overall_pct = min(65, int(base + curr_chunk))
            self._set_ui_progress(overall_pct, f"Scanning match [{self._current_video_idx}/{self._total_videos}]: {int(current)}s / {int(total)}s")

    def _is_basic_plan(self):
        """Checks if current machine is strictly on Basic tier (Trial activates full Pro+)."""
        try:
            is_valid, vault_data, _ = hwid_shield.load_and_verify_vault()
            plan_str = (vault_data.get("plan") if (is_valid and vault_data) else self.config.get("plan", "Basic")).upper()
            if "TRIAL" in plan_str or "PRO" in plan_str or "LIFETIME" in plan_str:
                return False
            return "BASIC" in plan_str
        except Exception:
            return False

    def scan_capture_folder(self, folder=None):
        is_valid, _, err_msg = hwid_shield.load_and_verify_vault()
        if not is_valid:
            return {"folder": folder or "", "files": [], "count": 0, "total_mins": 0, "file_names": [], "error": err_msg}
        if not folder:
            folder = self.config.get("capture_folder", r"d:\Data\Capture\Ui")
            if not os.path.exists(folder):
                folder = r"d:\Data\Capture"

        if not os.path.exists(folder):
            return {"folder": folder, "files": [], "count": 0, "total_mins": 0, "file_names": []}

        exts = ('.mp4', '.mkv', '.mov', '.avi')
        try:
            files = [
                os.path.join(folder, f) for f in os.listdir(folder)
                if f.lower().endswith(exts) and not f.startswith('.')
            ]
            files.sort()

            total_sec = 0
            for f in files:
                try:
                    import cv2
                    cap = cv2.VideoCapture(f)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30
                    fc = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                    cap.release()
                    if fps > 0:
                        total_sec += (fc / fps)
                except Exception:
                    pass

            mins = int(round(total_sec / 60))
            warning_msg = None
            if self._is_basic_plan() and len(files) > 5:
                files = files[:5]
                warning_msg = "⚡ Basic Plan Notice: Folder scan is capped at 5 videos at once. Upgrade to Pro/Pro+ for unlimited folder queueing!"
                self._ui_log(f"⚠️ {warning_msg}")

            return {
                "folder": folder,
                "files": files,
                "count": len(files),
                "total_mins": mins,
                "file_names": [os.path.basename(f) for f in files],
                "warning": warning_msg
            }
        except Exception as e:
            print("Error scanning capture folder:", e)
            return {"folder": folder, "files": [], "count": 0, "total_mins": 0, "file_names": [], "error": str(e)}

    def select_files(self):
        if not self._window:
            return {"files": [], "count": 0, "total_mins": 0, "file_names": []}
        file_types = ('Video Files (*.mp4;*.mkv;*.mov;*.avi)', 'All files (*.*)')
        dialog_type = getattr(webview.FileDialog, 'OPEN', webview.OPEN_DIALOG)
        result = self._window.create_file_dialog(dialog_type, allow_multiple=True, file_types=file_types)
        if not result:
            return {"files": [], "count": 0, "total_mins": 0, "file_names": []}
        files = list(result)
        total_sec = 0
        for f in files:
            try:
                import cv2
                cap = cv2.VideoCapture(f)
                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                fc = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                cap.release()
                if fps > 0:
                    total_sec += (fc / fps)
            except Exception:
                pass
        mins = int(round(total_sec / 60))
        warning_msg = None
        if self._is_basic_plan() and len(files) > 5:
            files = files[:5]
            warning_msg = "⚡ Basic Plan Notice: You selected more than 5 videos. Basic is capped at 5 videos at once. Upgrade to Pro/Pro+ for unlimited batch queue!"
            self._ui_log(f"⚠️ {warning_msg}")

        return {
            "files": files,
            "count": len(files),
            "total_mins": mins,
            "file_names": [os.path.basename(f) for f in files],
            "warning": warning_msg
        }

    def select_folder(self):
        if not self._window:
            return {"files": [], "count": 0, "total_mins": 0, "file_names": []}
        dialog_type = getattr(webview.FileDialog, 'FOLDER', webview.FOLDER_DIALOG)
        result = self._window.create_file_dialog(dialog_type)
        if not result or len(result) == 0:
            return {"files": [], "count": 0, "total_mins": 0, "file_names": []}
        folder = result[0]
        self.config["capture_folder"] = folder
        self._save_config()
        return self.scan_capture_folder(folder)

    def browse_export(self):
        if not self._window:
            return ""
        dialog_type = getattr(webview.FileDialog, 'FOLDER', webview.FOLDER_DIALOG)
        result = self._window.create_file_dialog(dialog_type)
        return result[0] if result and len(result) > 0 else ""

    def browse_music(self):
        if not self._window:
            return ""
        file_types = ('Audio Files (*.mp3;*.wav;*.m4a;*.flac)', 'All files (*.*)')
        dialog_type = getattr(webview.FileDialog, 'OPEN', webview.OPEN_DIALOG)
        result = self._window.create_file_dialog(dialog_type, allow_multiple=False, file_types=file_types)
        return result[0] if result and len(result) > 0 else ""

    def get_unique_export_path(self, folder, base_name, ext=".mp4"):
        candidate = os.path.join(folder, f"{base_name}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter = 1
        while True:
            candidate = os.path.join(folder, f"{base_name} ({counter}){ext}")
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    def _verify_tier_and_format(self, req_plan, req_edit_level, req_fmt):
        """Strict anti-tamper tier verification against hardware cryptographically sealed vault."""
        is_valid, vault_data, _ = hwid_shield.load_and_verify_vault()
        if is_valid and vault_data:
            v_plan = str(vault_data.get("plan", "Basic")).lower()
            if "pro+" in v_plan or "pro_plus" in v_plan or "lifetime" in v_plan:
                verified_tier = "Pro+"
            elif "pro" in v_plan:
                verified_tier = "Pro"
            else:
                verified_tier = "Basic"
        else:
            verified_tier = "Basic"

        req_lvl_str = str(req_edit_level).lower()
        if "pro+" in req_lvl_str or "pro_plus" in req_lvl_str:
            eff_level = "Pro+"
        elif "basic" in req_lvl_str:
            eff_level = "Basic"
        else:
            eff_level = "Pro"

        if verified_tier == "Basic":
            return "Basic", "Basic", "landscape"
        elif verified_tier == "Pro":
            eff_fmt = "vertical" if req_fmt == "both" else req_fmt
            return "Pro", ("Basic" if eff_level == "Basic" else "Pro"), eff_fmt
        else:
            # Pro+ tier allows ALL formats (landscape, vertical, both) with zero restrictions
            return "Pro+", eff_level, req_fmt

    def get_output_videos(self, folder=None):
        target_dir = folder or self.config.get("export_folder", r"D:\Data\Capture\Edited")
        if target_dir and os.path.exists(target_dir):
            if self.config.get("export_folder") != target_dir:
                self.config["export_folder"] = target_dir
                self._save_config()
        if not os.path.exists(target_dir):
            return []
        results = []
        exts = ('.mp4', '.mkv', '.mov')
        try:
            # Search root target_dir and dedicated subfolders (Landscape, Vertical Shorts, etc.)
            search_dirs = [target_dir]
            for entry in os.listdir(target_dir):
                sub_p = os.path.join(target_dir, entry)
                if os.path.isdir(sub_p):
                    # Skip Thumbnails and Social Kits directories for video search
                    if entry.lower() in ("thumbnails", "social kits", "socialkits", "social kit", "social_kits"):
                        continue
                    search_dirs.append(sub_p)

            folder_thumbs = os.path.join(target_dir, "Thumbnails")
            folder_kits = os.path.join(target_dir, "Social Kits")

            found_files = []
            for s_dir in search_dirs:
                if not os.path.exists(s_dir):
                    continue
                for f in os.listdir(s_dir):
                    if f.lower().endswith(exts):
                        full_path = os.path.join(s_dir, f)
                        try:
                            mtime = os.path.getmtime(full_path)
                            found_files.append((mtime, f, full_path, s_dir))
                        except Exception:
                            continue

            # Sort all videos by newest first
            found_files.sort(key=lambda x: x[0], reverse=True)

            for mtime, f, full_path, curr_dir in found_files:
                sz_mb = round(os.path.getsize(full_path) / (1024 * 1024), 1)
                date_str = datetime.datetime.fromtimestamp(mtime).strftime("%b %d, %Y %I:%M %p")
                is_vert = "vert" in f.lower() or "short" in f.lower() or "vertical" in curr_dir.lower()
                fmt_desc = "9:16 Shorts • 1080x1920" if is_vert else "16:9 Landscape • 1080p 60fps"

                stem = os.path.splitext(f)[0]
                # Robust thumbnail matching in Thumbnails/, video folder, or root target_dir
                thumb_candidates = [
                    os.path.join(folder_thumbs, f"{stem}.jpg"),
                    os.path.join(folder_thumbs, f"{stem.replace('Highlights_', 'Thumbnail_')}.jpg"),
                    os.path.join(folder_thumbs, f"{stem.replace('Highlights_Landscape', 'Thumbnail_Landscape').replace('Highlights_Vertical_Shorts', 'Thumbnail_Vertical_Shorts')}.jpg"),
                    os.path.join(curr_dir, f"{stem}.jpg"),
                    os.path.join(curr_dir, f"{stem.replace('Highlights_', 'Thumbnail_')}.jpg"),
                    os.path.join(curr_dir, f"{stem.replace('Highlights_Landscape', 'Thumbnail_Landscape').replace('Highlights_Vertical_Shorts', 'Thumbnail_Vertical_Shorts')}.jpg"),
                    os.path.join(target_dir, f"{stem}.jpg"),
                    os.path.join(target_dir, f"{stem.replace('Highlights_', 'Thumbnail_')}.jpg"),
                    os.path.join(target_dir, f"{stem.replace('Highlights_Landscape', 'Thumbnail_Landscape').replace('Highlights_Vertical_Shorts', 'Thumbnail_Vertical_Shorts')}.jpg"),
                    os.path.join(folder_thumbs, "THUNDER_Thumbnail_Vertical_Shorts.jpg" if is_vert else "THUNDER_Thumbnail_Landscape.jpg"),
                    os.path.join(folder_thumbs, "THUNDER_Thumbnail.jpg"),
                    os.path.join(target_dir, "THUNDER_Thumbnail_Vertical_Shorts.jpg" if is_vert else "THUNDER_Thumbnail_Landscape.jpg"),
                    os.path.join(target_dir, "THUNDER_Thumbnail.jpg"),
                ]
                thumb_path = None
                for tc in thumb_candidates:
                    if os.path.exists(tc):
                        thumb_path = tc
                        break
                has_thumb = thumb_path is not None

                # Robust social kit matching in Social Kits/, video folder, or root target_dir
                kit_candidates = [
                    os.path.join(folder_kits, f"{stem}.txt"),
                    os.path.join(folder_kits, f"{stem.replace('Highlights_', 'SocialKit_')}.txt"),
                    os.path.join(folder_kits, f"{stem.replace('Highlights_Landscape', 'SocialKit_Landscape').replace('Highlights_Vertical_Shorts', 'SocialKit_Vertical_Shorts')}.txt"),
                    os.path.join(curr_dir, f"{stem}.txt"),
                    os.path.join(curr_dir, f"{stem.replace('Highlights_', 'SocialKit_')}.txt"),
                    os.path.join(curr_dir, f"{stem.replace('Highlights_Landscape', 'SocialKit_Landscape').replace('Highlights_Vertical_Shorts', 'SocialKit_Vertical_Shorts')}.txt"),
                    os.path.join(target_dir, f"{stem}.txt"),
                    os.path.join(target_dir, f"{stem.replace('Highlights_', 'SocialKit_')}.txt"),
                    os.path.join(target_dir, f"{stem.replace('Highlights_Landscape', 'SocialKit_Landscape').replace('Highlights_Vertical_Shorts', 'SocialKit_Vertical_Shorts')}.txt"),
                    os.path.join(folder_kits, "THUNDER_SocialKit_Vertical_Shorts.txt" if is_vert else "THUNDER_SocialKit_Landscape.txt"),
                    os.path.join(folder_kits, "THUNDER_SocialKit.txt"),
                    os.path.join(target_dir, "THUNDER_SocialKit_Vertical_Shorts.txt" if is_vert else "THUNDER_SocialKit_Landscape.txt"),
                    os.path.join(target_dir, "THUNDER_SocialKit.txt"),
                ]
                kit_path = None
                for kc in kit_candidates:
                    if os.path.exists(kc):
                        kit_path = kc
                        break
                has_kit = kit_path is not None

                folder_name = os.path.basename(curr_dir) if os.path.abspath(curr_dir) != os.path.abspath(target_dir) else ""

                results.append({
                    "name": f,
                    "path": full_path,
                    "folder": folder_name,
                    "size": f"{sz_mb} MB",
                    "date": date_str,
                    "format": fmt_desc,
                    "is_vert": is_vert,
                    "has_thumb": has_thumb,
                    "thumb_path": thumb_path if has_thumb else None,
                    "has_kit": has_kit,
                    "kit_path": kit_path if has_kit else None
                })
        except Exception as e:
            print("Error scanning output folder:", e)
        return results

    def read_social_kit(self, kit_path):
        if not kit_path or not os.path.exists(kit_path):
            return {"status": "error", "message": "Social kit file not found"}
        try:
            with open(kit_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "ok", "content": content}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def open_thumbnail_image(self, thumb_path):
        if thumb_path and os.path.exists(thumb_path):
            os.startfile(thumb_path)
            return True
        return False

    def open_folder(self, folder_path=None):
        if not folder_path:
            folder_path = self.config.get("export_folder", r"D:\Data\Capture\Edited")
        if folder_path:
            self.config["export_folder"] = folder_path
            self._save_config()
        os.makedirs(folder_path, exist_ok=True)
        os.startfile(folder_path)

    def play_video(self, video_path):
        if os.path.exists(video_path):
            os.startfile(video_path)

    def trigger_upload(self, video_path, plan="Pro+"):
        if not os.path.exists(video_path):
            return {"status": "error", "message": "Video file not found."}
        channel = self.config.get("channel_name", "MAAKTHUNDER")
        yt = self.config.get("yt", "YOUTUBE.COM/@MAAKTHUNDER")
        return {
            "status": "success",
            "message": f"Auto-Upload queued successfully for {os.path.basename(video_path)} to connected channel: {channel} ({yt})"
        }

    def get_auto_upload_data(self):
        """Scans the export folder for generated vertical shorts and landscape videos, paired with their social kits."""
        ch = load_youtube_channel()
        export_folder = self.config.get("export_folder", r"D:\Data\Capture\Edited")
        vert_folder = os.path.join(export_folder, "Vertical Shorts")
        land_folder = os.path.join(export_folder, "Landscape")
        kits_folder = os.path.join(export_folder, "Social Kits")

        videos = []

        def _parse_social_kit(kit_path):
            title = ""
            desc = ""
            tags = ""
            if os.path.exists(kit_path):
                try:
                    with open(kit_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    if "=== YOUTUBE VIDEO TITLE ===" in content:
                        parts = content.split("=== YOUTUBE VIDEO TITLE ===")[1]
                        title = parts.split("===")[0].strip()
                    if "=== YOUTUBE DESCRIPTION ===" in content:
                        parts = content.split("=== YOUTUBE DESCRIPTION ===")[1]
                        desc = parts.split("===")[0].strip()
                    if "=== SEO TAGS (COPY & PASTE INTO YOUTUBE TAGS BOX) ===" in content:
                        tags = content.split("=== SEO TAGS (COPY & PASTE INTO YOUTUBE TAGS BOX) ===")[1].strip()
                except Exception:
                    pass
            return title, desc, tags

        # 1. Check Vertical Shorts
        if os.path.exists(vert_folder):
            for fname in sorted(os.listdir(vert_folder)):
                if fname.lower().endswith(".mp4"):
                    full_p = os.path.join(vert_folder, fname)
                    sz_mb = round(os.path.getsize(full_p) / (1024 * 1024), 1)
                    base_no_ext = os.path.splitext(fname)[0]
                    kit_name = base_no_ext.replace("THUNDER_Highlights_", "THUNDER_SocialKit_") + ".txt"
                    kit_p = os.path.join(kits_folder, kit_name)
                    title, desc, tags = _parse_social_kit(kit_p)
                    if not title:
                        title = f"{self.config.get('channel_name', 'MAAKTHUNDER')} | UNSTOPPABLE 9:16 CLUTCH #Shorts"
                    videos.append({
                        "path": full_p,
                        "filename": fname,
                        "category": "Vertical Short (9:16)",
                        "size_mb": sz_mb,
                        "title": title,
                        "description": desc,
                        "tags": tags,
                        "is_short": True
                    })

        # 2. Check Landscape Videos
        if os.path.exists(land_folder):
            for fname in sorted(os.listdir(land_folder)):
                if fname.lower().endswith(".mp4"):
                    full_p = os.path.join(land_folder, fname)
                    sz_mb = round(os.path.getsize(full_p) / (1024 * 1024), 1)
                    base_no_ext = os.path.splitext(fname)[0]
                    kit_name = base_no_ext.replace("THUNDER_Highlights_", "THUNDER_SocialKit_") + ".txt"
                    kit_p = os.path.join(kits_folder, kit_name)
                    title, desc, tags = _parse_social_kit(kit_p)
                    if not title:
                        title = f"{self.config.get('channel_name', 'MAAKTHUNDER')} | 1080p 60fps ESPORTS HIGHLIGHTS"
                    videos.append({
                        "path": full_p,
                        "filename": fname,
                        "category": "Landscape Montage (16:9)",
                        "size_mb": sz_mb,
                        "title": title,
                        "description": desc,
                        "tags": tags,
                        "is_short": False
                    })

        return {
            "channel": ch,
            "videos": videos,
            "export_folder": export_folder
        }

    def start_youtube_upload(self, payload):
        """Starts asynchronous YouTube upload in a background daemon thread."""
        ch = load_youtube_channel()
        if not ch or not ch.get("channel_id"):
            return {"status": "error", "message": "No YouTube channel linked. Please connect your channel first."}
        
        token = ch.get("token")
        if not token:
            return {"status": "auth_required", "message": "YouTube access token missing. Please click 'Reconnect / Switch Channel' to authenticate with Google."}
        
        video_path = payload.get("video_path")
        if not video_path or not os.path.exists(video_path):
            return {"status": "error", "message": f"Selected video file does not exist: {video_path}"}
        
        title = payload.get("title") or "PUBG Mobile Esports Highlights #Shorts"
        description = payload.get("description") or ""
        tags = payload.get("tags") or "PUBG Mobile, MAAKTHUNDER, Gaming"
        privacy = payload.get("privacy") or "unlisted"
        playlist_id = payload.get("playlist_id") or None
        
        self._upload_cancelled = False
        
        def _worker():
            try:
                def _prog(pct, msg):
                    if self._window and not getattr(self, "_upload_cancelled", False):
                        safe_msg = json.dumps(msg)
                        self._window.evaluate_js(f"if (window.onUploadProgress) window.onUploadProgress({int(pct)}, {safe_msg});")
                
                res = self._execute_resumable_upload(token, video_path, title, description, tags, privacy, playlist_id, _prog, payload)
                if self._window:
                    safe_res = json.dumps(res)
                    self._window.evaluate_js(f"if (window.onUploadComplete) window.onUploadComplete({safe_res});")
            except Exception as e:
                err_res = {"status": "error", "message": str(e)}
                if self._window:
                    safe_err = json.dumps(err_res)
                    self._window.evaluate_js(f"if (window.onUploadComplete) window.onUploadComplete({safe_err});")
        
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return {"status": "started", "message": f"Uploading {os.path.basename(video_path)} to YouTube..."}

    def cancel_youtube_upload(self):
        """Cancels an in-progress YouTube upload."""
        self._upload_cancelled = True
        return {"status": "ok"}

    def _execute_resumable_upload(self, token, video_path, title, description, tags, privacy="unlisted", playlist_id=None, progress_cb=None, extra_payload=None):
        """Performs resumable chunked upload to YouTube Data API v3."""
        import requests
        if getattr(self, "_upload_cancelled", False):
            return {"status": "cancelled", "message": "Upload cancelled by user."}
        
        file_size = os.path.getsize(video_path)
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tag_list = tags or []
        
        if progress_cb:
            progress_cb(5, "Connecting to YouTube API & initiating upload...")
        
        # 1. Initialize Resumable Upload
        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size)
        }
        extra = extra_payload or {}
        coppa_val = str(extra.get("coppa", "false")).lower() in ["true", "yes"]
        license_val = "creativeCommon" if extra.get("license") == "creativeCommon" else "youtube"
        embeddable_val = bool(extra.get("embeddable", True))
        lang_val = extra.get("lang") or "ur"
        category_val = str(extra.get("category") or "20")

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tag_list[:500],
                "categoryId": category_val,
                "defaultLanguage": "en",
                "defaultAudioLanguage": lang_val
            },
            "status": {
                "privacyStatus": privacy.lower() if privacy in ["unlisted", "public", "private"] else "unlisted",
                "selfDeclaredMadeForKids": coppa_val,
                "embeddable": embeddable_val,
                "license": license_val,
                "publicStatsViewable": True
            }
        }
        
        try:
            resp = requests.post(init_url, headers=headers, json=body, timeout=20)
        except Exception as e_req:
            return {"status": "error", "message": f"Connection to YouTube failed: {e_req}"}

        if resp.status_code == 401:
            return {"status": "auth_required", "message": "YouTube access token has expired. Please click 'Reconnect / Switch Channel' to refresh your Google session."}
        if resp.status_code not in (200, 201):
            err_msg = resp.text
            try:
                err_msg = resp.json().get("error", {}).get("message", err_msg)
            except Exception:
                pass
            return {"status": "error", "message": f"YouTube API Error ({resp.status_code}): {err_msg}"}
        
        upload_url = resp.headers.get("Location")
        if not upload_url:
            return {"status": "error", "message": "YouTube failed to return a valid upload location."}
        
        # 2. Upload in 8MB chunks
        chunk_size = 8 * 1024 * 1024
        with open(video_path, "rb") as f:
            offset = 0
            while offset < file_size:
                if getattr(self, "_upload_cancelled", False):
                    return {"status": "cancelled", "message": "Upload cancelled by user."}
                
                chunk = f.read(chunk_size)
                chunk_len = len(chunk)
                chunk_end = offset + chunk_len - 1
                chunk_headers = {
                    "Content-Type": "video/mp4",
                    "Content-Length": str(chunk_len),
                    "Content-Range": f"bytes {offset}-{chunk_end}/{file_size}"
                }
                
                try:
                    chunk_resp = requests.put(upload_url, headers=chunk_headers, data=chunk, timeout=120)
                except Exception as e_ch:
                    return {"status": "error", "message": f"Upload network error during chunk transmission: {e_ch}"}

                if chunk_resp.status_code in (200, 201):
                    # Done!
                    v_data = chunk_resp.json()
                    vid_id = v_data.get("id")
                    
                    if playlist_id and vid_id:
                        try:
                            pl_url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
                            pl_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                            pl_body = {
                                "snippet": {
                                    "playlistId": playlist_id,
                                    "resourceId": {"kind": "youtube#video", "videoId": vid_id}
                                }
                            }
                            requests.post(pl_url, headers=pl_headers, json=pl_body, timeout=10)
                        except Exception as e_pl:
                            print("Playlist add note:", e_pl)
                    
                    if progress_cb:
                        progress_cb(100, "🎉 Upload complete! Video is live on YouTube.")
                    
                    return {
                        "status": "success",
                        "video_id": vid_id,
                        "video_url": f"https://youtu.be/{vid_id}",
                        "shorts_url": f"https://youtube.com/shorts/{vid_id}",
                        "title": title
                    }
                elif chunk_resp.status_code == 308:
                    offset += chunk_len
                    pct = max(10, min(98, int((offset / file_size) * 100)))
                    mb_up = offset / (1024 * 1024)
                    mb_tot = file_size / (1024 * 1024)
                    if progress_cb:
                        progress_cb(pct, f"Uploading to YouTube: {mb_up:.1f} MB / {mb_tot:.1f} MB ({pct}%)...")
                else:
                    return {"status": "error", "message": f"Upload chunk error ({chunk_resp.status_code}): {chunk_resp.text}"}

    def check_for_updates(self):
        """Checks the remote manifest or local fallback for latest version and changelog."""
        manifest_data = None
        error_msg = None

        # 1. Try remote URL first
        try:
            req = urllib.request.Request(
                UPDATE_MANIFEST_URL,
                headers={"User-Agent": "THUNDER-Studio-Updater/1.0"}
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                if resp.status == 200:
                    manifest_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            error_msg = str(e)

        # 2. Fallback to local version.json if remote is not yet reachable
        if not manifest_data and os.path.exists(LOCAL_VERSION_FILE):
            try:
                with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
            except Exception:
                pass

        if not manifest_data:
            return {
                "success": False,
                "has_update": False,
                "current_version": APP_VERSION,
                "error": error_msg or "Could not reach update server."
            }

        latest_ver = manifest_data.get("latest_version", APP_VERSION)
        has_update = self._is_newer_version(APP_VERSION, latest_ver)

        return {
            "success": True,
            "has_update": has_update,
            "current_version": APP_VERSION,
            "latest_version": latest_ver,
            "release_date": manifest_data.get("release_date", "October 2026"),
            "download_url": manifest_data.get("download_url", "https://github.com/MAAKTHUNDER/thunder-releases/releases/latest"),
            "changelog": manifest_data.get("changelog", []),
            "mandatory": manifest_data.get("mandatory", False)
        }

    def _is_newer_version(self, current, latest):
        def parse_v(v_str):
            cleaned = str(v_str).lower().lstrip("v").strip()
            parts = []
            for p in cleaned.split("."):
                digits = "".join(ch for ch in p if ch.isdigit())
                parts.append(int(digits) if digits else 0)
            return parts
        try:
            return parse_v(latest) > parse_v(current)
        except Exception:
            return False

    def open_external_url(self, url):
        """Opens external release or download link in default browser."""
        if not url:
            url = "https://github.com/MAAKTHUNDER/thunder-releases/releases/latest"
        webbrowser.open(url)
        return True

    def start_processing(self, payload):
        is_valid, _, err_msg = hwid_shield.load_and_verify_vault()
        if not is_valid:
            self._ui_log(f"❌ Access Denied: {err_msg}")
            if self._window:
                self._window.evaluate_js("checkStartupLicenseLock()")
            return
        if self.is_processing:
            return
        thread = threading.Thread(target=self._run_pipeline, args=(payload,), daemon=True)
        thread.start()

    def execute_curated_render(self, payload):
        is_valid, _, err_msg = hwid_shield.load_and_verify_vault()
        if not is_valid:
            self._ui_log(f"❌ Access Denied: {err_msg}")
            if self._window:
                self._window.evaluate_js("checkStartupLicenseLock()")
            return
        if self.is_processing:
            return
        thread = threading.Thread(target=self._run_render_curated, args=(payload,), daemon=True)
        thread.start()

    def cancel_process(self):
        if not self.is_processing and self._stage == "idle":
            return True
        self.is_processing = False
        self._stage = "idle"
        if hasattr(self, 'engine'):
            self.engine.cancel_requested = True
            self.engine.cancel_render()
        self._ui_log("🛑 Process cancelled by user. Active encoding and background tasks halted.")
        self._set_ui_progress(0, "Process cancelled by user.")
        if self._window:
            try:
                self._window.evaluate_js("onProcessComplete()")
            except Exception:
                pass
        # Ensure trailing engine scan threads finish their current tick before resetting is_scanning
        def _delayed_reset():
            time.sleep(0.5)
            self.is_scanning = False
        threading.Thread(target=_delayed_reset, daemon=True).start()
        return True

    def _run_pipeline(self, payload):
        self.is_processing = True
        try:
            files = payload.get("files", [])
            if not files:
                scan_res = self.scan_capture_folder()
                files = scan_res.get("files", [])

            if not files:
                self._ui_log("\n⚠️ No gameplay videos found to process! Please select video files or scan a folder.")
                self._set_ui_progress(0, "Error: No gameplay videos selected")
                return

            export_folder = payload.get("exportFolder", r"D:\Data\Capture\Edited")
            music_file = payload.get("musicFile", r"d:\Data\Capture\Ui\Background Music.mp3")
            music_offset_str = payload.get("musicOffset", "00:55")
            fmt = payload.get("format", "both")
            player_ign = (payload.get("playerIgn") or "").strip()
            channel_name = payload.get("channelName", "MAAKTHUNDER")
            yt = payload.get("yt", "YOUTUBE.COM/@MAAKTHUNDER")
            tt = payload.get("tt", "TIKTOK.COM/@MAAKTHUNDER")
            fb = payload.get("fb", "FACEBOOK.COM/MAAKTHUNDER")
            plan = payload.get("plan", "Pro+")
            edit_level = payload.get("editLevel", "Pro")
            target_duration = payload.get("targetDuration", 90)

            # Plan Tier Enforcement (Strict Offline Anti-Tamper)
            plan, edit_level, fmt = self._verify_tier_and_format(plan, edit_level, fmt)

            # Parse Target Duration for Splitting (60s, 90s, or Full Compilation)
            target_dur_val = 90
            if str(target_duration).lower() in ("full", "0", "none", "compilation"):
                target_dur_val = 0
            else:
                try:
                    target_dur_val = int(target_duration)
                except Exception:
                    target_dur_val = 90

            try:
                parts = music_offset_str.strip().split(":")
                if len(parts) == 2:
                    music_offset = int(parts[0]) * 60 + float(parts[1])
                else:
                    music_offset = float(music_offset_str)
            except Exception:
                music_offset = 55.0

            os.makedirs(export_folder, exist_ok=True)
            pipeline_start = time.time()
            self._set_ui_progress(3, "Initializing studio pipeline...")

            # Clean header logs
            self._ui_log(f"📁 Target Videos: {len(files)} file(s)")
            if player_ign:
                self._ui_log(f"🎮 Player IGN: '{player_ign}'")
            else:
                self._ui_log("🎮 Player IGN: Auto-Detect (Zero-Input Neural Radar)")
            self._ui_log(f"🎵 Music Track: '{os.path.basename(music_file)}' (Start Drop: {music_offset:.1f}s)")
            self._ui_log("--------------------------------------------------")

            # Generate Branded Esports Intros & Outros (with Crown 亗 glyph support)
            self.engine.generate_branded_assets(
                player_ign=player_ign,
                channel_name=channel_name,
                yt_link=yt,
                tt_link=tt,
                fb_link=fb
            )

            import queue
            verification_queue = queue.Queue()
            verified_events = []
            rejected_events = []

            def verifier_worker():
                import cv2
                caps = {}
                try:
                    while True:
                        item = verification_queue.get()
                        if item is None:
                            break
                        if not self.is_processing:
                            verification_queue.task_done()
                            continue
                        vpath = item.get("video")
                        if vpath not in caps:
                            caps[vpath] = cv2.VideoCapture(vpath)
                        cap = caps[vpath]

                        ok, reason = self.engine.verify_candidate_event(cap, item, target_ign=player_ign)
                        t_min = int(item["time"]) // 60
                        t_sec_rem = int(item["time"]) % 60
                        if ok:
                            print(f"      🛡️ [AI VERIFIED] {t_min:02d}:{t_sec_rem:02d} vs {item['victim']} (Standing & Active)", flush=True)
                            verified_events.append(item)
                        else:
                            print(f"      🚫 [AI REJECTED] {t_min:02d}:{t_sec_rem:02d} vs {item['victim']} ({reason})", flush=True)
                            rejected_events.append(item)

                        verification_queue.task_done()
                except Exception as ex:
                    print("Verifier worker error:", ex)
                finally:
                    for c in caps.values():
                        c.release()

            verifier_thread = threading.Thread(target=verifier_worker, daemon=True)
            verifier_thread.start()

            all_clips = []
            self._stage = "scanning"
            self._total_videos = len(files)
            scan_cache = self._load_scan_cache()
            scan_total_start = time.time()

            for idx, vid_path in enumerate(files, start=1):
                if not self.is_processing:
                    self._ui_log("\n⚠️ Scanning stopped by user.")
                    break
                if not os.path.exists(vid_path):
                    self._ui_log(f"⚠️ Video file not found: {vid_path}")
                    continue
                
                self._current_video_idx = idx
                vid_name = os.path.basename(vid_path)
                vid_scan_start = time.time()

                # --- SMART SCAN CACHE CHECK (Instant 0.01s resume vs Fresh Scan) ---
                curr_size = os.path.getsize(vid_path)
                curr_mtime = os.path.getmtime(vid_path)
                cached_entry = scan_cache.get(vid_path) or scan_cache.get(vid_name)
                force_fresh = payload.get("forceFreshScan", False)

                if not force_fresh and cached_entry and cached_entry.get("clips") and cached_entry.get("size") == curr_size and abs(cached_entry.get("mtime", 0) - curr_mtime) < 5:
                    cached_clips = cached_entry.get("clips", [])
                    for c in cached_clips:
                        c["source"] = vid_path
                    self._ui_log(f"⚡ [{idx}/{len(files)}] Loaded from Previous Scan ({len(cached_clips)} Clips Found): {vid_name}")
                    all_clips.extend(cached_clips)
                    continue

                if force_fresh and cached_entry:
                    self._ui_log(f"🔄 [{idx}/{len(files)}] Starting Fresh Scan (Re-analyzing {vid_name} with latest AI)...")

                self._ui_log(f"\n[{idx}/{len(files)}] Scanning Video: {vid_name}...")
                
                # Silence internal frame-by-frame debug logs during scan
                self.is_scanning = True
                try:
                    def on_candidate_detected(ev_item):
                        verification_queue.put(ev_item)

                    self.engine.analyze_single_video(
                        vid_path,
                        target_ign=player_ign,
                        on_event_detected=on_candidate_detected,
                        is_cancelled_fn=lambda: not self.is_processing
                    )
                finally:
                    self.is_scanning = False

                if not self.is_processing:
                    break

                # Wait for this video's clips to complete 2nd verification
                verification_queue.join()
                vid_verified = [ev for ev in verified_events if ev.get("video") == vid_path]
                clips = self.engine.cluster_combat_events(vid_verified, vid_path)
                vid_sec = time.time() - vid_scan_start
                vid_m, vid_s = int(vid_sec // 60), int(vid_sec % 60)
                vid_time_str = f"{vid_m:02d}:{vid_s:02d}"
                self._ui_log(f"✓ [{idx}/{len(files)}] Scanning Complete: {len(clips)} Clips Found ({vid_time_str}).")
                all_clips.extend(clips)

                # Store in persistent cache
                scan_cache[vid_path] = {
                    "size": curr_size,
                    "mtime": curr_mtime,
                    "clips": clips
                }
                self._save_scan_cache(scan_cache)

            # Signal verifier worker to exit
            verification_queue.put(None)
            verifier_thread.join()

            if not self.is_processing:
                self._ui_log("\n⚠️ Scanning process cancelled by user. Scanner reset.")
                self._set_ui_progress(0, "Scan cancelled.")
                if self._window:
                    self._window.evaluate_js("onProcessComplete()")
                return

            total_scan_sec = time.time() - scan_total_start
            self._last_scan_duration = total_scan_sec
            scan_m, scan_s = int(total_scan_sec // 60), int(total_scan_sec % 60)
            scan_time_str = f"{scan_m:02d}:{scan_s:02d}"

            self._stage = "rendering"
            if not all_clips:
                self._ui_log("\n⚠️ No confirmed eliminations detected in selected footage.")
                self._set_ui_progress(100, f"Scan Complete (0 clips found • ⏱️ {scan_time_str})")
                if self._window:
                    self._window.evaluate_js("onProcessComplete()")
                return

            self._ui_log(f"\n✓ Total Clips Found: {len(all_clips)} (⏱️ Scan Time: {scan_time_str})")
            # Autosave complete studio project state
            self.save_studio_project({
                "version": "1.0",
                "total_clips": len(all_clips),
                "clips": all_clips,
                "scan_duration": total_scan_sec
            })
            self._set_ui_progress(65, "All matches scanned. Opening Interactive Review Studio...")
            if self._window:
                safe_json = json.dumps(all_clips)
                self._window.evaluate_js(f"openClipReviewStudio({safe_json})")
            return

            # MULTI-PART SPLITTING: Partition clips into upload-ready episodes (e.g. 60s Shorts, 90s Esports Highlight)
            clip_batches = self.engine.partition_clips_by_duration(all_clips, target_sec=target_dur_val)
            total_parts = len(clip_batches)
            if total_parts > 1:
                self._ui_log(f"\n✂️ Multi-Part Mode: Splitting {len(all_clips)} highlights into {total_parts} balanced videos (~{target_dur_val}s each).")

            # RENDER OUTPUTS PART-BY-PART (Auto-increment filenames, organized into 4 subfolders)
            folder_land = os.path.join(export_folder, "Landscape")
            folder_vert = os.path.join(export_folder, "Vertical Shorts")
            folder_thumbs = os.path.join(export_folder, "Thumbnails")
            folder_kits = os.path.join(export_folder, "Social Kits")

            for part_idx, batch_clips in enumerate(clip_batches, start=1):
                if not self.is_processing:
                    self._ui_log("\n⚠️ Rendering cancelled by user.")
                    break
                part_suffix = f"_Part_{part_idx}" if total_parts > 1 else ""
                part_label = f" [Part {part_idx}/{total_parts}]" if total_parts > 1 else ""

                if fmt in ("landscape", "both"):
                    os.makedirs(folder_land, exist_ok=True)
                    os.makedirs(folder_thumbs, exist_ok=True)
                    os.makedirs(folder_kits, exist_ok=True)
                    out_land = self.get_unique_export_path(folder_land, f"THUNDER_Highlights_Landscape{part_suffix}")
                    self._ui_log(f"\n🎬 Rendering 16:9 Landscape Montage{part_label} (1080p 60fps)...")
                    self._ui_log(f"   📁 Output: Landscape/{os.path.basename(out_land)}")
                    self._set_ui_progress(70 + int((part_idx / total_parts) * 15), f"Compiling 16:9 Landscape Montage{part_label}...")
                    lic = self.get_license_info()
                    is_trial_mode = lic.get("watermark_active", False)
                    self.engine.render_montage(
                        batch_clips, music_file, music_offset, out_land, is_vertical=False,
                        player_ign=player_ign, channel_name=channel_name,
                        yt_link=yt, tt_link=tt, fb_link=fb,
                        edit_level=edit_level,
                        is_trial=is_trial_mode
                    )

                if fmt in ("vertical", "both"):
                    os.makedirs(folder_vert, exist_ok=True)
                    os.makedirs(folder_thumbs, exist_ok=True)
                    os.makedirs(folder_kits, exist_ok=True)
                    out_vert = self.get_unique_export_path(folder_vert, f"THUNDER_Highlights_Vertical_Shorts{part_suffix}")
                    self._ui_log(f"\n📱 Rendering 9:16 Vertical Shorts Montage{part_label}...")
                    self._ui_log(f"   📁 Output: Vertical Shorts/{os.path.basename(out_vert)}")
                    self._set_ui_progress(85 + int((part_idx / total_parts) * 13), f"Generating 9:16 Shorts{part_label} with punch-zooms...")
                    lic = self.get_license_info()
                    is_trial_mode = lic.get("watermark_active", False)
                    self.engine.render_montage(
                        batch_clips, music_file, music_offset, out_vert, is_vertical=True,
                        player_ign=player_ign, channel_name=channel_name,
                        yt_link=yt, tt_link=tt, fb_link=fb,
                        edit_level=edit_level,
                        is_trial=is_trial_mode
                    )

                # --- AUTO 3D ESPORTS YOUTUBE THUMBNAIL GENERATOR ---
                thumb_name = f"THUNDER_Thumbnail{part_suffix}.jpg"
                out_thumb = os.path.join(folder_thumbs, thumb_name)
                self._ui_log(f"   🖼️ Generating 3D Esports Thumbnail: Thumbnails/{thumb_name}...")
                self.engine.generate_thumbnail(
                    batch_clips, out_thumb,
                    player_ign=player_ign, channel_name=channel_name,
                    part_num=part_idx, total_parts=total_parts
                )

                # --- AUTO SOCIAL MEDIA KIT & TAGS GENERATOR ---
                social_kit = self.engine.generate_social_kit(
                    batch_clips, player_ign=player_ign, channel_name=channel_name,
                    part_num=part_idx, total_parts=total_parts,
                    yt=yt, tt=tt, fb=fb
                )
                kit_txt_name = f"THUNDER_SocialKit{part_suffix}.txt"
                kit_txt_path = os.path.join(folder_kits, kit_txt_name)
                with open(kit_txt_path, "w", encoding="utf-8") as f_kit:
                    f_kit.write(f"=== YOUTUBE VIDEO TITLE ===\n{social_kit['title']}\n\n")
                    f_kit.write(f"=== YOUTUBE DESCRIPTION ===\n{social_kit['description']}\n\n")
                    f_kit.write(f"=== TIKTOK / REELS / SHORTS HOOK & CAPTION ===\n{social_kit['shorts_caption']}\n\n")
                    f_kit.write(f"=== SEO TAGS (COPY & PASTE INTO YOUTUBE TAGS BOX) ===\n{social_kit['tags']}\n")
                self._ui_log(f"   📋 Generated Ready-to-Copy Social Kit: Social Kits/{kit_txt_name}")

            total_sec = time.time() - pipeline_start
            mins = int(total_sec // 60)
            secs = int(total_sec % 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

            self._ui_log("\n🎉 ALL HIGHLIGHTS SUCCESSFULLY GENERATED & EXPORTED!")
            self._ui_log(f"⏱️ Total Studio Processing Time: {time_str}")
            self._ui_log(f"📁 Destination: {export_folder}")

        except RenderCancelledError:
            self._ui_log("\n🛑 Video rendering cancelled by user. Background tasks halted.")
            self._set_ui_progress(0, "Render cancelled by user.")
        except RenderCancelledError:
            self._ui_log("\n🛑 Video rendering cancelled by user. Background tasks halted.")
            self._set_ui_progress(0, "Render cancelled by user.")
        except Exception as e:
            self._ui_log(f"\n❌ Error during execution: {str(e)}")
            self._set_ui_progress(0, f"Error: {str(e)}")
        finally:
            self.is_processing = False
            self.is_scanning = False
            self._stage = "idle"
            if self._window:
                self._window.evaluate_js("onProcessComplete()")


    def _run_render_curated(self, payload):
        self.is_processing = True
        if hasattr(self, 'engine'):
            self.engine.cancel_requested = False
        try:
            clips = payload.get("clips", [])
            if not clips:
                self._ui_log("\n⚠️ No clips selected for rendering.")
                return

            export_folder = payload.get("exportFolder", r"D:\Data\Capture\Edited")
            music_file = payload.get("musicFile", r"d:\Data\Capture\Ui\Background Music.mp3")
            music_offset_str = payload.get("musicOffset", "00:55")
            fmt = payload.get("format", "both")
            player_ign = (payload.get("playerIgn") or "").strip()
            channel_name = payload.get("channelName", "MAAKTHUNDER")
            yt = payload.get("yt", "YOUTUBE.COM/@MAAKTHUNDER")
            tt = payload.get("tt", "TIKTOK.COM/@MAAKTHUNDER")
            fb = payload.get("fb", "FACEBOOK.COM/MAAKTHUNDER")
            plan = payload.get("plan", "Pro+")
            edit_level = payload.get("editLevel", "Pro")
            target_duration = payload.get("targetDuration", 90)
            vfx_hd = payload.get("vfxHd", False)
            vfx_shake = payload.get("vfxShake", False)

            # Plan Tier Enforcement (Strict Offline Anti-Tamper)
            plan, edit_level, fmt = self._verify_tier_and_format(plan, edit_level, fmt)

            try:
                parts = music_offset_str.strip().split(":")
                music_offset = int(parts[0]) * 60 + float(parts[1]) if len(parts) == 2 else float(music_offset_str)
            except Exception:
                music_offset = 55.0

            os.makedirs(export_folder, exist_ok=True)
            pipeline_start = time.time()
            self._set_ui_progress(68, "Initiating final render...")

            manual_parts = payload.get("manualParts")
            target_dur_str = str(target_duration).lower()
            if manual_parts and isinstance(manual_parts, list) and len(manual_parts) > 0:
                clip_batches = manual_parts
                self._ui_log(f"\n🛠️ Manual Parts Mode: Exporting {len(clip_batches)} custom configured episode part(s).")
            elif target_dur_str in ("match_aware", "60_90", "auto", "smart", "60-90"):
                clip_batches = self.engine.partition_clips_match_aware(clips, min_sec=60, max_sec=120)
                self._ui_log(f"\n🧠 Smart Match-Aware Mode: Partitioned {len(clips)} highlights into {len(clip_batches)} video(s) (60-120s balanced episodes without splitting any match!).")
            elif target_dur_str in ("full", "0", "none", "compilation", "single"):
                clip_batches = [clips]
                self._ui_log(f"\n🎬 Single Full Video Mode: Compiling all {len(clips)} highlights into 1 video.")
            elif target_dur_str in ("individual", "clips", "each"):
                clip_batches = [[c] for c in clips]
                self._ui_log(f"\n✂️ Individual Clips Mode: Exporting each of the {len(clips)} highlights as separate videos.")
            else:
                try:
                    target_dur_val = int(target_duration)
                except Exception:
                    target_dur_val = 90
                clip_batches = self.engine.partition_clips_by_duration(clips, target_sec=target_dur_val)

            total_parts = len(clip_batches)
            if total_parts > 1:
                self._ui_log(f"\n✂️ Partitioned {len(clips)} highlights into {total_parts} final video(s).")

            folder_land = os.path.join(export_folder, "Landscape")
            folder_vert = os.path.join(export_folder, "Vertical Shorts")
            folder_thumbs = os.path.join(export_folder, "Thumbnails")
            folder_kits = os.path.join(export_folder, "Social Kits")

            for part_idx, batch_clips in enumerate(clip_batches, start=1):
                if not self.is_processing or (hasattr(self, 'engine') and self.engine.cancel_requested):
                    self._ui_log("\n🛑 Video rendering cancelled by user.")
                    break
                part_suffix = f"_Part_{part_idx}" if total_parts > 1 else ""
                part_label = f" [Part {part_idx}/{total_parts}]" if total_parts > 1 else ""

                if fmt in ("landscape", "both"):
                    os.makedirs(folder_land, exist_ok=True)
                    os.makedirs(folder_thumbs, exist_ok=True)
                    os.makedirs(folder_kits, exist_ok=True)
                    out_land = self.get_unique_export_path(folder_land, f"THUNDER_Highlights_Landscape{part_suffix}")
                    self._ui_log(f"\n🎬 Rendering 16:9 Landscape Montage{part_label} (1080p 60fps)...")
                    self._ui_log(f"   📁 Output: Landscape/{os.path.basename(out_land)}")
                    self._set_ui_progress(70 + int((part_idx / total_parts) * 15), f"Compiling 16:9 Landscape Montage{part_label}...")
                    lic = self.get_license_info()
                    is_trial_mode = lic.get("watermark_active", False)
                    self.engine.render_montage(
                        batch_clips, music_file, music_offset, out_land, is_vertical=False,
                        player_ign=player_ign, channel_name=channel_name,
                        yt_link=yt, tt_link=tt, fb_link=fb,
                        edit_level=edit_level,
                        is_trial=is_trial_mode
                    )

                    # --- AUTO 3D ESPORTS 16:9 LANDSCAPE THUMBNAIL ---
                    out_thumb_land = os.path.join(folder_thumbs, f"THUNDER_Thumbnail_Landscape{part_suffix}.jpg")
                    self._ui_log(f"   🖼️ Generating 16:9 3D Esports Thumbnail: Thumbnails/{os.path.basename(out_thumb_land)}...")
                    self.engine.generate_thumbnail(
                        batch_clips, out_thumb_land,
                        player_ign=player_ign, channel_name=channel_name,
                        part_num=part_idx, total_parts=total_parts, is_vertical=False
                    )

                    # --- AUTO SOCIAL MEDIA KIT & TAGS ---
                    social_kit_land = self.engine.generate_social_kit(
                        batch_clips, player_ign=player_ign, channel_name=channel_name,
                        part_num=part_idx, total_parts=total_parts,
                        yt=yt, tt=tt, fb=fb
                    )
                    kit_txt_land = os.path.join(folder_kits, f"THUNDER_SocialKit_Landscape{part_suffix}.txt")
                    with open(kit_txt_land, "w", encoding="utf-8") as f_kit:
                        f_kit.write(f"=== YOUTUBE VIDEO TITLE ===\n{social_kit_land['title']}\n\n")
                        f_kit.write(f"=== YOUTUBE DESCRIPTION ===\n{social_kit_land['description']}\n\n")
                        f_kit.write(f"=== TIKTOK / REELS / SHORTS HOOK & CAPTION ===\n{social_kit_land['shorts_caption']}\n\n")
                        f_kit.write(f"=== SEO TAGS (COPY & PASTE INTO YOUTUBE TAGS BOX) ===\n{social_kit_land['tags']}\n")
                    self._ui_log(f"   📋 Generated Landscape Social Kit: Social Kits/{os.path.basename(kit_txt_land)}")

                if fmt in ("vertical", "both"):
                    os.makedirs(folder_vert, exist_ok=True)
                    os.makedirs(folder_thumbs, exist_ok=True)
                    os.makedirs(folder_kits, exist_ok=True)
                    out_vert = self.get_unique_export_path(folder_vert, f"THUNDER_Highlights_Vertical_Shorts{part_suffix}")
                    self._ui_log(f"\n📱 Rendering 9:16 Vertical Shorts Montage{part_label}...")
                    self._ui_log(f"   📁 Output: Vertical Shorts/{os.path.basename(out_vert)}")
                    self._set_ui_progress(85 + int((part_idx / total_parts) * 13), f"Generating 9:16 Shorts{part_label} with punch-zooms...")
                    lic = self.get_license_info()
                    is_trial_mode = lic.get("watermark_active", False)
                    self.engine.render_montage(
                        batch_clips, music_file, music_offset, out_vert, is_vertical=True,
                        player_ign=player_ign, channel_name=channel_name,
                        yt_link=yt, tt_link=tt, fb_link=fb,
                        edit_level=edit_level,
                        is_trial=is_trial_mode
                    )

                    # --- AUTO 3D ESPORTS 9:16 VERTICAL THUMBNAIL (1080x1920) ---
                    out_thumb_vert = os.path.join(folder_thumbs, f"THUNDER_Thumbnail_Vertical_Shorts{part_suffix}.jpg")
                    self._ui_log(f"   📱 Generating 9:16 Vertical Shorts Thumbnail: Thumbnails/{os.path.basename(out_thumb_vert)}...")
                    self.engine.generate_thumbnail(
                        batch_clips, out_thumb_vert,
                        player_ign=player_ign, channel_name=channel_name,
                        part_num=part_idx, total_parts=total_parts, is_vertical=True
                    )

                    # --- AUTO SOCIAL MEDIA KIT & HOOKS ---
                    social_kit_vert = self.engine.generate_social_kit(
                        batch_clips, player_ign=player_ign, channel_name=channel_name,
                        part_num=part_idx, total_parts=total_parts,
                        yt=yt, tt=tt, fb=fb
                    )
                    kit_txt_vert = os.path.join(folder_kits, f"THUNDER_SocialKit_Vertical_Shorts{part_suffix}.txt")
                    with open(kit_txt_vert, "w", encoding="utf-8") as f_kit:
                        shorts_title = f"{channel_name} | UNSTOPPABLE 9:16 CLUTCH #Shorts"
                        f_kit.write(f"=== YOUTUBE VIDEO TITLE ===\n{shorts_title}\n\n")
                        f_kit.write(f"=== YOUTUBE DESCRIPTION ===\n{social_kit_vert['description']}\n\n")
                        f_kit.write(f"=== TIKTOK / REELS / SHORTS HOOK & CAPTION ===\n{social_kit_vert['shorts_caption']}\n\n")
                        f_kit.write(f"=== SEO TAGS (COPY & PASTE INTO YOUTUBE TAGS BOX) ===\n{social_kit_vert['tags']}\n")
                    self._ui_log(f"   📋 Generated Vertical Social Kit: Social Kits/{os.path.basename(kit_txt_vert)}")

            total_sec = time.time() - pipeline_start
            render_m, render_s = int(total_sec // 60), int(total_sec % 60)
            render_time_str = f"{render_m:02d}:{render_s:02d}"
            scan_duration = getattr(self, "_last_scan_duration", 0.0)

            self._ui_log("\n🎉 ALL HIGHLIGHTS SUCCESSFULLY GENERATED & EXPORTED!")
            if scan_duration > 0:
                scan_m, scan_s = int(scan_duration // 60), int(scan_duration % 60)
                tot_pipe_sec = scan_duration + total_sec
                pipe_m, pipe_s = int(tot_pipe_sec // 60), int(tot_pipe_sec % 60)
                pipe_time_str = f"{pipe_m:02d}:{pipe_s:02d}"
                self._ui_log("⏱️ Performance Benchmark Summary:")
                self._ui_log(f"   ├── 🔍 AI Scan Time:       {scan_m:02d}:{scan_s:02d}")
                self._ui_log(f"   ├── 🎬 Final Render Time:  {render_time_str}")
                self._ui_log(f"   └── 🏁 Total Engine Time:  {pipe_time_str} (Excluding manual organizer time)")
                self._set_ui_progress(100, f"Highlights Generated Successfully in {pipe_time_str}!")
            else:
                self._ui_log(f"⏱️ Total Render Time: {render_time_str}")
                self._set_ui_progress(100, f"Highlights Generated Successfully in {render_time_str}!")
            self._ui_log(f"📁 Root Export Destination: {export_folder}")
            if os.path.exists(folder_land) and os.listdir(folder_land):
                self._ui_log(f"   ├── 📁 1. Landscape Videos: {folder_land}")
            if os.path.exists(folder_vert) and os.listdir(folder_vert):
                self._ui_log(f"   ├── 📁 2. Vertical Shorts: {folder_vert}")
            if os.path.exists(folder_thumbs) and os.listdir(folder_thumbs):
                self._ui_log(f"   ├── 📁 3. Thumbnails: {folder_thumbs}")
            if os.path.exists(folder_kits) and os.listdir(folder_kits):
                self._ui_log(f"   └── 📁 4. Social Kits: {folder_kits}")

        except RenderCancelledError:
            self._ui_log("\n🛑 Video rendering cancelled by user. Background tasks halted.")
            self._set_ui_progress(0, "Render cancelled by user.")
        except Exception as e:
            self._ui_log(f"\n❌ Error during execution: {str(e)}")
            self._set_ui_progress(0, f"Error: {str(e)}")
        finally:
            self.is_processing = False
            self._stage = "idle"
            if self._window:
                self._window.evaluate_js("onProcessComplete()")


class MediaStreamHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _CURRENT_API_INSTANCE
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/cancel":
            if _CURRENT_API_INSTANCE:
                _CURRENT_API_INSTANCE.cancel_process()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "cancelled": true}')
            return
        if parsed_url.path == "/auth_callback":
            params = urllib.parse.parse_qs(parsed_url.query)
            uid = params.get("uid", [""])[0]
            email = params.get("email", [""])[0]
            display_name = params.get("displayName", params.get("name", [""]))[0]
            photo_url = params.get("photoURL", params.get("photo", [""]))[0]
            token = params.get("token", [""])[0]
            if email:
                user_data = {
                    "uid": uid,
                    "email": email,
                    "displayName": display_name,
                    "photoURL": photo_url,
                    "token": token,
                    "logged_in_at": time.time()
                }
                save_user_session(user_data)
                
                # BIDIRECTIONAL GOOGLE ACCOUNT & LICENSE PASS SYNC
                try:
                    sys_hwid = hwid_shield.get_system_hwid()
                    user_prof = pk_license_engine.get_user_cloud_profile(uid)
                    cloud_key = user_prof.get("license_key") if user_prof else None
                    
                    if cloud_key:
                        # User already owns a bound license in the cloud -> auto-activate on this machine!
                        p_raw = str(user_prof.get("plan", "pro_plus")).lower()
                        p_mapped = "Pro+" if p_raw in ["pro+", "pro_plus", "lifetime", "trial"] else ("Basic" if p_raw == "basic" else "Pro")
                        exp = int(user_prof.get("expires_at", 0))
                        is_life = bool(user_prof.get("is_lifetime", False)) or exp == 0
                        days = "Lifetime" if is_life else max(1, int((exp - int(time.time())) // 86400))
                        hwid_shield.save_vault(cloud_key, p_mapped, email, exp, days)
                        if user_prof.get("hwid") != sys_hwid:
                            pk_license_engine.bind_license_to_google_user(uid, email, cloud_key, plan=p_mapped, is_lifetime=is_life, expires_at=exp, hwid=sys_hwid, auth_token=token)
                    else:
                        # Cloud does not have a key bound yet.
                        # Check if this PC currently has an active license in local vault:
                        is_valid, existing_vault, _ = hwid_shield.load_and_verify_vault()
                        if is_valid and existing_vault and existing_vault.get("license_key"):
                            loc_key = existing_vault.get("license_key")
                            loc_plan = existing_vault.get("plan", "Pro+")
                            loc_exp = int(existing_vault.get("expires_at", 0))
                            loc_is_life = existing_vault.get("days_left") == "Lifetime" or loc_exp == 0
                            pk_license_engine.bind_license_to_google_user(uid, email, loc_key, plan=loc_plan, is_lifetime=loc_is_life, expires_at=loc_exp, hwid=sys_hwid, auth_token=token)
                        else:
                            # Check if an existing license was registered to this Google email:
                            clean_em = email.strip().lower()
                            lic_info = pk_license_engine.lookup_license_by_identifier(clean_em)
                            if lic_info.get("found") and not lic_info.get("is_expired"):
                                k = lic_info.get("key")
                                if k:
                                    p = lic_info.get("plan", "Pro+")
                                    p_mapped = "Pro+" if str(p).lower() in ["pro+", "pro_plus", "trial"] else ("Basic" if str(p).lower() == "basic" else "Pro")
                                    exp = int(lic_info.get("expires_at", 0))
                                    is_life = bool(lic_info.get("is_lifetime", False)) or exp == 0
                                    days = "Lifetime" if is_life else lic_info.get("days_left", 30)
                                    hwid_shield.save_vault(k, p_mapped, email, exp, days)
                                    pk_license_engine.bind_license_to_google_user(uid, email, k, plan=p_mapped, is_lifetime=is_life, expires_at=exp, hwid=sys_hwid, auth_token=token)
                except Exception as elic:
                    print("Google-License sync note:", elic)

                if _CURRENT_API_INSTANCE and _CURRENT_API_INSTANCE._window:
                    safe_json = json.dumps(user_data)
                    try:
                        _CURRENT_API_INSTANCE._window.evaluate_js(f"window.onGoogleAuthSuccess({safe_json})")
                    except Exception as ej:
                        print("evaluate_js auth error:", ej)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>THUNDER Studio - Verified</title><style>body{{background:#070b14;color:#e2e8f0;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center;}}.card{{background:#0f172a;border:1px solid rgba(0,229,255,0.4);box-shadow:0 0 30px rgba(0,229,255,0.2);padding:40px;border-radius:16px;max-width:420px;}}h2{{color:#00e5ff;margin-bottom:8px;}}p{{color:#94a3b8;font-size:14px;}}.badge{{background:#1e293b;padding:8px 16px;border-radius:999px;font-size:13px;color:#38bdf8;}}</style></head><body><div class='card'><div style='font-size:40px;margin-bottom:12px;'>⚡</div><h2>Sign-In Verified!</h2><p>Welcome, <strong>{display_name or email}</strong>.<br>Your session is active in THUNDER Studio.</p><div class='badge'>You can close this tab and return to the app</div></div><script>setTimeout(function(){{ window.close(); }}, 2000);</script></body></html>"""
            self.wfile.write(html.encode("utf-8"))
            return

        elif parsed_url.path == "/youtube_callback":
            params = urllib.parse.parse_qs(parsed_url.query)
            ch_id = params.get("channel_id", [""])[0]
            ch_title = params.get("channel_title", [""])[0]
            ch_handle = params.get("channel_handle", [""])[0]
            ch_avatar = params.get("channel_avatar", [""])[0]
            ch_subs = params.get("channel_subs", [""])[0]
            ch_pls_raw = params.get("playlists", ["[]"])[0]
            ch_token = params.get("token", [""])[0]

            try:
                ch_pls = json.loads(ch_pls_raw)
            except Exception:
                ch_pls = []

            if ch_id and ch_title:
                ch_data = {
                    "channel_id": ch_id,
                    "title": ch_title,
                    "handle": ch_handle,
                    "avatar": ch_avatar,
                    "subscribers": ch_subs,
                    "playlists": ch_pls,
                    "token": ch_token,
                    "connected_at": time.time()
                }
                save_youtube_channel(ch_data)

                # Sync to user profile in Firestore if user is logged in
                try:
                    u_sess = load_user_session()
                    if u_sess and u_sess.get("uid"):
                        pk_license_engine._firestore_post("users", u_sess["uid"], {
                            "youtube_channel_id": ch_id,
                            "youtube_channel_title": ch_title,
                            "youtube_channel_handle": ch_handle,
                            "youtube_channel_avatar": ch_avatar
                        }, auth_token=u_sess.get("token"))
                except Exception as ef:
                    print("Firestore youtube sync note:", ef)

                if _CURRENT_API_INSTANCE and _CURRENT_API_INSTANCE._window:
                    safe_json = json.dumps(ch_data)
                    try:
                        _CURRENT_API_INSTANCE._window.evaluate_js(f"if (window.onYouTubeConnected) window.onYouTubeConnected({safe_json});")
                    except Exception as ej:
                        print("evaluate_js youtube connected error:", ej)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"""<!DOCTYPE html><html><body style="background:#030712;color:#fff;font-family:sans-serif;text-align:center;padding:50px;">
                <h1 style="color:#22c55e;">&#10003; YouTube Channel Connected!</h1>
                <p>THUNDER Studio has received your channel credentials.</p>
                <p style="color:#94a3b8;">You can close this tab and return to the Desktop App.</p>
                <script>setTimeout(function(){ window.close(); }, 2000);</script>
            </body></html>""")
            return

        query = parsed_url.query
        params = urllib.parse.parse_qs(query)
        file_path = params.get("file", [None])[0]
        if not file_path or not os.path.exists(file_path):
            self.send_response(404)
            self.end_headers()
            return

        file_size = os.path.getsize(file_path)
        range_header = self.headers.get("Range", None)

        if range_header:
            bytes_str = range_header.replace("bytes=", "")
            parts = bytes_str.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1
            length = (end - start) + 1

            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    chunk_size = 128 * 1024
                    while remaining > 0:
                        read_bytes = f.read(min(chunk_size, remaining))
                        if not read_bytes:
                            break
                        self.wfile.write(read_bytes)
                        remaining -= len(read_bytes)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass
        else:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                with open(file_path, "rb") as f:
                    chunk_size = 128 * 1024
                    while True:
                        read_bytes = f.read(chunk_size)
                        if not read_bytes:
                            break
                        self.wfile.write(read_bytes)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass

    def log_message(self, format, *args):
        pass

class ThreadedMediaServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

def start_media_server(port=54321):
    try:
        server = ThreadedMediaServer(("127.0.0.1", port), MediaStreamHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print(f"Media stream server active on http://127.0.0.1:{port}")
        return server
    except Exception as e:
        print("Media server startup note:", e)
        return None

def _apply_windows_icon(window_title, ico_path):
    """Applies custom THUNDER App icon to Windows Taskbar, Alt-Tab, and Title Bar."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        myappid = "maakthunder.thunderstudio.highlightapp.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    def _setter():
        time.sleep(1.0)
        try:
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE = 0x00000040
            hIcon = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if hIcon:
                hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
                if hwnd:
                    WM_SETICON = 0x0080
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hIcon)  # Small icon (Title Bar & System menu)
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hIcon)  # Big icon (Windows Taskbar & Alt+Tab)
        except Exception as e:
            print("Windows Taskbar Icon setup note:", e)

    t = threading.Thread(target=_setter, daemon=True)
    t.start()

def main():
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    ico_path = get_resource_path(os.path.join("assets", "thunder_app_icon.ico"))
    window_title = "THUNDER — PUBG Mobile Highlight Automation Studio"

    _apply_windows_icon(window_title, ico_path)
    start_media_server(54321)
    html_path = get_resource_path(os.path.join("web", "studio_desktop.html"))

    api = ThunderStudioAPI()
    window = webview.create_window(
        title=window_title,
        url=html_path,
        js_api=api,
        width=1320,
        height=920,
        min_size=(1160, 780),
        background_color="#070a13"
    )
    api.set_window(window)

    def _on_window_loaded():
        def _bg_push():
            time.sleep(0.3)
            # 1. Immediate local render (0ms from vault)
            try:
                window.evaluate_js("updateLicenseUI()")
            except Exception:
                pass
            # 2. Automatic Cloud Sync at startup: queries Firestore to get latest days/plan
            try:
                res = api.sync_cloud_license()
                if res and res.get("status") == "ok":
                    window.evaluate_js("updateLicenseUI()")
            except Exception:
                pass
        threading.Thread(target=_bg_push, daemon=True).start()

    window.events.loaded += _on_window_loaded
    webview.start(debug=False)

if __name__ == "__main__":
    main()
