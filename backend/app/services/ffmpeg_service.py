"""
CliperKu - Layanan FFmpeg dan FFprobe.
Bertanggung jawab untuk membaca metadata video dan memotong klip secara akurat.
Keamanan: Seluruh perintah dieksekusi dengan daftar argumen (tanpa shell string).
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Callable, Awaitable
from app.core.config import FFMPEG_PATH, FFPROBE_PATH
from app.schemas.video import VideoMetadata, ClipInfo


class FFmpegService:
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Mengubah detik menjadi format MM:SS atau HH:MM:SS."""
        total_sec = int(seconds)
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        secs = total_sec % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @classmethod
    async def get_metadata(cls, video_path: Path) -> VideoMetadata:
        """
        Membaca metadata video menggunakan FFprobe secara asynchronous.
        Aman dari injection karena menggunakan list argumen.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"File video tidak ditemukan: {video_path.name}")

        cmd = [
            str(FFPROBE_PATH),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"FFprobe gagal: {stderr.decode(errors='replace')}")

        data = json.loads(stdout.decode(errors='replace'))
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        # Cari stream video dan audio utama
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            raise ValueError("File tidak memiliki stream video yang valid")

        duration_sec = float(fmt.get("duration") or video_stream.get("duration") or 0.0)
        file_size_bytes = int(fmt.get("size") or video_path.stat().st_size)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        # Hitung fps
        fps = 30.0
        r_frame_rate = video_stream.get("r_frame_rate", "30/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            if float(den) > 0:
                fps = round(float(num) / float(den), 2)

        return VideoMetadata(
            filename=video_path.name,
            file_size_mb=file_size_mb,
            duration_seconds=round(duration_sec, 2),
            duration_display=cls._format_duration(duration_sec),
            width=int(video_stream.get("width", 0)),
            height=int(video_stream.get("height", 0)),
            fps=fps,
            codec=video_stream.get("codec_name", "unknown"),
            audio_codec=audio_stream.get("codec_name") if audio_stream else None
        )

    @classmethod
    async def cut_clip_accurate(
        cls,
        input_path: Path,
        output_path: Path,
        start_sec: float,
        end_sec: float,
        register_process: Optional[Callable[[asyncio.subprocess.Process], None]] = None
    ) -> None:
        """
        Memotong video secara akurat pada titik waktu frame yang tepat.
        
        Mengapa re-encode (bukan -c copy)?
        Stream copy (-c copy) hanya dapat memotong pada keyframe (I-frame) terdekat.
        Jika pengguna ingin memotong di detik 12.5 dan keyframe terdekat di detik 10.0,
        hasil klip akan meleset hingga 2.5 detik atau gambar mengalami freeze/desync.
        
        Dengan re-encode libx264 preset veryfast dan CRF 22, FFmpeg merender ulang
        frame secara presisi frame-by-frame dengan kecepatan sangat tinggi dan
        kualitas visual tetap terjaga.
        """
        duration = end_sec - start_sec
        if duration <= 0:
            raise ValueError("Durasi klip harus lebih besar dari 0 detik")

        # Argumen aman dalam bentuk list
        # -ss sebelum -i dan -t durasi menghasilkan pencarian cepat sekaligus decode akurat
        cmd = [
            str(FFMPEG_PATH),
            "-y",                        # Overwrite output jika ada
            "-ss", f"{start_sec:.3f}",   # Posisi mulai presisi milidetik
            "-t", f"{duration:.3f}",     # Durasi klip
            "-i", str(input_path),       # File input
            "-c:v", "libx264",           # Re-encode H.264
            "-preset", "veryfast",       # Cepat dan hemat CPU
            "-crf", "22",                # Kualitas visual seimbang
            "-c:a", "aac",               # Audio AAC kompatibel luas
            "-b:a", "192k",              # Bitrate audio jernih
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",   # Memungkinkan video langsung di-stream di browser
            str(output_path)
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        if register_process:
            register_process(proc)

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace")
            raise RuntimeError(f"FFmpeg gagal memotong klip: {err_msg}")

