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

export interface ClipRange {
  start: number;
  end: number;
  title?: string;
}

export interface ClipInfo {
  filename: string;
  title: string;
  start: number;
  end: number;
  duration: number;
  file_size_mb: number;
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface JobInfo {
  job_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  result?: ClipInfo[];
  error?: string;
}

export interface AppConfig {
  max_upload_size_mb: number;
  allowed_extensions: string[];
  disk_reserve_margin_gb?: number;
  free_disk_gb?: number;
}

