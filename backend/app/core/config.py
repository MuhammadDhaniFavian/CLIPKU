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
# Batas ukuran file video dalam bytes (default: 500 MB)
# Mudah diubah di sini tanpa mengubah kode lain.
MAX_UPLOAD_SIZE_MB = 500
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

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

