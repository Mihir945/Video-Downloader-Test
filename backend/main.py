import os
import re
import sys
import time
import uuid
import shutil
import logging
import threading
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("video_downloader")

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
FRONTEND_DIR = BASE_DIR / "frontend"

# Ensure downloads directory exists
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Automatically add common Windows FFmpeg directories to PATH if not already present
local_app_data = os.environ.get("LOCALAPPDATA", "")
if local_app_data:
    winget_links = os.path.join(local_app_data, "Microsoft", "WinGet", "Links")
    if os.path.isdir(winget_links) and winget_links not in os.environ.get("PATH", ""):
        os.environ["PATH"] = winget_links + os.pathsep + os.environ.get("PATH", "")

    winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.is_dir():
        for bin_dir in winget_packages.glob("**/bin"):
            if (bin_dir / "ffmpeg.exe").exists() or (bin_dir / "ffmpeg").exists():
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                break

program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
for common_path in [
    Path("C:/ffmpeg/bin"),
    Path(program_files) / "ffmpeg" / "bin",
]:
    if common_path.is_dir() and str(common_path) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(common_path) + os.pathsep + os.environ.get("PATH", "")

# Configure certifi CA bundle if available to prevent Windows SSL verification failures
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

app = FastAPI(
    title="Video Downloader API",
    description="Backend API for fetching video metadata, downloading video and audio streams, and merging them into MP4.",
    version="1.0.0"
)

# Enable CORS for cross-origin requests (e.g. running frontend via VS Code Live Server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "Content-Type"],
)

# In-memory store for tracking download jobs
# Structure: { download_id: { status, progress, title, filepath, filename, error, created_at } }
download_jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()


class FetchRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: Optional[str] = "best"


def get_ffmpeg_binary() -> Optional[str]:
    """Finds ffmpeg executable from PATH or bundled imageio_ffmpeg."""
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


def get_node_binary() -> Optional[str]:
    """Finds Node.js executable for yt-dlp JS challenge solving."""
    exe = shutil.which("node")
    if exe:
        return exe
    for path in ["/usr/bin/node", "/usr/local/bin/node", "C:\\Program Files\\nodejs\\node.exe"]:
        if os.path.exists(path):
            return path
    return None


def get_base_ydl_opts() -> Dict[str, Any]:
    """Constructs robust yt-dlp options supporting Node.js JS challenge runtime."""
    node_exe = get_node_binary()

    opts: Dict[str, Any] = {
        "nocheckcertificate": True,
        "no_warnings": True,
        "remote_components": ["ejs:github"],
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }
    if node_exe:
        opts["js_runtimes"] = {"node": {"path": node_exe}}
    return opts


def check_ffmpeg() -> bool:
    """Check if ffmpeg executable is available in system PATH or imageio_ffmpeg."""
    return get_ffmpeg_binary() is not None


def cleanup_old_downloads(max_age_seconds: int = 3600):
    """Remove files in the downloads directory that are older than max_age_seconds."""
    now = time.time()
    try:
        for file_path in DOWNLOADS_DIR.glob("*"):
            if file_path.is_file() and file_path.name != ".gitkeep":
                if now - file_path.stat().st_mtime > max_age_seconds:
                    try:
                        file_path.unlink()
                        logger.info(f"Cleaned up expired file: {file_path.name}")
                    except Exception as e:
                        logger.warning(f"Could not delete {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize video title into a clean, safe filename.
    Replaces problematic characters (such as yt-dlp substitutions and Windows invalid characters).
    """
    clean = filename.replace('\u29f8', '-').replace('\uff5c', '-').replace('|', '-').replace('/', '-')
    clean = clean.replace('\\', '-').replace(':', '-').replace('*', '').replace('?', '').replace('"', '').replace('<', '').replace('>', '')
    clean = re.sub(r'[\r\n\t]+', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip(' .')
    if not clean.lower().endswith(".mp4"):
        clean = f"{Path(clean).stem}.mp4"
    if clean == ".mp4" or not clean:
        clean = "video.mp4"
    return clean


def format_duration(seconds: Optional[int]) -> str:
    """Convert duration in seconds to MM:SS or HH:MM:SS format."""
    if not seconds or seconds <= 0:
        return "Unknown"
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


@app.get("/health")
def health_check():
    """System health check and diagnostic information."""
    return {
        "status": "healthy",
        "ffmpeg_installed": check_ffmpeg(),
        "downloads_dir": str(DOWNLOADS_DIR)
    }


def categorize_ytdlp_error(error_msg: str, operation: str = "fetching video details") -> str:
    """
    Parses yt-dlp extraction or download errors into clear, user-friendly explanations.
    Distinguishes external platform access/bot verification challenges from application bugs,
    and provides legitimate alternatives for owner-authorized content.
    """
    upper_err = error_msg.upper()
    lower_err = error_msg.lower()

    if "CONFIRM YOU'RE NOT A BOT" in upper_err or "CONFIRM YOU’RE NOT A BOT" in upper_err:
        return (
            "YouTube Bot Verification: YouTube detected automated access from this server's IP address "
            "and requested interactive verification ('Sign in to confirm you're not a bot').\n\n"
            "This is an external access control check applied by YouTube to datacenter/cloud hosting IPs, "
            "not a bug in the application. Per platform terms and security standards, automated bot challenges "
            "are not bypassed.\n\n"
            "Legitimate options for content you are authorized to access:\n"
            "- Video Owners: You can download your own videos directly in high quality from YouTube Studio (studio.youtube.com > Content > Options > Download).\n"
            "- Use your original uploaded master video file from your storage.\n"
            "- If running this application locally on your computer, residential network connections are typically not blocked."
        )

    if "SIGN IN TO CONFIRM YOUR AGE" in upper_err:
        return (
            "Age-Restricted Content: This video requires age verification on YouTube. "
            "To safeguard account privacy and adhere to platform access controls, automated sign-in is not supported."
        )

    if "PRIVATE VIDEO" in upper_err:
        return (
            "Private Video: This video is designated Private by its uploader and can only be accessed "
            "by accounts explicitly granted permission."
        )

    if "DRM" in upper_err:
        return "DRM Protected: This content is protected by Digital Rights Management (DRM) and cannot be downloaded."

    if "INCOMPLETE YOUTUBE ID" in upper_err or "VIDEO UNAVAILABLE" in upper_err:
        return "Video Unavailable: The video does not exist, has been removed, or the URL is malformed. Please verify the URL."

    if "HTTP ERROR 429" in upper_err or "TOO MANY REQUESTS" in upper_err:
        return "Rate Limited: YouTube is temporarily limiting automated requests from this server IP. Please wait a few moments before trying again."

    if "FFMPEG" in lower_err:
        return "FFmpeg Error: FFmpeg is required to process and merge media streams. Please ensure FFmpeg is installed."

    clean_error = re.sub(r"^ERROR:\s*", "", error_msg, flags=re.IGNORECASE)
    clean_error = re.sub(r"\[youtube\]\s*", "", clean_error, flags=re.IGNORECASE)
    return f"Unable to complete {operation}: {clean_error.strip()}"


@app.post("/fetch")
def fetch_video_info(req: FetchRequest):
    """
    Accepts a video URL, validates it, and retrieves metadata
    along with genuinely available video resolution and quality options.
    """
    url = req.url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Invalid URL. Please enter a valid HTTP or HTTPS video URL.")

    logger.info(f"[METADATA EXTRACTION START] URL: {url}")

    # Options for fast metadata extraction using JS challenge solver and modern player clients
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
                logger.error(f"[METADATA EXTRACTION FAILED] Empty metadata returned for URL: {url}")
                raise HTTPException(status_code=404, detail="Could not extract video metadata.")

            # Check if this is a playlist
            if "_type" in info and info["_type"] == "playlist":
                entries = list(info.get("entries", []))
                if not entries:
                    raise HTTPException(status_code=400, detail="The provided URL is an empty playlist.")
                info = entries[0]

            title = info.get("title", "Untitled Video")
            thumbnail = info.get("thumbnail") or (info.get("thumbnails")[-1]["url"] if info.get("thumbnails") else "")
            duration = info.get("duration")
            uploader = info.get("uploader") or info.get("channel") or "Unknown Creator"

            # Parse and organize available formats
            raw_formats = info.get("formats", [])
            quality_options = []

            # 1. Best Quality option (combines best video and best audio into MP4)
            quality_options.append({
                "format_id": "best",
                "label": "Best Available Quality (Full HD/4K + Audio, MP4)",
                "resolution": "Best",
                "ext": "mp4",
                "has_audio": True
            })

            # 2. Filter available video streams by height/resolution
            seen_heights = set()
            sorted_formats = sorted(
                [f for f in raw_formats if f.get("vcodec") != "none" and f.get("height")],
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
                    "format_id": f"{format_id}",
                    "label": f"{height}p{fps_str} (MP4 with Audio){size_str}",
                    "resolution": f"{height}p",
                    "ext": "mp4",
                    "has_audio": True
                })

            # If no separated video streams were found, check direct audio/video formats
            if len(quality_options) == 1:
                for fmt in raw_formats:
                    if fmt.get("vcodec") != "none":
                        fid = fmt.get("format_id")
                        resolution = fmt.get("resolution") or fmt.get("format_note") or "Standard"
                        quality_options.append({
                            "format_id": fid,
                            "label": f"Direct Stream: {resolution} ({fmt.get('ext', 'mp4')})",
                            "resolution": str(resolution),
                            "ext": fmt.get("ext", "mp4"),
                            "has_audio": fmt.get("acodec") != "none"
                        })

            logger.info(f"[METADATA EXTRACTION SUCCESS] Title: '{title}' | Formats: {len(quality_options)}")

            return {
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
                "duration_formatted": format_duration(duration),
                "uploader": uploader,
                "formats": quality_options,
                "url": url
            }

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"[METADATA EXTRACTION FAILED] yt-dlp DownloadError for URL {url}: {error_msg}")
        detail = categorize_ytdlp_error(error_msg, "metadata extraction")
        raise HTTPException(status_code=400, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[METADATA EXTRACTION FAILED] Unexpected error for URL {url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch video details: {str(e)}")


def run_download_task(download_id: str, url: str, format_id: str):
    """
    Background worker thread function that downloads video and audio streams,
    merges them using FFmpeg into an MP4 container, and reports actual progress.
    """
    with jobs_lock:
        job = download_jobs.get(download_id)
        if not job:
            return
        job["status"] = "downloading"
        job["progress"] = 0.0

    logger.info(f"[DOWNLOAD PROCESSING START] ID: {download_id} | URL: {url} | Format: {format_id}")

    # Ensure cleanup of old downloads
    cleanup_old_downloads()

    # Define unique output template
    output_template = str(DOWNLOADS_DIR / f"{download_id}_%(title).150B.%(ext)s")

    # Determine format selector string
    if format_id == "best":
        format_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    else:
        # Fallback chain ensures audio is always merged into video
        format_selector = f"{format_id}+bestaudio[ext=m4a]/{format_id}+bestaudio/{format_id}/best"

    def progress_hook(d):
        """Callback invoked by yt-dlp to report genuine download progress."""
        try:
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                pct = 0.0
                if total > 0:
                    pct = round((downloaded / total) * 100, 1)
                    # Keep at max 95% while downloading so merging is 96-98% and ready is 99%
                    pct = min(pct, 95.0)

                with jobs_lock:
                    if download_id in download_jobs:
                        download_jobs[download_id]["status"] = "downloading"
                        download_jobs[download_id]["progress"] = max(download_jobs[download_id]["progress"], pct)

            elif status == "finished":
                with jobs_lock:
                    if download_id in download_jobs:
                        download_jobs[download_id]["status"] = "merging"
                        download_jobs[download_id]["progress"] = 96.0
        except Exception as err:
            logger.error(f"Error inside progress_hook: {err}")

    def postprocessor_hook(d):
        """Callback invoked by yt-dlp during FFmpeg postprocessing and merging."""
        try:
            status = d.get("status")
            if status == "started":
                with jobs_lock:
                    if download_id in download_jobs:
                        download_jobs[download_id]["status"] = "merging"
                        download_jobs[download_id]["progress"] = 97.0
        except Exception as err:
            logger.error(f"Error inside postprocessor_hook: {err}")

    ydl_opts = get_base_ydl_opts()
    ydl_opts.update({
        "format": format_selector,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "quiet": True,
        "overwrites": True,
        "socket_timeout": 35,
    })

    # Pass explicit FFmpeg location if available
    ffmpeg_exe = get_ffmpeg_binary()
    if ffmpeg_exe:
        ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_exe)
    else:
        logger.warning("FFmpeg executable not detected on system PATH or imageio_ffmpeg.")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Failed to retrieve stream data during download.")

            # Search for the output file in downloads directory matching download_id
            matched_files = [
                f for f in DOWNLOADS_DIR.glob(f"{download_id}_*")
                if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl")
            ]
            if not matched_files:
                raise Exception("Download completed but merged output file could not be located on disk.")

            # Prefer .mp4 container
            mp4_files = [f for f in matched_files if f.suffix.lower() == ".mp4"]
            target_file = mp4_files[0] if mp4_files else matched_files[0]

            # If target file is not mp4, attempt remuxing with FFmpeg
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
                except Exception as remux_err:
                    logger.warning(f"Could not remux {target_file} to mp4: {remux_err}")

            # Format and sanitize clean filename for the user
            raw_name = target_file.name[len(download_id) + 1:]
            clean_name = sanitize_filename(raw_name)

            # Mark job as completed and ready for browser file transfer
            # Note: Progress is set to 99.0% on the backend. The frontend reaches
            # 100% only after the actual file transfer to the user's computer completes.
            with jobs_lock:
                if download_id in download_jobs:
                    download_jobs[download_id]["status"] = "completed"
                    download_jobs[download_id]["progress"] = 99.0
                    download_jobs[download_id]["filepath"] = str(target_file)
                    download_jobs[download_id]["filename"] = clean_name
            logger.info(f"[DOWNLOAD PROCESSING SUCCESS] ID: {download_id} | Output file prepared: {clean_name}")

    except Exception as e:
        error_text = str(e)
        logger.error(f"[DOWNLOAD PROCESSING FAILED] ID: {download_id} | Error: {error_text}", exc_info=True)
        user_msg = categorize_ytdlp_error(error_text, "video stream downloading")

        with jobs_lock:
            if download_id in download_jobs:
                download_jobs[download_id]["status"] = "failed"
                download_jobs[download_id]["error"] = user_msg


@app.post("/download")
def start_download(req: DownloadRequest):
    """
    Accepts video URL and selected quality format ID,
    initiates asynchronous download and FFmpeg merging,
    and returns a unique download_id for progress polling.
    """
    url = req.url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Invalid video URL.")

    format_id = req.format_id or "best"
    download_id = uuid.uuid4().hex[:12]

    with jobs_lock:
        download_jobs[download_id] = {
            "status": "pending",
            "progress": 0.0,
            "filepath": None,
            "filename": None,
            "error": None,
            "created_at": time.time(),
        }

    # Start download task in background thread
    worker = threading.Thread(
        target=run_download_task,
        args=(download_id, url, format_id),
        daemon=True
    )
    worker.start()

    return {"download_id": download_id}


@app.get("/progress/{download_id}")
def get_download_progress(download_id: str):
    """
    Returns the real-time download status, percentage completed,
    output filename, or error description.
    """
    with jobs_lock:
        job = download_jobs.get(download_id)
        if job:
            return {
                "download_id": download_id,
                "status": job["status"],       # pending, downloading, merging, completed, failed
                "progress": job["progress"],   # float 0.0 to 99.0 while on backend
                "filename": job.get("filename"),
                "error": job.get("error")
            }

    # Fallback: Check if file exists on disk (e.g. server reloaded during operation)
    if re.match(r"^[a-zA-Z0-9_\-]+$", download_id):
        matched = [
            f for f in DOWNLOADS_DIR.glob(f"{download_id}_*")
            if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl")
        ]
        if matched:
            target = [f for f in matched if f.suffix.lower() == ".mp4"]
            file_found = target[0] if target else matched[0]
            clean_name = sanitize_filename(file_found.name[len(download_id) + 1:])
            return {
                "download_id": download_id,
                "status": "completed",
                "progress": 99.0,
                "filename": clean_name,
                "error": None
            }

    raise HTTPException(status_code=404, detail="Download job not found or expired.")


@app.get("/download/file/{download_id}")
def download_file(download_id: str):
    """
    Transfers the finished merged MP4 file to the user's browser with
    Content-Disposition attachment and correct media type.
    """
    # Sanitize download_id to prevent path traversal
    if not re.match(r"^[a-zA-Z0-9_\-]+$", download_id):
        raise HTTPException(status_code=400, detail="Invalid download ID format.")

    filepath = None
    filename = None

    with jobs_lock:
        job = download_jobs.get(download_id)
        if job:
            if job["status"] == "failed":
                raise HTTPException(status_code=400, detail=job.get("error") or "Download processing failed.")
            if job["status"] != "completed" or not job.get("filepath"):
                raise HTTPException(status_code=400, detail=f"Download is not ready yet. Current status: {job['status']}")
            filepath = Path(job["filepath"])
            filename = job.get("filename")

    # If job is not in memory (e.g. server reloaded), check disk
    if not filepath or not filepath.exists():
        matched = [
            f for f in DOWNLOADS_DIR.glob(f"{download_id}_*")
            if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl")
        ]
        mp4_matches = [f for f in matched if f.suffix.lower() == ".mp4"]
        if mp4_matches:
            filepath = mp4_matches[0]
            if not filename:
                filename = filepath.name[len(download_id) + 1:]
        elif matched:
            filepath = matched[0]
            if not filename:
                filename = filepath.name[len(download_id) + 1:]

    if not filepath or not filepath.exists():
        raise HTTPException(status_code=404, detail="The requested video file was not found or has expired.")

    # Format and sanitize filename for the browser
    clean_name = sanitize_filename(filename or filepath.name)

    # ASCII-safe fallback for older clients
    safe_ascii_name = re.sub(r'[^\w\s.-]', '_', clean_name).strip(' .')
    safe_ascii_name = re.sub(r'_+', '_', safe_ascii_name)
    if not safe_ascii_name.lower().endswith(".mp4"):
        safe_ascii_name += ".mp4"
    if safe_ascii_name == ".mp4" or not safe_ascii_name:
        safe_ascii_name = "video.mp4"

    # RFC 5987 / RFC 6266 UTF-8 encoded filename for modern browsers
    encoded_filename = urllib.parse.quote(clean_name, encoding="utf-8")
    content_disposition = f'attachment; filename="{safe_ascii_name}"; filename*=UTF-8\'\'{encoded_filename}'

    return FileResponse(
        path=str(filepath),
        media_type="video/mp4",
        headers={
            "Content-Disposition": content_disposition,
            "Access-Control-Expose-Headers": "Content-Disposition, Content-Length, Content-Type",
        }
    )


ADS_TXT_FILE = FRONTEND_DIR / "ads.txt"


@app.get("/ads.txt", response_class=FileResponse)
def get_ads_txt():
    """
    Serves the Google AdSense ads.txt verification file at the domain root
    with text/plain media type as required by search and AdSense crawlers.
    """
    if not ADS_TXT_FILE.exists():
        raise HTTPException(status_code=404, detail="ads.txt file not found.")
    return FileResponse(
        path=str(ADS_TXT_FILE),
        media_type="text/plain",
        headers={"Content-Type": "text/plain; charset=utf-8"}
    )


# Serve frontend static assets if frontend directory exists
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Video Downloader backend server on http://127.0.0.1:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
