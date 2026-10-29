export interface VideoMetadata {
  filename: string;
  file_size_mb: number;
  duration_seconds: number;
  duration_display: string;
  width: number;
  height: number;
  fps: number;
  codec: string;
  audio_codec?: string;
}

export type VerticalMode = 'blur' | 'crop' | 'square' | 'none';
export type SubtitleStyle = 'tiktok_yellow' | 'clean_white' | 'none';

export interface ClipRange {
  start: number;
  end: number;
  title?: string;
  custom_subtitle?: string;
}

export interface ClipInfo {
  filename: string;
  title: string;
  start: number;
  end: number;
  duration: number;
  file_size_mb: number;
  is_vertical?: boolean;
  format_mode?: string;
  has_subtitles?: boolean;
  srt_filename?: string;
}


export interface WordTimestamp {
  word: string;
  start: number;
  end: number;
  probability: number;
}

export interface TranscriptSegment {
  id: number;
  start: number;
  end: number;
  text: string;
  words: WordTimestamp[];
}

export interface TranscriptionResult {
  video_id: string;
  language: string;
  language_probability: number;
  duration: number;
  segments: TranscriptSegment[];
  full_text: string;
}

export type CandidateStatus = 'menunggu' | 'diterima' | 'ditolak';

export interface ScoreBreakdown {
  hook_score: number;
  context_score: number;
  value_score: number;
  clarity_score: number;
  duration_score: number;
  penalty: number;
}

export interface MomentCandidate {
  id: string;
  start: number;
  end: number;
  duration: number;
  judul: string;
  skor: number;
  alasan: string;
  status: CandidateStatus;
  text: string;
  breakdown?: ScoreBreakdown;
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface JobInfo {
  job_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  result?: ClipInfo[];
  transcription?: TranscriptionResult;
  error?: string;
}

export interface AppConfig {
  max_upload_size_mb: number;
  allowed_extensions: string[];
  disk_reserve_margin_gb?: number;
  free_disk_gb?: number;
}
