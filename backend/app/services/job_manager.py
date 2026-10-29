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
import json
from app.core.config import TEMP_DIR, OUTPUT_DIR
from app.schemas.video import JobStatus, JobInfo, ClipRange, ClipInfo, TranscriptionResult
from app.services.ffmpeg_service import FFmpegService
from app.services.whisper_service import whisper_service
from app.services.subtitle_service import SubtitleService



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

    async def run_cut_job(
        self,
        job_id: str,
        input_path: Path,
        clips: List[ClipRange],
        video_id: Optional[str] = None,
        vertical_mode: str = "none",
        burn_subtitles: bool = True,
        subtitle_style: str = "tiktok_yellow"
    ):
        """
        Menjalankan proses pemotongan dalam antrean terkontrol (1 job berat per waktu).
        Mendukung konversi format vertikal 9:16 dan burn-in subtitle ASS secara sinkron.
        """
        job = self.jobs.get(job_id)
        if not job:
            return

        async with self.lock:
            if job.status == JobStatus.CANCELLED:
                return

            job.status = JobStatus.RUNNING
            job.message = "Mempersiapkan pemrosesan video..."
            job.progress = 5

            # Muat transkrip jika burn_subtitles aktif
            transcript_segments = []
            v_id = video_id or input_path.stem
            transcript_file = TEMP_DIR / f"{v_id}_transcript.json"

            if burn_subtitles and subtitle_style != "none" and transcript_file.exists():
                try:
                    with open(transcript_file, "r", encoding="utf-8") as f:
                        t_data = json.load(f)
                    t_res = TranscriptionResult(**t_data)
                    transcript_segments = t_res.segments
                except Exception as e:
                    print(f"[JobManager] Gagal membaca file transkrip: {e}")

            output_clips: List[ClipInfo] = []
            total_clips = len(clips)
            is_vertical = (vertical_mode in ["blur", "crop"])
            is_square = (vertical_mode == "square")

            try:
                for idx, clip in enumerate(clips):
                    if job.status == JobStatus.CANCELLED:
                        break

                    clip_num = idx + 1
                    status_text = f"Memproses klip {clip_num} dari {total_clips}"
                    if is_vertical:
                        status_text += " [9:16 Vertikal]"
                    elif is_square:
                        status_text += " [1:1 Kotak]"
                    if burn_subtitles and subtitle_style != "none":
                        status_text += " [Burn-in Subtitle]"
                    job.message = f"{status_text} ({clip.start:.1f}s - {clip.end:.1f}s)..."

                    clean_name = input_path.stem
                    if is_vertical:
                        suffix = "_9x16"
                    elif is_square:
                        suffix = "_1x1"
                    else:
                        suffix = ""
                    clip_filename = f"{clean_name}_clip_{clip_num}_{int(clip.start)}s_{int(clip.end)}s{suffix}.mp4"
                    output_path = OUTPUT_DIR / clip_filename
                    self.created_files[job_id].append(output_path)

                    # Buat subtitle ASS dan SRT jika diaktifkan
                    ass_path: Optional[Path] = None
                    srt_filename: Optional[str] = None

                    if burn_subtitles and subtitle_style != "none":
                        ass_content, srt_content = SubtitleService.generate_subtitles_for_clip(
                            segments=transcript_segments,
                            clip_start=clip.start,
                            clip_end=clip.end,
                            style=subtitle_style,
                            is_vertical=is_vertical,
                            custom_text=clip.custom_subtitle,
                            is_square=is_square
                        )

                        # Tulis ASS hanya jika ada konten subtitle (ada kata terdeteksi)
                        if ass_content and srt_content:
                            ass_path = TEMP_DIR / f"{clean_name}_clip_{clip_num}.ass"
                            with open(ass_path, "w", encoding="utf-8") as f:
                                f.write(ass_content)
                            self.created_files[job_id].append(ass_path)

                            srt_filename = f"{clean_name}_clip_{clip_num}_{int(clip.start)}s_{int(clip.end)}s{suffix}.srt"
                            srt_path = OUTPUT_DIR / srt_filename
                            with open(srt_path, "w", encoding="utf-8") as f:
                                f.write(srt_content)
                            self.created_files[job_id].append(srt_path)

                    def register_proc(p):
                        self.active_processes[job_id] = p

                    # Eksekusi pemotongan akurat dengan vertical mode & subtitle
                    await FFmpegService.cut_clip_accurate(
                        input_path=input_path,
                        output_path=output_path,
                        start_sec=clip.start,
                        end_sec=clip.end,
                        vertical_mode=vertical_mode,
                        ass_subtitle_path=ass_path,
                        register_process=register_proc
                    )

                    self.active_processes.pop(job_id, None)

                    # Bersihkan file ASS sementara setelah render selesai
                    if ass_path and ass_path.exists():
                        try:
                            ass_path.unlink()
                        except Exception:
                            pass

                    if job.status == JobStatus.CANCELLED:
                        self._cleanup_job_files(job_id)
                        return

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
                            file_size_mb=size_mb,
                            is_vertical=is_vertical,
                            format_mode=vertical_mode,
                            has_subtitles=(ass_path is not None),
                            srt_filename=srt_filename
                        )
                    )

                    progress_pct = int(5 + ((idx + 1) / total_clips) * 90)
                    job.progress = min(progress_pct, 95)

                if job.status != JobStatus.CANCELLED:
                    job.status = JobStatus.COMPLETED
                    job.progress = 100
                    job.message = f"Berhasil memproses {len(output_clips)} klip!"
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

