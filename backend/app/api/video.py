"""
CliperKu - Router API Video & Job Pemotongan.
Keamanan:
- Validasi ekstensi dan tipe file
- Streaming upload chunk-by-chunk untuk efisiensi RAM
- Batas ukuran file 500 MB (dapat diubah via config)
- Mencegah arbitrary path traversal (hanya file di dalam TEMP_DIR yang diproses)
"""

import asyncio
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import aiofiles

from app.core.config import (
    TEMP_DIR,
    OUTPUT_DIR,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
    ALLOWED_EXTENSIONS
)
from app.schemas.video import (
    VideoMetadata,
    CutRequest,
    JobInfo,
    ClipRange,
    AutoSplitRequest
)
from app.services.ffmpeg_service import FFmpegService
from app.services.job_manager import job_manager

router = APIRouter(prefix="/api", tags=["video"])

UPLOADS_DIR = TEMP_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get_safe_video_path(video_id: str) -> Path:
    """Mencegah path traversal dengan memastikan file berada di dalam UPLOADS_DIR."""
    # Pastikan video_id hanya karakter alfanumerik / dash
    safe_id = Path(video_id).name
    # Cari file yang diawali safe_id
    matches = list(UPLOADS_DIR.glob(f"{safe_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Video tidak ditemukan atau telah kedaluwarsa")
    return matches[0]


@router.get("/config")
def get_public_config():
    """Mengembalikan konfigurasi publik untuk ditampilkan di UI."""
    return {
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
        "allowed_extensions": list(ALLOWED_EXTENSIONS),
    }


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """
    Streaming upload video ke disk per potongan 1MB.
    Memastikan penggunaan RAM tetap sangat kecil walau ukuran file hingga 500 MB.
    """
    orig_name = file.filename or "video.mp4"
    ext = Path(orig_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format file '{ext}' tidak didukung. Harap gunakan: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    video_id = str(uuid.uuid4())[:8]
    target_path = UPLOADS_DIR / f"{video_id}{ext}"

    total_bytes = 0
    chunk_size = 1024 * 1024  # 1 MB per chunk

    try:
        async with aiofiles.open(target_path, "wb") as out_file:
            while chunk := await file.read(chunk_size):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                    # Hapus file yang melebihi batas
                    if target_path.exists():
                        target_path.unlink()
                    raise HTTPException(
                        status_code=413,
                        detail=f"Ukuran file melebihi batas maksimal ({MAX_UPLOAD_SIZE_MB} MB)"
                    )
                await out_file.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan video: {str(e)}")

    # Baca metadata via ffprobe
    try:
        metadata = await FFmpegService.get_metadata(target_path)
    except Exception as e:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(status_code=400, detail=f"File video korup atau tidak dapat dibaca: {str(e)}")

    return {
        "video_id": video_id,
        "filename": orig_name,
        "metadata": metadata
    }


@router.get("/video/{video_id}/metadata", response_model=VideoMetadata)
async def get_video_metadata(video_id: str):
    """Membaca metadata dari video yang sudah diunggah."""
    video_path = get_safe_video_path(video_id)
    return await FFmpegService.get_metadata(video_path)


@router.post("/video/{video_id}/auto-split")
async def generate_auto_splits(video_id: str, request: AutoSplitRequest):
    """
    Membantu pengguna membagi video panjang secara otomatis
    berdasarkan durasi klip tertentu (misal: 30, 45, 60 detik).
    """
    video_path = get_safe_video_path(video_id)
    metadata = await FFmpegService.get_metadata(video_path)
    total_dur = metadata.duration_seconds

    splits: list[ClipRange] = []
    current_start = 0.0
    clip_dur = float(request.clip_duration)
    clip_idx = 1

    while current_start < total_dur:
        current_end = min(current_start + clip_dur, total_dur)
        # Jika sisa durasi terakhir terlalu pendek (< 5 detik) dan sudah ada klip sebelumnya
        if (current_end - current_start) < 5 and len(splits) > 0:
            # Perpanjang klip terakhir
            splits[-1].end = current_end
            break
        splits.append(
            ClipRange(
                start=round(current_start, 2),
                end=round(current_end, 2),
                title=f"Klip {clip_idx} ({int(current_start)}s - {int(current_end)}s)"
            )
        )
        current_start += clip_dur
        clip_idx += 1

    return {"video_id": video_id, "clips": splits}


@router.post("/clips/cut")
async def request_cut(req: CutRequest):
    """
    Mendaftarkan permintaan pemotongan video ke antrean job latar belakang.
    """
    video_path = get_safe_video_path(req.video_id)
    metadata = await FFmpegService.get_metadata(video_path)

    # Validasi timestamp terhadap durasi video
    for c in req.clips:
        if c.end > metadata.duration_seconds + 0.5:
            raise HTTPException(
                status_code=400,
                detail=f"Titik akhir klip ({c.end}s) melebihi durasi video ({metadata.duration_seconds}s)"
            )

    job_id = job_manager.create_job()

    # Jalankan proses di background async task
    asyncio.create_task(
        job_manager.run_cut_job(
            job_id=job_id,
            input_path=video_path,
            clips=req.clips
        )
    )

    return {"job_id": job_id, "message": "Job pemotongan berhasil didaftarkan"}


@router.get("/jobs/{job_id}", response_model=JobInfo)
async def get_job_status(job_id: str):
    """Polling status dan progress job pemotongan (0 - 100%)."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Membatalkan job yang sedang antri atau berjalan."""
    success = await job_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Job tidak dapat dibatalkan (sudah selesai atau tidak ditemukan)"
        )
    return {"message": "Job berhasil dibatalkan dan file sementara dibersihkan"}


@router.get("/clips/{clip_filename}")
async def get_clip_file(clip_filename: str):
    """
    Menyediakan file video MP4 hasil pemotongan untuk preview dan unduh.
    Aman dari directory traversal.
    """
    safe_filename = Path(clip_filename).name
    clip_path = OUTPUT_DIR / safe_filename

    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="File klip tidak ditemukan")

    return FileResponse(
        path=clip_path,
        media_type="video/mp4",
        filename=safe_filename,
        headers={"Accept-Ranges": "bytes"}
    )

