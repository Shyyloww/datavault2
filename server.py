from flask import Flask, request, jsonify
import time
import json
import os
import threading

app = Flask(__name__)

# --- PERSISTENCE SETUP ---
# Render's persistent disk is mounted at this path automatically.
# We do not need to create it ourselves.
DATA_DIR = '/var/data' 
SESSIONS_FILE = os.path.join(DATA_DIR, 'sessions.json')

SESSIONS = {}
sessions_lock = threading.Lock()

def load_sessions():
    """Loads sessions from the JSON file into the in-memory dictionary."""
    global SESSIONS
    with sessions_lock:
        if os.path.exists(SESSIONS_FILE):
            try:
                # Check if file is not empty before trying to load
                if os.path.getsize(SESSIONS_FILE) > 0:
                    with open(SESSIONS_FILE, 'r') as f:
                        SESSIONS = json.load(f)
                    print(f"[*] Loaded {len(SESSIONS)} sessions from {SESSIONS_FILE}")
                else:
                    print(f"[*] Sessions file is empty. Starting fresh.")
                    SESSIONS = {}
            except (json.JSONDecodeError, IOError) as e:
                print(f"[!] Error loading sessions file: {e}. Starting fresh.")
                SESSIONS = {}
        else:
            print(f"[*] No sessions file found at {SESSIONS_FILE}. Starting fresh.")
            SESSIONS = {}

def save_sessions():
    """Saves the current in-memory session dictionary to the JSON file."""
    with sessions_lock:
        try:
            with open(SESSIONS_FILE, 'w') as f:
                json.dump(SESSIONS, f, indent=4)
        except IOError as e:
            print(f"[!] Critical error: Could not save sessions to file: {e}")

# --- API ENDPOINTS ---

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    session_id = data.get("session_id")
    if session_id:
        print(f"[*] [{time.strftime('%Y-%m-%d %H:%M:%S')}] New session registered: {data.get('hostname')}")
        with sessions_lock:
            SESSIONS[session_id] = {
                "session_id": session_id, "hostname": data.get("hostname"),
                "data": data.get("data"), "last_seen": time.time()
            }
        save_sessions()
    return jsonify({"status": "ok"}), 200

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    session_id = data.get("session_id")
    if session_id in SESSIONS:
        with sessions_lock:
            SESSIONS[session_id]["last_seen"] = time.time()
        save_sessions() 
    return jsonify({"status": "ok"}), 200

@app.route('/api/get_sessions', methods=['GET'])
def get_sessions():
    with sessions_lock:
        return jsonify(list(SESSIONS.values()))

@app.route('/api/delete_session', methods=['POST'])
def delete_session():
    data = request.json
    session_id = data.get("session_id")
    if session_id and session_id in SESSIONS:
        with sessions_lock:
            del SESSIONS[session_id]
        save_sessions()
        print(f"[*] [{time.strftime('%Y-%m-%d %H:%M:%S')}] Deleted session: {session_id}")
        return jsonify({"status": "deleted"}), 200
    return jsonify({"status": "not_found"}), 404

def run_server():
    load_sessions()
    app.run(host='0.0.0.0', port=5002)

if __name__ == '__main__':
    run_server()