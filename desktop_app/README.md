# Video Downloader - Native Desktop Edition (Tkinter)

A standalone native Windows desktop application for fetching YouTube video metadata, selecting quality options (up to 4K), merging streams with FFmpeg, and downloading directly to your laptop.

---

## ⚡ 1-Click Launch

Double-click the **`run_gui.bat`** file in the root directory to instantly launch the desktop app.

---

## 🚀 Features

- **Native Windows GUI**: Built with standard Python `tkinter` and `ttk` with crisp High-DPI support (`Segoe UI`).
- **Thumbnail & Metadata**: Shows video thumbnail preview, channel name, and duration.
- **Genuine Quality Dropdown**: Choose between Best Available (Full HD/4K), 1080p, 720p, 480p, etc.
- **Save Location Selector**: Choose where to save your videos (defaults to `C:\Users\<You>\Downloads`), with a "Browse..." button and an instant "Open Folder" button.
- **Multi-threaded**: Extraction and downloading run in background worker threads so the window never freezes.
- **FFmpeg Merging**: Automatically combines high-resolution video streams and high-bitrate audio streams into standard MP4 files.
- **Bot Challenge Protection**: Uses `visionos` and `android` multi-client fallbacks to prevent bot verification challenges.

---

## 💻 Manual Terminal Launch

```powershell
.\venv\Scripts\python.exe desktop_app\app.py
```
