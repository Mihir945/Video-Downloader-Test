# Video Downloader Web Application

A clean, minimalist, full-stack video downloader built with **FastAPI**, **Vanilla JavaScript**, **HTML/CSS**, and **FFmpeg**.

This application allows users to fetch video metadata, select genuine quality streams (up to 1080p/4K), merge video and audio streams seamlessly using FFmpeg, and download the resulting MP4 directly to their computer.

---

## 🌐 Live Web Application

👉 **[https://video-downloader-test-q9wq.onrender.com/](https://video-downloader-test-q9wq.onrender.com/)**

Open the link above in any browser on desktop or mobile to fetch and download videos directly online without installing anything!

---

## ⚡ 1-Click Launch (Instant Local App)

If you are running this locally on Windows:

1. Double-click the **[`run.bat`](run.bat)** file in the root folder.
2. It will automatically start the backend server and open your browser to:
   👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

*(No manual terminal commands required!)*

---

## 🚀 Live Online Deployment (For 24/7 Web Access)

Because this web app requires **Python** and **FFmpeg** to merge audio and video streams, it cannot be hosted on pure static hosts like GitHub Pages alone.

To host it online for free with 1 click:

### Option A: Render.com (Recommended & Free)
1. Fork or push this repository to your GitHub account (`Mihir945/Video-Downloader-Test`).
2. Log in to [Render.com](https://render.com) and click **New +** &rarr; **Web Service**.
3. Connect your repository `Video-Downloader-Test`.
4. Configure:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Click **Deploy**. Render will generate a live URL where anyone can use your downloader online!

---

## Architecture Overview

```
┌────────────────────────────────┐
│      Frontend (HTML/CSS/JS)    │
│  - URL Input & Validation      │
│  - Thumbnail & Quality Picker  │
│  - Real-time Progress Polling  │
│  - Browser File Download (Blob)│
│  - AdSense Integration (ads.js)│
└───────────────▲────────────────┘
                │
                │ HTTP Fetch API (JSON)
                ▼
┌────────────────────────────────┐
│      FastAPI Backend           │
│  - POST /fetch                 │
│  - POST /download              │
│  - GET  /progress/{id}         │
│  - GET  /download/file/{id}    │
│  - GET  /ads.txt               │
└───────────────▲────────────────┘
                │
                │ yt-dlp + FFmpeg
                ▼
┌────────────────────────────────┐
│  Media Processing & Storage    │
│  - Video stream extraction     │
│  - Audio stream extraction     │
│  - FFmpeg MP4 merge & cleanup  │
└────────────────────────────────┘
```

1. **Frontend**: Plain HTML5, modern CSS, and Vanilla JavaScript. Fetches video metadata, dynamically populates available quality options, initiates downloads, streams response bytes into browser memory, and saves directly to the user's Downloads folder.
2. **Backend**: FastAPI with Python. Interacts with `yt-dlp` to extract formats and stream URLs, registers background download worker threads, merges streams via FFmpeg, cleans up old files automatically, and serves the finished MP4 file with RFC 5987 / RFC 6266 `Content-Disposition` attachment headers.
3. **FFmpeg Engine**: Combines separate video and high-bitrate audio streams into standard MP4 containers.
4. **Google AdSense Ready**: Modular AdSense setup in `frontend/ads.js` with compliant placements, `/ads.txt` route, and a complete Privacy Policy page at `/privacy.html`.

---

## Project Structure

```
video downloader/
├── backend/
│   ├── main.py              # FastAPI server, endpoints, FFmpeg hooks, file transfer
│   └── requirements.txt     # Python backend dependencies
├── frontend/
│   ├── index.html           # Main UI markup
│   ├── style.css            # Clean, responsive CSS styling
│   ├── script.js            # Frontend downloader logic & file stream transfer
│   ├── ads.js               # Modular Google AdSense integration (disabled by default)
│   ├── ads.txt              # Standard AdSense authorized seller verification file
│   └── privacy.html         # Mandatory Privacy Policy page for ad compliance
├── downloads/               # Temporary cache for merged MP4 files (auto-purged)
├── run.bat                  # 1-Click launcher for Windows
├── .gitignore               # Ignores venv, pycache, and downloaded videos
└── README.md                # Project documentation
```

---

## Prerequisites (For Local Setup)

1. **Python 3.9+** (Tested on Python 3.13)
2. **FFmpeg** (Required to merge video and audio streams into standard MP4)

### Installing FFmpeg on Windows
```powershell
winget install Gyan.FFmpeg
```

---

## Manual Backend Startup

If you prefer using the terminal instead of `run.bat`:

```powershell
# 1. Activate Virtual Environment
.\venv\Scripts\Activate.ps1

# 2. Run the Server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/fetch` | Accepts `{"url": "..."}`, validates URL, returns title, thumbnail, duration, and available format options. |
| `POST` | `/download` | Accepts `{"url": "...", "format_id": "..."}`, starts background job, returns `{"download_id": "..."}`. |
| `GET` | `/progress/{download_id}` | Returns current status (`pending`, `downloading`, `merging`, `completed`, `failed`), progress percentage, and filename. |
| `GET` | `/download/file/{download_id}` | Transfers the completed MP4 file as an attachment to the user's browser. |
| `GET` | `/ads.txt` | Serves the official Google AdSense authorized sellers verification file. |
| `GET` | `/health` | Diagnostic endpoint returning system status and FFmpeg availability. |

---

## Policy & Disclaimer

This software is designed solely for downloading videos that the user owns or has explicit authorization to download. It does **not** bypass DRM, encryption, access controls, or user authentication restrictions. Always respect copyright laws and platform terms of service.
