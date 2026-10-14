"""
CliperKu - Layanan Transkripsi Suara Lokal (Faster-Whisper).
Fitur:
- Transkripsi offline 100% di laptop pengguna
- Word-level timestamps (timestamp per kata) untuk presisi pemotongan & sinkronisasi subtitle
- Deteksi GPU CUDA otomatis dengan fallback aman ke CPU (int8)
- Membaca audio langsung via format WAV 16kHz mono ke numpy array (tahan bug library)
- Model caching (hanya dimuat sekali di memori)
"""

import os
import asyncio
import wave
import ctypes
import numpy as np
from pathlib import Path
from typing import Optional, Callable, List, Tuple
from faster_whisper import WhisperModel
import ctranslate2

from app.core.config import (
    MODELS_DIR,
    DEFAULT_WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE
)
from app.schemas.video import WordTimestamp, TranscriptSegment, TranscriptionResult


class WhisperService:
    _instance = None
    _loaded_model_name: Optional[str] = None
    _model: Optional[WhisperModel] = None

    @classmethod
    def get_instance(cls) -> "WhisperService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def detect_device() -> Tuple[str, str]:
        """
        Mendeteksi ketersediaan GPU NVIDIA CUDA secara otomatis.
        Jika GPU tersedia dan cublas64_12.dll ada, gunakan cuda float16.
        Jika tidak, fallback ke CPU int8 (sangat cepat dan hemat RAM).
        """
        if WHISPER_DEVICE != "auto":
            dev = WHISPER_DEVICE
            comp = WHISPER_COMPUTE_TYPE if WHISPER_COMPUTE_TYPE != "auto" else ("float16" if dev == "cuda" else "int8")
            return dev, comp

        try:
            cuda_count = ctranslate2.get_cuda_device_count()
            if cuda_count > 0:
                # Periksa apakah pustaka CUDA 12 cublas tersedia di Windows
                if os.name == "nt":
                    handle = ctypes.windll.kernel32.LoadLibraryW("cublas64_12.dll")
                    if handle != 0:
                        return "cuda", "float16"
                else:
                    return "cuda", "float16"
        except Exception:
            pass

        return "cpu", "int8"

    def _resolve_model_path(self, model_name: str) -> str:
        """
        Mengecek apakah model sudah ada di folder lokal backend/models/<model_name>,
        atau di cache HuggingFace, atau mengembalikan nama repo model.
        """
        local_dir = MODELS_DIR / model_name
        if local_dir.exists() and (local_dir / "model.bin").exists():
            return str(local_dir)

        # Cek cache HuggingFace
        hf_cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / f"models--Systran--faster-whisper-{model_name}" / "snapshots"
        if hf_cache_dir.exists():
            snapshots = list(hf_cache_dir.glob("*"))
            if snapshots and (snapshots[0] / "model.bin").exists():
                return str(snapshots[0])

        return model_name

    def load_model(self, model_name: Optional[str] = None) -> WhisperModel:
        """
        Memuat model ke memori (lazy loading). Jika model yang diminta sudah aktif,
        gunakan instance yang ada tanpa memuat ulang.
        """
        target_model = model_name or DEFAULT_WHISPER_MODEL

        if self._model is not None and self._loaded_model_name == target_model:
            return self._model

        device, compute_type = self.detect_device()
        model_path_or_name = self._resolve_model_path(target_model)

        print(f"[WhisperService] Memuat model '{target_model}' dari '{model_path_or_name}' di perangkat: {device} ({compute_type})...")

        try:
            self._model = WhisperModel(
                model_path_or_name,
                device=device,
                compute_type=compute_type
            )
            self._loaded_model_name = target_model
            return self._model
        except Exception as e:
            print(f"[WhisperService] Gagal memuat di {device} ({e}), beralih ke fallback CPU int8...")
            self._model = WhisperModel(
                model_path_or_name,
                device="cpu",
                compute_type="int8"
            )
            self._loaded_model_name = target_model
            return self._model

    @staticmethod
    def _load_wav_as_numpy(audio_path: Path) -> np.ndarray:
        """
        Membaca file audio WAV 16kHz mono langsung menjadi numpy array float32.
        Menghindari pemanggilan PyAV av.open yang bisa mengalami bug versi.
        """
        with wave.open(str(audio_path), "rb") as w:
            n_channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            raw_frames = w.readframes(w.getnframes())

            if sampwidth == 2:
                # 16-bit PCM integer -> float32 [-1.0, 1.0]
                data = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                data = np.frombuffer(raw_frames, dtype=np.float32)

            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1)

            return data

    def transcribe_file_sync(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        model_name: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Tuple[str, float, float, List[TranscriptSegment], str]:
        """
        Eksekusi transkripsi sinkron (dijalankan di threadpool / executor).
        Mengembalikan: (bahasa, probabilitas_bahasa, durasi, list_segmen, teks_lengkap)
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"File audio tidak ditemukan: {audio_path.name}")

        model = self.load_model(model_name)

        if progress_callback:
            progress_callback(30, "Membaca audio dan menyiapkan analisis...")

        # Baca data audio langsung ke numpy array float32
        audio_array = self._load_wav_as_numpy(audio_path)

        if progress_callback:
            progress_callback(40, "Menganalisis ucapan dengan AI Whisper...")

        # faster-whisper transcribe dengan word_timestamps
        segments_gen, info = model.transcribe(
            audio_array,
            language=language if language and language != "auto" else None,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        detected_lang = info.language
        lang_prob = round(float(info.language_probability), 3)
        duration = round(float(info.duration), 2)

        collected_segments: List[TranscriptSegment] = []
        all_text_parts: List[str] = []

        total_audio_sec = max(duration, 1.0)

        for idx, seg in enumerate(segments_gen):
            words_list: List[WordTimestamp] = []
            if seg.words:
                for w in seg.words:
                    words_list.append(
                        WordTimestamp(
                            word=w.word.strip(),
                            start=round(float(w.start), 3),
                            end=round(float(w.end), 3),
                            probability=round(float(w.probability), 3)
                        )
                    )

            cleaned_text = seg.text.strip()
            all_text_parts.append(cleaned_text)

            collected_segments.append(
                TranscriptSegment(
                    id=idx + 1,
                    start=round(float(seg.start), 2),
                    end=round(float(seg.end), 2),
                    text=cleaned_text,
                    words=words_list
                )
            )

            if progress_callback:
                pct = min(int(40 + (seg.end / total_audio_sec) * 50), 92)
                progress_callback(pct, f"Mentranskrip ucapan ({seg.end:.1f}s / {duration:.1f}s)...")

        full_text = " ".join(all_text_parts)
        return detected_lang, lang_prob, duration, collected_segments, full_text


whisper_service = WhisperService.get_instance()
