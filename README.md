# CliperKu 🎬
**AI Auto Clipper Lokal untuk Mengubah Video Panjang Menjadi Video Pendek Siap Upload**

CliperKu adalah aplikasi web lokal untuk memotong dan mengonversi video panjang (seperti podcast, wawancara, webinar, presentasi) menjadi klip-klip video pendek secara otomatis, privat, dan tanpa ketergantungan API pihak ketiga (100% Bebas Kuota & Gratis).

---

## 🌟 Fitur Utama (Fase 1 - 6 Selesai Penuh)

### 1. 🛡️ 100% Offline & Aman
- Seluruh pemrosesan video, transkripsi AI, dan pengeditan berjalan langsung di laptop/PC lokal.
- Backend terikat aman hanya ke `127.0.0.1` (localhost) dengan proteksi directory traversal.
- Tidak ada data video atau audio yang dikirim ke internet.

### 2. ⚡ Streaming Upload 2 GB & Proteksi Ruang Harddisk
- Mendukung berkas video berukuran besar hingga **2 GB** dengan penggunaan RAM minimal (*chunk-by-chunk streaming*).
- **Pemeriksaan Sisa Disk Otomatis**: Menolak unggahan jika ruang kosong harddisk kurang dari ukuran file + cadangan sistem 5 GB demi menjaga kestabilan komputer pengguna.

### 3. 🎙️ Transkripsi AI Lokal (Faster-Whisper)
- Menggunakan mesin *Faster-Whisper* CPU int8 berkecepatan tinggi dengan auto-deteksi bahasa (Bahasa Indonesia, Inggris, dll.).
- Dilengkapi **word-level timestamps** (cap waktu presisi tingkat kata) untuk akurasi pemotongan dan sinkronisasi teks.
- Interaktif: Cari kata kunci di transkrip dan lompat pemutaran video secara instan.

### 4. 🧠 Seleksi Momen Otomatis & Sistem Scoring (0 - 100)
- Menganalisis transkrip ucapan berdasarkan 5 dimensi penilaian cerdas:
  - **Hook Daya Tarik (0-20)**: Pertanyaan menarik, kata kejutan, atau awal pembuka yang kuat.
  - **Struktur Konteks (0-25)**: Kelengkapan alur awal, pertengahan, dan kesimpulan utuh tanpa kalimat gantung.
  - **Nilai Konten (0-20)**: Bobot informasi, cerita, tips, dan penjelasan inti.
  - **Kejelasan Ucapan (0-10)**: Tingkat keyakinan ucapan dan kelancaran artikulasi.
  - **Kesesuaian Durasi (0-10)**: Durasi optimal 15 - 60 detik untuk format media sosial.
- Dilengkapi kurasi interaktif bagi pengguna: **Terima (Accept)**, **Tolak (Reject)**, atau sesuaikan durasi & judul klip.

### 5. 📱 Format Multi-Platform & Burn-in Subtitle
- **Preset Format Cepat 1-Klik**:
  - 📱 **TikTok / Reels / Shorts**: 9:16 Vertikal (1080x1920) dengan latar belakang blur estetis.
  - ⬛ **Instagram Feed Kotak**: 1:1 Persegi (1080x1080) dengan latar belakang blur.
  - 🖥️ **YouTube / Lanskap**: Mempertahankan rasio aspek asli video.
- **Subtitle Otomatis Bergerak**:
  - Gaya *TikTok Yellow* (Teks kuning tebal berbingkai hitam profesional).
  - Gaya *Clean White* (Teks putih modern minimalis).
- **Ekspor Ganda**: Menghasilkan video MP4 dengan subtitle *hardcoded* (burn-in) dan menyediakan berkas teks pendamping `.SRT` untuk keperluan closed-caption.

### 6. 📦 Ekspor Batch & Launcher 1-Klik
- **Unduh Semua Klip (.ZIP)**: Mengemas seluruh klip MP4 dan berkas SRT dalam satu berkas arsip ZIP lokal dengan satu klik.
- **Buka Folder Hasil**: Membuka folder output langsung di Windows File Explorer.
- **Peluncur Cepat**: Cukup klik `start.bat` untuk menjalankan backend dan antarmuka web sekaligus.

---

## 🚀 Cara Menjalankan

### Cara 1: Menggunakan Launcher (Rekomendasi untuk Windows)
1. Cukup klik ganda file **`start.bat`** di folder utama.
2. Jendela browser akan otomatis terbuka di `http://localhost:5173`.
3. Untuk mematikan aplikasi setelah selesai, jalankan file **`stop.bat`**.

---

### Cara 2: Menjalankan Secara Manual lewat Terminal

1. **Jalankan Backend (FastAPI)**:
   ```powershell
   cd backend
   .\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

2. **Jalankan Frontend (React + Vite)**:
   ```powershell
   cd frontend
   npm run dev
   ```
   Buka peramban di `http://localhost:5173`.

---

## 🧪 Pengujian Otomatis (Test Suite)

Seluruh komponen telah diuji dan terverifikasi 100% lolos:
- `backend/test_upload_limits.py` : Pengujian batas upload 2 GB & proteksi margin disk 5 GB.
- `backend/test_fase5_e2e.py`      : Pengujian end-to-end format vertikal 9:16 & burn-in subtitle ASS.
- `backend/test_fase6_e2e.py`      : Pengujian format kotak 1:1 (ffprobe 1080x1080) & ekspor batch ZIP.
- `frontend/ npm run build`        : Pengujian kompilasi TypeScript dan bundler Vite.

---

## 🛠️ Tumpukan Teknologi
- **Backend**: Python 3.13, FastAPI, Uvicorn, Faster-Whisper, FFmpeg (GPL build lokal).
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS, Lucide Icons.
- **Sistem Penyimpanan**: Berkas lokal (tidak membutuhkan instalasi basis data eksternal).
"# CLIPKU" 
