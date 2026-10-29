"""
CliperKu - Pengujian End-to-End Fase 6 (Batch ZIP Export, Preset Format Kotak 1:1, dan Integrasi Subtitle)
Menggunakan modul bawaan Python (urllib, zipfile, subprocess) 100% offline tanpa dependensi eksternal.
"""

import os
import sys
import time
import json
import subprocess
import zipfile
import io
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
TEST_VIDEO_PATH = PROJECT_DIR / "test_speech_video.mp4"
FFPROBE_PATH = PROJECT_DIR / "tools" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffprobe.exe"


def verify_video_dimensions(file_path: Path, expected_w: int, expected_h: int):
    cmd = [
        str(FFPROBE_PATH),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(file_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    dim_str = res.stdout.strip()
    w, h = map(int, dim_str.split("x"))
    assert w == expected_w and h == expected_h, f"Dimensi tidak cocok: dapat {w}x{h}, diharapkan {expected_w}x{expected_h}"
    return w, h


def upload_multipart(video_path: Path):
    boundary = "----WebKitFormBoundaryCliperKuTestFase6"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{video_path.name}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: video/mp4\r\n\r\n")
    with open(video_path, "rb") as f:
        body.extend(f.read())
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, data: dict):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.headers, resp.read()


def get_json(url: str):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("=" * 65)
    print("PENGUJIAN END-TO-END FASE 6: PRESET 1:1 KOTAK & BATCH EXPORT ZIP")
    print("=" * 65)

    # 1. Cek kesehatan backend
    print("\n[1] Memeriksa status backend server...")
    try:
        conf = get_json(f"{BASE_URL}/api/config")
        print(f"    Backend aktif. Batas upload: {conf['max_upload_size_mb']} MB")
    except Exception as e:
        print(f"    ERROR: Backend tidak dapat dihubungi: {e}")
        sys.exit(1)

    # 2. Upload video untuk pengujian
    print("\n[2] Mengunggah video sampel...")
    upload_res = upload_multipart(TEST_VIDEO_PATH)
    video_id = upload_res["video_id"]
    print(f"    Upload berhasil. Video ID: {video_id}")

    # 3. Transkripsi suara untuk subtitle
    print("\n[3] Menjalankan transkripsi suara lokal...")
    _, _, raw_res = post_json(f"{BASE_URL}/api/video/{video_id}/transcribe", {"video_id": video_id})
    t_job_id = json.loads(raw_res.decode("utf-8"))["job_id"]

    for _ in range(40):
        time.sleep(1)
        job_data = get_json(f"{BASE_URL}/api/jobs/{t_job_id}")
        if job_data["status"] == "completed":
            break
    assert job_data["status"] == "completed", "Transkripsi timeout/gagal"
    print("    Transkripsi selesai.")

    # 4. Potong klip format Kotak 1:1 (Square)
    print("\n[4] Memotong klip format Kotak 1:1 (Latar Blur) dengan Subtitle TikTok...")
    cut_payload = {
        "video_id": video_id,
        "clips": [{"start": 0.0, "end": 3.5, "title": "Klip Kotak 1:1 Test"}],
        "vertical_mode": "square",
        "burn_subtitles": True,
        "subtitle_style": "tiktok_yellow"
    }
    _, _, raw_cut = post_json(f"{BASE_URL}/api/clips/cut", cut_payload)
    cut_job_id = json.loads(raw_cut.decode("utf-8"))["job_id"]

    for _ in range(40):
        time.sleep(1)
        cut_data = get_json(f"{BASE_URL}/api/jobs/{cut_job_id}")
        st = cut_data["status"]
        if st in ["completed", "failed"]:
            break

    assert cut_data["status"] == "completed", f"Pemotongan gagal: {cut_data.get('error')}"
    clip_result = cut_data["result"][0]
    clip_filename = clip_result["filename"]
    print(f"    Klip berhasil dibuat: {clip_filename}")

    # 5. Verifikasi resolusi video 1:1 (1080x1080)
    print("\n[5] Memverifikasi dimensi video keluaran melalui ffprobe...")
    output_clip_path = BACKEND_DIR / "output" / clip_filename
    w, h = verify_video_dimensions(output_clip_path, 1080, 1080)
    print(f"    Dimensi video terverifikasi presisi: {w}x{h} (1:1 Aspect Ratio)")

    # 6. Verifikasi Batch Export ZIP
    print("\n[6] Menguji endpoint POST /api/clips/export-zip...")
    zip_payload = {"clip_filenames": [clip_filename]}
    status, headers, content = post_json(f"{BASE_URL}/api/clips/export-zip", zip_payload)
    assert status == 200, f"Export ZIP gagal: status {status}"
    content_type = headers.get("content-type", "")
    assert "application/zip" in content_type or "octet-stream" in content_type
    print(f"    Header Content-Type valid: {content_type}")

    # Buka ZIP di memori dan verifikasi entri di dalamnya
    zip_bytes = io.BytesIO(content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        namelist = zf.namelist()
        print(f"    Isi file ZIP yang diterima: {namelist}")
        assert clip_filename in namelist, f"{clip_filename} tidak ada dalam file ZIP"
        srt_name = Path(clip_filename).stem + ".srt"
        if (BACKEND_DIR / "output" / srt_name).exists():
            assert srt_name in namelist, f"File subtitle {srt_name} tidak disertakan dalam ZIP"
            print(f"    File subtitle {srt_name} berhasil ikut terkemas ke dalam ZIP!")

    # 7. Menguji error handling export ZIP
    print("\n[7] Menguji validasi dan error handling export-zip...")
    # List kosong
    try:
        post_json(f"{BASE_URL}/api/clips/export-zip", {"clip_filenames": []})
        assert False, "Harusnya melempar HTTPError 422/400"
    except urllib.error.HTTPError as e:
        assert e.code in [400, 422]
        print(f"    Daftar kosong ditolak dengan benar (HTTP {e.code}).")

    # File fiktif
    try:
        post_json(f"{BASE_URL}/api/clips/export-zip", {"clip_filenames": ["file_fiktif_12345.mp4"]})
        assert False, "Harusnya melempar HTTPError 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404
        print("    File yang tidak ada ditolak dengan benar (HTTP 404).")

    print("\n" + "=" * 65)
    print(" SEMUA PENGUJIAN FASE 6 BERHASIL LOLOS 100%!")
    print("=" * 65)


if __name__ == "__main__":
    main()
