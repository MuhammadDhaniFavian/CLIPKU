"""
Test End-to-End Fase 3: Transkripsi Ucapan AI Faster-Whisper Lokal.
Menguji:
1. Upload video dengan suara percakapan
2. Ekstraksi audio 16kHz mono WAV otomatis
3. Transkripsi AI lokal dengan word-level timestamps & GPU CUDA / CPU
4. Polling background job status hingga selesai (100%)
5. Validasi hasil teks, segmen, dan kata
6. Pengambilan transkrip via GET /api/video/{id}/transcript
7. Pemotongan klip berdasarkan segmen transkripsi
"""

import asyncio
import os
import sys
from pathlib import Path
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_BASE = "http://127.0.0.1:8000/api"

TEST_VIDEO = Path(__file__).resolve().parent.parent / "test_speech_video.mp4"


async def run_fase3_tests():
    print("=" * 60)
    print("🚀 MEMULAI PENGUJIAN FASE 3: AI FASTER-WHISPER TRANSKRIPSI")
    print("=" * 60)

    if not TEST_VIDEO.exists():
        print(f"❌ File video uji coba tidak ditemukan: {TEST_VIDEO}")
        sys.exit(1)

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as client:
        # 1. Upload Video
        print("\n[Langkah 1] Mengunggah test_speech_video.mp4...")
        with open(TEST_VIDEO, "rb") as f:
            files = {"file": (TEST_VIDEO.name, f, "video/mp4")}
            res = await client.post("/api/upload", files=files)

        assert res.status_code == 200, f"Upload gagal: {res.text}"
        data = res.json()
        video_id = data["video_id"]
        metadata = data["metadata"]
        print(f"✅ Video berhasil diunggah!")
        print(f"   Video ID : {video_id}")
        print(f"   Durasi   : {metadata['duration_seconds']}s")
        print(f"   Resolusi : {metadata['width']}x{metadata['height']}")

        # 2. Start Transcribe Job
        print("\n[Langkah 2] Memulai background job transkripsi AI Whisper...")
        transcribe_payload = {
            "video_id": video_id,
            "language": None,      # auto-detect
            "model_size": "tiny"
        }
        res = await client.post(f"/api/video/{video_id}/transcribe", json=transcribe_payload)
        assert res.status_code == 200, f"Gagal memulai transkripsi: {res.text}"
        job_data = res.json()
        job_id = job_data["job_id"]
        print(f"✅ Job transkripsi terdaftar! Job ID: {job_id}")

        # 3. Poll Job Status
        print("\n[Langkah 3] Memantau progress job transkripsi...")
        max_polls = 60
        completed = False
        final_job = None

        for i in range(max_polls):
            await asyncio.sleep(1.0)
            res = await client.get(f"/api/jobs/{job_id}")
            assert res.status_code == 200
            final_job = res.json()
            status = final_job["status"]
            progress = final_job["progress"]
            message = final_job["message"]
            print(f"   [{progress:3d}%] Status: {status:<10} | {message}")

            if status == "completed":
                completed = True
                break
            elif status in ["failed", "cancelled"]:
                print(f"❌ Job berakhir dengan status: {status}")
                print(f"   Error: {final_job.get('error')}")
                sys.exit(1)

        assert completed, "Timeout menunggu job transkripsi selesai"
        print("✅ Job transkripsi selesai 100%!")

        # 4. Verifikasi Hasil Transkripsi dari Job
        trans = final_job.get("transcription")
        assert trans is not None, "Data transkripsi kosong pada job"
        print("\n[Langkah 4] Memverifikasi data transkripsi:")
        print(f"   Bahasa Terdeteksi : {trans['language'].upper()} (keyakinan: {trans['language_probability']:.2f})")
        print(f"   Jumlah Segmen     : {len(trans['segments'])}")
        print(f"   Teks Lengkap      : {trans['full_text']}")

        assert len(trans["segments"]) > 0, "Segmen ucapan tidak boleh kosong"
        assert "cliperku" in trans["full_text"].lower() or "video" in trans["full_text"].lower() or "laptop" in trans["full_text"].lower(), (
            f"Teks transkripsi tidak mengenali ucapan yang diharapkan: {trans['full_text']}"
        )

        # Periksa word-level timestamps
        first_seg = trans["segments"][0]
        print(f"\n   Detail Segmen Pertama:")
        print(f"   Waktu  : {first_seg['start']}s -> {first_seg['end']}s")
        print(f"   Ucapan : \"{first_seg['text']}\"")
        print(f"   Jumlah kata ber-timestamp: {len(first_seg['words'])}")
        if first_seg["words"]:
            first_word = first_seg["words"][0]
            print(f"   Contoh Kata Pertama: '{first_word['word']}' ({first_word['start']}s - {first_word['end']}s)")

        # 5. Uji Endpoint GET /api/video/{id}/transcript
        print("\n[Langkah 5] Menguji endpoint GET /api/video/{video_id}/transcript...")
        res = await client.get(f"/api/video/{video_id}/transcript")
        assert res.status_code == 200, f"Gagal mengambil transcript: {res.text}"
        cached_trans = res.json()
        assert cached_trans["video_id"] == video_id
        assert cached_trans["full_text"] == trans["full_text"]
        print("✅ Endpoint /api/video/{id}/transcript berfungsi dan mengembalikan data yang identik!")

        # 6. Uji Endpoint Video Stream
        print("\n[Langkah 6] Menguji endpoint streaming video sumber...")
        res = await client.get(f"/api/video/{video_id}/stream", headers={"Range": "bytes=0-1024"})
        assert res.status_code in [200, 206], f"Stream video gagal: {res.status_code}"
        print("✅ Endpoint /api/video/{id}/stream mendukung streaming preview browser!")

        # 7. Uji Pemotongan Klip Berdasarkan Segmen Transkripsi
        print("\n[Langkah 7] Menguji pemotongan klip berdasarkan segmen transkripsi...")
        clip_start = first_seg["start"]
        clip_end = min(first_seg["end"] + 1.0, metadata["duration_seconds"])

        cut_req = {
            "video_id": video_id,
            "clips": [
                {
                    "start": clip_start,
                    "end": clip_end,
                    "title": f"Klip dari Transkrip: {first_seg['text'][:20]}"
                }
            ]
        }
        res = await client.post("/api/clips/cut", json=cut_req)
        assert res.status_code == 200
        cut_job_id = res.json()["job_id"]

        for _ in range(30):
            await asyncio.sleep(1.0)
            res = await client.get(f"/api/jobs/{cut_job_id}")
            if res.json()["status"] == "completed":
                break

        res = await client.get(f"/api/jobs/{cut_job_id}")
        cut_job_info = res.json()
        assert cut_job_info["status"] == "completed"
        created_clip = cut_job_info["result"][0]
        print(f"✅ Klip berhasil dipotong dari segmen ucapan transkripsi!")
        print(f"   Nama File: {created_clip['filename']}")
        print(f"   Durasi   : {created_clip['duration']}s")
        print(f"   Ukuran   : {created_clip['file_size_mb']} MB")

    print("\n" + "=" * 60)
    print("🎉 SEMUA PENGUJIAN FASE 3 (TRANSKRIPSI AI LOKAL) BERHASIL 100%!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_fase3_tests())

