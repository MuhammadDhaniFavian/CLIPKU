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
import shutil
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
import aiofiles

from app.core.config import (
    TEMP_DIR,
    OUTPUT_DIR,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
    ALLOWED_EXTENSIONS,
    DISK_RESERVE_MARGIN_GB,
    DISK_RESERVE_MARGIN_BYTES
)
from app.schemas.video import (
    VideoMetadata,
    CutRequest,
    JobInfo,
    ClipRange,
    AutoSplitRequest,
    TranscribeRequest,
    TranscriptionResult,
    CandidateStatus,
    ScoreBreakdown,
    MomentCandidate,
    AnalyzeMomentsRequest,
    UpdateCandidateRequest
)
from app.services.ffmpeg_service import FFmpegService
from app.services.job_manager import job_manager
from app.services.moment_service import MomentService


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
    disk_info = shutil.disk_usage(TEMP_DIR)
    free_disk_gb = round(disk_info.free / (1024 * 1024 * 1024), 2)
    return {
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
        "allowed_extensions": list(ALLOWED_EXTENSIONS),
        "disk_reserve_margin_gb": DISK_RESERVE_MARGIN_GB,
        "free_disk_gb": free_disk_gb
    }


@router.post("/upload")
async def upload_video(request: Request, file: UploadFile = File(...)):
    """
    Streaming upload video ke disk per potongan 1MB.
    Memeriksa:
    1. Ekstensi file
    2. Batas ukuran maksimal file (2 GB)
    3. Sisa ruang disk (harus cukup untuk ukuran file + cadangan 5 GB)
    """
    orig_name = file.filename or "video.mp4"
    ext = Path(orig_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format file '{ext}' tidak didukung. Harap gunakan: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 1. Estimasi ukuran file dari header atau objek file jika tersedia
    content_length_header = request.headers.get("content-length")
    header_size = 0
    if content_length_header:
        try:
            header_size = int(content_length_header)
        except ValueError:
            header_size = 0

    file_obj_size = getattr(file, "size", None) or 0
    estimated_size = max(header_size, file_obj_size)

    max_gb_display = f"{MAX_UPLOAD_SIZE_MB // 1024} GB" if MAX_UPLOAD_SIZE_MB >= 1024 else f"{MAX_UPLOAD_SIZE_MB} MB"

    if estimated_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Ukuran file melebihi batas maksimal ({max_gb_display})"
        )

    # 2. Pemeriksaan sisa ruang disk di drive proyek
    free_disk_bytes = shutil.disk_usage(TEMP_DIR).free
    required_disk_bytes = estimated_size + DISK_RESERVE_MARGIN_BYTES

    if free_disk_bytes < required_disk_bytes:
        free_gb = free_disk_bytes / (1024 ** 3)
        req_gb = required_disk_bytes / (1024 ** 3)
        file_gb = estimated_size / (1024 ** 3)
        raise HTTPException(
            status_code=507,
            detail=(
                f"Sisa ruang disk di drive proyek tidak mencukupi. "
                f"Tersisa {free_gb:.2f} GB, dibutuhkan minimal {req_gb:.2f} GB "
                f"({file_gb:.2f} GB ukuran file + {DISK_RESERVE_MARGIN_GB:.1f} GB cadangan sistem)."
            )
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
                        detail=f"Ukuran file melebihi batas maksimal ({max_gb_display})"
                    )

                # Periksa sisa ruang disk selama penulisan file
                current_free = shutil.disk_usage(TEMP_DIR).free
                if current_free < DISK_RESERVE_MARGIN_BYTES:
                    if target_path.exists():
                        target_path.unlink()
                    raise HTTPException(
                        status_code=507,
                        detail=(
                            f"Ruang penyimpanan disk hampir penuh saat proses upload. "
                            f"Sisa ruang disk kurang dari cadangan minimum {DISK_RESERVE_MARGIN_GB:.1f} GB."
                        )
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


@router.post("/video/{video_id}/transcribe")
async def start_transcription(video_id: str, req: Optional[TranscribeRequest] = None):
    """
    Mendaftarkan job transkripsi ucapan lokal (Faster-Whisper) ke antrean background job.
    """
    video_path = get_safe_video_path(video_id)
    language = req.language if req else None
    model_size = req.model_size if req else None

    job_id = job_manager.create_job()

    asyncio.create_task(
        job_manager.run_transcribe_job(
            job_id=job_id,
            video_id=video_id,
            video_path=video_path,
            language=language,
            model_name=model_size
        )
    )

    return {
        "job_id": job_id,
        "message": "Job transkripsi AI Whisper berhasil didaftarkan"
    }


@router.get("/video/{video_id}/transcript", response_model=TranscriptionResult)
async def get_video_transcript(video_id: str):
    """
    Mengambil hasil transkripsi ucapan (kalimat dan kata dengan timestamp)
    yang tersimpan dari video.
    """
    transcript_file = TEMP_DIR / f"{video_id}_transcript.json"
    if not transcript_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Transkrip belum tersedia untuk video ini. Jalankan proses transkripsi terlebih dahulu."
        )

    import json
    with open(transcript_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return TranscriptionResult(**data)


@router.get("/video/{video_id}/stream")
async def stream_source_video(video_id: str):
    """
    Streaming video asli yang diunggah untuk pemutar video di browser.
    Mendukung header Accept-Ranges untuk seeking lancar.
    """
    video_path = get_safe_video_path(video_id)
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=video_path.name,
        headers={"Accept-Ranges": "bytes"}
    )


@router.post("/video/{video_id}/analyze-moments", response_model=list[MomentCandidate])
async def analyze_video_moments(video_id: str, req: Optional[AnalyzeMomentsRequest] = None):
    """
    Menganalisis hasil transkripsi ucapan dan menilai kandidat momen terbaik (skor 0-100).
    Menghasilkan rekomendasi klip berkonteks lengkap dengan hook, bobot nilai, dan alasan.
    """
    transcript_file = TEMP_DIR / f"{video_id}_transcript.json"
    if not transcript_file.exists():
        raise HTTPException(
            status_code=400,
            detail="Transkrip ucapan belum tersedia. Harap jalankan proses transkripsi terlebih dahulu."
        )

    import json
    with open(transcript_file, "r", encoding="utf-8") as f:
        trans_data = json.load(f)

    transcription = TranscriptionResult(**trans_data)

    min_dur = req.min_duration if req else 15
    max_dur = req.max_duration if req else 60
    target_clips = req.target_clips if req else 5

    candidates = MomentService.generate_candidates(
        transcription=transcription,
        min_duration=min_dur,
        max_duration=max_dur,
        target_clips=target_clips
    )

    # Simpan kandidat momen ke cache file lokal
    moments_cache_file = TEMP_DIR / f"{video_id}_moments.json"
    with open(moments_cache_file, "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in candidates], f, indent=2)

    return candidates


@router.get("/video/{video_id}/moments", response_model=list[MomentCandidate])
async def get_video_moments(video_id: str):
    """
    Mengambil daftar kandidat momen yang telah dinilai dan tersimpan untuk video ini.
    """
    moments_cache_file = TEMP_DIR / f"{video_id}_moments.json"
    if not moments_cache_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Analisis momen belum dilakukan untuk video ini."
        )

    import json
    with open(moments_cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [MomentCandidate(**item) for item in data]


@router.patch("/video/{video_id}/moments/{moment_id}", response_model=MomentCandidate)
async def update_moment_candidate(
    video_id: str,
    moment_id: str,
    req: UpdateCandidateRequest
):
    """
    Memperbarui kurasi kandidat momen (status diterima/ditolak, atau edit durasi/judul).
    """
    moments_cache_file = TEMP_DIR / f"{video_id}_moments.json"
    if not moments_cache_file.exists():
        raise HTTPException(status_code=404, detail="File kandidat momen tidak ditemukan.")

    import json
    with open(moments_cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    found_idx = None
    for idx, item in enumerate(data):
        if item.get("id") == moment_id:
            found_idx = idx
            break

    if found_idx is None:
        raise HTTPException(status_code=404, detail=f"Kandidat momen ID '{moment_id}' tidak ditemukan.")

    # Update atribut
    candidate = data[found_idx]
    if req.status is not None:
        candidate["status"] = req.status.value
    if req.start is not None:
        candidate["start"] = req.start
    if req.end is not None:
        candidate["end"] = req.end
    if req.judul is not None:
        candidate["judul"] = req.judul

    # Recalculate duration if start or end changed
    candidate["duration"] = round(candidate["end"] - candidate["start"], 2)

    data[found_idx] = candidate

    with open(moments_cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return MomentCandidate(**candidate)



