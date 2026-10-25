"""
CliperKu - Layanan Pembuatan Subtitle (ASS & SRT).
Modul 5:
- Mengonversi timestamp tingkat kata dari Faster-Whisper menjadi subtitle ASS & SRT
- Pengelompokan kata yang nyaman dibaca (3 - 7 kata per baris/tampilan)
- Menyesuaikan timestamp relatif terhadap titik awal pemotongan klip
- Menyediakan template gaya ASS (TikTok Yellow, Clean White)
- Mendukung font Arial yang universal dan mendukung karakter bahasa Indonesia
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, Optional
from app.schemas.video import TranscriptSegment, WordTimestamp


class SubtitleService:
    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        """Mengubah detik ke format waktu ASS: H:MM:SS.cc (centiseconds)."""
        sec = max(0.0, seconds)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        cs = int(round((sec - int(sec)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Mengubah detik ke format waktu SRT: HH:MM:SS,mmm (milliseconds)."""
        sec = max(0.0, seconds)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        if ms >= 1000:
            ms = 999
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @classmethod
    def create_ass_header(cls, style: str = "tiktok_yellow", is_vertical: bool = True) -> str:
        """
        Membuat header file ASS dengan styling profesional.
        Style tiktok_yellow: teks kuning tebal, outline hitam tebal, shadow.
        Style clean_white: teks putih bersih, outline hitam halus.
        """
        res_x = 1080 if is_vertical else 1280
        res_y = 1920 if is_vertical else 720

        # Margin bawah: untuk 9:16 diangkat setinggi 300px agar tidak tertutup tombol TikTok
        margin_v = 300 if is_vertical else 50
        font_size = 56 if is_vertical else 38

        if style == "clean_white":
            primary_color = "&H00FFFFFF"  # White
            outline_color = "&H00000000"  # Black
            outline_size = 3.5
            shadow_size = 1.5
        else:
            # Default: tiktok_yellow (BGR: Blue=00, Green=FF, Red=FF)
            primary_color = "&H0000FFFF"  # Bright Yellow
            outline_color = "&H00000000"  # Black
            outline_size = 4.5
            shadow_size = 2.0

        header = f"""[Script Info]
Title: CliperKu Auto Subtitles
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default, Arial, {font_size}, {primary_color}, &H000000FF, {outline_color}, &H80000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, {outline_size}, {shadow_size}, 2, 40, 40, {margin_v}, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        return header

    @classmethod
    def generate_subtitles_for_clip(
        cls,
        segments: List[TranscriptSegment],
        clip_start: float,
        clip_end: float,
        style: str = "tiktok_yellow",
        is_vertical: bool = True,
        custom_text: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Menghasilkan konten subtitle ASS dan SRT untuk rentang klip tertentu.
        Timestamp disesuaikan relatif terhadap detik awal klip (0.00s).
        Mengelompokkan 3 - 6 kata per event agar nyaman dibaca.
        Mengembalikan: (ass_content, srt_content)
        """
        clip_duration = clip_end - clip_start
        events_ass: List[str] = []
        events_srt: List[str] = []
        srt_counter = 1

        # Jika pengguna menyediakan teks kustom pengganti
        if custom_text:
            text_lines = [l.strip() for l in custom_text.splitlines() if l.strip()]
            if not text_lines:
                text_lines = [custom_text.strip()]

            line_dur = clip_duration / max(1, len(text_lines))
            for i, line in enumerate(text_lines):
                t_start = i * line_dur
                t_end = min((i + 1) * line_dur, clip_duration)
                ass_start = cls._format_ass_time(t_start)
                ass_end = cls._format_ass_time(t_end)
                events_ass.append(f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{line}")

                srt_start = cls._format_srt_time(t_start)
                srt_end = cls._format_srt_time(t_end)
                events_srt.append(f"{srt_counter}\n{srt_start} --> {srt_end}\n{line}\n")
                srt_counter += 1

            ass_full = cls.create_ass_header(style, is_vertical) + "\n".join(events_ass)
            srt_full = "\n".join(events_srt)
            return ass_full, srt_full

        # Kumpulkan semua kata yang berada di dalam rentang klip
        clip_words: List[WordTimestamp] = []
        for seg in segments:
            # Lewati segmen yang di luar rentang klip
            if seg.end < clip_start or seg.start > clip_end:
                continue

            if seg.words:
                for w in seg.words:
                    if w.end >= clip_start and w.start <= clip_end:
                        clip_words.append(w)
            else:
                # Jika word-level timestamps kosong, buat estimasi per kata dari teks segmen
                words_raw = seg.text.strip().split()
                if words_raw:
                    seg_dur = max(0.1, seg.end - seg.start)
                    w_dur = seg_dur / len(words_raw)
                    for idx, wrd in enumerate(words_raw):
                        w_st = seg.start + (idx * w_dur)
                        w_en = w_st + w_dur
                        if w_en >= clip_start and w_st <= clip_end:
                            clip_words.append(WordTimestamp(word=wrd, start=w_st, end=w_en, probability=1.0))

        if not clip_words:
            # Fallback jika tidak ada kata terdeteksi
            ass_full = cls.create_ass_header(style, is_vertical)
            return ass_full, ""

        # Kelompokkan kata-kata menjadi chunk 3 - 5 kata per tampilan
        chunk_size = 4
        i = 0
        while i < len(clip_words):
            chunk = clip_words[i:i + chunk_size]
            t_start = max(0.0, chunk[0].start - clip_start)
            t_end = min(clip_duration, chunk[-1].end - clip_start)

            # Jaga durasi tampilan minimal 0.8 detik agar tidak berkedip terlalu cepat
            if (t_end - t_start) < 0.8:
                t_end = min(clip_duration, t_start + 0.8)

            chunk_text = " ".join(w.word for w in chunk)

            ass_start = cls._format_ass_time(t_start)
            ass_end = cls._format_ass_time(t_end)
            events_ass.append(f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{chunk_text}")

            srt_start = cls._format_srt_time(t_start)
            srt_end = cls._format_srt_time(t_end)
            events_srt.append(f"{srt_counter}\n{srt_start} --> {srt_end}\n{chunk_text}\n")

            srt_counter += 1
            i += len(chunk)

        ass_full = cls.create_ass_header(style, is_vertical) + "\n".join(events_ass)
        srt_full = "\n".join(events_srt)
        return ass_full, srt_full

