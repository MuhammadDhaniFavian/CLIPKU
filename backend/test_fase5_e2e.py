import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.parse

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
TEST_VIDEO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_speech_video.mp4"))
FFPROBE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools", "ffmpeg", "ffmpeg-master-latest-win64-gpl", "bin", "ffprobe.exe"))

def wait_for_server():
    print("[1] Menunggu backend server di 127.0.0.1:8000...")
    for _ in range(15):
        try:
            req = urllib.request.Request(f"{BASE_URL}/api/config")
            with urllib.request.urlopen(req, timeout=3) as res:
                if res.status == 200:
                    print("    Backend siap!")
                    return True
        except Exception:
            time.sleep(1)
    print("    ERROR: Backend tidak merespons.")
    return False

def upload_video():
    print("\n[2] Mengunggah test_speech_video.mp4...")
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    filename = os.path.basename(TEST_VIDEO_PATH)

    with open(TEST_VIDEO_PATH, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )

    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read().decode("utf-8"))
        duration = data.get("metadata", {}).get("duration_seconds", "N/A")
        print(f"    Upload berhasil! Video ID: {data['video_id']}, Durasi: {duration}s")
        return data["video_id"]

def transcribe_video(video_id):
    print(f"\n[3] Memulai transkripsi Whisper lokal untuk {video_id}...")
    req = urllib.request.Request(
        f"{BASE_URL}/api/video/{video_id}/transcribe",
        data=json.dumps({"video_id": video_id, "language": "id", "model_size": "tiny"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as res:
        job_info = json.loads(res.read().decode("utf-8"))
        job_id = job_info["job_id"]
        print(f"    Transkripsi job dijadwalkan: {job_id}")

    # Polling hingga selesai
    for _ in range(60):
        time.sleep(1)
        req = urllib.request.Request(f"{BASE_URL}/api/jobs/{job_id}")
        with urllib.request.urlopen(req) as res:
            info = json.loads(res.read().decode("utf-8"))
            if info["status"] == "completed":
                trans = info.get("transcription", {})
                print(f"    Transkripsi selesai! {len(trans.get('segments', []))} segmen ditemukan.")
                return trans
            elif info["status"] in ("failed", "cancelled"):
                raise RuntimeError(f"Transkripsi gagal: {info.get('message')}")
    raise TimeoutError("Transkripsi timeout!")

def cut_vertical_clip_with_subtitles(video_id):
    print(f"\n[4] Memotong klip vertikal 9:16 (Latar Blur) dengan Subtitle TikTok Kuning...")
    req_body = {
        "video_id": video_id,
        "clips": [
            {
                "start": 0.0,
                "end": 4.5,
                "title": "Klip Vertikal Uji 9:16"
            }
        ],
        "vertical_mode": "blur",
        "burn_subtitles": True,
        "subtitle_style": "tiktok_yellow"
    }

    req = urllib.request.Request(
        f"{BASE_URL}/api/clips/cut",
        data=json.dumps(req_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req) as res:
        job_info = json.loads(res.read().decode("utf-8"))
        job_id = job_info["job_id"]
        print(f"    Cut job dijadwalkan: {job_id}")

    # Polling hingga selesai
    for _ in range(90):
        time.sleep(1)
        req = urllib.request.Request(f"{BASE_URL}/api/jobs/{job_id}")
        with urllib.request.urlopen(req) as res:
            info = json.loads(res.read().decode("utf-8"))
            if info["status"] == "completed":
                clips = info.get("result", [])
                print(f"    Pemotongan & Burn-in selesai! {len(clips)} klip dihasilkan.")
                return clips[0]
            elif info["status"] in ("failed", "cancelled"):
                raise RuntimeError(f"Cut job gagal: {info.get('message')}")
    raise TimeoutError("Cut job timeout!")

def verify_output_clip(clip_info):
    print("\n[5] Memverifikasi resolusi, durasi, dan file subtitle companion...")
    filename = clip_info["filename"]
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "output"))
    clip_path = os.path.join(output_dir, filename)

    assert os.path.exists(clip_path), f"File video {clip_path} tidak ditemukan di disk!"
    print(f"    File MP4 ada: {clip_path} ({os.path.getsize(clip_path)} bytes)")

    # Periksa dimensi via ffprobe
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "json",
        clip_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(res.stdout)
    stream = probe_data["streams"][0]
    w = int(stream["width"])
    h = int(stream["height"])
    print(f"    Dimensi video terverifikasi: {w}x{h}")
    assert w == 1080 and h == 1920, f"Dimensi bukan 1080x1920! Didapat: {w}x{h}"

    # Verifikasi ClipInfo fields
    assert clip_info.get("is_vertical") is True, "ClipInfo.is_vertical harus True!"
    assert clip_info.get("has_subtitles") is True, "ClipInfo.has_subtitles harus True!"
    assert clip_info.get("srt_filename"), "ClipInfo.srt_filename harus ada!"

    srt_filename = clip_info["srt_filename"]
    srt_path = os.path.join(output_dir, srt_filename)
    assert os.path.exists(srt_path), f"File SRT {srt_path} tidak ditemukan di disk!"
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()
    print(f"    File SRT ada: {srt_filename} ({len(srt_content)} karakter)")
    assert "-->" in srt_content, "SRT tidak berisi penanda timestamp --> !"
    print(f"    Contoh baris SRT:\n{srt_content.strip()[:150]}...")

    # Uji unduh SRT dari endpoint API
    sub_url = f"{BASE_URL}/api/clips/{filename}/subtitles"
    with urllib.request.urlopen(sub_url) as res:
        assert res.status == 200
        downloaded_srt = res.read().decode("utf-8")
        assert len(downloaded_srt) > 0
        print(f"    Endpoint GET /api/clips/{filename}/subtitles mengembalikan 200 OK ({len(downloaded_srt)} bytes)")

def test_open_output_folder_endpoint():
    print("\n[6] Menguji endpoint POST /api/open-output-folder...")
    req = urllib.request.Request(
        f"{BASE_URL}/api/open-output-folder",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        print(f"    Respons: {data['message']} (Path: {data['folder_path']})")

if __name__ == "__main__":
    try:
        assert wait_for_server()
        vid = upload_video()
        trans = transcribe_video(vid)
        clip = cut_vertical_clip_with_subtitles(vid)
        verify_output_clip(clip)
        test_open_output_folder_endpoint()
        print("\n==========================================")
        print(" SEMUA UJI FASE 5 BERHASIL (100% LOLOS) ")
        print("==========================================")
    except Exception as e:
        print(f"\n[GAGAL] Error saat menjalankan tes: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
