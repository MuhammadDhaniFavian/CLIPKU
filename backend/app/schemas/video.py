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


class ClipRange(BaseModel):
    """Rentang waktu untuk satu klip."""
    start: float = Field(ge=0, description="Detik mulai")
    end: float = Field(gt=0, description="Detik selesai")
    title: Optional[str] = None

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


class ClipInfo(BaseModel):
    """Informasi satu klip yang sudah dipotong."""
    filename: str
    title: str
    start: float
    end: float
    duration: float
    file_size_mb: float


class JobInfo(BaseModel):
    """Informasi status sebuah job."""
    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100, default=0)
    message: str = ""
    result: Optional[list[ClipInfo]] = None
    error: Optional[str] = None


class AutoSplitRequest(BaseModel):
    """Permintaan pembagian otomatis berdasarkan durasi."""
    video_id: str
    clip_duration: int = Field(default=30, ge=5, le=300)

