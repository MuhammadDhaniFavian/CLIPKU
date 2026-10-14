"""
CliperKu - Pengelola Job Latar Belakang (Job Manager).
Fitur:
- Status job: queued, running, completed, failed, cancelled
- Hanya 1 job berat berjalan pada satu waktu (menggunakan asyncio.Lock)
- Mendukung pembatalan seketika (menghentikan proses FFmpeg yang aktif)
- Pembersihan file sementara secara otomatis saat job selesai, gagal, atau dibatalkan
"""

import asyncio
import os
import uuid
from pathlib import Path
from typing import Dict, Optional, List
from app.core.config import TEMP_DIR, OUTPUT_DIR
from app.schemas.video import JobStatus, JobInfo, ClipRange, ClipInfo, TranscriptionResult
from app.services.ffmpeg_service import FFmpegService
from app.services.whisper_service import whisper_service


class JobManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(JobManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.jobs: Dict[str, JobInfo] = {}
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.created_files: Dict[str, List[Path]] = {}
        self.lock = asyncio.Lock()

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())[:8]
        self.jobs[job_id] = JobInfo(
            job_id=job_id,
            status=JobStatus.QUEUED,
            progress=0,
            message="Menunggu antrean pemrosesan..."
        )
        self.created_files[job_id] = []
        return job_id

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        return self.jobs.get(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            return False

        job.status = JobStatus.CANCELLED
        job.message = "Proses dibatalkan oleh pengguna."

        # Matikan proses FFmpeg yang sedang berjalan jika ada
        proc = self.active_processes.get(job_id)
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
            self.active_processes.pop(job_id, None)

        # Bersihkan file parsial yang belum selesai dibuat job ini
        self._cleanup_job_files(job_id)
        return True

    def _cleanup_job_files(self, job_id: str):
        """Menghapus file yang terdaftar pada job yang dibatalkan/gagal."""
        file_list = self.created_files.get(job_id, [])
        for file_path in file_list:
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                pass

    async def run_cut_job(self, job_id: str, input_path: Path, clips: List[ClipRange]):
        """
        Menjalankan proses pemotongan dalam antrean terkontrol (1 job berat per waktu).
        """
        job = self.jobs.get(job_id)
        if not job:
            return

        async with self.lock:
            # Jika sebelum giliran jalan pengguna sudah membatalkan
            if job.status == JobStatus.CANCELLED:
                return

            job.status = JobStatus.RUNNING
            job.message = "Memulai pemotongan video..."
            job.progress = 5

            output_clips: List[ClipInfo] = []
            total_clips = len(clips)

            try:
                for idx, clip in enumerate(clips):
                    if job.status == JobStatus.CANCELLED:
                        break

                    clip_num = idx + 1
                    job.message = f"Memotong klip {clip_num} dari {total_clips} ({clip.start:.1f}s - {clip.end:.1f}s)..."

                    # Nama file klip terstandar
                    clean_name = input_path.stem
                    clip_filename = f"{clean_name}_clip_{clip_num}_{int(clip.start)}s_{int(clip.end)}s.mp4"
                    output_path = OUTPUT_DIR / clip_filename
                    self.created_files[job_id].append(output_path)

                    def register_proc(p):
                        self.active_processes[job_id] = p

                    # Eksekusi pemotongan akurat
                    await FFmpegService.cut_clip_accurate(
                        input_path=input_path,
                        output_path=output_path,
                        start_sec=clip.start,
                        end_sec=clip.end,
                        register_process=register_proc
                    )

                    # Lepas referensi proses yang sudah selesai
                    self.active_processes.pop(job_id, None)

                    if job.status == JobStatus.CANCELLED:
                        self._cleanup_job_files(job_id)
                        return

                    # Hitung ukuran file hasil
                    size_mb = round(output_path.stat().st_size / (1024 * 1024), 2)
                    duration = round(clip.end - clip.start, 2)
                    title = clip.title or f"Klip {clip_num}"

                    output_clips.append(
                        ClipInfo(
                            filename=clip_filename,
                            title=title,
                            start=clip.start,
                            end=clip.end,
                            duration=duration,
                            file_size_mb=size_mb
                        )
                    )

                    # Update progress bar
                    progress_pct = int(5 + ((idx + 1) / total_clips) * 90)
                    job.progress = min(progress_pct, 95)

                if job.status != JobStatus.CANCELLED:
                    job.status = JobStatus.COMPLETED
                    job.progress = 100
                    job.message = f"Berhasil memotong {len(output_clips)} klip!"
                    job.result = output_clips

            except Exception as e:
                if job.status != JobStatus.CANCELLED:
                    job.status = JobStatus.FAILED
                    job.error = str(e)
                    job.message = f"Gagal memproses klip: {str(e)}"
                    self._cleanup_job_files(job_id)
            finally:
                self.active_processes.pop(job_id, None)

    async def run_transcribe_job(
        self,
        job_id: str,
        video_id: str,
        video_path: Path,
        language: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        """
        Menjalankan proses transkripsi AI Whisper lokal di antrean job.
        1. Ekstraksi audio 16kHz mono WAV dari video via FFmpeg
        2. Analisis ucapan dan timestamp per kata via Faster-Whisper
        3. Simpan hasil transkripsi ke JSON lokal untuk caching
        4. Pembersihan otomatis file WAV sementara
        """
        job = self.jobs.get(job_id)
        if not job:
            return

        async with self.lock:
            if job.status == JobStatus.CANCELLED:
                return

            job.status = JobStatus.RUNNING
            job.message = "Mengekstrak audio 16kHz dari video..."
            job.progress = 5

            # File audio sementara untuk Whisper
            temp_audio_path = TEMP_DIR / f"{video_id}_audio_16k.wav"
            self.created_files[job_id].append(temp_audio_path)

            try:
                def register_proc(p):
                    self.active_processes[job_id] = p

                # 1. Ekstrak audio via FFmpeg
                await FFmpegService.extract_audio_for_whisper(
                    video_path=video_path,
                    output_audio_path=temp_audio_path,
                    register_process=register_proc
                )

                self.active_processes.pop(job_id, None)

                if job.status == JobStatus.CANCELLED:
                    self._cleanup_job_files(job_id)
                    return

                job.progress = 25
                job.message = "Memuat model AI Whisper dan menganalisis ucapan..."

                # 2. Jalankan transkripsi di thread terpisah (karena Faster-Whisper CPU/GPU sync)
                loop = asyncio.get_running_loop()

                def progress_cb(pct: int, msg: str):
                    if job.status != JobStatus.CANCELLED:
                        job.progress = pct
                        job.message = msg

                detected_lang, lang_prob, duration, segments, full_text = await loop.run_in_executor(
                    None,
                    lambda: whisper_service.transcribe_file_sync(
                        audio_path=temp_audio_path,
                        language=language,
                        model_name=model_name,
                        progress_callback=progress_cb
                    )
                )

                if job.status == JobStatus.CANCELLED:
                    self._cleanup_job_files(job_id)
                    return

                # 3. Bentuk hasil transkripsi
                result = TranscriptionResult(
                    video_id=video_id,
                    language=detected_lang,
                    language_probability=lang_prob,
                    duration=duration,
                    segments=segments,
                    full_text=full_text
                )

                # Simpan metadata transkrip ke JSON file (untuk cache dan endpoint transcript)
                transcript_cache_file = TEMP_DIR / f"{video_id}_transcript.json"
                import json
                with open(transcript_cache_file, "w", encoding="utf-8") as f:
                    f.write(result.model_dump_json(indent=2))

                # 4. Hapus audio WAV sementara (hemat ruang disk)
                if temp_audio_path.exists():
                    temp_audio_path.unlink()

                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.transcription = result
                job.message = f"Transkripsi selesai! Terdeteksi: '{detected_lang.upper()}' ({len(segments)} segmen ucapan)"

            except Exception as e:
                if job.status != JobStatus.CANCELLED:
                    job.status = JobStatus.FAILED
                    job.error = str(e)
                    job.message = f"Gagal mentranskripsi video: {str(e)}"
                    self._cleanup_job_files(job_id)
            finally:
                self.active_processes.pop(job_id, None)
                # Pastikan file audio WAV dihapus
                if temp_audio_path.exists():
                    try:
                        temp_audio_path.unlink()
                    except Exception:
                        pass


# Singleton job manager instance

job_manager = JobManager()

