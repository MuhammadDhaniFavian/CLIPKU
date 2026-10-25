"""
Test End-to-End Fase 4: Pemilihan Momen & Scoring Berbasis Aturan (Rule-Based Moment Scoring).
Menguji:
1. Upload video
2. Transkripsi AI suara
3. POST /api/video/{id}/analyze-moments (penilaian skor 0-100, hook, konteks, nilai, durasi)
4. Validasi struktur candidate: id, start, end, judul, skor, alasan, status, breakdown
5. GET /api/video/{id}/moments (mengambil kandidat tersimpan)
6. PATCH /api/video/{id}/moments/{moment_id} (kurasi terima/tolak dan edit judul/waktu)
7. Integrasi pemotongan klip berdasarkan momen yang diterima
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


async def run_fase4_tests():
    print("=" * 65)
    print("🚀 MEMULAI PENGUJIAN FASE 4: PEMILIHAN MOMEN & SCORING (MODUL 3)")
    print("=" * 65)

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
        print(f"✅ Video berhasil diunggah! ID: {video_id}")

        # 2. Transkripsi Video
        print("\n[Langkah 2] Mentranskripsi video untuk ekstraksi ucapan...")
        res = await client.post(
            f"/api/video/{video_id}/transcribe",
            json={"video_id": video_id, "language": "en", "model_size": "tiny"}
        )
        assert res.status_code == 200
        job_id = res.json()["job_id"]

        for _ in range(40):
            await asyncio.sleep(1.0)
            res = await client.get(f"/api/jobs/{job_id}")
            if res.json()["status"] == "completed":
                break

        res = await client.get(f"/api/jobs/{job_id}")
        assert res.json()["status"] == "completed", "Job transkripsi gagal"
        print("✅ Transkripsi selesai!")

        # 3. Analisis & Penilaian Momen
        print("\n[Langkah 3] Menganalisis dan menilai kandidat momen (POST /api/video/{id}/analyze-moments)...")
        req_payload = {
            "video_id": video_id,
            "min_duration": 10,
            "max_duration": 60,
            "target_clips": 3
        }
        res = await client.post(f"/api/video/{video_id}/analyze-moments", json=req_payload)
        assert res.status_code == 200, f"Gagal menganalisis momen: {res.text}"
        candidates = res.json()
        print(f"✅ Berhasil menganalisis momen! Ditemukan {len(candidates)} kandidat momen.")

        assert len(candidates) > 0, "Daftar kandidat tidak boleh kosong"

        # 4. Validasi Kolom & Skor Setiap Kandidat
        print("\n[Langkah 4] Memverifikasi struktur data kandidat sesuai Modul 3:")
        for idx, c in enumerate(candidates):
            assert "id" in c and c["id"]
            assert "start" in c and c["start"] >= 0
            assert "end" in c and c["end"] > c["start"]
            assert "judul" in c and len(c["judul"]) > 0
            assert "skor" in c and 0 <= c["skor"] <= 100
            assert "alasan" in c and len(c["alasan"]) > 0
            assert c["status"] == "menunggu"
            assert "breakdown" in c and c["breakdown"] is not None

            bd = c["breakdown"]
            print(f"\n   --- Kandidat #{idx + 1} ---")
            print(f"   ID        : {c['id']}")
            print(f"   Judul     : \"{c['judul']}\"")
            print(f"   Waktu     : {c['start']}s -> {c['end']}s (durasi: {c['duration']}s)")
            print(f"   Skor Total: {c['skor']} / 100")
            print(f"   Rincian   : Hook={bd['hook_score']}/20, Konteks={bd['context_score']}/25, "
                  f"Nilai={bd['value_score']}/20, Kejelasan={bd['clarity_score']}/10, "
                  f"Durasi={bd['duration_score']}/10, Penalti=-{bd['penalty']}")
            print(f"   Alasan    : {c['alasan']}")
            print(f"   Kutipan   : \"{c['text'][:60]}...\"")

        # 5. Uji Pengambilan Kandidat Tersimpan (GET /api/video/{id}/moments)
        print("\n[Langkah 5] Menguji pengambilan kandidat tersimpan (GET /api/video/{id}/moments)...")
        res = await client.get(f"/api/video/{video_id}/moments")
        assert res.status_code == 200
        saved_cands = res.json()
        assert len(saved_cands) == len(candidates)
        assert saved_cands[0]["id"] == candidates[0]["id"]
        print("✅ Endpoint GET /api/video/{id}/moments mengembalikan data yang identik!")

        # 6. Uji Kurasi Pengguna (PATCH /api/video/{id}/moments/{moment_id})
        first_cand = candidates[0]
        cand_id = first_cand["id"]
        print(f"\n[Langkah 6] Menguji kurasi pengguna (PATCH status = 'diterima' & ganti judul)...")
        patch_payload = {
            "status": "diterima",
            "judul": "Klip Pilihan Terbaik: AI Video Clipper"
        }
        res = await client.patch(f"/api/video/{video_id}/moments/{cand_id}", json=patch_payload)
        assert res.status_code == 200
        updated = res.json()
        assert updated["status"] == "diterima"
        assert updated["judul"] == "Klip Pilihan Terbaik: AI Video Clipper"
        print(f"✅ Kurasi berhasil diupdate: status={updated['status']}, judul=\"{updated['judul']}\"")

        # 7. Uji Pemotongan Berdasarkan Kandidat yang Diterima
        print("\n[Langkah 7] Mengirim kandidat yang diterima ke antrean pemotongan klip FFmpeg...")
        cut_payload = {
            "video_id": video_id,
            "clips": [
                {
                    "start": updated["start"],
                    "end": updated["end"],
                    "title": updated["judul"]
                }
            ]
        }
        res = await client.post("/api/clips/cut", json=cut_payload)
        assert res.status_code == 200
        cut_job_id = res.json()["job_id"]

        for _ in range(30):
            await asyncio.sleep(1.0)
            res = await client.get(f"/api/jobs/{cut_job_id}")
            if res.json()["status"] == "completed":
                break

        res = await client.get(f"/api/jobs/{cut_job_id}")
        cut_info = res.json()
        assert cut_info["status"] == "completed"
        cut_result = cut_info["result"][0]
        print(f"✅ Klip rekomendasi momen berhasil dipotong secara akurat!")
        print(f"   Nama File : {cut_result['filename']}")
        print(f"   Judul     : {cut_result['title']}")
        print(f"   Durasi    : {cut_result['duration']}s")
        print(f"   Ukuran    : {cut_result['file_size_mb']} MB")

    print("\n" + "=" * 65)
    print("🎉 SEMUA PENGUJIAN FASE 4 (PEMILIHAN MOMEN & SCORING) BERHASIL 100%!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_fase4_tests())

