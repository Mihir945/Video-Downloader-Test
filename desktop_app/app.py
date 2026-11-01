"""
Video Downloader - Native Windows Desktop Application
Built with Tkinter, ttk, Pillow, yt-dlp, and FFmpeg.

Features:
- Native GUI for Windows with crisp High-DPI support (Segoe UI).
- Real-time video metadata extraction (Title, Channel, Duration, Thumbnail).
- Genuine quality selector (Full HD/4K, 1080p, 720p, 480p, etc.).
- Multi-client fallback (visionos, android, web) preventing bot challenges.
- Save directory selector with Browse... and instant "Open Folder" button.
- Real-time downloading and FFmpeg merging progress bar.
- Fully multithreaded (UI never hangs or freezes).
"""

import os
import sys
import re
import io
import time
import shutil
import urllib.request
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

# Enable High-DPI awareness on Windows for crisp fonts and graphics
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import yt_dlp
import yt_dlp

# Optional Pillow for thumbnail rendering
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Import shared backend helpers
try:
    from backend.main import (
        get_base_ydl_opts,
        get_ffmpeg_binary,
        check_ffmpeg,
        sanitize_filename,
        format_duration,
        categorize_ytdlp_error,
    )
except ImportError:
    # Standalone fallbacks if run outside repository
    def get_ffmpeg_binary() -> Optional[str]:
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        try:
            import imageio_ffmpeg
            img_exe = imageio_ffmpeg.get_ffmpeg_exe()
            if img_exe and os.path.exists(img_exe):
                return img_exe
        except Exception:
            pass
        return None

    def check_ffmpeg() -> bool:
        return get_ffmpeg_binary() is not None

    def sanitize_filename(filename: str) -> str:
        clean = re.sub(r'[\\/*?:"<>|]', "-", filename)
        clean = re.sub(r"\s+", " ", clean).strip(" .")
        if not clean.lower().endswith(".mp4"):
            clean += ".mp4"
        return clean or "video.mp4"

    def format_duration(seconds: Optional[int]) -> str:
        if not seconds or seconds <= 0:
            return "Unknown"
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        if hrs > 0:
            return f"{hrs}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

    def categorize_ytdlp_error(error_msg: str, operation: str = "processing") -> str:
        upper = error_msg.upper()
        if "CONFIRM YOU'RE NOT A BOT" in upper:
            return "YouTube Bot Verification: Platform requested interactive bot verification."
        if "PRIVATE VIDEO" in upper:
            return "Private Video: This video is private and requires authentication."
        if "SIGN IN TO CONFIRM YOUR AGE" in upper:
            return "Age-Restricted Video: This video requires age verification."
        clean = re.sub(r"^ERROR:\s*", "", error_msg, flags=re.IGNORECASE)
        clean = re.sub(r"\[youtube\]\s*", "", clean, flags=re.IGNORECASE)
        return clean.strip()

    def get_base_ydl_opts() -> Dict[str, Any]:
        return {
            "nocheckcertificate": True,
            "no_warnings": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["visionos", "android", "web"]
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        }


class VideoDownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Video Downloader - Desktop Edition")
        self.root.geometry("720x840")
        self.root.minsize(640, 700)
        self.root.configure(bg="#f8fafc")

        # Application state
        self.current_video_data: Optional[Dict[str, Any]] = None
        self.quality_options: List[Dict[str, Any]] = []
        self.thumbnail_photo: Optional[Any] = None
        self.is_downloading: bool = False
        self.default_download_dir = Path.home() / "Downloads"

        # Center the window on screen
        self._center_window(720, 840)

        # Build UI
        self._setup_styles()
        self._build_ui()

        # Check FFmpeg on startup
        self.root.after(200, self._check_ffmpeg_startup)

    def _center_window(self, width: int, height: int):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 30)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Colors
        bg_card = "#ffffff"
        text_primary = "#0f172a"
        primary_color = "#4f46e5"       # Indigo
        primary_hover = "#4338ca"
        success_color = "#10b981"       # Emerald
        success_hover = "#059669"

        # Fonts
        self.font_header = ("Segoe UI", 16, "bold")
        self.font_subtitle = ("Segoe UI", 9)
        self.font_label = ("Segoe UI", 10, "bold")
        self.font_body = ("Segoe UI", 9)
        self.font_btn = ("Segoe UI", 10, "bold")
        self.font_title = ("Segoe UI", 11, "bold")

        # Configure TTK styles
        style.configure("TFrame", background="#f8fafc")
        style.configure("Card.TFrame", background=bg_card, relief="solid", borderwidth=1)
        style.configure("TLabel", background="#f8fafc", foreground=text_primary, font=self.font_body)
        style.configure("Card.TLabel", background=bg_card, foreground=text_primary, font=self.font_body)
        style.configure("Title.TLabel", background="#f8fafc", foreground=text_primary, font=self.font_header)
        style.configure("Subtitle.TLabel", background="#f8fafc", foreground="#64748b", font=self.font_subtitle)

        # Primary Button (Fetch)
        style.configure(
            "Primary.TButton",
            font=self.font_btn,
            background=primary_color,
            foreground="#ffffff",
            padding=(16, 8),
            borderwidth=0
        )
        style.map("Primary.TButton", background=[("active", primary_hover), ("disabled", "#94a3b8")])

        # Success Button (Download)
        style.configure(
            "Success.TButton",
            font=self.font_btn,
            background=success_color,
            foreground="#ffffff",
            padding=(20, 10),
            borderwidth=0
        )
        style.map("Success.TButton", background=[("active", success_hover), ("disabled", "#94a3b8")])

        # Secondary Button (Browse / Open)
        style.configure(
            "Secondary.TButton",
            font=self.font_body,
            background="#e2e8f0",
            foreground="#1e293b",
            padding=(10, 6),
            borderwidth=0
        )
        style.map("Secondary.TButton", background=[("active", "#cbd5e1")])

        # Custom progressbar
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#e2e8f0",
            background=primary_color,
            thickness=14
        )

    def _build_ui(self):
        # Main scrollable canvas container to support smaller screens
        self.main_container = tk.Frame(self.root, bg="#f8fafc")
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # 1. Header Section
        header_frame = tk.Frame(self.main_container, bg="#f8fafc")
        header_frame.pack(fill=tk.X, pady=(0, 16))

        title_lbl = ttk.Label(header_frame, text="Video Downloader", style="Title.TLabel")
        title_lbl.pack(anchor="w")

        sub_lbl = ttk.Label(
            header_frame,
            text="Download authorized videos in full quality with audio merged in MP4 format",
            style="Subtitle.TLabel"
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # 2. URL Input Card
        url_card = tk.Frame(self.main_container, bg="#ffffff", bd=1, relief=tk.SOLID, padx=16, pady=16)
        url_card.pack(fill=tk.X, pady=(0, 14))

        url_label = tk.Label(url_card, text="Video URL", font=self.font_label, bg="#ffffff", fg="#0f172a")
        url_label.pack(anchor="w", pady=(0, 6))

        input_row = tk.Frame(url_card, bg="#ffffff")
        input_row.pack(fill=tk.X)

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            input_row,
            textvariable=self.url_var,
            font=("Segoe UI", 10),
            bd=1,
            relief=tk.SOLID,
            highlightthickness=1,
            highlightcolor="#4f46e5"
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self.fetch_video())

        # Paste context menu
        self._add_paste_context_menu(self.url_entry)

        self.paste_btn = ttk.Button(input_row, text="Paste", style="Secondary.TButton", command=self._paste_clipboard)
        self.paste_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.fetch_btn = ttk.Button(input_row, text="Fetch Video", style="Primary.TButton", command=self.fetch_video)
        self.fetch_btn.pack(side=tk.LEFT)

        # 3. Alert / Message Bar
        self.alert_frame = tk.Frame(self.main_container, bg="#fef2f2", bd=1, relief=tk.SOLID, padx=14, pady=10)
        self.alert_label = tk.Label(
            self.alert_frame,
            text="",
            font=("Segoe UI", 9),
            bg="#fef2f2",
            fg="#991b1b",
            justify=tk.LEFT,
            wraplength=640
        )
        self.alert_label.pack(fill=tk.X)
        # Initially hidden
        self.alert_frame.pack_forget()

        # 4. Save Directory Selector Card
        dest_card = tk.Frame(self.main_container, bg="#ffffff", bd=1, relief=tk.SOLID, padx=16, pady=12)
        dest_card.pack(fill=tk.X, pady=(0, 14))

        dest_header = tk.Frame(dest_card, bg="#ffffff")
        dest_header.pack(fill=tk.X, pady=(0, 4))

        dest_label = tk.Label(dest_header, text="Save Destination", font=self.font_label, bg="#ffffff", fg="#0f172a")
        dest_label.pack(side=tk.LEFT)

        dest_row = tk.Frame(dest_card, bg="#ffffff")
        dest_row.pack(fill=tk.X)

        self.dest_var = tk.StringVar(value=str(self.default_download_dir))
        self.dest_entry = tk.Entry(
            dest_row,
            textvariable=self.dest_var,
            font=("Segoe UI", 9),
            bd=1,
            relief=tk.SOLID,
            state="readonly"
        )
        self.dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 8))

        self.browse_btn = ttk.Button(dest_row, text="Browse...", style="Secondary.TButton", command=self._browse_destination)
        self.browse_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.open_folder_btn = ttk.Button(dest_row, text="Open Folder", style="Secondary.TButton", command=self._open_destination_folder)
        self.open_folder_btn.pack(side=tk.LEFT)

        # 5. Video Preview Card (Populated upon fetch)
        self.preview_card = tk.Frame(self.main_container, bg="#ffffff", bd=1, relief=tk.SOLID, padx=16, pady=16)
        # Pack preview card initially hidden
        self.preview_card.pack(fill=tk.BOTH, expand=True, pady=(0, 14))
        self.preview_card.pack_forget()

        # Video Info Row (Thumbnail + Meta)
        meta_row = tk.Frame(self.preview_card, bg="#ffffff")
        meta_row.pack(fill=tk.X, pady=(0, 14))

        # Thumbnail Label
        self.thumb_frame = tk.Frame(meta_row, bg="#000000", width=220, height=124)
        self.thumb_frame.pack_propagate(False)
        self.thumb_frame.pack(side=tk.LEFT, padx=(0, 16))

        self.thumb_label = tk.Label(self.thumb_frame, text="[No Preview]", bg="#1e293b", fg="#94a3b8")
        self.thumb_label.pack(fill=tk.BOTH, expand=True)

        # Details Column
        details_col = tk.Frame(meta_row, bg="#ffffff")
        details_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.title_label = tk.Label(
            details_col,
            text="Video Title",
            font=self.font_title,
            bg="#ffffff",
            fg="#0f172a",
            wraplength=380,
            justify=tk.LEFT,
            anchor="w"
        )
        self.title_label.pack(fill=tk.X, anchor="w", pady=(0, 4))

        self.channel_label = tk.Label(
            details_col,
            text="Creator",
            font=self.font_subtitle,
            bg="#ffffff",
            fg="#64748b",
            anchor="w"
        )
        self.channel_label.pack(fill=tk.X, anchor="w", pady=(0, 4))

        self.duration_badge = tk.Label(
            details_col,
            text="Duration: --:--",
            font=("Segoe UI", 8, "bold"),
            bg="#e2e8f0",
            fg="#334155",
            padx=8,
            pady=3
        )
        self.duration_badge.pack(anchor="w")

        # Quality Selector
        quality_frame = tk.Frame(self.preview_card, bg="#ffffff")
        quality_frame.pack(fill=tk.X, pady=(0, 14))

        q_label = tk.Label(quality_frame, text="Select Quality / Resolution", font=self.font_label, bg="#ffffff", fg="#0f172a")
        q_label.pack(anchor="w", pady=(0, 4))

        self.format_combobox = ttk.Combobox(quality_frame, state="readonly", font=("Segoe UI", 9))
        self.format_combobox.pack(fill=tk.X, ipady=3)

        # Download Button
        self.download_btn = ttk.Button(
            self.preview_card,
            text="Download MP4",
            style="Success.TButton",
            command=self.start_download
        )
        self.download_btn.pack(fill=tk.X, pady=(4, 10))

        # 6. Progress Section
        self.progress_frame = tk.Frame(self.preview_card, bg="#ffffff")
        self.progress_frame.pack(fill=tk.X, pady=(6, 0))
        self.progress_frame.pack_forget()

        self.status_label = tk.Label(
            self.progress_frame,
            text="Initializing download...",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#475569"
        )
        self.status_label.pack(anchor="w", pady=(0, 4))

        self.progressbar = ttk.Progressbar(
            self.progress_frame,
            orient="horizontal",
            mode="determinate",
            style="Horizontal.TProgressbar"
        )
        self.progressbar.pack(fill=tk.X, pady=(0, 6))

        self.success_banner = tk.Label(
            self.progress_frame,
            text="",
            font=("Segoe UI", 9, "bold"),
            bg="#f0fdf4",
            fg="#166534",
            bd=1,
            relief=tk.SOLID,
            padx=10,
            pady=6,
            wraplength=620,
            justify=tk.LEFT
        )
        self.success_banner.pack(fill=tk.X, pady=(4, 0))
        self.success_banner.pack_forget()

        # 7. Footer Status Bar
        footer = tk.Frame(self.root, bg="#e2e8f0", height=26, padx=12)
        footer.pack(side=tk.BOTTOM, fill=tk.X)

        self.footer_status = tk.Label(
            footer,
            text="Ready",
            font=("Segoe UI", 8),
            bg="#e2e8f0",
            fg="#475569"
        )
        self.footer_status.pack(side=tk.LEFT)

        self.ffmpeg_indicator = tk.Label(
            footer,
            text="FFmpeg: Checking...",
            font=("Segoe UI", 8),
            bg="#e2e8f0",
            fg="#475569"
        )
        self.ffmpeg_indicator.pack(side=tk.RIGHT)

    def _add_paste_context_menu(self, widget):
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Paste", command=self._paste_clipboard)
        menu.add_command(label="Clear", command=lambda: self.url_var.set(""))

        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_menu)

    def _paste_clipboard(self):
        try:
            clipboard_text = self.root.clipboard_get().strip()
            if clipboard_text:
                self.url_var.set(clipboard_text)
                self.url_entry.icursor(tk.END)
        except Exception:
            pass

    def _browse_destination(self):
        chosen = filedialog.askdirectory(
            title="Select Download Destination Folder",
            initialdir=self.dest_var.get() or str(self.default_download_dir)
        )
        if chosen:
            self.dest_var.set(chosen)

    def _open_destination_folder(self):
        folder = Path(self.dest_var.get())
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(folder)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open directory: {e}")

    def _check_ffmpeg_startup(self):
        has_ffmpeg = check_ffmpeg()
        if has_ffmpeg:
            self.ffmpeg_indicator.config(text="FFmpeg: Available (Merging Enabled)", fg="#166534")
        else:
            self.ffmpeg_indicator.config(text="FFmpeg: Missing (Audio merge may be limited)", fg="#991b1b")

    def show_alert(self, text: str, is_error: bool = True):
        self.alert_frame.config(bg="#fef2f2" if is_error else "#eff6ff")
        self.alert_label.config(
            text=text,
            bg="#fef2f2" if is_error else "#eff6ff",
            fg="#991b1b" if is_error else "#1e40af"
        )
        self.alert_frame.pack(fill=tk.X, pady=(0, 14), before=self.preview_card)

    def hide_alert(self):
        self.alert_frame.pack_forget()
        self.alert_label.config(text="")

    def fetch_video(self):
        if self.is_downloading:
            messagebox.showwarning("Busy", "A video download is currently in progress. Please wait.")
            return

        url = self.url_var.get().strip()
        if not url:
            self.show_alert("Please enter or paste a valid video URL.", is_error=True)
            return

        self.hide_alert()
        self.fetch_btn.config(state="disabled", text="Fetching...")
        self.footer_status.config(text="Connecting to video provider and extracting metadata...")
        self.preview_card.pack_forget()

        # Run extraction in background thread
        thread = threading.Thread(target=self._async_fetch_metadata, args=(url,), daemon=True)
        thread.start()

    def _async_fetch_metadata(self, url: str):
        ydl_opts = get_base_ydl_opts()
        ydl_opts.update({
            "extract_flat": False,
            "skip_download": True,
            "quiet": True,
            "ignoreerrors": False,
            "socket_timeout": 25,
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("Could not extract video metadata.")

                # If playlist, pick first item
                if info.get("_type") == "playlist":
                    entries = list(info.get("entries", []))
                    if not entries:
                        raise Exception("The provided URL is an empty playlist.")
                    info = entries[0]

                title = info.get("title", "Untitled Video")
                thumbnail = info.get("thumbnail") or (info.get("thumbnails")[-1]["url"] if info.get("thumbnails") else "")
                duration = info.get("duration")
                uploader = info.get("uploader") or info.get("channel") or "Unknown Creator"

                # Parse formats
                raw_formats = info.get("formats", [])
                quality_options = []

                # Best quality option
                quality_options.append({
                    "format_id": "best",
                    "label": "Best Available Quality (Full HD/4K + Audio, MP4)"
                })

                seen_heights = set()
                sorted_formats = sorted(
                    [f for f in raw_formats if f.get("vcodec") != "none" and f.get("height") and (f.get("url") or f.get("manifest_url"))],
                    key=lambda x: (x.get("height", 0), x.get("tbr") or 0),
                    reverse=True
                )

                for fmt in sorted_formats:
                    height = fmt.get("height")
                    if not height or height in seen_heights:
                        continue
                    seen_heights.add(height)

                    format_id = fmt.get("format_id")
                    fps = fmt.get("fps")
                    fps_str = f" {fps}fps" if fps and fps > 30 else ""
                    filesize = fmt.get("filesize") or fmt.get("filesize_approx")
                    size_str = f" (~{filesize // (1024 * 1024)} MB)" if filesize else ""

                    quality_options.append({
                        "format_id": str(format_id),
                        "label": f"{height}p{fps_str} (MP4 with Audio){size_str}"
                    })

                # Direct stream fallback
                if len(quality_options) == 1:
                    for fmt in raw_formats:
                        if fmt.get("vcodec") != "none" and (fmt.get("url") or fmt.get("manifest_url")):
                            fid = fmt.get("format_id")
                            resolution = fmt.get("resolution") or fmt.get("format_note") or "Standard"
                            quality_options.append({
                                "format_id": str(fid),
                                "label": f"Direct Stream: {resolution} ({fmt.get('ext', 'mp4')})"
                            })

                data = {
                    "url": url,
                    "title": title,
                    "uploader": uploader,
                    "duration": duration,
                    "duration_formatted": format_duration(duration),
                    "thumbnail": thumbnail,
                    "quality_options": quality_options
                }

                self.root.after(0, self._on_fetch_success, data)

        except yt_dlp.utils.DownloadError as e:
            err_msg = categorize_ytdlp_error(str(e), "metadata extraction")
            self.root.after(0, self._on_fetch_error, err_msg)
        except Exception as e:
            err_msg = f"Failed to fetch video: {str(e)}"
            self.root.after(0, self._on_fetch_error, err_msg)

    def _on_fetch_success(self, data: Dict[str, Any]):
        self.fetch_btn.config(state="normal", text="Fetch Video")
        self.footer_status.config(text="Metadata fetched successfully.")
        self.current_video_data = data
        self.quality_options = data["quality_options"]

        # Populate UI elements
        self.title_label.config(text=data["title"])
        self.channel_label.config(text=f"Published by {data['uploader']}")
        self.duration_badge.config(text=f"Duration: {data['duration_formatted']}")

        # Populate combobox
        labels = [opt["label"] for opt in self.quality_options]
        self.format_combobox["values"] = labels
        if labels:
            self.format_combobox.current(0)

        # Reset progress bar & success banner
        self.progress_frame.pack_forget()
        self.success_banner.pack_forget()
        self.download_btn.config(state="normal")

        # Display preview card
        self.preview_card.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        # Asynchronously fetch thumbnail image if Pillow is available
        thumb_url = data.get("thumbnail")
        if HAS_PIL and thumb_url:
            threading.Thread(target=self._async_load_thumbnail, args=(thumb_url,), daemon=True).start()
        else:
            self.thumb_label.config(text="[Preview Ready]", image="")

    def _async_load_thumbnail(self, url: str):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data))
            # Resize keeping aspect ratio to fit inside 220x124
            img.thumbnail((220, 124), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.root.after(0, self._set_thumbnail, photo)
        except Exception:
            pass

    def _set_thumbnail(self, photo):
        self.thumbnail_photo = photo
        self.thumb_label.config(image=photo, text="")

    def _on_fetch_error(self, error_message: str):
        self.fetch_btn.config(state="normal", text="Fetch Video")
        self.footer_status.config(text="Fetch failed.")
        self.show_alert(error_message, is_error=True)

    def start_download(self):
        if not self.current_video_data:
            messagebox.showwarning("Warning", "Please fetch a video first.")
            return

        save_dir = Path(self.dest_var.get().strip() or str(self.default_download_dir))
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Invalid Directory", f"Could not create destination directory: {e}")
            return

        selected_idx = self.format_combobox.current()
        if selected_idx < 0 or selected_idx >= len(self.quality_options):
            format_id = "best"
        else:
            format_id = self.quality_options[selected_idx]["format_id"]

        self.is_downloading = True
        self.download_btn.config(state="disabled")
        self.fetch_btn.config(state="disabled")
        self.format_combobox.config(state="disabled")

        # Show progress section
        self.progress_frame.pack(fill=tk.X, pady=(6, 0))
        self.progressbar["value"] = 0
        self.status_label.config(text="Connecting to download streams...", fg="#475569")
        self.success_banner.pack_forget()

        # Start download thread
        thread = threading.Thread(
            target=self._async_download_worker,
            args=(self.current_video_data["url"], format_id, save_dir),
            daemon=True
        )
        thread.start()

    def _async_download_worker(self, url: str, format_id: str, save_dir: Path):
        download_id = f"dl_{int(time.time())}"
        output_tmpl = str(save_dir / f"{download_id}_%(title).150B.%(ext)s")

        if format_id == "best":
            format_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            format_selector = f"{format_id}+bestaudio[ext=m4a]/{format_id}+bestaudio/{format_id}/best"

        def progress_hook(d):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                speed_str = f" @ {speed / (1024 * 1024):.1f} MB/s" if speed > 0 else ""
                pct = 0.0
                if total > 0:
                    pct = min(95.0, (downloaded / total) * 100)
                    mb_down = downloaded / (1024 * 1024)
                    mb_tot = total / (1024 * 1024)
                    msg = f"Downloading stream: {mb_down:.1f} MB / {mb_tot:.1f} MB ({pct:.1f}%){speed_str}"
                else:
                    mb_down = downloaded / (1024 * 1024)
                    msg = f"Downloading stream: {mb_down:.1f} MB{speed_str}"

                self.root.after(0, self._update_progress_ui, pct, msg)

            elif status == "finished":
                self.root.after(0, self._update_progress_ui, 96.0, "Merging video & audio with FFmpeg into MP4...")

        def postprocessor_hook(d):
            if d.get("status") == "started":
                self.root.after(0, self._update_progress_ui, 97.0, "FFmpeg postprocessing: Finalizing MP4 container...")

        ydl_opts = get_base_ydl_opts()
        ydl_opts.update({
            "format": format_selector,
            "outtmpl": output_tmpl,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "quiet": True,
            "overwrites": True,
            "socket_timeout": 35,
        })

        ffmpeg_exe = get_ffmpeg_binary()
        if ffmpeg_exe:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_exe)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)

            # Locate downloaded file
            matches = [
                f for f in save_dir.glob(f"{download_id}_*")
                if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl")
            ]
            if not matches:
                raise Exception("Merged output file was not found on disk.")

            mp4_matches = [f for f in matches if f.suffix.lower() == ".mp4"]
            target_file = mp4_matches[0] if mp4_matches else matches[0]

            # Remux to MP4 if needed and FFmpeg is available
            if target_file.suffix.lower() != ".mp4" and ffmpeg_exe:
                mp4_path = target_file.with_suffix(".mp4")
                try:
                    import subprocess
                    subprocess.run(
                        [ffmpeg_exe, "-y", "-i", str(target_file), "-c", "copy", str(mp4_path)],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    if mp4_path.exists():
                        try:
                            target_file.unlink()
                        except Exception:
                            pass
                        target_file = mp4_path
                except Exception:
                    pass

            # Rename to clean filename without the dl_ timestamp prefix
            raw_title = target_file.name[len(download_id) + 1:]
            clean_name = sanitize_filename(raw_title)
            final_path = save_dir / clean_name

            # Avoid overwrite collisions
            if final_path.exists() and final_path != target_file:
                final_path = save_dir / f"{Path(clean_name).stem}_{int(time.time())}.mp4"

            try:
                target_file.rename(final_path)
            except Exception:
                final_path = target_file

            self.root.after(0, self._on_download_success, final_path)

        except Exception as e:
            user_err = categorize_ytdlp_error(str(e), "downloading")
            self.root.after(0, self._on_download_error, user_err)

    def _update_progress_ui(self, pct: float, message: str):
        self.progressbar["value"] = pct
        self.status_label.config(text=message)
        self.footer_status.config(text=message)

    def _on_download_success(self, final_path: Path):
        self.is_downloading = False
        self.progressbar["value"] = 100
        self.status_label.config(text="Download complete! 100%", fg="#166534")
        self.footer_status.config(text=f"Saved: {final_path.name}")

        self.success_banner.config(
            text=f"SUCCESS: Video downloaded successfully!\nSaved to: {final_path}"
        )
        self.success_banner.pack(fill=tk.X, pady=(4, 0))

        # Re-enable inputs
        self.download_btn.config(state="normal")
        self.fetch_btn.config(state="normal")
        self.format_combobox.config(state="readonly")

        # Show prompt offering to open folder
        if messagebox.askyesno("Download Complete", f"Successfully saved:\n{final_path.name}\n\nWould you like to open the folder now?"):
            self._open_destination_folder()

    def _on_download_error(self, error_message: str):
        self.is_downloading = False
        self.status_label.config(text="Download failed.", fg="#991b1b")
        self.footer_status.config(text="Download failed.")
        self.download_btn.config(state="normal")
        self.fetch_btn.config(state="normal")
        self.format_combobox.config(state="readonly")
        messagebox.showerror("Download Error", error_message)


def main():
    root = tk.Tk()
    app = VideoDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
