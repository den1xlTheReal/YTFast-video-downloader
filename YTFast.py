import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import yt_dlp
import threading
import queue
import time
import uuid
import sys
import os
import subprocess
import platform

# -----------------------------------------------------------------------------
# HELPER: RESOURCE PATH (Fixes Font in .EXE)
# -----------------------------------------------------------------------------
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# -----------------------------------------------------------------------------
# CONFIGURATION & THEME
# -----------------------------------------------------------------------------
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

# LOAD FONT WITH RESOURCE PATH FIX
font_file = "CherryBombOne-Regular.ttf"
font_path = resource_path(font_file)

try:
    if os.path.exists(font_path):
        ctk.FontManager.load_font(font_path)
        # Assuming family name is "Cherry Bomb One"
        APP_FONT = ("Cherry Bomb One", 14)
        APP_FONT_BOLD = ("Cherry Bomb One", 16)
        APP_FONT_LARGE = ("Cherry Bomb One", 22)
        APP_FONT_SMALL = ("Cherry Bomb One", 12)
    else:
        # If file not found, fallback immediately
        print(f"Font file not found at: {font_path}")
        raise Exception("Font Missing")
except Exception as e:
    # Fallback if font fails to load
    print(f"Using fallback font. Error: {e}")
    APP_FONT = ("Arial", 14)
    APP_FONT_BOLD = ("Arial", 16, "bold")
    APP_FONT_LARGE = ("Arial", 22, "bold")
    APP_FONT_SMALL = ("Arial", 12)

APP_WIDTH = 900
APP_HEIGHT = 750
COLOR_BG = "#12121f"
COLOR_CARD = "#151526"
COLOR_ACCENT = "#f97316"  # Bright Orange
COLOR_ACCENT_HOVER = "#d96414"
COLOR_TEXT = "#FFFFFF"
COLOR_TEXT_GRAY = "#AAAAAA"
COLOR_ERROR = "#CF6679"
COLOR_INPUT_BG = "#12121f"

# -----------------------------------------------------------------------------
# LOGIC & WORKER
# -----------------------------------------------------------------------------

class DownloadManager:
    def __init__(self, update_callback):
        self.queue = queue.Queue()
        self.current_task = None
        self.cancelled_ids = set() 
        self.cancel_flag = threading.Event()
        self.update_callback = update_callback
        self.is_running = True
        
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def add_task(self, url, settings, task_id):
        self.queue.put({
            'url': url,
            'settings': settings,
            'id': task_id
        })

    def cancel_task(self, task_id):
        self.cancelled_ids.add(task_id)
        if self.current_task and self.current_task['id'] == task_id:
            self.cancel_flag.set()

    def _worker_loop(self):
        while self.is_running:
            try:
                task = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            if task['id'] in self.cancelled_ids:
                self.update_callback(task['id'], "status", "Cancelled")
                self.queue.task_done()
                continue

            self.current_task = task
            self.cancel_flag.clear()
            
            self.update_callback(task['id'], "status", "Initializing...")
            self.update_callback(task['id'], "progress", 0.0)

            try:
                self._process_download(task)
                if not self.cancel_flag.is_set():
                    self.update_callback(task['id'], "status", "Completed")
                    self.update_callback(task['id'], "progress", 1.0)
                else:
                    self.update_callback(task['id'], "status", "Cancelled")
            except Exception as e:
                err_msg = str(e)
                if "Cancelled" in err_msg:
                    self.update_callback(task['id'], "status", "Cancelled")
                else:
                    print(f"Error: {e}")
                    self.update_callback(task['id'], "status", "Error")
            finally:
                self.queue.task_done()
                self.current_task = None
                if task['id'] in self.cancelled_ids:
                    self.cancelled_ids.remove(task['id'])

    def _progress_hook(self, d, task_id):
        if self.cancel_flag.is_set():
            raise Exception("Cancelled by user")

        if d['status'] == 'downloading':
            try:
                p = d.get('_percent_str', '0%').replace('%','')
                progress = float(p) / 100
                self.update_callback(task_id, "progress", progress)
                self.update_callback(task_id, "status", f"Downloading... {d.get('_percent_str')}")
            except:
                pass
        elif d['status'] == 'finished':
            self.update_callback(task_id, "status", "Processing...")

    def _process_download(self, task):
        url = task['url']
        mode = task['settings']['mode'] 
        quality = task['settings'].get('quality', 'best')
        path = task['settings'].get('path', os.getcwd())

        ydl_opts = {
            'progress_hooks': [lambda d: self._progress_hook(d, task['id'])],
            'outtmpl': '%(title)s.%(ext)s',
            'paths': {'home': path}, 
            'quiet': True,
            'no_warnings': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            'concurrent_fragment_downloads': 4,
        }

        if mode == 'audio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '192',
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': False,
                }],
                'writethumbnail': False,
            })
        else:
            if quality != 'best':
                fmt = f"bestvideo[height<={quality}][vcodec^=avc]+bestaudio[acodec^=mp4a]/bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
            else:
                fmt = "bestvideo[vcodec^=avc]+bestaudio[acodec^=mp4a]/bestvideo+bestaudio/best"
            
            ydl_opts.update({
                'format': fmt,
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if self.cancel_flag.is_set(): raise Exception("Cancelled")
            
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown Title')
            self.update_callback(task['id'], "title", title)
            
            if self.cancel_flag.is_set(): raise Exception("Cancelled")
            
            ydl.download([url])

# -----------------------------------------------------------------------------
# GUI COMPONENTS
# -----------------------------------------------------------------------------

class DownloadItemFrame(ctk.CTkFrame):
    def __init__(self, master, task_id, url, cancel_command, open_command, **kwargs):
        super().__init__(master, fg_color="#12121f", corner_radius=25, **kwargs)
        self.task_id = task_id
        self.cancel_command = cancel_command
        self.open_command = open_command
        self.download_path = ""
        
        self.grid_columnconfigure(1, weight=1)

        # Icon
        self.icon_lbl = ctk.CTkLabel(self, text="▶", font=APP_FONT_LARGE, text_color=COLOR_ACCENT, width=40)
        self.icon_lbl.grid(row=0, column=0, rowspan=2, padx=15, pady=15)

        # Title / URL
        self.title_lbl = ctk.CTkLabel(self, text=url, font=APP_FONT, text_color=COLOR_TEXT, anchor="w")
        self.title_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(12, 0))

        # Status
        self.status_lbl = ctk.CTkLabel(self, text="Queued", font=APP_FONT_SMALL, text_color=COLOR_TEXT_GRAY, anchor="w")
        self.status_lbl.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 10))

        # Action Button (X or Folder)
        self.action_btn = ctk.CTkButton(self, text="✕", width=30, height=30, corner_radius=15,
                                        font=APP_FONT_BOLD, fg_color=COLOR_ERROR, hover_color="#A04040",
                                        command=self._on_cancel_click)
        self.action_btn.grid(row=0, column=2, rowspan=2, padx=15)

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self, height=8, corner_radius=4, progress_color=COLOR_ACCENT)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=15, pady=(0, 15))

    def _on_cancel_click(self):
        if self.cancel_command:
            self.cancel_command(self.task_id)

    def _on_open_click(self):
        if self.open_command:
            self.open_command(self.download_path)

    def update_progress(self, val):
        self.progress_bar.set(val)

    def update_status(self, text):
        self.status_lbl.configure(text=text)
        if text == "Completed":
            self.progress_bar.configure(progress_color=COLOR_ACCENT)
            # Switch to Folder Icon
            self.action_btn.configure(text="📂", fg_color="#12121f", hover_color="#0b0b14", 
                                      command=self._on_open_click)
        elif text == "Cancelled":
            self.progress_bar.configure(progress_color=COLOR_ERROR)
            self.action_btn.configure(state="disabled", fg_color="#12121f")
        elif text == "Error":
            self.progress_bar.configure(progress_color=COLOR_ERROR)

    def update_title(self, text):
        if len(text) > 55: text = text[:52] + "..."
        self.title_lbl.configure(text=text)
    
    def set_path(self, path):
        self.download_path = path

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Fast YT Downloader")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.configure(fg_color=COLOR_BG)
        
        # State
        self.items = {}
        self.manager = DownloadManager(self.update_item_callback)
        self.current_mode = "Simple"
        
        # Path Init
        desired_path = "w:/Windows Components/Desktop"
        if os.path.exists(desired_path):
            self.download_path = desired_path
        else:
            self.download_path = os.path.join(os.path.expanduser("~"), "Desktop")

        # UI Setup
        self._build_top_bar()
        self._build_input_area()
        self._build_list_area()

        # Keyboard Bindings
        self.bind("<Control-v>", self.on_paste)
        
        # Initial State
        self.toggle_mode("Simple")

    def _build_top_bar(self):
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=30, pady=(25, 10))

        logo = ctk.CTkLabel(top_frame, text="⚡ Fast YT", font=APP_FONT_LARGE, text_color=COLOR_ACCENT)
        logo.pack(side="left")

        # Mode Switch: Simple / Advanced
        self.mode_switch = ctk.CTkSegmentedButton(
            top_frame, 
            values=["Simple", "Advanced"],
            command=self.toggle_mode,
            width=220,
            height=32,
            corner_radius=16, 
            font=APP_FONT,
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            unselected_color=COLOR_BG, 
            unselected_hover_color="#1a1a1a",
            fg_color=COLOR_BG,
            text_color=COLOR_TEXT
        )
        self.mode_switch.set("Simple")
        self.mode_switch.pack(side="right")

    def _build_input_area(self):
        # Container Box
        self.input_container = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=20)
        self.input_container.pack(fill="x", padx=30, pady=10)

        # --- Row 1: URL & Actions ---
        row1 = ctk.CTkFrame(self.input_container, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=(25, 15))

        # URL Entry Pill
        self.url_entry = ctk.CTkEntry(row1, placeholder_text="Paste URL here...", 
                                      height=44, corner_radius=22, # Pill
                                      font=APP_FONT, border_width=0, fg_color=COLOR_INPUT_BG)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Paste Button Pill (Fixed Colors)
        self.paste_btn = ctk.CTkButton(row1, text="Paste", width=90, height=44, corner_radius=22,
                                       fg_color="#12121f", hover_color="#0b0b14", 
                                       font=APP_FONT, command=self.manual_paste)
        self.paste_btn.pack(side="left", padx=(0, 10))

        # Download Button Pill
        self.action_btn = ctk.CTkButton(row1, text="Download", width=130, height=44, corner_radius=22,
                                        font=APP_FONT_BOLD, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                                        command=self.manual_add_from_entry)
        self.action_btn.pack(side="left")

        # --- Row 2: Path & Options ---
        row2 = ctk.CTkFrame(self.input_container, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=(0, 25))

        # Path Pill (Left) (Fixed Colors)
        path_name = self._get_path_display_name(self.download_path)
        self.path_btn = ctk.CTkButton(row2, text=path_name, width=120, height=36, corner_radius=18,
                                      fg_color="#12121f", hover_color="#0b0b14", text_color=COLOR_TEXT_GRAY,
                                      font=APP_FONT_SMALL, command=self.change_path)
        self.path_btn.pack(side="left")

        # Options (Right)
        self.options_frame = ctk.CTkFrame(row2, fg_color="transparent")
        self.options_frame.pack(side="right")

        # SIMPLE MODE
        self.simple_frame = ctk.CTkFrame(self.options_frame, fg_color="transparent")
        
        # Option Switch: Quick Video / Audio Only
        self.option_switch = ctk.CTkSegmentedButton(
            self.simple_frame,
            values=["Quick Video", "Audio Only"],
            width=250,
            height=32,
            corner_radius=16,
            font=APP_FONT,
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            unselected_color=COLOR_CARD,
            unselected_hover_color="#0b0b14",
            fg_color=COLOR_CARD, 
            text_color=COLOR_TEXT
        )
        self.option_switch.set("Quick Video")
        self.option_switch.pack(side="left")
        
        # ADVANCED MODE
        self.adv_frame = ctk.CTkFrame(self.options_frame, fg_color="transparent")
        ctk.CTkLabel(self.adv_frame, text="Max Quality:", font=APP_FONT).pack(side="left", padx=(0,10))
        self.quality_combo = ctk.CTkComboBox(self.adv_frame, values=["Best Available", "2160", "1440", "1080", "720"], 
                                             width=150, height=32, corner_radius=16, font=APP_FONT,
                                             fg_color=COLOR_INPUT_BG, border_width=0, button_color="#12121f")
        self.quality_combo.set("Best Available")
        self.quality_combo.pack(side="left")

    def _build_list_area(self):
        # Queue Container Box
        self.queue_container = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=20)
        self.queue_container.pack(fill="both", expand=True, padx=30, pady=(10, 30))
        
        # Scrollable Area inside Container
        self.scroll_frame = ctk.CTkScrollableFrame(self.queue_container, fg_color="transparent", label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=15)

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _get_path_display_name(self, path):
        if not path: return "Select Folder"
        base = os.path.basename(os.path.normpath(path))
        return base if base else path

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def change_path(self):
        path = filedialog.askdirectory(initialdir=self.download_path)
        if path:
            self.download_path = path
            self.path_btn.configure(text=self._get_path_display_name(path))

    def open_download_folder(self, path):
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            print(f"Could not open folder: {e}")

    def toggle_mode(self, mode):
        self.current_mode = mode
        if mode == "Simple":
            self.adv_frame.pack_forget()
            self.simple_frame.pack(fill="x")
            self.action_btn.configure(text="Download")
            self.url_entry.configure(placeholder_text="Ctrl+V anywhere to auto-start...")
        else:
            self.simple_frame.pack_forget()
            self.adv_frame.pack(fill="x")
            self.action_btn.configure(text="Add to Queue")
            self.url_entry.configure(placeholder_text="Paste URL here...")

    def manual_paste(self):
        try:
            content = self.clipboard_get()
            self.url_entry.delete(0, 'end')
            self.url_entry.insert(0, content)
            if self.current_mode == "Simple":
                self.manual_add_from_entry()
        except:
            pass

    def on_paste(self, event):
        try:
            content = self.clipboard_get()
        except:
            return

        if self.current_mode == "Simple":
            if self.validate_url(content):
                self.start_download_task(content)
                self.url_entry.delete(0, 'end')
                self.url_entry.insert(0, content) 
        else:
            if self.focus_get() != self.url_entry:
                self.url_entry.delete(0, 'end')
                self.url_entry.insert(0, content)

    def manual_add_from_entry(self):
        url = self.url_entry.get().strip()
        if self.validate_url(url):
            self.start_download_task(url)
            self.url_entry.delete(0, 'end')

    def validate_url(self, url):
        return url and ("http" in url)

    def start_download_task(self, url):
        task_id = str(uuid.uuid4())
        
        settings = {}
        settings['path'] = self.download_path
        
        if self.current_mode == "Simple":
            # Map segmented button text to logic
            opt = self.option_switch.get()
            settings['mode'] = 'video' if opt == "Quick Video" else 'audio'
            settings['quality'] = 'best'
        else:
            settings['mode'] = 'video'
            q = self.quality_combo.get()
            settings['quality'] = q if q != "Best Available" else 'best'

        # Create UI Item
        item = DownloadItemFrame(
            self.scroll_frame, 
            task_id, 
            url,
            cancel_command=self.manager.cancel_task,
            open_command=self.open_download_folder
        )
        item.set_path(self.download_path)
        item.pack(fill="x", padx=0, pady=5)
        self.items[task_id] = item

        self.manager.add_task(url, settings, task_id)

    # -------------------------------------------------------------------------
    # CALLBACKS
    # -------------------------------------------------------------------------
    
    def update_item_callback(self, task_id, update_type, value):
        self.after(0, lambda: self._apply_update(task_id, update_type, value))

    def _apply_update(self, task_id, update_type, value):
        if task_id not in self.items: return
        item = self.items[task_id]
        if update_type == "progress":
            item.update_progress(value)
        elif update_type == "status":
            item.update_status(value)
        elif update_type == "title":
            item.update_title(value)

if __name__ == "__main__":
    app = App()
    app.mainloop()