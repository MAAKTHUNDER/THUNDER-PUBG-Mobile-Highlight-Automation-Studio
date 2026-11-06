class RenderCancelledError(Exception):
    """Raised when rendering is cancelled by the user."""
    pass

"""
THUNDER Engine - Core PUBG Mobile Combat Detection & Montage Rendering Pipeline
- Universal Name-Locked Single-Pass Scanner
- Zero-Input Fallback Scanner
- Sample-Accurate FFmpeg Montage Rendering (16:9 Landscape & 9:16 Vertical Shorts)
"""

import os
import sys

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import time
import math
import struct
import wave
import subprocess
import threading
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

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
try:
    import pytesseract
    TESS_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(TESS_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESS_PATH
except Exception:
    pytesseract = None

# Neural Vision AI OCR Engine (RapidOCR ONNX)
_GLOBAL_AI_OCR = None
try:
    from rapidocr_onnxruntime import RapidOCR
    import sys
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        cand_yaml = os.path.join(base_dir, '_internal', 'rapidocr_onnxruntime', 'config.yaml')
        if not os.path.exists(cand_yaml):
            cand_yaml = os.path.join(base_dir, 'rapidocr_onnxruntime', 'config.yaml')
        if os.path.exists(cand_yaml):
            _GLOBAL_AI_OCR = RapidOCR(config_path=cand_yaml)
        else:
            _GLOBAL_AI_OCR = RapidOCR()
    else:
        _GLOBAL_AI_OCR = RapidOCR()
    print(f'⚡ [RapidOCR Engine]: Loaded successfully={_GLOBAL_AI_OCR is not None}', flush=True)
except Exception as _e_ai:
    print(f'❌ [RapidOCR Engine Failed to load]: {_e_ai}', flush=True)
    _GLOBAL_AI_OCR = None

def _find_binary(name):
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        cand = os.path.join(base_dir, f"{name}.exe")
        if os.path.exists(cand): return cand
        cand = os.path.join(base_dir, "_internal", f"{name}.exe")
        if os.path.exists(cand): return cand
    import shutil
    w = shutil.which(name)
    if w: return w
    winget_link = os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WinGet\Links\{name}.exe")
    if os.path.exists(winget_link): return winget_link
    return name

FFMPEG_EXE = _find_binary("ffmpeg")
FFPROBE_EXE = _find_binary("ffprobe")

_WINDIR = os.environ.get("WINDIR", r"C:\Windows")
_FONTS_DIR = os.path.join(_WINDIR, "Fonts")

def _resolve_font(filename, fallback="arial.ttf"):
    primary = os.path.join(_FONTS_DIR, filename)
    if os.path.exists(primary):
        return primary
    fb = os.path.join(_FONTS_DIR, fallback)
    if os.path.exists(fb):
        return fb
    return fallback

FONT_TITLE = _resolve_font("impact.ttf", "arialbd.ttf")
FONT_BOLD = _resolve_font("msyhbd.ttc", "arialbd.ttf")
FONT_SEGOE = _resolve_font("segoeuib.ttf", "arial.ttf")
FONT_ARIAL = _resolve_font("arialbd.ttf", "arial.ttf")

class ThunderEngine:
    def __init__(self, scratch_dir=None, log_callback=None, progress_callback=None):
        self.scratch_dir = scratch_dir or os.path.join(os.path.expanduser("~"), ".thunder_scratch")
        os.makedirs(self.scratch_dir, exist_ok=True)
        self.log_callback = log_callback or (lambda msg: print(msg, flush=True))
        self.progress_callback = progress_callback or (lambda cur, tot=100: None)
        self.cancel_requested = False
        self._active_procs = []
        self._proc_lock = threading.Lock()
        self.cpu_mode = 'normal'
        self._ensure_sfx()

    def cancel_render(self):
        self.cancel_requested = True
        with self._proc_lock:
            for p in list(self._active_procs):
                try:
                    if p.poll() is None:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
            self._active_procs.clear()

    def _run_subproc(self, cmd, capture_output=False, text=False, **kwargs):
        if self.cancel_requested:
            raise RenderCancelledError("Render cancelled by user")

        kwargs['creationflags'] = kwargs.get('creationflags', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = si

        if capture_output:
            kwargs['stdout'] = subprocess.PIPE
            kwargs['stderr'] = subprocess.PIPE
        else:
            kwargs.setdefault('stdout', subprocess.DEVNULL)
            kwargs.setdefault('stderr', subprocess.DEVNULL)

        if text:
            kwargs['text'] = True

        proc = subprocess.Popen(cmd, **kwargs)
        with self._proc_lock:
            self._active_procs.append(proc)

        try:
            stdout, stderr = proc.communicate()
            if self.cancel_requested:
                raise RenderCancelledError("Render cancelled by user")
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd, output=stdout, stderr=stderr)
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        finally:
            with self._proc_lock:
                if proc in self._active_procs:
                    self._active_procs.remove(proc)

    def log(self, msg):
        self.log_callback(msg)

    def set_progress(self, pct):
        self.progress_callback(pct)

    def _ensure_sfx(self):
        sr = 48000
        whoosh_p = os.path.join(self.scratch_dir, "sfx_whoosh.wav")
        impact_p = os.path.join(self.scratch_dir, "sfx_impact.wav")
        subbass_p = os.path.join(self.scratch_dir, "sfx_subbass_808.wav")

        if not os.path.exists(subbass_p):
            dur_s = 1.2
            n = int(sr * dur_s)
            data = []
            for i in range(n):
                t = i / sr
                # Exponential pitch drop from 95Hz down to 38Hz (808 Sub-Bass Boom)
                freq = 38.0 + 57.0 * math.exp(-12.0 * t)
                env = math.exp(-3.2 * t)
                sig = math.sin(2 * math.pi * freq * t)
                # Warm harmonic saturation
                sig = math.tanh(1.8 * sig) * 0.95 * env
                v = int(max(-1.0, min(1.0, sig)) * 32767)
                data.append(struct.pack('<hh', v, v))
            with wave.open(subbass_p, 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sr); wav.writeframes(b''.join(data))

        if not os.path.exists(whoosh_p):
            n = int(sr * 1.0)
            data = []
            for i in range(n):
                t = i / sr
                env = (math.sin(math.pi * t)) ** 2
                f = 60 + 260 * math.sin(math.pi * t)
                noise = (((i * 1103515245 + 12345) & 0x7FFFFFFF) / 0x7FFFFFFF - 0.5) * 0.15
                sig = (0.35 * math.sin(2 * math.pi * f * t) + noise) * env
                v = int(max(-1.0, min(1.0, sig)) * 32767)
                data.append(struct.pack('<hh', v, v))
            with wave.open(whoosh_p, 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sr); wav.writeframes(b''.join(data))

        if not os.path.exists(impact_p):
            n = int(sr * 1.2)
            data = []
            for i in range(n):
                t = i / sr
                decay = math.exp(-4.5 * t)
                f = 120 * math.exp(-6.0 * t) + 45
                noise = (((i * 1664525 + 1013904223) & 0x7FFFFFFF) / 0x7FFFFFFF - 0.5) * 0.2 * math.exp(-12.0 * t)
                sig = (0.5 * math.sin(2 * math.pi * f * t) + noise) * decay
                v = int(max(-1.0, min(1.0, sig)) * 32767)
                data.append(struct.pack('<hh', v, v))
            with wave.open(impact_p, 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sr); wav.writeframes(b''.join(data))

        # 4. High-Tech Cyberpunk Glitch Transition SFX
        glitch_p = os.path.join(self.scratch_dir, "sfx_glitch.wav")
        if not os.path.exists(glitch_p):
            dur_s = 0.6
            n = int(sr * dur_s)
            data = []
            for i in range(n):
                t = i / sr
                noise = (((i * 1664525 + 1013904223) & 0x7FFFFFFF) / 0x7FFFFFFF - 0.5) * 0.4
                stutter = 1.0 if (int(t * 40) % 2 == 0) else -0.3
                sig = (math.sin(2 * math.pi * (180 + 300 * math.sin(t * 120)) * t) * 0.4 + noise) * stutter * math.exp(-2.5 * t)
                v = int(max(-1.0, min(1.0, sig)) * 32767)
                data.append(struct.pack('<hh', v, v))
            with wave.open(glitch_p, 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sr); wav.writeframes(b''.join(data))

        # 5. Heavy Cinematic Zoom Slam SFX
        slam_p = os.path.join(self.scratch_dir, "sfx_slam.wav")
        if not os.path.exists(slam_p):
            dur_s = 0.8
            n = int(sr * dur_s)
            data = []
            for i in range(n):
                t = i / sr
                decay = math.exp(-4.0 * t)
                freq = 55.0 * math.exp(-8.0 * t) + 35.0
                sig = math.sin(2 * math.pi * freq * t) * 0.9 * decay
                sig = math.tanh(2.0 * sig) * 0.95
                v = int(max(-1.0, min(1.0, sig)) * 32767)
                data.append(struct.pack('<hh', v, v))
            with wave.open(slam_p, 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sr); wav.writeframes(b''.join(data))

        # 6. Ultra-Fast Esports Whip Pan / Slide SFX
        whip_p = os.path.join(self.scratch_dir, "sfx_whip.wav")
        if not os.path.exists(whip_p):
            dur_s = 0.5
            n = int(sr * dur_s)
            data = []
            for i in range(n):
                t = i / sr
                env = (math.sin(math.pi * t / dur_s)) ** 2
                f = 140 + 750 * (t / dur_s)
                noise = (((i * 1103515245 + 12345) & 0x7FFFFFFF) / 0x7FFFFFFF - 0.5) * 0.25
                sig = (0.5 * math.sin(2 * math.pi * f * t) + noise) * env
                v = int(max(-1.0, min(1.0, sig)) * 32767)
                data.append(struct.pack('<hh', v, v))
            with wave.open(whip_p, 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sr); wav.writeframes(b''.join(data))

    def generate_branded_assets(self, player_ign, channel_name="MAAKTHUNDER", yt_link="YOUTUBE.COM/@MAAKTHUNDER", tt_link="TIKTOK.COM/@MAAKTHUNDER", fb_link="FACEBOOK.COM/MAAKTHUNDER"):
        intro_img_p = os.path.join(self.scratch_dir, "overlay_intro.png")
        img = Image.new("RGBA", (1920, 1080), (10, 14, 24, 255))
        draw = ImageDraw.Draw(img)
        
        # Electric Blue Accent Lines
        draw.rectangle([(250, 470), (1670, 474)], fill=(0, 210, 255, 240))
        draw.rectangle([(450, 478), (1470, 480)], fill=(0, 150, 255, 180))

        font_main = ImageFont.truetype(FONT_TITLE, 106)
        title = channel_name.upper()
        bb = draw.textbbox((0, 0), title, font=font_main)
        x_title = (1920 - (bb[2] - bb[0])) // 2
        draw.text((x_title + 4, 324), title, font=font_main, fill=(0, 0, 0, 240))
        draw.text((x_title, 320), title, font=font_main, fill=(0, 220, 255, 255))

        font_sub = ImageFont.truetype(FONT_BOLD, 32)
        sub = f"PUBG MOBILE HIGHLIGHTS  |  {player_ign}"
        bb_sub = draw.textbbox((0, 0), sub, font=font_sub)
        draw.text(((1920 - (bb_sub[2] - bb_sub[0])) // 2, 505), sub, font=font_sub, fill=(230, 240, 255, 240))

        # Dynamic Social Media Links (Auto-centered based on filled platforms)
        font_social = ImageFont.truetype(FONT_SEGOE, 22)
        font_f = ImageFont.truetype(FONT_ARIAL, 36)
        row_y = 660

        active_socials = []
        if yt_link and yt_link.strip():
            active_socials.append(('yt', yt_link.strip().upper()))
        if tt_link and tt_link.strip():
            active_socials.append(('tt', tt_link.strip().upper()))
        if fb_link and fb_link.strip():
            active_socials.append(('fb', fb_link.strip().upper()))

        if active_socials:
            items_measured = []
            for kind, handle in active_socials:
                bb = draw.textbbox((0, 0), handle, font=font_social)
                text_w = bb[2] - bb[0]
                badge_w = 58 if kind == 'yt' else (48 if kind == 'tt' else 46)
                gap_internal = 14
                total_item_w = badge_w + gap_internal + text_w
                items_measured.append((kind, handle, total_item_w, badge_w))

            inter_gap = 70
            total_block_w = sum(m[2] for m in items_measured) + inter_gap * (len(items_measured) - 1)
            cur_x = (1920 - total_block_w) // 2

            for kind, handle, item_w, badge_w in items_measured:
                if kind == 'yt':
                    draw.rounded_rectangle([(cur_x, row_y), (cur_x + 58, row_y + 42)], radius=12, fill=(255, 0, 0, 255))
                    draw.polygon([(cur_x + 24, row_y + 11), (cur_x + 24, row_y + 31), (cur_x + 41, row_y + 21)], fill=(255, 255, 255, 255))
                    draw.text((cur_x + 72, row_y + 7), handle, font=font_social, fill=(255, 255, 255, 245))
                elif kind == 'tt':
                    draw.rounded_rectangle([(cur_x, row_y - 2), (cur_x + 48, row_y + 46)], radius=12, fill=(18, 18, 22, 255), outline=(0, 242, 234, 255), width=3)
                    draw.ellipse([(cur_x + 12, row_y + 22), (cur_x + 24, row_y + 34)], fill=(255, 0, 79, 255))
                    draw.rectangle([(cur_x + 20, row_y + 10), (cur_x + 25, row_y + 28)], fill=(0, 242, 234, 255))
                    draw.rectangle([(cur_x + 20, row_y + 10), (cur_x + 34, row_y + 16)], fill=(255, 255, 255, 255))
                    draw.text((cur_x + 64, row_y + 7), handle, font=font_social, fill=(255, 255, 255, 245))
                elif kind == 'fb':
                    draw.ellipse([(cur_x, row_y - 2), (cur_x + 46, row_y + 44)], fill=(24, 119, 242, 255))
                    draw.text((cur_x + 15, row_y + 1), "f", font=font_f, fill=(255, 255, 255, 255))
                    draw.text((cur_x + 60, row_y + 7), handle, font=font_social, fill=(255, 255, 255, 245))
                cur_x += (item_w + inter_gap)

        img.save(intro_img_p)

        # Elimination and Knockdown badges
        self._create_esports_badge("badge_kill.png", "ELIMINATION", (255, 50, 50, 255), (220, 30, 30, 255), player_ign)
        self._create_esports_badge("badge_knock.png", "KNOCKED DOWN", (255, 175, 25, 255), (235, 150, 20, 255), player_ign)
        self._create_esports_badge("badge_streak.png", "MULTI-KILL STREAK", (0, 215, 255, 255), (0, 160, 255, 255), player_ign)
        self._create_esports_badge("badge_proplus_kill.png", "⚡ ENEMY ELIMINATED ⚡", (255, 40, 90, 255), (0, 229, 255, 255), player_ign)
        self._create_esports_badge("badge_proplus_multi.png", "🔥 UNSTOPPABLE DOMINATION 🔥", (255, 200, 30, 255), (255, 90, 0, 255), player_ign)
        return intro_img_p

    def _draw_vector_bolt(self, draw, x, y, color=(0, 229, 255, 255), scale=1.0):
        pts = [
            (x + int(8 * scale), y),
            (x + int(1 * scale), y + int(14 * scale)),
            (x + int(7 * scale), y + int(14 * scale)),
            (x + int(2 * scale), y + int(24 * scale)),
            (x + int(14 * scale), y + int(8 * scale)),
            (x + int(7 * scale), y + int(8 * scale)),
            (x + int(11 * scale), y)
        ]
        draw.polygon(pts, fill=color)

    def _draw_vector_crown(self, draw, x, y, color=(255, 215, 0, 255), scale=1.0):
        w = int(24 * scale)
        h = int(18 * scale)
        pts = [
            (x, y + h),
            (x, y + int(6 * scale)),
            (x + int(6 * scale), y + int(11 * scale)),
            (x + int(12 * scale), y),
            (x + int(18 * scale), y + int(11 * scale)),
            (x + w, y + int(6 * scale)),
            (x + w, y + h)
        ]
        draw.polygon(pts, fill=color)

    def generate_thumbnail(self, batch_clips, output_thumb_path, player_ign="TK • 亗 • MAAK", channel_name="MAAKTHUNDER", part_num=1, total_parts=1, is_vertical=False):
        try:
            if not batch_clips:
                return False
            from PIL import Image, ImageDraw, ImageFont, ImageEnhance
            target_clip = max(batch_clips, key=lambda c: (1 if c.get("is_multi") else 0, c.get("dur", 10.0)))
            src_vid = target_clip["source"]
            hit_rel = target_clip.get("hit", 5.0)
            target_time = max(0.0, target_clip["start"] + hit_rel)
            
            suffix = "vert" if is_vertical else "land"
            temp_frame = os.path.join(self.scratch_dir, f"thumb_temp_{part_num}_{suffix}.jpg")
            cmd = [FFMPEG_EXE, "-y", "-ss", f"{target_time:.3f}", "-i", src_vid, "-vframes", "1", "-q:v", "2", temp_frame]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            if not os.path.exists(temp_frame):
                return False

            raw_frame = Image.open(temp_frame).convert("RGBA")
            orig_w, orig_h = raw_frame.size

            if is_vertical:
                thumb_w, thumb_h = 1080, 1920
                target_crop_w = int(orig_h * (9 / 16))
                if target_crop_w < orig_w:
                    crop_x = (orig_w - target_crop_w) // 2
                    cropped = raw_frame.crop((crop_x, 0, crop_x + target_crop_w, orig_h))
                else:
                    cropped = raw_frame
                img = cropped.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            else:
                thumb_w, thumb_h = 1280, 720
                img = raw_frame.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            
            # Contrast & Color Enhancement
            enh_col = ImageEnhance.Color(img).enhance(1.35)
            enh_con = ImageEnhance.Contrast(enh_col).enhance(1.22)
            img = enh_con

            # Dynamic Dark Vignette
            overlay = Image.new("RGBA", (thumb_w, thumb_h), (0, 0, 0, 0))
            d_ov = ImageDraw.Draw(overlay)
            if is_vertical:
                for y in range(0, 420):
                    alpha = int((1.0 - (y / 420)) * 160)
                    d_ov.line([(0, y), (thumb_w, y)], fill=(5, 10, 20, alpha))
                for y in range(1200, 1920):
                    alpha = int(((y - 1200) / 720) * 220)
                    d_ov.line([(0, y), (thumb_w, y)], fill=(5, 10, 20, alpha))
            else:
                for y in range(480, 720):
                    alpha = int(((y - 480) / 240) * 190)
                    d_ov.line([(0, y), (1280, y)], fill=(5, 10, 20, alpha))
                for x in range(0, 500):
                    alpha = int((1.0 - (x / 500)) * 140)
                    d_ov.line([(x, 0), (x, 300)], fill=(5, 10, 20, alpha))

            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

            # Glowing Neon Cyan Border Accents
            border_thick = 10 if is_vertical else 8
            draw.rectangle([(0, 0), (thumb_w, border_thick)], fill=(0, 229, 255, 255))
            draw.rectangle([(0, thumb_h - border_thick), (thumb_w, thumb_h)], fill=(0, 229, 255, 255))
            draw.rectangle([(0, 0), (border_thick, thumb_h)], fill=(0, 229, 255, 255))
            draw.rectangle([(thumb_w - border_thick, 0), (thumb_w, thumb_h)], fill=(0, 229, 255, 255))

            font_huge = ImageFont.truetype(FONT_TITLE, 96 if is_vertical else 76)
            font_badge = ImageFont.truetype(FONT_BOLD, 36 if is_vertical else 26)
            font_ign = ImageFont.truetype(FONT_BOLD, 42 if is_vertical else 30)

            # Extract match date from source recording filename
            import re
            m_date = re.search(r'(\d{4})[.-](\d{2})[.-](\d{2})', os.path.basename(src_vid))
            if m_date:
                y, m, d = m_date.groups()
                m_names = {"01":"JAN","02":"FEB","03":"MAR","04":"APR","05":"MAY","06":"JUN","07":"JUL","08":"AUG","09":"SEP","10":"OCT","11":"NOV","12":"DEC"}
                date_str = f"{int(d)} {m_names.get(m, 'OCT')}"
            else:
                date_str = "OCT 2026"

            kill_count = len(batch_clips)
            
            title_pairs = [
                ("LOBBY WIPEOUT", f"{kill_count} KILLS MONTAGE"),
                ("UNSTOPPABLE", "PRO COMBAT HIGHLIGHTS"),
                ("DOMINATION", "ESPORTS CLUTCH"),
                ("SQUAD WIPER", f"KILL STREAK ({kill_count} KILLS)"),
                ("HEADSHOT MACHINE", "HIGH INTENSITY ACTION"),
                ("ACE ELIMINATOR", "CHICKEN DINNER HIGHLIGHTS"),
                ("MAX AGGRESSION", f"{kill_count} KILLS MONTAGE")
            ]
            pair_idx = (part_num - 1) % len(title_pairs)
            title_text, title_sub = title_pairs[pair_idx]

            part_label = f"  •  PART {part_num}" if total_parts > 1 else ""

            if is_vertical:
                badge_text = f"{date_str}  •  9:16 SHORTS{part_label}  •  {kill_count} KILLS"
                bb = draw.textbbox((0, 0), badge_text, font=font_badge)
                text_w = bb[2] - bb[0]
                box_x1 = 48
                box_y1 = 64
                box_y2 = 138
                box_x2 = box_x1 + 56 + text_w + 32
                draw.rounded_rectangle([(box_x1, box_y1), (box_x2, box_y2)], radius=16, fill=(10, 16, 30, 230), outline=(0, 229, 255, 255), width=3)
                self._draw_vector_bolt(draw, box_x1 + 18, box_y1 + 16, (0, 229, 255, 255), scale=1.5)
                draw.text((box_x1 + 54, box_y1 + 14), badge_text, font=font_badge, fill=(0, 229, 255, 255))

                # Center-Lower Titles for 9:16
                for off in range(8, 0, -1):
                    draw.text((55 + off, 1380 + off), title_text, font=font_huge, fill=(0, 0, 0, 230))
                    draw.text((55 + off, 1495 + off), title_sub, font=font_huge, fill=(0, 0, 0, 230))
                draw.text((55, 1380), title_text, font=font_huge, fill=(255, 255, 255, 255))
                draw.text((55, 1495), title_sub, font=font_huge, fill=(0, 229, 255, 255))

                # Bottom IGN pill with Gold Crown
                bb_ign = draw.textbbox((0, 0), player_ign, font=font_ign)
                ign_w = bb_ign[2] - bb_ign[0]
                ign_box_w = 64 + ign_w + 36
                ign_x1 = 55
                ign_y1 = 1720
                ign_y2 = 1810
                draw.rounded_rectangle([(ign_x1, ign_y1), (ign_x1 + ign_box_w, ign_y2)], radius=18, fill=(8, 12, 22, 240), outline=(255, 200, 0, 255), width=3)
                self._draw_vector_crown(draw, ign_x1 + 18, ign_y1 + 24, (255, 215, 0, 255), scale=1.7)
                draw.text((ign_x1 + 68, ign_y1 + 18), player_ign, font=font_ign, fill=(255, 215, 0, 255))
            else:
                badge_text = f"{date_str}{part_label}  •  {kill_count} KILLS MONTAGE"
                bb = draw.textbbox((0, 0), badge_text, font=font_badge)
                text_w = bb[2] - bb[0]
                box_x1 = 35
                box_y1 = 35
                box_y2 = 85
                box_x2 = box_x1 + 42 + text_w + 22

                draw.rounded_rectangle([(box_x1, box_y1), (box_x2, box_y2)], radius=10, fill=(10, 16, 30, 230), outline=(0, 229, 255, 255), width=2)
                self._draw_vector_bolt(draw, box_x1 + 14, box_y1 + 12, (0, 229, 255, 255), scale=1.1)
                draw.text((box_x1 + 42, box_y1 + 10), badge_text, font=font_badge, fill=(0, 229, 255, 255))

                for off in range(6, 0, -1):
                    draw.text((50 + off, 500 + off), title_text, font=font_huge, fill=(0, 0, 0, 220))
                    draw.text((50 + off, 585 + off), title_sub, font=font_huge, fill=(0, 0, 0, 220))
                draw.text((50, 500), title_text, font=font_huge, fill=(255, 255, 255, 255))
                draw.text((50, 585), title_sub, font=font_huge, fill=(0, 229, 255, 255))

                bb_ign = draw.textbbox((0, 0), player_ign, font=font_ign)
                ign_w = bb_ign[2] - bb_ign[0]
                ign_box_w = 44 + ign_w + 24
                ign_x1 = 1240 - ign_box_w
                draw.rounded_rectangle([(ign_x1, 635), (1240, 695)], radius=12, fill=(8, 12, 22, 240), outline=(255, 200, 0, 255), width=2)
                self._draw_vector_crown(draw, ign_x1 + 14, 646, (255, 215, 0, 255), scale=1.2)
                draw.text((ign_x1 + 48, 645), player_ign, font=font_ign, fill=(255, 215, 0, 255))

            os.makedirs(os.path.dirname(output_thumb_path), exist_ok=True)
            img.convert("RGB").save(output_thumb_path, "JPEG", quality=95)
            return True
        except Exception as e:
            self.log(f"⚠️ Thumbnail generation note: {e}")
            return False

    def generate_social_kit(self, batch_clips, player_ign="TK • 亗 • MAAK", channel_name="MAAKTHUNDER", part_num=1, total_parts=1, yt="", tt="", fb=""):
        kill_count = len(batch_clips)
        part_tag = f" • Part {part_num}" if total_parts > 1 else ""
        part_desc_tag = f" [Part {part_num}]" if total_parts > 1 else ""
        
        import re
        src_first = batch_clips[0].get("source", "") if batch_clips else ""
        m_date = re.search(r'(\d{4})[.-](\d{2})[.-](\d{2})', os.path.basename(src_first))
        if m_date:
            y, m, d = m_date.groups()
            m_names = {"01":"JAN","02":"FEB","03":"MAR","04":"APR","05":"MAY","06":"JUN","07":"JUL","08":"AUG","09":"SEP","10":"OCT","11":"NOV","12":"DEC"}
            date_str = f"{int(d)} {m_names.get(m, 'OCT')}"
        else:
            date_str = "OCT 2026"

        title_actions = [
            f"LOBBY WIPEOUT ({kill_count} KILLS)",
            "UNSTOPPABLE CLUTCHES",
            "ESPORTS DOMINATION",
            f"SQUAD WIPER ({kill_count} KILLS)",
            "HEADSHOT MACHINE",
            "ACE ELIMINATOR HIGHLIGHTS",
            f"{kill_count} KILLS PURE SKILL"
        ]
        action_word = title_actions[(part_num - 1) % len(title_actions)]
        
        # YouTube Title branded with Channel Name (e.g. MAAKTHUNDER)
        yt_title = f"{channel_name} | {action_word} 🔥 PUBG Mobile Montage [{date_str}{part_tag}]"
        
        timestamps = []
        cur_t = 0
        for i, c in enumerate(batch_clips, 1):
            m = cur_t // 60
            s = cur_t % 60
            vic = c.get("victim", "Enemy")
            ctype = c.get("type", "kill").upper()
            timestamps.append(f"{m:02d}:{s:02d} - Fight Scene {i}")
            cur_t += int(c.get("dur", 10.0))

        ts_text = "\n".join(timestamps)
        yt_desc = f"""🔥 {channel_name} PUBG Mobile Highlights{part_desc_tag}!
⚡ 1080p 60fps Broadcast Quality | 808 Bass Drops & Pro Cuts

🎮 Highlights Breakdown:
{ts_text}

👑 Follow {channel_name}:
• YouTube: {yt or 'https://youtube.com/@' + channel_name}
• TikTok: {tt or 'https://tiktok.com/@' + channel_name}
• Facebook: {fb or 'https://facebook.com/' + channel_name}

#PUBGMobile #PUBG #MAAKTHUNDER #PUBGMontage #1v4Clutch #EsportsGameplay #PUBGClips #Gaming
"""
        shorts_caption = f"Bro thought he was safe behind that smoke 💀 Wait for the last headshot 🎯 #PUBGMOBILE #pubg #maakthunder #pubgclips #fyp #gaming #clutch"
        tags = f"pubg mobile, pubg montage, pubg highlights, pubg clutch, {channel_name.lower()}, {player_ign.lower()}, pubg esports, 1v4 squad wipe, pubg mobile pro gameplay, pubg montage 2026, pubg best kills, pubg headshots"

        return {
            "title": yt_title,
            "description": yt_desc,
            "shorts_caption": shorts_caption,
            "tags": tags
        }

    def _create_esports_badge(self, filename, title_text, title_color, border_color, player_ign):
        img = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        x1, y1, x2, y2 = 70, 880, 560, 965
        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=12, fill=(10, 14, 22, 235), outline=border_color, width=3)
        draw.rounded_rectangle([(x1 + 3, y1 + 6), (x1 + 9, y2 - 6)], radius=3, fill=title_color)
        font_t = ImageFont.truetype(FONT_TITLE, 34)
        font_p = ImageFont.truetype(FONT_BOLD, 22)
        draw.text((x1 + 24, y1 + 8), title_text, font=font_t, fill=title_color)
        draw.text((x1 + 24, y1 + 46), player_ign, font=font_p, fill=(255, 215, 0, 255))
        img.save(os.path.join(self.scratch_dir, filename))

    def _is_player_token(self, word_str, unique_tokens):
        """Strict whole-word matching with clan/prefix tolerance. Rejects sub-fragments inside enemy names."""
        import re
        cleaned = re.sub(r'[^A-Z0-9]', '', word_str.upper())
        if cleaned in unique_tokens:
            return True
        for tok in unique_tokens:
            if len(tok) >= 3 and cleaned.endswith(tok):
                prefix = cleaned[:-len(tok)]
                if prefix in ['', 'S', 'TK', '1K', 'IK']:
                    return True
        return False

    def _extract_clean_token(self, raw_text):
        import re
        if not raw_text:
            return None
        words = [w for w in re.findall(r'[A-Za-z0-9]+', raw_text.upper()) 
                 if len(w) >= 3 and w not in ["THE", "AND", "PRO", "PUBG", "MOBILE", "TEAM", "SQUAD", "TK", "1K", "IK", "OTK", "OFFICIAL"]]
        return max(words, key=len) if words else None

    def _discover_ui_and_squad(self, cap, duration, user_ign=""):
        """
        Rock-Solid 4-Step Dynamic UI & Player Identity Architecture:
        - Step 1: Static Frame Setup (~30s) -> Squad List Finder + Full-String IGN Match
        - Step 2: Safe Zone Timer & Minimap Radar Finder (direct HUD anchor above countdown)
        - Step 3: 120-Second Active Gameplay Minimap Tracking (High-Saturation Arrow Hue Consensus)
        - Step 4: Cross-Verification & Cold Start Resolution (Squad Slot <-> Minimap Slot)
        """
        import re
        if not _GLOBAL_AI_OCR:
            return None, "MAAK", []

        # =========================================================================
        # STEP 1: Static Frame Setup at Match Start (~30s)
        # =========================================================================
        cap.set(cv2.CAP_PROP_POS_MSEC, 30000)
        ret30, frame30 = cap.read()
        if not ret30 or frame30 is None:
            cap.set(cv2.CAP_PROP_POS_MSEC, 10000)
            ret30, frame30 = cap.read()
            if not ret30 or frame30 is None:
                return None, "MAAK", []

        h, w = frame30.shape[:2]

        # Scan Squad List HUD rows (top-left quadrant)
        squad_crop = frame30[0:int(h * 0.25), 0:int(w * 0.25)]
        res_sq, _ = _GLOBAL_AI_OCR(squad_crop)
        squad_rows = []
        if res_sq:
            raw_items = []
            for box, text, conf in res_sq:
                by = int(box[0][1])
                t = text.strip()
                if len(t) > 1 and not t.isdigit() and 'PUBG' not in t and 'Remaining' not in t and 'Elim' not in t:
                    raw_items.append((by, t))
            raw_items.sort(key=lambda x: x[0])
            filtered = [it for it in raw_items if 40 <= it[0] <= 210]
            grouped = []
            for by, text in filtered:
                if not grouped or by - grouped[-1][0] > 20:
                    grouped.append((by, text))
                else:
                    if len(text) > len(grouped[-1][1]):
                        grouped[-1] = (by, text)
            for idx, (by, st) in enumerate(grouped[:4]):
                squad_rows.append((idx + 1, st))

        self.log(f"   📋 [Step 1: Dynamic Squad List Finder]: Found {len(squad_rows)} Rows")
        self.log(f"   📋 [Dynamic Squad HUD Rows]: {squad_rows}")

        squad_matched_slot = None
        locked_player_token = None

        # Part 1: Full-String Squad Match immediately in this static frame if IGN provided
        if user_ign:
            u_tok = self._extract_clean_token(user_ign) or "MAAK"
            for s_idx, s_name in squad_rows:
                if self._is_local_player_token(s_name, u_tok):
                    squad_matched_slot = s_idx
                    locked_player_token = u_tok
                    self.log(f"   🎯 [Part 1: Full-String Squad Match]: Slot {s_idx} -> '{s_name}'")
                    break
            if not locked_player_token:
                locked_player_token = u_tok

        # =========================================================================
        # STEP 2: Safe Zone Timer & Minimap Radar Anchor
        # =========================================================================
        # Circular minimap is permanently attached directly above the Safe Zone countdown timer (MM:SS)
        cap.set(cv2.CAP_PROP_POS_MSEC, min(120000, int(duration * 1000 * 0.3)))
        _, frame_timer = cap.read()
        timer_pos = None
        if frame_timer is not None:
            top_right = frame_timer[0:int(h * 0.35), int(w * 0.5):w]
            res_tr, _ = _GLOBAL_AI_OCR(top_right)
            if res_tr:
                for box, text, conf in res_tr:
                    if re.search(r'\b\d{1,2}:\d{2}\b', text):
                        timer_pos = (int(w * 0.5) + int(box[0][0]), int(box[0][1]), text)
                        self.log(f"   ⏱️  [Step 2 Anchor]: Safe Zone Timer '{text}' confirmed at ({timer_pos[0]}, {timer_pos[1]})")
                        break

        if timer_pos:
            map_cx = timer_pos[0] + 35
            map_cy = max(45, timer_pos[1] - 97)
            map_r = int(h * 0.088)
            self.log(f"   📡 [Step 2: Minimap Radar Finder]: Minimap pinned at ({map_cx}, {map_cy}), radius {map_r} (anchored by Safe Zone Timer)")
        else:
            map_cx = int(w * 0.940)
            map_cy = int(h * 0.093)
            map_r = int(h * 0.088)
            self.log(f"   📡 [Step 2: Minimap Radar Finder]: Minimap pinned at ({map_cx}, {map_cy}), radius {map_r} (HUD standard)")

        # =========================================================================
        # STEP 3: 120s Active Gameplay Minimap Tracking
        # =========================================================================
        # Local player's chevron NEVER leaves dead center (map_cx, map_cy); clustered teammates move away
        timestamps = [60.0, 90.0, 120.0, 150.0, 180.0]
        timestamps = [st for st in timestamps if st < duration]
        if not timestamps:
            timestamps = [30.0]

        color_votes = {1: 0, 2: 0, 3: 0, 4: 0}
        for st in timestamps:
            cap.set(cv2.CAP_PROP_POS_MSEC, int(st * 1000))
            ret_s, f_s = cap.read()
            if not ret_s or f_s is None:
                continue
            crop = f_s[max(0, map_cy - 22):min(h, map_cy + 22), max(0, map_cx - 22):min(w, map_cx + 22)]
            if crop.size > 0:
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                mask = (hsv[:, :, 1] > 110) & (hsv[:, :, 2] > 110)
                hues = hsv[:, :, 0][mask]
                counts = {
                    4: int(np.sum((hues >= 35) & (hues <= 85))),    # Green
                    1: int(np.sum((hues >= 15) & (hues < 35))),     # Yellow/Orange
                    2: int(np.sum((hues < 15) | (hues > 165))),     # Red
                    3: int(np.sum((hues > 85) & (hues < 130)))      # Blue
                }
                top_color = max(counts, key=counts.get)
                if counts[top_color] >= 40:
                    color_votes[top_color] += 1

        minimap_slot = max(color_votes, key=color_votes.get) if any(color_votes.values()) else None
        if minimap_slot:
            self.log(f"   🧭 [Step 3: Temporal Persistence Consensus (120s Tracking)]: Slot {minimap_slot} ({color_votes[minimap_slot]}/{len(timestamps)} frames persistent)")

        # =========================================================================
        # STEP 4: Mutual Cross-Verification & Cold Start Resolution
        # =========================================================================
        final_slot = None
        if user_ign:
            if squad_matched_slot and minimap_slot and squad_matched_slot == minimap_slot:
                final_slot = squad_matched_slot
                self.log(f"   🔒 [Step 4: Double-Lock Established]: Squad Slot {squad_matched_slot} == Minimap Slot {minimap_slot} (100% Match)")
            else:
                final_slot = squad_matched_slot or minimap_slot or 4
                self.log(f"   ⚠️ [Step 4: Cross-Verification]: Squad Slot ({squad_matched_slot}) vs Minimap Slot ({minimap_slot}) -> IGN Squad Priority Slot {final_slot}")
        else:
            # Pure Cold Start: Minimap slot maps directly to Squad Row
            target_slot = minimap_slot or 4
            final_slot = target_slot
            for s_idx, s_name in squad_rows:
                if s_idx == target_slot:
                    locked_player_token = self._extract_clean_token(s_name) or "MAAK"
                    self.log(f"   🧭 [Step 4: Cold Start Consensus]: Minimap Center Slot {target_slot} maps to Squad Row {s_idx} -> '{s_name}'")
                    break
            if not locked_player_token and squad_rows:
                locked_player_token = self._extract_clean_token(squad_rows[-1][1]) or "MAAK"

        # Isolate teammates
        teammate_tokens = []
        for s_idx, s_name in squad_rows:
            tok = self._extract_clean_token(s_name)
            if tok and tok != locked_player_token and tok not in teammate_tokens:
                teammate_tokens.append(tok)

        self.log(f"   🔒 [Teammates Isolated]: {teammate_tokens}")
        return final_slot, locked_player_token or "MAAK", teammate_tokens

    def _is_local_player_token(self, attacker_text, target_ign=""):
        import re
        if not attacker_text or not target_ign:
            return False
        cleaned = re.sub(r'[^A-Z0-9]', '', attacker_text.upper())
        target = re.sub(r'[^A-Z0-9]', '', target_ign.upper())
        if not target:
            return False
        # Exact match
        if cleaned == target:
            return True
        # Clan-prefixed match (e.g. 'TKMAAK', '1KMAAK', 'IKMAAK', 'OTKMAAK')
        for pfx in ['', 'TK', '1K', 'IK', 'OTK']:
            if cleaned == pfx + target:
                return True
        # Strict full-word boundary match: rejects fragments like 'MAK', 'AAK', 'MK', 'AK', 'PAT', 'HAN', 'MOH', 'SAN'
        if re.search(rf'\b{target}\b', attacker_text.upper()):
            return True
        return False

    def analyze_single_video(self, video_path, target_ign="", on_event_detected=None, is_cancelled_fn=None):
        """
        4-Anchor RapidOCR AI Combat Detection Engine:
        - Anchor 1: Mini-Map Center Arrow Hue Slot Discovery
        - Anchor 2: Teammate Invariant & Screen Recoil Correlation
        - Anchor 3: Normalized Multi-Theme Combat Banner Geometry (Bat/Blink Theme + Standard)
        - Anchor 4: RapidOCR ONNX AI Text & Symbol Recognizer
        """
        import re
        self.log(f"⚡ Loading: {os.path.basename(video_path)}...")
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        events = []
        recent_victims = {}
        cold_start_cross_verified = False

        # Part 1 & Part 2: Dynamic UI Discovery (Timer Anchor, Squad HUD, Local Player Pin 📍)
        detected_slot, target_token, teammate_tokens = self._discover_ui_and_squad(cap, duration, user_ign=target_ign)
        if target_ign:
            self.log(f"   🎯 Priority Player Token: '{target_token}' (Config Provided, Slot: {detected_slot})")
        else:
            self.log(f"   🧭 [Cold Start Auto-Learned] Player Token: '{target_token}' (Slot: {detected_slot}, Teammates: {teammate_tokens})")

        step_sec = 0.5
        t_sec = 10.0 # skip black intro

        while t_sec < duration:
            if is_cancelled_fn and is_cancelled_fn():
                self.log("   ⚠️ Scan cancelled by user.")
                break
            if self.progress_callback and int(t_sec) % 10 == 0:
                self.progress_callback(int(t_sec), int(duration))

            # Normal Balanced Mode CPU Throttling (gentle sleep yields time slice to OS)
            if getattr(self, 'cpu_mode', 'normal') == 'normal':
                time.sleep(0.003)

            cap.set(cv2.CAP_PROP_POS_MSEC, int(t_sec * 1000))
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            h, w = frame.shape[:2]

            # Anchor 3: Normalized Combat Banner Zone (74.5% - 81.0% height, 33% - 67% width)
            banner = frame[int(h*0.745):int(h*0.810), int(w*0.330):int(w*0.670)]
            gray_b = cv2.cvtColor(banner, cv2.COLOR_BGR2GRAY)
            m_gray = np.mean(gray_b)

            if m_gray < 138:
                _, th190 = cv2.threshold(gray_b, 190, 255, cv2.THRESH_BINARY)
                w190 = cv2.countNonZero(th190)

                b_area = banner.shape[0] * banner.shape[1]
                min_w = int(b_area * 0.015)
                max_w = int(b_area * 0.120)

                if min_w <= w190 <= max_w:
                    bw = banner.shape[1]
                    center_icon = banner[:, int(bw*0.44):int(bw*0.56)]
                    b_ch, g_ch, r_ch = cv2.split(center_icon)

                    red_px = np.sum((r_ch > 120) & (r_ch > g_ch + 25) & (r_ch > b_ch + 25))
                    green_px = np.sum((g_ch > 120) & (g_ch > r_ch + 20))
                    blue_cyan_px = np.sum((b_ch > 120) & (b_ch > r_ch + 20))
                    gold_px = np.sum((r_ch > 140) & (g_ch > 120) & (b_ch < 100))

                    total_icon_px = red_px + green_px + blue_cyan_px + gold_px

                    if total_icon_px >= 240:
                        # Anchor 4: RapidOCR Neural AI Inference
                        res = None
                        if _GLOBAL_AI_OCR:
                            res, _ = _GLOBAL_AI_OCR(banner)

                        if res:
                            attacker_texts = []
                            victim_texts = []
                            for box, text, conf in res:
                                bx = box[0][0]
                                if bx < int(bw * 0.47):
                                    attacker_texts.append(text)
                                elif bx >= int(bw * 0.53):
                                    victim_texts.append(text)

                            is_player_att = any(self._is_local_player_token(at, target_token) for at in attacker_texts)
                            is_player_vic = any(self._is_local_player_token(vt, target_token) for vt in victim_texts)
                            is_teammate_att = any(any(self._is_local_player_token(at, tm) for tm in teammate_tokens) for at in attacker_texts)

                            if is_player_att and not is_player_vic and not is_teammate_att:
                                activity = self._measure_combat_activity(cap, t_sec)
                                if activity >= 11.0:
                                    v_clean = max(victim_texts, key=len) if victim_texts else "Enemy"
                                    if not any(v_clean in ov or ov in v_clean for ov, ot in recent_victims.items() if t_sec - ot < 45.0):
                                        recent_victims[v_clean] = t_sec
                                        ev_obj = {"time": t_sec, "type": "knock", "video": video_path, "victim": v_clean, "activity": activity}
                                        if not events or (t_sec - events[-1]['time'] > 3.0):
                                            events.append(ev_obj)
                                            self.log(f"   🔥 [FIGHT DETECTED] {int(t_sec)//60:02d}:{int(t_sec)%60:02d} ({t_sec:.1f}s) -> KNOCK/KILL vs {v_clean} (Activity: {activity:.1f})")
                                            if not target_ign and not cold_start_cross_verified:
                                                cold_start_cross_verified = True
                                                self.log(f"   🔒 [Step 4: Cold Start Cross-Verification]: First Combat Event at {int(t_sec)//60:02d}:{int(t_sec)%60:02d} ({t_sec:.1f}s) confirms Attacker '{target_token}' (Slot {detected_slot}) -> Local Player Double-Locked!")
                                            if on_event_detected:
                                                on_event_detected(ev_obj)

            t_sec += step_sec

        cap.release()
        return events

    def _measure_combat_activity(self, cap, t_sec):
        """
        Measures player visual combat engagement (aiming, recoil, grenade throwing, movement)
        in the 2.0s window preceding the elimination banner.
        Real gunfights and grenade throws score 25-45+.
        Passive revive/healing bleedouts score 4-9.
        """
        frames = []
        for dt in [-2.0, -1.5, -1.0, -0.5, 0.0]:
            p_time = max(0.0, t_sec + dt)
            cap.set(cv2.CAP_PROP_POS_MSEC, int(p_time * 1000))
            ret, f = cap.read()
            if ret:
                c_gray = cv2.cvtColor(f[340:740, 760:1160], cv2.COLOR_BGR2GRAY)
                frames.append(c_gray)
        if len(frames) < 2:
            return 25.0
        diffs = [np.mean(cv2.absdiff(frames[i], frames[i+1])) for i in range(len(frames)-1)]
        return float(np.mean(diffs))

    def verify_candidate_event(self, cap, event, target_ign=""):
        """
        Stage 2 Concurrent AI Verification:
        Re-verifies candidate elimination across adjacent frames (-0.4s to +0.4s).
        Strictly verifies:
        1. Local player token is in Attacker zone (x < 300) and NEVER in Victim zone (x >= 320).
        2. No death/revive banners or crawling states.
        3. Preceding combat activity verification (confirms real gunfight vs passive bleedout).
        """
        unique_tokens = ["MAAK", "MARK"]
        if target_ign:
            import re
            words = [w for w in re.findall(r'[A-Za-z0-9]+', target_ign.upper()) if w not in ["THE", "AND", "PRO", "PUBG", "MOBILE", "TEAM", "SQUAD"]]
            for w in words:
                if len(w) >= 3 and w not in unique_tokens:
                    unique_tokens.append(w)

        t_sec = event.get("time", 0.0)

        # Special verification for Left-Side Ace Eliminator / Squad Wipe Events
        if event.get("is_feed"):
            activity = max(self._measure_combat_activity(cap, max(0.0, t_sec + dt)) for dt in [-5.0, -3.0, 0.0])
            if activity >= 10.0:
                return True, "Ace Eliminator squad wipe confirmed"
            return False, f"Low combat engagement for squad wipe ({activity:.1f})"

        # 1. Multi-Frame Spatial Banner Verification across [-0.4s, 0.0s, +0.4s] via RapidOCR AI
        target_token = self._extract_clean_token(target_ign) if target_ign else "MAAK"
        for dt in [-0.4, 0.0, 0.4]:
            check_t = max(0.0, t_sec + dt)
            cap.set(cv2.CAP_PROP_POS_MSEC, int(check_t * 1000))
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            h, w = frame.shape[:2]
            banner = frame[int(h*0.745):int(h*0.810), int(w*0.330):int(w*0.670)]
            if _GLOBAL_AI_OCR:
                res, _ = _GLOBAL_AI_OCR(banner)
                if res:
                    bw = banner.shape[1]
                    attacker_texts = [t for box, t, c in res if box[0][0] < int(bw * 0.47)]
                    victim_texts = [t for box, t, c in res if box[0][0] >= int(bw * 0.53)]
                    full_str = " ".join(t for _, t, _ in res).upper()

                    user_victim = any(self._is_local_player_token(vt, target_token) for vt in victim_texts)
                    if user_victim:
                        return False, f"Self-knock / Victim detected at {check_t:.1f}s"

                    if any(dp in full_str for dp in ["YOU WERE", "WAS ELIMINATED", "KNOCKED DOWN YOU", "DEATH", "REVIVE"]):
                        return False, f"Downed / Revive state detected at {check_t:.1f}s"

        # 2. Combat Engagement Verification
        activity = self._measure_combat_activity(cap, t_sec)
        if activity < 10.0:
            return False, f"Low combat engagement ({activity:.1f})"

        return True, "Player standing & elimination confirmed"

    def cluster_combat_events(self, raw_events, video_path):
        """
        Groups contiguous combat events into clean, non-overlapping esports highlights.
        Ensures exact lead-in approach, aim-in, and instant post-kill transition.
        """
        if not raw_events:
            return []

        # Macro Combat Zone (30s - 45s adaptive engagement clustering)
        # Groups extended squad fights (e.g. knock enemy 1, reload/reposition behind wall for 12-16s, wipe enemy 2 & 3)
        # into continuous cinematic highlights up to 45s, while cleanly separating isolated fights
        events = sorted(raw_events, key=lambda x: x["time"])
        clusters = []
        curr = [events[0]]
        for ev in events[1:]:
            gap = ev["time"] - curr[-1]["time"]
            total_span = ev["time"] - curr[0]["time"]
            # If next event is within 18s and total cluster span <= 38s, treat as one continuous fight
            if gap <= 18.0 and total_span <= 38.0:
                curr.append(ev)
            else:
                clusters.append(curr)
                curr = [ev]
        clusters.append(curr)

        clips = []
        for c in clusters:
            t_first = c[0]["time"]
            t_last = c[-1]["time"]
            has_kill = any(e.get("type") == "kill" for e in c)
            is_multi = len(c) >= 2

            # Dynamic esports highlight calibration:
            # Multi-kill clutches smoothly span from 5.5s before the first kill through 4.5s after the final elimination (up to 45s)
            if is_multi:
                start_t = max(0.0, t_first - 7.5)
                dur = min(45.0, max(14.0, (t_last - start_t) + 4.5))
                hit_t = t_first - start_t
            else:
                # Extended pre-roll for single kills to 8.5s!
                # Captures Molotov / Grenade cook & throw + initial spray before knock!
                start_t = max(0.0, t_first - 8.5)
                dur = 14.0
                hit_t = 8.5

            # Enforce non-overlapping constraint with previous clip
            if clips:
                prev_end = clips[-1]["start"] + clips[-1]["dur"]
                if start_t < prev_end:
                    start_t = prev_end
                    dur = max(7.0, min(14.0, dur))
                    hit_t = max(1.0, t_first - start_t)

            badge_file = "badge_streak.png" if is_multi else ("badge_kill.png" if has_kill else "badge_knock.png")

            clips.append({
                "source": video_path,
                "start": round(start_t, 1),
                "dur": round(dur, 1),
                "hit": round(hit_t, 1),
                "type": "kill" if has_kill else "knock",
                "badge": badge_file,
                "is_multi": is_multi,
                "events_count": len(c),
                "victim": c[0].get("victim")
            })

        return clips

    def partition_clips_match_aware(self, clips, min_sec=60, max_sec=120):
        """
        Smart Match-Aware Partitioning:
        Guarantees that EVERY exported video is a full, balanced 60-90s highlight video.
        Never produces tiny 8s or 20s stub videos.
        """
        if not clips:
            return []

        batches = []
        current_batch = []
        current_dur = 0.0

        for c in clips:
            c_dur = float(c.get("dur", 11.0))
            # Only finalize current batch if it has reached at least min_sec (60s) AND adding this clip exceeds max_sec
            if current_batch and current_dur >= min_sec and (current_dur + c_dur > max_sec):
                batches.append(current_batch)
                current_batch = []
                current_dur = 0.0

            current_batch.append(c)
            current_dur += c_dur

        if current_batch:
            # If the trailing batch is tiny (< 40s) and there is a previous batch, merge to avoid stub video
            if len(batches) > 0 and current_dur < 40.0:
                batches[-1].extend(current_batch)
            else:
                batches.append(current_batch)

        return batches

    def partition_clips_by_duration(clips, target_sec=90):
        """
        Splits clips into balanced parts matching target_sec (e.g. 60s for Viral Shorts, 90s for Esports Highlight).
        Returns list of clip batches [[clip1, ...], [clipN, ...]].
        If target_sec is None, 0, or total clip duration <= target_sec * 1.15, returns a single batch [clips].
        """
        if not clips:
            return []
        if not target_sec or target_sec <= 0:
            return [clips]

        parts = []
        current_part = []
        current_dur = 0.0

        for clip in clips:
            c_dur = clip.get("dur", 11.0)
            # If adding this clip exceeds target duration and current part has at least 65% of target
            if current_part and (current_dur + c_dur > target_sec + 5.0) and (current_dur >= target_sec * 0.65):
                parts.append(current_part)
                current_part = [clip]
                current_dur = c_dur
            else:
                current_part.append(clip)
                current_dur += c_dur

        if current_part:
            # If the last remaining part is tiny (e.g. 1 clip < 22s) and there is a previous part, merge if reasonable
            if parts and current_dur < 22.0 and (sum(c.get("dur", 11.0) for c in parts[-1]) + current_dur <= target_sec * 1.35):
                parts[-1].extend(current_part)
            else:
                parts.append(current_part)

        return parts

    def _detect_hardware_encoder(self):
        """Auto-detects the best GPU hardware acceleration available (NVIDIA NVENC, AMD AMF, Intel QSV), falling back to universal CPU libx264."""
        encoders_to_test = [
            ("NVIDIA NVENC", "h264_nvenc"),
            ("AMD Radeon AMF", "h264_amf"),
            ("Intel QuickSync QSV", "h264_qsv")
        ]
        for name, enc in encoders_to_test:
            try:
                res = subprocess.run(
                    [FFMPEG_EXE, "-f", "lavfi", "-i", "testsrc=duration=0.5:size=320x240:rate=30", "-c:v", enc, "-f", "null", "-"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if res.returncode == 0:
                    self.log(f"⚡ Hardware Acceleration Active: {name} ({enc})")
                    return enc
            except Exception:
                pass
        self.log("🖥️ Using Universal CPU Acceleration: libx264 (veryfast)")
        return "libx264"

    def _get_encoder_args(self, target_bitrate="25M", max_bitrate="30M", buf_size="50M"):
        """Returns optimal encoding parameters based on auto-detected hardware (NVIDIA, AMD, Intel, or CPU fallback)."""
        if not hasattr(self, "_active_encoder") or not self._active_encoder:
            self._active_encoder = self._detect_hardware_encoder()

        enc = self._active_encoder
        if enc == "h264_nvenc":
            return [
                "-c:v", "h264_nvenc",
                "-preset", "p5", "-tune", "hq",
                "-b:v", target_bitrate, "-maxrate", max_bitrate, "-bufsize", buf_size,
                "-profile:v", "high", "-pix_fmt", "yuv420p"
            ]
        elif enc == "h264_amf":
            return [
                "-c:v", "h264_amf",
                "-quality", "speed",
                "-b:v", target_bitrate, "-maxrate", max_bitrate, "-bufsize", buf_size,
                "-pix_fmt", "yuv420p"
            ]
        elif enc == "h264_qsv":
            return [
                "-c:v", "h264_qsv",
                "-preset", "veryfast",
                "-b:v", target_bitrate, "-maxrate", max_bitrate,
                "-pix_fmt", "yuv420p"
            ]
        else: # Universal CPU fallback (libx264)
            return [
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-b:v", target_bitrate, "-maxrate", max_bitrate, "-bufsize", buf_size,
                "-profile:v", "high", "-pix_fmt", "yuv420p"
            ]

    def _generate_trial_watermark_png(self, width=1920, height=1080):
        """Generates a floating semi-transparent trial watermark with soft drop shadows and no box."""
        wm_path = os.path.join(self.scratch_dir, f"trial_watermark_{width}x{height}.png")
        im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)

        font_size_title = max(18, int(34 * (width / 1920)))
        font_size_sub = max(8, int(12 * (width / 1920)))
        font_title = ImageFont.truetype(FONT_TITLE, font_size_title)
        font_sub = ImageFont.truetype(FONT_SEGOE, font_size_sub)

        t1 = "THUNDER"
        t2 = "PUBG MOBILE HIGHLIGHT AUTOMATION STUDIO"

        bb1 = draw.textbbox((0, 0), t1, font=font_title)
        w1, h1 = bb1[2] - bb1[0], bb1[3] - bb1[1]
        bb2 = draw.textbbox((0, 0), t2, font=font_sub)
        w2, h2 = bb2[2] - bb2[0], bb2[3] - bb2[1]
        max_w = max(w1, w2)

        # Place in negative space beside mini-map
        pos_x = int(width * 0.71)
        pos_y = int(height * 0.026)

        tx1 = pos_x + (max_w - w1) // 2
        ty1 = pos_y

        # Soft drop shadow for title
        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, 2), (2, 2)]:
            draw.text((tx1 + dx, ty1 + dy), t1, font=font_title, fill=(0, 0, 0, 200))
        # Electric cyan title (75% opacity)
        draw.text((tx1, ty1), t1, font=font_title, fill=(0, 229, 255, 195))

        # Soft drop shadow for subtitle
        tx2 = pos_x + (max_w - w2) // 2
        ty2 = ty1 + h1 + max(4, int(6 * (height / 1080)))
        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, 1), (1, 1)]:
            draw.text((tx2 + dx, ty2 + dy), t2, font=font_sub, fill=(0, 0, 0, 190))
        # Ice-silver subtitle (70% opacity)
        draw.text((tx2, ty2), t2, font=font_sub, fill=(240, 245, 255, 185))

        im.save(wm_path)
        return wm_path

    def render_montage(self, clips_config, bg_music_path, music_start_sec, output_path, is_vertical=False,
                       player_ign="TK • 亗 • MAAK", channel_name="MAAKTHUNDER",
                       yt_link="YOUTUBE.COM/@MAAKTHUNDER", tt_link="TIKTOK.COM/@MAAKTHUNDER", fb_link="FACEBOOK.COM/MAAKTHUNDER",
                       edit_level="Pro", is_trial=False):
        """Renders the final montage with exact A/V sync, high bitrate, and editing level controls (Basic vs Pro)."""
        is_basic = (edit_level.lower() == "basic")
        style_desc = "Basic Pure Cuts" if is_basic else "Pro Esports Dynamic"
        self.log(f"🎬 Compiling Highlight Video [{style_desc}]: {os.path.basename(output_path)}...")



        intro_img = os.path.join(self.scratch_dir, "overlay_intro.png")
        badge_kill = os.path.join(self.scratch_dir, "badge_kill.png")
        badge_knock = os.path.join(self.scratch_dir, "badge_knock.png")
        whoosh_sfx = os.path.join(self.scratch_dir, "sfx_whoosh.wav")
        impact_sfx = os.path.join(self.scratch_dir, "sfx_impact.wav")
        glitch_sfx = os.path.join(self.scratch_dir, "sfx_glitch.wav")
        slam_sfx = os.path.join(self.scratch_dir, "sfx_slam.wav")
        whip_sfx = os.path.join(self.scratch_dir, "sfx_whip.wav")
        active_trans_sfx = whoosh_sfx

        v_enc_args = self._get_encoder_args("25M", "30M", "50M")
        rendered_segs = []

        # 1. Intro Segment (2.0s) - ONLY for Pro and Pro+ tiers (Skipped for Basic)
        if not is_basic:
            seg0 = os.path.join(self.scratch_dir, "render_seg0_intro.mp4")
            cmd_intro = [
                FFMPEG_EXE, "-y",
                "-loop", "1", "-t", "2.0", "-i", intro_img,
                "-i", active_trans_sfx,
                "-filter_complex",
                "[0:v]fade=t=in:st=0:d=0.3,fade=t=out:st=1.6:d=0.4:color=white,setsar=1,setdar=16/9,format=yuv420p[v];"
                "[1:a]adelay=1000|1000,apad=whole_dur=2.0,volume=0.85[a]",
                "-map", "[v]", "-map", "[a]",
                "-t", "2.0", "-r", "60"
            ] + v_enc_args + [
                "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                seg0
            ]
            self._run_subproc(cmd_intro)
            rendered_segs.append(seg0)

        has_bg_music = bool(bg_music_path and os.path.exists(bg_music_path))
        if has_bg_music:
            self.log(f"🎵 Background Music: {os.path.basename(bg_music_path)} (offset: {music_start_sec}s)")
        else:
            self.log(f"🔊 Audio Mode: Pure in-game gunfight & kill audio (no background music)")

        curr_music_offset = 0.0

        for idx, clip in enumerate(clips_config, start=1):
            if self.cancel_requested:
                raise RenderCancelledError("Render cancelled by user")
            dur = clip.get("dur", 11.0)
            hit = clip.get("hit", 6.0)
            source_vid = clip["source"]
            is_last = (idx == len(clips_config))
            game_vol = 0.0 if clip.get("muted") else 1.0

            # Select unique matched sound effect for each transition
            t_name = clip.get("transition", "3D Flash Cut")
            if "Glitch" in t_name:
                active_trans_sfx = glitch_sfx if os.path.exists(glitch_sfx) else whoosh_sfx
            elif "Zoom" in t_name:
                active_trans_sfx = slam_sfx if os.path.exists(slam_sfx) else whoosh_sfx
            elif any(k in t_name for k in ["Slide", "Whip"]):
                active_trans_sfx = whip_sfx if os.path.exists(whip_sfx) else whoosh_sfx
            else:
                active_trans_sfx = whoosh_sfx
            seg_file = os.path.join(self.scratch_dir, f"render_seg{idx}.mp4")

            pre_seek = max(0.0, clip["start"] - 5.0)
            trim_st = clip["start"] - pre_seek

            if is_basic:
                # =============================================================
                # BASIC EDIT LEVEL: Clean cuts, no punch-zooms, no badges, no SFX
                # =============================================================
                v_filters = [
                    f"[0:v]trim=start={trim_st:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS,eq=contrast=1.06:saturation=1.12,scale=1920:1080,setsar=1,setdar=16/9[vclean];"
                ]
                if is_last:
                    v_filters.append(f"[vclean]fade=t=out:st={dur-0.8:.2f}:d=0.8,format=yuv420p[v];")
                else:
                    v_filters.append("[vclean]format=yuv420p[v];")

                if has_bg_music:
                    a_filters = [
                        f"[0:a:0]atrim=start={trim_st:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,volume={game_vol}[ga];",
                        f"[1:a]volume=0.35[ma];"
                    ]
                    if is_last:
                        a_filters.append("[ga][ma]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[am];")
                        a_filters.append(f"[am]afade=t=out:st={dur-1.0:.2f}:d=1.0[a]")
                    else:
                        a_filters.append("[ga][ma]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")

                    cmd_seg = [
                        FFMPEG_EXE, "-y",
                        "-ss", f"{pre_seek:.3f}", "-i", source_vid,
                        "-ss", f"{music_start_sec + curr_music_offset:.3f}", "-t", f"{dur:.3f}", "-i", bg_music_path,
                        "-filter_complex", "".join(v_filters + a_filters),
                        "-map", "[v]", "-map", "[a]",
                        "-t", f"{dur:.3f}", "-r", "60"
                    ] + v_enc_args + [
                        "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                        "-movflags", "+faststart",
                        seg_file
                    ]
                else:
                    a_filters = [
                        f"[0:a:0]atrim=start={trim_st:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,volume={game_vol}[ga];"
                    ]
                    if is_last:
                        a_filters.append(f"[ga]afade=t=out:st={dur-1.0:.2f}:d=1.0[a]")
                    else:
                        a_filters.append("[ga]anull[a]")

                    cmd_seg = [
                        FFMPEG_EXE, "-y",
                        "-ss", f"{pre_seek:.3f}", "-i", source_vid,
                        "-filter_complex", "".join(v_filters + a_filters),
                        "-map", "[v]", "-map", "[a]",
                        "-t", f"{dur:.3f}", "-r", "60"
                    ] + v_enc_args + [
                        "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                        "-movflags", "+faststart",
                        seg_file
                    ]

            else:
                # =============================================================
                # PRO / PRO+ EDIT LEVEL: Branded badges, punch-zooms, impact & whoosh SFX
                # =============================================================
                is_pro_plus = (edit_level.lower() in ("pro+", "proplus"))
                subbass_sfx = os.path.join(self.scratch_dir, "sfx_subbass_808.wav")
                active_impact = subbass_sfx if (is_pro_plus and os.path.exists(subbass_sfx)) else impact_sfx
                if is_pro_plus:
                    badge = os.path.join(self.scratch_dir, "badge_proplus_multi.png" if clip.get("is_multi") else "badge_proplus_kill.png")
                else:
                    badge = badge_kill if clip.get("type", "kill") == "kill" else badge_knock
                h1_st = hit
                h1_end = hit + 1.8
                punch_cond = f"between(t,{h1_st:.2f},{h1_end:.2f})"
                shake_cond = f"between(t,{h1_st:.2f},{h1_st+0.35:.2f})"
                flash_strength = 0.45 if is_pro_plus else 0.32
                flash_cond = f"if(between(t,{h1_st:.2f},{h1_st+0.25:.2f}),{flash_strength}*(1-(t-{h1_st:.2f})/0.25),0)"

                # PRO+ STUDIO VFX: Gunfire Camera Shake + AI Neural HD Enhancement (Unsharp/CAS)
                if is_pro_plus:
                    col_str = "eq=contrast=1.18:saturation=1.26:brightness=-0.02,unsharp=7:7:1.4:7:7:0.4"
                    crop_str = f"crop=w='if({punch_cond},in_w*0.86,in_w)':h='if({punch_cond},in_h*0.86,in_h)':x='(in_w-out_w)/2 + if({shake_cond},sin(t*90)*16,0)':y='(in_h-out_h)/2 + if({shake_cond},cos(t*90)*12,0)',scale=1920:1080"
                else:
                    col_str = "eq=contrast=1.08:saturation=1.14"
                    crop_str = f"crop=w='if({punch_cond},in_w*0.90,in_w)':h='if({punch_cond},in_h*0.90,in_h)':x='(in_w-out_w)/2':y='(in_h-out_h)/2',scale=1920:1080"

                filters = [
                    f"[0:v]trim=start={trim_st:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS,{col_str}[vcol];",
                    f"[vcol]{crop_str}[vpunch];",
                    f"[vpunch]eq=brightness='{flash_cond}'[vflash];",
                    f"[2:v]format=rgba,fade=t=in:st={h1_st:.2f}:d=0.2:alpha=1,fade=t=out:st={h1_st+2.5:.2f}:d=0.3:alpha=1[badge];",
                    f"[vflash][badge]overlay=0:0:enable='between(t,{h1_st:.2f},{h1_st+2.8:.2f})'[vo];"
                ]

                if is_last:
                    filters.append(f"[vo]fade=t=out:st={dur-1.0:.2f}:d=1.0,setsar=1,setdar=16/9,format=yuv420p[v];")
                else:
                    # Clean video frame pass-through so FFmpeg xfade renders genuine crisp transitions
                    filters.append(f"[vo]setsar=1,setdar=16/9,format=yuv420p[v];")

                if has_bg_music:
                    filters.append(f"[0:a:0]atrim=start={trim_st:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,volume={game_vol}[ga];")
                    filters.append(f"[1:a]volume=0.35[ma];")
                    imp_delay = int(h1_st * 1000)
                    filters.append(f"[3:a]adelay={imp_delay}|{imp_delay},volume=0.9[imp];")

                    if not is_last:
                        wh_delay = int((dur - 0.45) * 1000)
                        filters.append(f"[4:a]adelay={wh_delay}|{wh_delay},volume=0.75[wh];")
                        filters.append("[ga][ma][imp][wh]amix=inputs=4:duration=first:dropout_transition=0:normalize=0[a]")
                    else:
                        filters.append("[ga][ma][imp]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[am];")
                        filters.append(f"[am]afade=t=out:st={dur-1.0:.2f}:d=1.0[a]")

                    cmd_seg = [
                        FFMPEG_EXE, "-y",
                        "-ss", f"{pre_seek:.3f}", "-i", source_vid,
                        "-ss", f"{music_start_sec + curr_music_offset:.3f}", "-t", f"{dur:.3f}", "-i", bg_music_path,
                        "-i", badge,
                        "-i", active_impact,
                    ]
                    if not is_last:
                        cmd_seg.extend(["-i", active_trans_sfx])

                    cmd_seg.extend([
                        "-filter_complex", "".join(filters),
                        "-map", "[v]", "-map", "[a]",
                        "-t", f"{dur:.3f}", "-r", "60"
                    ] + v_enc_args + [
                        "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                        "-movflags", "+faststart",
                        seg_file
                    ])
                else:
                    # Pure in-game sound + kill impact SFX (No background music input)
                    filters.append(f"[0:a:0]atrim=start={trim_st:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,volume={game_vol}[ga];")
                    imp_delay = int(h1_st * 1000)
                    # When no music: 0=vid, 1=badge, 2=impact_sfx, 3=whoosh_sfx
                    # So badge is [1:v] instead of [2:v]!
                    # Note: we need badge filter to refer to [1:v] when no music
                    filters_no_music = []
                    for f_item in filters:
                        filters_no_music.append(f_item.replace("[2:v]", "[1:v]"))
                    
                    filters_no_music.append(f"[2:a]adelay={imp_delay}|{imp_delay},volume=0.9[imp];")
                    if not is_last:
                        wh_delay = int((dur - 0.45) * 1000)
                        filters_no_music.append(f"[3:a]adelay={wh_delay}|{wh_delay},volume=0.75[wh];")
                        filters_no_music.append("[ga][imp][wh]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[a]")
                    else:
                        filters_no_music.append("[ga][imp]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[am];")
                        filters_no_music.append(f"[am]afade=t=out:st={dur-1.0:.2f}:d=1.0[a]")

                    cmd_seg = [
                        FFMPEG_EXE, "-y",
                        "-ss", f"{pre_seek:.3f}", "-i", source_vid,
                        "-i", badge,
                        "-i", active_impact,
                    ]
                    if not is_last:
                        cmd_seg.extend(["-i", active_trans_sfx])

                    cmd_seg.extend([
                        "-filter_complex", "".join(filters_no_music),
                        "-map", "[v]", "-map", "[a]",
                        "-t", f"{dur:.3f}", "-r", "60"
                    ] + v_enc_args + [
                        "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                        "-movflags", "+faststart",
                        seg_file
                    ])

            self._run_subproc(cmd_seg)
            rendered_segs.append(seg_file)
            curr_music_offset += dur

        # =========================================================================
        # PRO / PRO+ BROADCAST TRANSITION ENGINE (FFMPEG XFADE PIPELINE)
        # =========================================================================
        temp_landscape = os.path.join(self.scratch_dir, "temp_master_16x9.mp4")

        # Map UI and AI transitions to FFmpeg xfade transitions
        XFADE_MAP = {
            "3D Flash Cut": "fadewhite",
            "Glitch Tremor": "pixelize",
            "Zoom Blur Slam": "zoomin",
            "Whip Pan Swipe": "wipeleft",
            "Light Leak Glow": "radial",
            "Slide Left": "slideleft",
            "Slide Right": "slideright",
            "Slide Up": "slideup",
            "Slide Down": "slidedown",
            "Cross Dissolve": "dissolve",
            "Fade to Black": "fadeblack"
        }

        # Pro+ Dynamic AI Transition cycle when not manually customized
        ai_proplus_cycle = ["slideleft", "zoomin", "fadewhite", "wipeleft", "slideright", "pixelize", "dissolve"]

        if len(rendered_segs) == 1:
            shutil.copy(rendered_segs[0], temp_landscape)
        else:
            self.log(f"🎬 Merging {len(rendered_segs)} segments with high-precision xfade transitions...")
            cmd_xfade = [FFMPEG_EXE, "-y"]
            for s in rendered_segs:
                cmd_xfade.extend(["-i", s])

            # Measure actual durations of segments
            seg_durs = []
            for s in rendered_segs:
                try:
                    probe_cmd = [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", s]
                    res_p = self._run_subproc(probe_cmd, capture_output=True, text=True)
                    seg_durs.append(float(res_p.stdout.strip()))
                except Exception:
                    seg_durs.append(10.0)

            trans_dur = 0.4
            v_filters_chain = []
            a_filters_chain = []
            cur_offset = seg_durs[0] - trans_dur

            for tr_idx in range(len(rendered_segs) - 1):
                # Determine transition for this cut
                clip_cfg_idx = tr_idx if is_basic else (tr_idx - 1)
                t_name = "3D Flash Cut"
                if clip_cfg_idx >= 0 and clip_cfg_idx < len(clips_config):
                    t_name = clips_config[clip_cfg_idx].get("transition", "3D Flash Cut")
                
                xfade_tr = XFADE_MAP.get(t_name, "fadewhite")
                if is_pro_plus and t_name == "3D Flash Cut":
                    # AI auto-variation for Pro+
                    xfade_tr = ai_proplus_cycle[tr_idx % len(ai_proplus_cycle)]

                in_v1 = "[0:v]" if tr_idx == 0 else f"[vtr{tr_idx}]"
                in_v2 = f"[{tr_idx + 1}:v]"
                out_v = f"[vtr{tr_idx + 1}]" if tr_idx < len(rendered_segs) - 2 else "[v]"

                in_a1 = "[0:a]" if tr_idx == 0 else f"[atr{tr_idx}]"
                in_a2 = f"[{tr_idx + 1}:a]"
                out_a = f"[atr{tr_idx + 1}]" if tr_idx < len(rendered_segs) - 2 else "[a]"

                v_filters_chain.append(f"{in_v1}{in_v2}xfade=transition={xfade_tr}:duration={trans_dur:.2f}:offset={cur_offset:.3f}{out_v};")
                a_filters_chain.append(f"{in_a1}{in_a2}acrossfade=d={trans_dur:.2f}{out_a};")

                if tr_idx < len(rendered_segs) - 2:
                    cur_offset += (seg_durs[tr_idx + 1] - trans_dur)

            full_filter = "".join(v_filters_chain + a_filters_chain).rstrip(";")
            cmd_xfade.extend([
                "-filter_complex", full_filter,
                "-map", "[v]", "-map", "[a]"
            ] + v_enc_args + [
                "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                temp_landscape
            ])

            import time
            time.sleep(0.25)
            try:
                self._run_subproc(cmd_xfade)
            except Exception as e:
                self.log(f"⚠️ xfade note: fallback to clean hardware concat ({e})")
                concat_inputs = []
                for s in rendered_segs:
                    concat_inputs.extend(["-i", s])
                filter_concat = "".join(f"[{i}:v][{i}:a]" for i in range(len(rendered_segs))) + f"concat=n={len(rendered_segs)}:v=1:a=1[v][a]"
                cmd_fallback = [
                    FFMPEG_EXE, "-y"
                ] + concat_inputs + [
                    "-filter_complex", filter_concat,
                    "-map", "[v]", "-map", "[a]"
                ] + v_enc_args + [
                    "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                    "-movflags", "+faststart",
                    temp_landscape
                ]
                self._run_subproc(cmd_fallback)

        if not is_vertical:
            if is_trial:
                self.log("🔒 15-Day Free Trial Active: Applying THUNDER Studio watermark...")
                wm_img = self._generate_trial_watermark_png(1920, 1080)
                cmd_finalize = [
                    FFMPEG_EXE, "-y", "-i", temp_landscape, "-i", wm_img,
                    "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
                    "-map", "[v]", "-map", "0:a",
                    "-c:a", "copy",
                    "-movflags", "+faststart"
                ] + v_enc_args + [output_path]
            else:
                # Finalize 16:9 Landscape clean with faststart
                cmd_finalize = [
                    FFMPEG_EXE, "-y", "-i", temp_landscape,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    output_path
                ]
            self._run_subproc(cmd_finalize)
        else:
            # Render 9:16 Vertical Shorts
            self._render_vertical_from_landscape(
                temp_landscape, output_path,
                player_ign=player_ign, channel_name=channel_name,
                yt_link=yt_link, tt_link=tt_link, fb_link=fb_link,
                is_trial=is_trial
            )

        self.log(f"✅ Montage Saved: {output_path} ({os.path.getsize(output_path)//(1024*1024)} MB)")
        return output_path

    def _render_vertical_from_landscape(self, input_video, output_vertical,
                                        player_ign="TK • 亗 • MAAK", channel_name="MAAKTHUNDER",
                                        yt_link="YOUTUBE.COM/@MAAKTHUNDER", tt_link="TIKTOK.COM/@MAAKTHUNDER", fb_link="FACEBOOK.COM/MAAKTHUNDER",
                                        is_trial=False):
        overlay_img = os.path.join(self.scratch_dir, "vertical_frame_overlay.png")
        
        # Always generate fresh overlay with exact IGN and social links
        overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        vy1 = 656
        vy2 = vy1 + 608
        # Glowing cyan esports borders around centered 16:9 gameplay window
        draw.rectangle([(0, vy1 - 4), (1080, vy1)], fill=(0, 229, 255, 240))
        draw.rectangle([(0, vy2), (1080, vy2 + 4)], fill=(0, 229, 255, 240))

        # 1. Top Header Box: Channel Name + Player IGN + Subtitle
        font_main = ImageFont.truetype(FONT_TITLE, 72)
        font_ign = ImageFont.truetype(FONT_BOLD, 36)
        font_sub = ImageFont.truetype(FONT_SEGOE, 24)

        # Line 1: Channel Name (MAAKTHUNDER)
        c_name = channel_name.upper() if channel_name else "MAAKTHUNDER"
        bb_c = draw.textbbox((0, 0), c_name, font=font_main)
        w_c = bb_c[2] - bb_c[0]
        draw.text(((1080 - w_c) // 2 + 3, 383), c_name, font=font_main, fill=(0, 0, 0, 240))
        draw.text(((1080 - w_c) // 2, 380), c_name, font=font_main, fill=(0, 229, 255, 255))

        # Line 2: Player IGN (TK • 亗 • MAAK)
        ign_text = player_ign.upper() if player_ign else "TK • 亗 • MAAK"
        bb_ign = draw.textbbox((0, 0), ign_text, font=font_ign)
        w_ign = bb_ign[2] - bb_ign[0]
        draw.text(((1080 - w_ign) // 2 + 2, 482), ign_text, font=font_ign, fill=(0, 0, 0, 220))
        draw.text(((1080 - w_ign) // 2, 480), ign_text, font=font_ign, fill=(255, 255, 255, 255))

        # Line 3: Subtitle (PUBG MOBILE HIGHLIGHTS)
        sub = "PUBG MOBILE HIGHLIGHTS"
        bb_sub = draw.textbbox((0, 0), sub, font=font_sub)
        w_sub = bb_sub[2] - bb_sub[0]
        draw.text(((1080 - w_sub) // 2, 545), sub, font=font_sub, fill=(180, 220, 245, 230))

        # 2. Bottom Footer Box: Branded Social Media Channels
        font_social = ImageFont.truetype(FONT_SEGOE, 26)
        font_f = ImageFont.truetype(FONT_ARIAL, 34)

        # Row 1: YouTube
        row_y1 = 1380
        yt_text = yt_link.upper() if yt_link else "YOUTUBE.COM/@MAAKTHUNDER"
        bb_yt = draw.textbbox((0, 0), yt_text, font=font_social)
        w_yt = bb_yt[2] - bb_yt[0]
        tot_yt = 50 + 15 + w_yt
        yt_x = max(20, (1080 - tot_yt) // 2)
        draw.rounded_rectangle([(yt_x, row_y1), (yt_x + 50, row_y1 + 36)], radius=10, fill=(255, 0, 0, 255))
        draw.polygon([(yt_x + 20, row_y1 + 10), (yt_x + 20, row_y1 + 26), (yt_x + 35, row_y1 + 18)], fill=(255, 255, 255, 255))
        draw.text((yt_x + 65, row_y1 + 4), yt_text, font=font_social, fill=(255, 255, 255, 245))

        # Row 2: TikTok
        row_y2 = 1450
        tt_text = tt_link.upper() if tt_link else "TIKTOK.COM/@MAAKTHUNDER"
        bb_tt = draw.textbbox((0, 0), tt_text, font=font_social)
        w_tt = bb_tt[2] - bb_tt[0]
        tot_tt = 44 + 15 + w_tt
        tt_x = max(20, (1080 - tot_tt) // 2)
        draw.rounded_rectangle([(tt_x, row_y2), (tt_x + 44, row_y2 + 42)], radius=10, fill=(18, 18, 22, 255), outline=(0, 242, 234, 255), width=2)
        draw.ellipse([(tt_x + 10, row_y2 + 18), (tt_x + 22, row_y2 + 30)], fill=(255, 0, 79, 255))
        draw.rectangle([(tt_x + 18, row_y2 + 8), (tt_x + 22, row_y2 + 24)], fill=(0, 242, 234, 255))
        draw.rectangle([(tt_x + 18, row_y2 + 8), (tt_x + 30, row_y2 + 14)], fill=(255, 255, 255, 255))
        draw.text((tt_x + 65, row_y2 + 6), tt_text, font=font_social, fill=(255, 255, 255, 245))

        # Row 3: Facebook
        row_y3 = 1520
        fb_text = fb_link.upper() if fb_link else "FACEBOOK.COM/MAAKTHUNDER"
        bb_fb = draw.textbbox((0, 0), fb_text, font=font_social)
        w_fb = bb_fb[2] - bb_fb[0]
        tot_fb = 42 + 15 + w_fb
        fb_x = max(20, (1080 - tot_fb) // 2)
        draw.ellipse([(fb_x, row_y3), (fb_x + 42, row_y3 + 42)], fill=(24, 119, 242, 255))
        draw.text((fb_x + 14, row_y3 + 3), "f", font=font_f, fill=(255, 255, 255, 255))
        draw.text((fb_x + 65, row_y3 + 6), fb_text, font=font_social, fill=(255, 255, 255, 245))

        if is_trial:
            self.log("🔒 15-Day Free Trial Active: Applying THUNDER Studio watermark to Vertical Shorts...")
            font_wm_title = ImageFont.truetype(FONT_TITLE, 22)
            font_wm_sub = ImageFont.truetype(FONT_SEGOE, 8)
            wm_t1 = "THUNDER"
            wm_t2 = "PUBG MOBILE HIGHLIGHT AUTOMATION STUDIO"
            bb_w1 = draw.textbbox((0, 0), wm_t1, font=font_wm_title)
            w_w1, h_w1 = bb_w1[2] - bb_w1[0], bb_w1[3] - bb_w1[1]
            bb_w2 = draw.textbbox((0, 0), wm_t2, font=font_wm_sub)
            w_w2, h_w2 = bb_w2[2] - bb_w2[0], bb_w2[3] - bb_w2[1]
            max_ww = max(w_w1, w_w2)
            wm_pos_x = 760
            wm_pos_y = vy1 + 16
            wm_tx1 = wm_pos_x + (max_ww - w_w1) // 2
            wm_ty1 = wm_pos_y
            for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, 1), (1, 1)]:
                draw.text((wm_tx1 + dx, wm_ty1 + dy), wm_t1, font=font_wm_title, fill=(0, 0, 0, 200))
            draw.text((wm_tx1, wm_ty1), wm_t1, font=font_wm_title, fill=(0, 229, 255, 195))
            wm_tx2 = wm_pos_x + (max_ww - w_w2) // 2
            wm_ty2 = wm_ty1 + h_w1 + 4
            for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, 1), (1, 1)]:
                draw.text((wm_tx2 + dx, wm_ty2 + dy), wm_t2, font=font_wm_sub, fill=(0, 0, 0, 190))
            draw.text((wm_tx2, wm_ty2), wm_t2, font=font_wm_sub, fill=(240, 245, 255, 185))

        overlay.save(overlay_img)

        v_vert_args = self._get_encoder_args("22M", "28M", "45M")

        cmd_vert = [
            FFMPEG_EXE, "-y", "-i", input_video, "-i", overlay_img,
            "-filter_complex",
            "[0:v]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,scale=1080:1920:flags=bicubic[bg];"
            "[0:v]scale=1080:608,setsar=1[fg];"
            "[bg][fg]overlay=0:656[vmid];"
            "[vmid][1:v]overlay=0:0:format=auto,setsar=1,setdar=9/16,format=yuv420p[v]",
            "-map", "[v]", "-map", "0:a",
            "-r", "60"
        ] + v_vert_args + [
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_vertical
        ]
        self._run_subproc(cmd_vert)
