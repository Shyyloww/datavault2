import threading
from gui import App
import server

if __name__ == "__main__":
    # Start the C2 server in a separate thread
    print("[*] Starting C2 server in the background...")
    server_thread = threading.Thread(target=server.run_server, daemon=True)
    server_thread.start()
    
    # Launch the main GUI application
    print("[*] Launching C2 Control Panel GUI...")
    app = App()
    app.mainloop()
    
    print("[*] Application has been closed.")