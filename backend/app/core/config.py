"""
CliperKu - Konfigurasi aplikasi.
Semua pengaturan yang bisa diubah ada di sini.
"""

import os
from pathlib import Path

# === Path Proyek ===
# config.py berada di backend/app/core/
APP_DIR = Path(__file__).resolve().parent.parent  # backend/app
BACKEND_DIR = APP_DIR.parent                     # backend/
WORKSPACE_DIR = BACKEND_DIR.parent               # d:\FAVIAN\project clip

TEMP_DIR = BACKEND_DIR / "temp"
OUTPUT_DIR = BACKEND_DIR / "output"

# Buat folder jika belum ada
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# === FFmpeg & FFprobe ===
# Cari di folder tools lokal terlebih dahulu, lalu fallback ke PATH sistem
LOCAL_FFMPEG = WORKSPACE_DIR / "tools" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg.exe"
LOCAL_FFPROBE = WORKSPACE_DIR / "tools" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffprobe.exe"

import shutil
FFMPEG_PATH = LOCAL_FFMPEG if LOCAL_FFMPEG.exists() else Path(shutil.which("ffmpeg") or "ffmpeg")
FFPROBE_PATH = LOCAL_FFPROBE if LOCAL_FFPROBE.exists() else Path(shutil.which("ffprobe") or "ffprobe")

# === Batas Upload ===
# Batas ukuran file video dalam bytes (default: 2 GB / 2048 MB)
MAX_UPLOAD_SIZE_MB = 2048
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Cadangan ruang disk minimum (dalam GB dan Bytes)
DISK_RESERVE_MARGIN_GB = 5.0
DISK_RESERVE_MARGIN_BYTES = int(DISK_RESERVE_MARGIN_GB * 1024 * 1024 * 1024)

# === Format Video yang Diterima ===
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# === Server ===
HOST = "127.0.0.1"
PORT = 8000
FRONTEND_URL = "http://localhost:5173"

# === Pemotongan Video ===
# Durasi default klip dalam detik
DEFAULT_CLIP_DURATIONS = [30, 45, 60]
MIN_CLIP_DURATION = 5
MAX_CLIP_DURATION = 300  # 5 menit

# === Job Queue ===
# Hanya 1 job berat berjalan pada satu waktu
MAX_CONCURRENT_JOBS = 1

# === AI Whisper Transkripsi Lokal ===
MODELS_DIR = BACKEND_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Ukuran model default: "tiny" untuk uji coba cepat, "base" atau "small" untuk akurasi tinggi
DEFAULT_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # auto / cuda / cpu
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "auto")  # auto / float16 / int8

