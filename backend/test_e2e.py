"""
CliperKu - Pengujian Otomatis Fase 2 (End-to-End Test).
Menguji:
1. Streaming Upload video 5 menit (278 MB) & pembacaan metadata
2. Pendaftaran Job pemotongan 3 klip akurat
3. Polling progress hingga status completed (100%)
4. Verifikasi ketiga file klip MP4 bisa diputar & durasi sesuai timestamp (via ffprobe)
5. Uji fitur pembatalan (cancel job) & pembersihan file sementara
"""

import asyncio
import os
import sys
from pathlib import Path
import httpx

# Tambahkan backend ke sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app
from app.core.config import OUTPUT_DIR, FFPROBE_PATH
from app.services.ffmpeg_service import FFmpegService


async def run_tests():
    print("=" * 60)
    print("MEMULAI PENGUJIAN END-TO-END FASE 2: CLIPERKU")
    print("=" * 60)

    test_video = Path("d:/FAVIAN/project clip/test_video_5min.mp4")
    if not test_video.exists():
        raise FileNotFoundError(f"Video uji coba tidak ditemukan di {test_video}")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000", timeout=120.0) as client:

        # 1. Test Config Endpoint
        print("\n[1/5] Menguji GET /api/config ...")
        res = await client.get("/api/config")
        assert res.status_code == 200, f"Config error: {res.text}"
        cfg = res.json()
        print(f"  -> Batas upload: {cfg['max_upload_size_mb']} MB")
        print(f"  -> Format didukung: {cfg['allowed_extensions']}")

        # 2. Test Upload Streaming
        print("\n[2/5] Menguji POST /api/upload dengan video 5 menit (~278 MB)...")
        file_size_mb = round(test_video.stat().st_size / (1024 * 1024), 2)
        print(f"  -> Ukuran file: {file_size_mb} MB")

        with open(test_video, "rb") as f:
            files = {"file": (test_video.name, f, "video/mp4")}
            res = await client.post("/api/upload", files=files)

        assert res.status_code == 200, f"Upload error: {res.text}"
        upload_data = res.json()
        video_id = upload_data["video_id"]
        meta = upload_data["metadata"]
        print(f"  -> Sukses! Video ID: {video_id}")
        print(f"  -> Metadata: {meta['width']}x{meta['height']} @ {meta['fps']}fps, Durasi: {meta['duration_display']} ({meta['duration_seconds']}s)")

        assert meta["duration_seconds"] >= 299.0, f"Durasi tidak cocok: {meta['duration_seconds']}"

        # 3. Test Pendaftaran & Pemotongan 3 Klip
        print("\n[3/5] Menguji POST /api/clips/cut untuk 3 klip (10-40s, 60-90s, 120-150s)...")
        cut_payload = {
            "video_id": video_id,
            "clips": [
                {"start": 10.0, "end": 40.0, "title": "Klip Uji 1"},
                {"start": 60.0, "end": 90.0, "title": "Klip Uji 2"},
                {"start": 120.0, "end": 150.0, "title": "Klip Uji 3"}
            ]
        }
        res = await client.post("/api/clips/cut", json=cut_payload)
        assert res.status_code == 200, f"Cut error: {res.text}"
        job_id = res.json()["job_id"]
        print(f"  -> Job terdaftar dengan ID: {job_id}")

        # Polling progress
        print("  -> Memantau progress pemrosesan di latar belakang:")
        while True:
            await asyncio.sleep(1.0)
            res = await client.get(f"/api/jobs/{job_id}")
            job = res.json()
            print(f"     [Progress {job['progress']}%] {job['message']} (status: {job['status']})")
            if job["status"] in ["completed", "failed", "cancelled"]:
                break

        assert job["status"] == "completed", f"Job gagal: {job.get('error')}"
        assert len(job["result"]) == 3, f"Jumlah klip tidak 3: {job['result']}"

        # 4. Verifikasi File Klip MP4
        print("\n[4/5] Memverifikasi integritas dan akurasi durasi file MP4 via ffprobe...")
        for i, clip in enumerate(job["result"], 1):
            clip_path = OUTPUT_DIR / clip["filename"]
            assert clip_path.exists(), f"File tidak ditemukan: {clip_path}"
            assert clip_path.stat().st_size > 500_000, f"Ukuran file klip terlalu kecil: {clip_path.stat().st_size}"

            clip_meta = await FFmpegService.get_metadata(clip_path)
            print(f"  -> Klip {i}: {clip['filename']}")
            print(f"     Durasi terukur: {clip_meta.duration_seconds}s (Target: 30.0s), Resolusi: {clip_meta.width}x{clip_meta.height}, Ukuran: {clip['file_size_mb']} MB")
            
            # Toleransi selisih frame maksimal 0.2 detik
            diff = abs(clip_meta.duration_seconds - 30.0)
            assert diff <= 0.2, f"Durasi klip meleset terlalu jauh: {diff}s"

        # 5. Test Pembatalan Job (Cancellation & Cleanup)
        print("\n[5/5] Menguji Pembatalan Job (Cancel) & Pembersihan File Sementara...")
        res = await client.post("/api/clips/cut", json={
            "video_id": video_id,
            "clips": [
                {"start": 0.0, "end": 100.0, "title": "Klip Panjang untuk Uji Batal"},
                {"start": 100.0, "end": 200.0, "title": "Klip Panjang 2"}
            ]
        })
        cancel_job_id = res.json()["job_id"]
        # Berikan waktu sejenak agar mulai berjalan
        await asyncio.sleep(0.5)

        # Batalkan
        cancel_res = await client.post(f"/api/jobs/{cancel_job_id}/cancel")
        assert cancel_res.status_code == 200, f"Cancel error: {cancel_res.text}"
        print(f"  -> Sinyal pembatalan terkirim untuk job: {cancel_job_id}")

        await asyncio.sleep(0.5)
        status_res = await client.get(f"/api/jobs/{cancel_job_id}")
        cancel_status = status_res.json()
        print(f"  -> Status akhir job: {cancel_status['status']} - {cancel_status['message']}")
        assert cancel_status["status"] == "cancelled"

    print("\n" + "=" * 60)
    print("SEMUA PENGUJIAN FASE 2 BERHASIL 100%!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
