import React, { useState, useEffect, useRef } from 'react';
import {
  Scissors,
  UploadCloud,
  Download,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Plus,
  Trash2,
  HardDrive,
  StopCircle
} from 'lucide-react';
import type { VideoMetadata, ClipRange, ClipInfo, JobInfo, AppConfig } from './types';

export default function App() {
  const [config, setConfig] = useState<AppConfig>({
    max_upload_size_mb: 500,
    allowed_extensions: ['.mp4', '.mov', '.mkv']
  });

  // State Video
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // State Klip
  const [clips, setClips] = useState<ClipRange[]>([]);
  const [splitDuration, setSplitDuration] = useState<number>(30);

  // State Job
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobInfo, setJobInfo] = useState<JobInfo | null>(null);
  const [completedClips, setCompletedClips] = useState<ClipInfo[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimerRef = useRef<number | null>(null);

  // Muat konfigurasi server saat pertama kali dibuka
  useEffect(() => {
    fetch('/api/config')
      .then((res) => res.json())
      .then((data) => setConfig(data))
      .catch((err) => console.error('Gagal memuat konfigurasi:', err));
  }, []);

  // Polling status job jika ada job aktif
  useEffect(() => {
    if (!activeJobId) return;

    const pollJob = async () => {
      try {
        const res = await fetch(`/api/jobs/${activeJobId}`);
        if (!res.ok) return;
        const data: JobInfo = await res.json();
        setJobInfo(data);

        if (data.status === 'completed') {
          if (data.result) setCompletedClips(data.result);
          setActiveJobId(null);
        } else if (data.status === 'failed' || data.status === 'cancelled') {
          setActiveJobId(null);
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    };

    pollJob();
    pollTimerRef.current = window.setInterval(pollJob, 1000);

    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [activeJobId]);

  // Handler Pilih Video
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!config.allowed_extensions.includes(ext)) {
      setErrorMessage(`Format file ${ext} tidak didukung. Gunakan: ${config.allowed_extensions.join(', ')}`);
      return;
    }

    if (file.size > config.max_upload_size_mb * 1024 * 1024) {
      setErrorMessage(`Ukuran file melebihi batas maksimal ${config.max_upload_size_mb} MB.`);
      return;
    }

    setErrorMessage(null);
    setVideoFile(file);
    setMetadata(null);
    setCompletedClips([]);
    setJobInfo(null);
    setClips([]);

    // Upload file
    setIsUploading(true);
    setUploadProgress(20);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Gagal mengunggah video.');
      }

      const data = await res.json();
      setVideoId(data.video_id);
      setMetadata(data.metadata);
      setUploadProgress(100);

      // Inisialisasi awal 3 klip otomatis
      generateDefaultClips(data.metadata.duration_seconds, 30);
    } catch (err: any) {
      setErrorMessage(err.message || 'Terjadi kesalahan saat upload.');
      setVideoFile(null);
    } finally {
      setIsUploading(false);
    }
  };

  const generateDefaultClips = (duration: number, clipDur: number) => {
    const newClips: ClipRange[] = [];
    let start = 0;
    let idx = 1;

    // Ambil maksimal 4 klip default
    while (start < duration && newClips.length < 4) {
      const end = Math.min(start + clipDur, duration);
      if (end - start < 5 && newClips.length > 0) break;
      newClips.push({
        start: parseFloat(start.toFixed(1)),
        end: parseFloat(end.toFixed(1)),
        title: `Klip ${idx}`
      });
      start += clipDur;
      idx++;
    }
    setClips(newClips);
  };

  const handleApplyAutoSplit = (dur: number) => {
    if (!metadata) return;
    setSplitDuration(dur);
    generateDefaultClips(metadata.duration_seconds, dur);
  };

  const handleAddClip = () => {
    if (!metadata) return;
    const lastClip = clips[clips.length - 1];
    const newStart = lastClip ? lastClip.end : 0;
    const newEnd = Math.min(newStart + splitDuration, metadata.duration_seconds);

    if (newStart >= metadata.duration_seconds) {
      setErrorMessage('Titik awal klip baru sudah mencapai akhir video.');
      return;
    }

    setClips([
      ...clips,
      {
        start: parseFloat(newStart.toFixed(1)),
        end: parseFloat(newEnd.toFixed(1)),
        title: `Klip ${clips.length + 1}`
      }
    ]);
  };

  const handleRemoveClip = (index: number) => {
    setClips(clips.filter((_clip: ClipRange, i: number) => i !== index));
  };

  const handleClipChange = (index: number, field: keyof ClipRange, value: any) => {
    const updated = [...clips];
    updated[index] = { ...updated[index], [field]: value };
    setClips(updated);
  };

  // Mulai Proses Pemotongan
  const handleStartCut = async () => {
    if (!videoId || clips.length === 0) return;
    setErrorMessage(null);
    setCompletedClips([]);

    // Validasi klip
    for (let i = 0; i < clips.length; i++) {
      if (clips[i].start >= clips[i].end) {
        setErrorMessage(`Klip #${i + 1}: Detik selesai (${clips[i].end}s) harus lebih besar dari detik mulai (${clips[i].start}s).`);
        return;
      }
    }

    try {
      const res = await fetch('/api/clips/cut', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_id: videoId,
          clips: clips,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal memulai job pemotongan.');
      }

      const data = await res.json();
      setActiveJobId(data.job_id);
      setJobInfo({
        job_id: data.job_id,
        status: 'queued',
        progress: 0,
        message: 'Job pemotongan terdaftar dalam antrean...',
      });
    } catch (err: any) {
      setErrorMessage(err.message || 'Gagal memproses klip.');
    }
  };

  // Batalkan Job
  const handleCancelJob = async () => {
    if (!activeJobId) return;
    try {
      await fetch(`/api/jobs/${activeJobId}/cancel`, { method: 'POST' });
      setActiveJobId(null);
      setJobInfo((prev: JobInfo | null) =>
        prev ? { ...prev, status: 'cancelled', message: 'Proses telah dibatalkan.' } : null
      );
    } catch (err) {
      console.error('Gagal membatalkan job:', err);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-4 md:p-8">
      <div className="max-w-5xl mx-auto space-y-8">
        
        {/* Header */}
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-zinc-800">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
                <Scissors className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-white via-zinc-200 to-purple-400 bg-clip-text text-transparent">
                  CliperKu
                </h1>
                <p className="text-xs text-zinc-400">AI Auto Clipper Lokal • MVP Fase 2</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300">
              <HardDrive className="w-3.5 h-3.5 text-purple-400" />
              <span>Batas: {config.max_upload_size_mb} MB</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-950/40 border border-emerald-800/40 text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>100% Offline Lokal</span>
            </div>
          </div>
        </header>

        {/* Error Alert */}
        {errorMessage && (
          <div className="p-4 rounded-xl bg-red-950/30 border border-red-800/50 flex items-start gap-3 text-red-300 text-sm">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-medium text-red-200">Terjadi Kesalahan</p>
              <p className="text-xs mt-0.5 text-red-300/90">{errorMessage}</p>
            </div>
            <button
              onClick={() => setErrorMessage(null)}
              className="text-red-400 hover:text-red-200 text-xs underline"
            >
              Tutup
            </button>
          </div>
        )}

        {/* Section 1: Upload Video */}
        <section className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6 backdrop-blur space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-300 text-xs font-bold flex items-center justify-center">
                1
              </span>
              <h2 className="text-base font-semibold text-zinc-200">Pilih Video Panjang</h2>
            </div>
            {videoFile && (
              <button
                onClick={() => fileInputRef.current?.click()}
                className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1 cursor-pointer"
              >
                <RefreshCw className="w-3 h-3" /> Ganti Video
              </button>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept={config.allowed_extensions.join(',')}
            onChange={handleFileSelect}
            className="hidden"
          />

          {!videoFile ? (
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-zinc-700 hover:border-purple-500/60 rounded-xl p-8 text-center cursor-pointer transition-all bg-zinc-900/20 hover:bg-zinc-800/20 space-y-3"
            >
              <div className="w-12 h-12 mx-auto rounded-full bg-purple-500/10 flex items-center justify-center text-purple-400">
                <UploadCloud className="w-6 h-6" />
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-200">Klik untuk memilih file video dari laptop</p>
                <p className="text-xs text-zinc-500 mt-1">
                  Mendukung {config.allowed_extensions.join(', ')} hingga {config.max_upload_size_mb} MB
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Progress Bar Upload */}
              {isUploading && (
                <div className="space-y-2">
                  <div className="flex justify-between text-xs text-zinc-400">
                    <span>Mengunggah video ke folder lokal...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-purple-500 transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    ></div>
                  </div>
                </div>
              )}

              {/* Metadata Card */}
              {metadata && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-xl bg-zinc-950/60 border border-zinc-800/80 text-xs">
                  <div>
                    <span className="text-zinc-500 block">Nama File</span>
                    <span className="text-zinc-200 font-medium truncate block" title={metadata.filename}>
                      {metadata.filename}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Durasi Total</span>
                    <span className="text-zinc-200 font-medium">
                      {metadata.duration_display} ({metadata.duration_seconds}s)
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Resolusi & FPS</span>
                    <span className="text-zinc-200 font-medium">
                      {metadata.width}x{metadata.height} @ {metadata.fps} fps
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block">Ukuran & Codec</span>
                    <span className="text-zinc-200 font-medium">
                      {metadata.file_size_mb} MB ({metadata.codec})
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Section 2: Konfigurasi Klip */}
        {metadata && (
          <section className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6 backdrop-blur space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-300 text-xs font-bold flex items-center justify-center">
                  2
                </span>
                <h2 className="text-base font-semibold text-zinc-200">Konfigurasi Potongan Klip</h2>
              </div>

              {/* Preset Tombol Auto Split */}
              <div className="flex items-center gap-2 text-xs">
                <span className="text-zinc-400">Preset durasi:</span>
                {[15, 30, 45, 60].map((sec) => (
                  <button
                    key={sec}
                    onClick={() => handleApplyAutoSplit(sec)}
                    className={`px-2.5 py-1 rounded-lg border transition-all cursor-pointer ${
                      splitDuration === sec
                        ? 'bg-purple-600 border-purple-500 text-white font-medium'
                        : 'bg-zinc-800/60 border-zinc-700/60 text-zinc-300 hover:bg-zinc-800'
                    }`}
                  >
                    {sec}s
                  </button>
                ))}
              </div>
            </div>

            {/* List Klip */}
            <div className="space-y-3">
              {clips.map((clip: ClipRange, index: number) => (
                <div
                  key={index}
                  className="flex flex-col sm:flex-row sm:items-center gap-3 p-3.5 rounded-xl bg-zinc-950/40 border border-zinc-800/80 text-xs"
                >
                  <div className="w-6 font-semibold text-zinc-400 flex items-center justify-center">
                    #{index + 1}
                  </div>
                  
                  <div className="flex-1">
                    <input
                      type="text"
                      value={clip.title || ''}
                      onChange={(e) => handleClipChange(index, 'title', e.target.value)}
                      placeholder="Judul klip..."
                      className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-zinc-200 focus:outline-none focus:border-purple-500"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className="text-zinc-500">Mulai:</span>
                      <input
                        type="number"
                        step="0.5"
                        min="0"
                        max={metadata.duration_seconds}
                        value={clip.start}
                        onChange={(e) =>
                          handleClipChange(index, 'start', parseFloat(e.target.value) || 0)
                        }
                        className="w-20 bg-zinc-900/80 border border-zinc-800 rounded-lg px-2 py-1.5 text-zinc-200 text-center focus:outline-none focus:border-purple-500"
                      />
                      <span className="text-zinc-500">s</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="text-zinc-500">Selesai:</span>
                      <input
                        type="number"
                        step="0.5"
                        min="0"
                        max={metadata.duration_seconds}
                        value={clip.end}
                        onChange={(e) =>
                          handleClipChange(index, 'end', parseFloat(e.target.value) || 0)
                        }
                        className="w-20 bg-zinc-900/80 border border-zinc-800 rounded-lg px-2 py-1.5 text-zinc-200 text-center focus:outline-none focus:border-purple-500"
                      />
                      <span className="text-zinc-500">s</span>
                    </div>

                    <span className="text-zinc-400 font-mono px-2">
                      ({(clip.end - clip.start).toFixed(1)}s)
                    </span>

                    <button
                      onClick={() => handleRemoveClip(index)}
                      className="p-1.5 text-zinc-500 hover:text-red-400 rounded-lg hover:bg-zinc-800/60 transition cursor-pointer"
                      title="Hapus klip ini"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}

              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={handleAddClip}
                  className="flex items-center gap-1.5 text-xs text-purple-400 hover:text-purple-300 px-3 py-1.5 rounded-lg border border-purple-500/30 bg-purple-500/10 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" /> Tambah Rentang Klip
                </button>

                <button
                  onClick={handleStartCut}
                  disabled={activeJobId !== null || clips.length === 0}
                  className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium text-xs shadow-lg transition-all cursor-pointer ${
                    activeJobId !== null || clips.length === 0
                      ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                      : 'bg-purple-600 hover:bg-purple-500 text-white shadow-purple-600/30'
                  }`}
                >
                  <Scissors className="w-4 h-4" />
                  <span>Mulai Potong ({clips.length} Klip)</span>
                </button>
              </div>
            </div>
          </section>
        )}

        {/* Section 3: Status Job Latar Belakang & Progress Bar */}
        {jobInfo && (
          <section className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6 backdrop-blur space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-300 text-xs font-bold flex items-center justify-center">
                  3
                </span>
                <h2 className="text-base font-semibold text-zinc-200">Status Pemrosesan</h2>
              </div>

              {activeJobId && (
                <button
                  onClick={handleCancelJob}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-red-950/40 border border-red-800/40 text-red-400 hover:bg-red-900/50 text-xs cursor-pointer"
                >
                  <StopCircle className="w-3.5 h-3.5" /> Batalkan Job
                </button>
              )}
            </div>

            <div className="p-4 rounded-xl bg-zinc-950/60 border border-zinc-800 space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-300 font-medium">{jobInfo.message}</span>
                <span className="font-mono text-purple-400 font-semibold">{jobInfo.progress}%</span>
              </div>

              <div className="w-full h-2.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    jobInfo.status === 'completed'
                      ? 'bg-emerald-500'
                      : jobInfo.status === 'failed'
                      ? 'bg-red-500'
                      : jobInfo.status === 'cancelled'
                      ? 'bg-amber-500'
                      : 'bg-purple-500'
                  }`}
                  style={{ width: `${jobInfo.progress}%` }}
                ></div>
              </div>

              <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                <span>Job ID: {jobInfo.job_id}</span>
                <span>•</span>
                <span className="uppercase font-semibold tracking-wider text-zinc-400">
                  Status: {jobInfo.status}
                </span>
              </div>
            </div>
          </section>
        )}

        {/* Section 4: Hasil Klip & Preview Player */}
        {completedClips.length > 0 && (
          <section className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6 backdrop-blur space-y-5">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <h2 className="text-base font-semibold text-zinc-200">
                Hasil Klip MP4 ({completedClips.length} Klip Siap)
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {completedClips.map((clip: ClipInfo, idx: number) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl bg-zinc-950/80 border border-zinc-800/80 space-y-3 flex flex-col justify-between"
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-sm text-zinc-200">{clip.title}</h3>
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 font-mono">
                        {clip.duration} detik
                      </span>
                    </div>
                    <p className="text-xs text-zinc-500 truncate" title={clip.filename}>
                      {clip.filename}
                    </p>
                  </div>

                  {/* HTML5 Video Player Preview */}
                  <div className="rounded-lg overflow-hidden bg-black border border-zinc-800 aspect-video flex items-center justify-center">
                    <video
                      controls
                      preload="metadata"
                      className="w-full h-full object-contain"
                      src={`/api/clips/${clip.filename}`}
                    >
                      Browser Anda tidak mendukung tag video.
                    </video>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-xs text-zinc-400">{clip.file_size_mb} MB</span>
                    <a
                      href={`/api/clips/${clip.filename}`}
                      download={clip.filename}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600/20 border border-purple-500/30 text-purple-300 hover:bg-purple-600 hover:text-white transition-all text-xs font-medium cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" /> Unduh MP4
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

      </div>
    </div>
  );
}
