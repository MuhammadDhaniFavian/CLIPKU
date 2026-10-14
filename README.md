# CliperKu 🎬
**AI Auto Clipper Lokal untuk Mengubah Video Panjang Menjadi Video Pendek**

CliperKu adalah aplikasi web lokal untuk memotong dan mengonversi video panjang (seperti podcast, wawancara, presentasi) menjadi klip-klip video pendek secara otomatis, aman, dan tanpa biaya API pihak ketiga.

---

## Fitur Utama (MVP Fase 2 Selesai)
- **100% Offline & Privat**: Seluruh pemrosesan video dilakukan langsung di komputer pengguna.
- **Streaming Upload**: Mendukung file video besar (hingga 500 MB secara bawaan) dengan penggunaan RAM minimal.
- **Pemotongan Presisi Frame**: Menggunakan FFmpeg re-encode H.264 ultrafast/veryfast untuk memastikan titik potong akurat pada detik dan frame yang ditentukan tanpa desync keyframe.
- **Sistem Job Latar Belakang**:
  - Status terstruktur: *queued*, *running*, *completed*, *failed*, *cancelled*.
  - Antrean aman: hanya 1 job berat berjalan dalam satu waktu.
  - Progress bar real-time (0 - 100%).
  - Dukungan pembatalan job (*cancellation*) seketika dan pembersihan file sementara secara otomatis.
- **Preview & Unduh**: Pemutar video HTML5 untuk memverifikasi klip langsung di browser sebelum mengunduh file MP4.
- **Keamanan Ketat**: Backend hanya mengikat ke `127.0.0.1`, CORS dibatasi ke frontend lokal, argumen dieksekusi tanpa string shell, dan bebas dari directory traversal.

---

## Cara Menjalankan

### Cara 1: Menggunakan Launcher Cepat (Windows)
Cukup klik ganda file `start.bat`.

### Cara 2: Manual lewat Terminal

1. **Jalankan Backend**:
   ```bash
   cd backend
   venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

2. **Jalankan Frontend**:
   ```bash
   cd frontend
   npm run dev
   ```
   Buka browser di `http://localhost:5173`.

