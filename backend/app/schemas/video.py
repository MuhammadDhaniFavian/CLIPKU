"""
CliperKu - Skema data (Pydantic models).
Mendefinisikan bentuk data yang masuk dan keluar dari API.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    """Status sebuah job pemrosesan."""
    QUEUED = "queued"          # antri
    RUNNING = "running"        # berjalan
    COMPLETED = "completed"    # selesai
    FAILED = "failed"          # gagal
    CANCELLED = "cancelled"    # dibatalkan


class VideoMetadata(BaseModel):
    """Metadata dari video yang diunggah."""
    filename: str
    file_size_mb: float
    duration_seconds: float
    duration_display: str  # format "MM:SS"
    width: int
    height: int
    fps: float
    codec: str
    audio_codec: Optional[str] = None


class VerticalMode(str, Enum):
    """Mode konversi rasio aspek video."""
    BLUR = "blur"      # 1080x1920 (9:16) dengan latar belakang blur (TikTok / Reels / Shorts)
    CROP = "crop"      # 1080x1920 (9:16) dengan crop tengah
    SQUARE = "square"  # 1080x1080 (1:1) dengan latar belakang blur (Instagram Feed)
    NONE = "none"      # Mempertahankan rasio aspek asli (Lanskap / YouTube)


class SubtitleStyle(str, Enum):
    """Gaya tampilan subtitle burn-in."""
    TIKTOK_YELLOW = "tiktok_yellow"  # Kuning cerah dengan outline hitam tebal
    CLEAN_WHITE = "clean_white"      # Putih bersih dengan outline hitam
    NONE = "none"                    # Tanpa burn-in subtitle


class ClipRange(BaseModel):
    """Rentang waktu untuk satu klip."""
    start: float = Field(ge=0, description="Detik mulai")
    end: float = Field(gt=0, description="Detik selesai")
    title: Optional[str] = None
    custom_subtitle: Optional[str] = None

    @field_validator("end")
    @classmethod
    def end_must_be_after_start(cls, v, info):
        if "start" in info.data and v <= info.data["start"]:
            raise ValueError("'end' harus lebih besar dari 'start'")
        return v


class CutRequest(BaseModel):
    """Permintaan pemotongan video menjadi klip-klip."""
    video_id: str
    clips: list[ClipRange] = Field(min_length=1, max_length=20)
    vertical_mode: VerticalMode = VerticalMode.BLUR
    burn_subtitles: bool = True
    subtitle_style: SubtitleStyle = SubtitleStyle.TIKTOK_YELLOW


class ClipInfo(BaseModel):
    """Informasi satu klip yang sudah dipotong."""
    filename: str
    title: str
    start: float
    end: float
    duration: float
    file_size_mb: float
    is_vertical: bool = False
    format_mode: str = "none"
    has_subtitles: bool = False
    srt_filename: Optional[str] = None



class WordTimestamp(BaseModel):
    """Timestamp tingkat kata untuk presisi tinggi & subtitle sinkron."""
    word: str
    start: float
    end: float
    probability: float = 1.0


class TranscriptSegment(BaseModel):
    """Satu potongan kalimat ucapan dalam transkripsi."""
    id: int
    start: float
    end: float
    text: str
    words: list[WordTimestamp] = []


class TranscriptionResult(BaseModel):
    """Hasil transkripsi lengkap dari video."""
    video_id: str
    language: str
    language_probability: float
    duration: float
    segments: list[TranscriptSegment]
    full_text: str


class TranscribeRequest(BaseModel):
    """Permintaan transkripsi suara video menggunakan AI Whisper."""
    video_id: str
    language: Optional[str] = None  # None = auto-detect, "id", "en", dsb.
    model_size: Optional[str] = None  # None = default config, "tiny", "base", "small"


class JobInfo(BaseModel):
    """Informasi status sebuah job."""
    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100, default=0)
    message: str = ""
    result: Optional[list[ClipInfo]] = None
    transcription: Optional[TranscriptionResult] = None
    error: Optional[str] = None


class AutoSplitRequest(BaseModel):
    """Permintaan pembagian otomatis berdasarkan durasi."""
    video_id: str
    clip_duration: int = Field(default=30, ge=5, le=300)


class CandidateStatus(str, Enum):
    """Status kurasi kandidat klip oleh pengguna."""
    MENUNGGU = "menunggu"
    DITERIMA = "diterima"
    DITOLAK = "ditolak"


class ScoreBreakdown(BaseModel):
    """Rincian perolehan poin penilaian (total 0-100)."""
    hook_score: int = Field(ge=0, le=20, description="Daya tarik awal / hook (0-20)")
    context_score: int = Field(ge=0, le=25, description="Kelengkapan struktur awal-isi-akhir (0-25)")
    value_score: int = Field(ge=0, le=20, description="Nilai informasi, cerita, atau pertanyaan (0-20)")
    clarity_score: int = Field(ge=0, le=10, description="Kejelasan ucapan / confidence (0-10)")
    duration_score: int = Field(ge=0, le=10, description="Kesesuaian durasi ideal 15-60 detik (0-10)")
    penalty: int = Field(ge=0, le=15, description="Pengurang jeda panjang / kalimat gantung (0-15)")


class MomentCandidate(BaseModel):
    """Kandidat momen menarik yang diidentifikasi oleh sistem scoring."""
    id: str
    start: float
    end: float
    duration: float
    judul: str
    skor: int = Field(ge=0, le=100)
    alasan: str
    status: CandidateStatus = CandidateStatus.MENUNGGU
    text: str
    breakdown: Optional[ScoreBreakdown] = None


class AnalyzeMomentsRequest(BaseModel):
    """Permintaan analisis dan penilaian kandidat momen dari transkrip."""
    video_id: str
    min_duration: int = Field(default=15, ge=5, le=60)
    max_duration: int = Field(default=60, ge=15, le=180)
    target_clips: int = Field(default=5, ge=1, le=15)


class UpdateCandidateRequest(BaseModel):
    """Permintaan pembaruan status atau penyesuaian kandidat momen."""
    status: Optional[CandidateStatus] = None
    start: Optional[float] = None
    end: Optional[float] = None
    judul: Optional[str] = None


class ExportZipRequest(BaseModel):
    """Permintaan pengunduhan batch klip dalam satu file ZIP."""
    clip_filenames: list[str] = Field(min_length=1, description="Daftar nama file klip untuk dimasukkan ke dalam arsip ZIP")



