"""
CliperKu - Pengujian Batas Upload 2 GB dan Pemeriksaan Sisa Ruang Disk.
Menguji:
1. GET /api/config mengembalikan batas 2048 MB (2 GB) dan cadangan disk 5 GB.
2. Penolakan file > 2 GB dengan pesan error yang jelas dan status 413.
3. Penolakan file jika sisa ruang disk kurang dari ukuran file + cadangan 5 GB (status 507).
"""

import asyncio
import io
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app
from app.core.config import MAX_UPLOAD_SIZE_MB, DISK_RESERVE_MARGIN_GB


async def run_tests():
    print("=" * 65)
    print("PENGUJIAN VALIDASI UPLOAD 2 GB & PEMERIKSAAN RUANG DISK")
    print("=" * 65)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000", timeout=60.0) as client:

        # 1. Uji Endpoint Config
        print("\n[1/3] Memeriksa endpoint GET /api/config ...")
        res = await client.get("/api/config")
        assert res.status_code == 200, f"Gagal membaca config: {res.text}"
        cfg = res.json()
        print(f"  -> Batas upload server: {cfg['max_upload_size_mb']} MB ({cfg['max_upload_size_mb'] // 1024} GB)")
        print(f"  -> Cadangan disk sistem: {cfg['disk_reserve_margin_gb']} GB")
        print(f"  -> Ruang disk bebas saat ini: {cfg['free_disk_gb']} GB")
        assert cfg["max_upload_size_mb"] == 2048, "Batas upload harus 2048 MB (2 GB)"
        assert cfg["disk_reserve_margin_gb"] == 5.0, "Cadangan disk harus 5 GB"

        # 2. Uji Penolakan File > 2 GB (Simulasi 2.2 GB)
        print("\n[2/3] Menguji penolakan file di atas 2 GB (simulasi 2.2 GB)...")
        boundary = "---------------------------CliperKuBoundaryTest123"
        header_part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="oversized_video.mp4"\r\n'
            f"Content-Type: video/mp4\r\n\r\n"
        ).encode("utf-8")
        footer_part = f"\r\n--{boundary}--\r\n".encode("utf-8")

        async def stream_2gb():
            yield header_part
            yield b"0" * 1024
            yield footer_part

        two_point_two_gb = 2200 * 1024 * 1024  # 2.2 GB
        headers = {
            "content-type": f"multipart/form-data; boundary={boundary}",
            "content-length": str(two_point_two_gb)
        }

        req = client.build_request("POST", "/api/upload", headers=headers, content=stream_2gb())
        res_2gb = await client.send(req)

        print(f"  -> Status respon file > 2 GB: {res_2gb.status_code}")
        print(f"  -> Pesan detail: {res_2gb.json().get('detail')}")
        assert res_2gb.status_code == 413, f"Harusnya 413, dapat {res_2gb.status_code}"
        assert "2 GB" in res_2gb.json().get("detail", ""), "Pesan error harus menyebut batas 2 GB"

        # 3. Uji Penolakan Ruang Disk Jika Kurang dari Ukuran File + Cadangan 5 GB
        print("\n[3/3] Menguji penolakan jika sisa ruang disk kurang dari ukuran file + cadangan 5 GB...")
        current_free_gb = cfg["free_disk_gb"]
        # Misal disk tersisa 25.4 GB, maka file berukuran (25.4 - 3.0) = 22.4 GB atau (free - 2 GB)
        # Jika file berukuran (free_disk - 2 GB), maka ruang yang dibutuhkan adalah (free - 2 + 5) = free + 3 GB!
        # Ini akan melebihi free_disk, sehingga ditolak dengan HTTP 507!
        # Namun ukuran file simulasi harus <= 2 GB (agar tidak tertolak di aturan 413 duluan):
        # Misal kita simulasikan file 1.5 GB dan kita uji kondisi disk:
        # Jika file 1.5 GB butuh 1.5 + 5.0 = 6.5 GB. Jika free disk < 6.5 GB, tolak.
        # Untuk menguji penolakan ruang disk, kita bisa set simulated size sedemikian rupa:
        simulated_disk_test_size = int((current_free_gb - 2.0) * 1024 * 1024 * 1024)
        if simulated_disk_test_size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            # Jika free disk laptop > 7 GB, file berukuran 2 GB butuh 2 + 5 = 7 GB.
            # Agar file <= 2 GB memicu disk check, kita uji dengan file 2 GB saat sisa disk < 7 GB,
            # atau kita uji formula disk check langsung.
            print(f"  -> Ruang disk saat ini ({current_free_gb} GB) masih sangat lega (> 7 GB).")
            print("  -> Menguji endpoint dengan simulasi request disk ketat...")
            
            # Mari kita uji logika disk check dengan file 1.9 GB pada skenario margin disk
            req_disk_size = int(1.9 * 1024 * 1024 * 1024) # 1.9 GB (di bawah 2 GB)
            # Kita uji pesan disk check langsung:
            free_disk_sim = current_free_gb * (1024**3)
            req_disk_sim = req_disk_size + (DISK_RESERVE_MARGIN_GB * 1024**3)
            print(f"     Sisa disk: {current_free_gb} GB, Dibutuhkan untuk file 1.9 GB + cadangan 5 GB: {req_disk_sim / (1024**3):.2f} GB")
            print(f"     Status ketersediaan: {'Cukup' if free_disk_sim >= req_disk_sim else 'Tidak Cukup'}")
            
            # Uji request nyata dengan ukuran di bawah 2 GB yang melebihi ruang disk:
            # Karena batas upload 2 GB, mari kita verifikasi respons ketika ruang disk tidak cukup:
            sim_headers = {
                "content-type": f"multipart/form-data; boundary={boundary}",
                "content-length": str(int((current_free_gb - 2.0) * 1024 * 1024 * 1024))
            }
            # Jika simulated_disk_test_size > 2 GB, server akan menolak dengan 413,
            # Jika free_disk laptop misalnya 25 GB, file 2 GB butuh 7 GB, jadi 25 GB cukup.
            # Mari verifikasi pesan 507 dengan file hipotetis jika free disk < required:
            # Kita mock shutil.disk_usage pada TEMP_DIR untuk menguji respon 507 secara presisi!
            from unittest.mock import patch, MagicMock
            import shutil
            with patch("shutil.disk_usage", return_value=MagicMock(total=100*1024**3, used=95*1024**3, free=5.5*1024**3)):
                # Free disk = 5.5 GB. File = 1.0 GB. Butuh = 1.0 + 5.0 = 6.0 GB (> 5.5 GB) -> Harus 507!
                headers_507 = {
                    "content-type": f"multipart/form-data; boundary={boundary}",
                    "content-length": str(1024 * 1024 * 1024) # 1 GB
                }
                req_507 = client.build_request("POST", "/api/upload", headers=headers_507, content=stream_2gb())
                res_507 = await client.send(req_507)
                print(f"  -> Respon saat ruang disk tidak cukup: {res_507.status_code}")
                print(f"  -> Pesan detail: {res_507.json().get('detail')}")
                assert res_507.status_code == 507, f"Harusnya 507, dapat {res_507.status_code}"
                assert "cadangan" in res_507.json().get("detail", "").lower(), "Pesan harus mencantumkan cadangan sistem"

    print("\n" + "=" * 65)
    print("SEMUA VALIDASI BATAS 2 GB & DISK CHECK LOLOS 100%!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_tests())
