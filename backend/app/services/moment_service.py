"""
CliperKu - Layanan Penilaian Momen Menarik (Moment Scoring Engine).
Modul 3:
- Mengidentifikasi kandidat klip dengan batas kalimat utuh (tanpa memotong di tengah kalimat)
- Menilai setiap kandidat dengan bobot 0 - 100 berdasarkan 5 kriteria utama:
  1. Hook / daya tarik awal (20)
  2. Kelengkapan konteks dan struktur awal-isi-akhir (25)
  3. Nilai informasi, cerita, atau pertanyaan (20)
  4. Kejelasan ucapan (10)
  5. Durasi sesuai (10)
  Pengurang (penalti): jeda berlebihan / kalimat terpotong (hingga -15)
- Menghasilkan judul ringkas dan alasan rekomendasi yang jelas
- Menyaring duplikasi momen (overlap filtering)
"""

import re
import uuid
from typing import List, Tuple, Optional
from app.schemas.video import (
    TranscriptionResult,
    TranscriptSegment,
    MomentCandidate,
    CandidateStatus,
    ScoreBreakdown
)

# Kata kunci untuk Hook pembuka (Indonesia & English)
HOOK_QUESTIONS = {
    "mengapa", "kenapa", "bagaimana", "apa yang", "tahukah kamu", "tahukah anda",
    "pernahkah", "siapa yang", "kapan", "apakah", "gimana", "kenapa ya",
    "why", "how", "what if", "did you know", "have you ever", "who", "when", "can you"
}

HOOK_TRIGGERS = {
    "ternyata", "rahasia", "kuncinya", "masalahnya", "faktanya", "yang penting",
    "jangan sampai", "kamu harus", "coba bayangkan", "yang paling menarik",
    "sebenarnya", "inilah alasan", "banyak orang salah", "kesalahan terbesar",
    "actually", "the secret", "the truth is", "the biggest mistake", "the problem is",
    "the key is", "you need to know", "imagine if", "here is why"
}

# Kata kunci nilai informasi / edukasi / cerita
VALUE_KEYWORDS = {
    "cara", "tips", "trik", "langkah", "belajar", "hasil", "solusi", "strategi",
    "pengalaman", "contoh", "metode", "rahasia", "teknik", "formula", "manfaat",
    "how to", "tutorial", "guide", "steps", "strategy", "example", "experience",
    "method", "solution", "result", "benefit", "technique", "system"
}

# Kata kunci penutup / konklusi
CONCLUSION_KEYWORDS = {
    "jadi", "kesimpulannya", "intinya", "itulah mengapa", "kesimpulan", "akhirnya",
    "in conclusion", "that's why", "so basically", "the takeaway is", "to summarize"
}

# Kata sambung yang menandakan kalimat belum selesai (menggantung) jika berada di akhir
HANGING_WORDS = {
    "dan", "atau", "tapi", "karena", "sehingga", "namun", "yaitu", "bahwa",
    "dengan", "untuk", "kalau", "jika", "supaya", "agar", "tetapi",
    "and", "or", "but", "because", "so", "that", "with", "if", "though", "although"
}


class MomentService:
    @staticmethod
    def _calculate_overlap(start1: float, end1: float, start2: float, end2: float) -> float:
        """Menghitung Intersection over Union (IoU) antara dua rentang waktu."""
        intersection = max(0.0, min(end1, end2) - max(start1, start2))
        union = max(end1, end2) - min(start1, start2)
        if union <= 0:
            return 0.0
        return intersection / union

    @staticmethod
    def _generate_title(text: str) -> str:
        """Membuat judul ringkas 4-8 kata dari teks momen."""
        clean = re.sub(r'[^\w\s]', '', text).strip()
        words = clean.split()
        if not words:
            return "Klip Menarik"

        # Ambil 5-7 kata pertama
        title_words = words[:min(7, len(words))]
        title = " ".join(title_words).capitalize()
        if len(words) > 7:
            title += "..."
        return title

    @classmethod
    def score_window(
        cls,
        segments: List[TranscriptSegment],
        total_video_duration: float
    ) -> Tuple[int, ScoreBreakdown, str]:
        """
        Menghitung skor kualitas momen (0 - 100) dan menyusun alasan.
        """
        if not segments:
            return 0, ScoreBreakdown(
                hook_score=0, context_score=0, value_score=0,
                clarity_score=0, duration_score=0, penalty=0
            ), "Segmen kosong."

        full_text = " ".join(s.text.strip() for s in segments)
        lower_text = full_text.lower()
        duration = segments[-1].end - segments[0].start

        first_seg_text = segments[0].text.strip().lower()
        last_seg_text = segments[-1].text.strip().lower()

        # ----------------------------------------------------
        # 1. Hook / Daya Tarik Awal (Maks 20 poin)
        # ----------------------------------------------------
        hook_pts = 4  # Poin dasar permulaan
        reasons_pos = []

        # Deteksi pertanyaan di awal
        has_question_hook = any(q in first_seg_text for q in HOOK_QUESTIONS) or first_seg_text.endswith("?")
        if has_question_hook:
            hook_pts += 9
            reasons_pos.append("diawali pertanyaan interaktif yang memancing rasa ingin tahu")
        
        # Deteksi trigger kata pembuka menarik
        has_trigger_hook = any(t in first_seg_text for t in HOOK_TRIGGERS)
        if has_trigger_hook:
            hook_pts += 7
            reasons_pos.append("memiliki kalimat pembuka (hook) yang menarik perhatian")

        hook_score = min(20, hook_pts)

        # ----------------------------------------------------
        # 2. Kelengkapan Konteks & Struktur (Maks 25 poin)
        # ----------------------------------------------------
        context_pts = 6

        # Kalimat penutup rapi (tanda titik/tanya/seru)
        last_char = segments[-1].text.strip()[-1] if segments[-1].text.strip() else ""
        if last_char in {".", "!", "?"}:
            context_pts += 8

        # Deteksi kata gantung di akhir kalimat
        last_words = last_seg_text.split()
        is_hanging = False
        if last_words:
            clean_last_word = re.sub(r'[^\w]', '', last_words[-1])
            if clean_last_word in HANGING_WORDS:
                is_hanging = True

        if not is_hanging:
            context_pts += 6
        
        # Deteksi kata kesimpulan di segmen akhir
        if any(c in last_seg_text for c in CONCLUSION_KEYWORDS):
            context_pts += 5
            reasons_pos.append("memiliki konklusi pesan yang tuntas")

        context_score = min(25, context_pts)

        # ----------------------------------------------------
        # 3. Nilai Informasi, Cerita, atau Pertanyaan (Maks 20 poin)
        # ----------------------------------------------------
        value_pts = 5
        matched_values = [v for v in VALUE_KEYWORDS if v in lower_text]
        if matched_values:
            value_pts += min(9, len(matched_values) * 3)
            reasons_pos.append("mengandung wawasan atau tips praktis")

        # Deteksi angka atau data spesifik
        if re.search(r'\b\d+\b|persen|%|pertama|kedua|ketiga', lower_text):
            value_pts += 6

        value_score = min(20, value_pts)

        # ----------------------------------------------------
        # 4. Kejelasan Ucapan (Maks 10 poin)
        # ----------------------------------------------------
        # Ambil rata-rata probability kata-kata
        all_probs = []
        for s in segments:
            for w in s.words:
                all_probs.append(w.probability)
        
        avg_prob = sum(all_probs) / len(all_probs) if all_probs else 0.9
        if avg_prob >= 0.85:
            clarity_score = 10
        elif avg_prob >= 0.70:
            clarity_score = 8
        elif avg_prob >= 0.50:
            clarity_score = 6
        else:
            clarity_score = 4

        # ----------------------------------------------------
        # 5. Kesesuaian Durasi (Maks 10 poin)
        # ----------------------------------------------------
        if 20 <= duration <= 45:
            duration_score = 10
            reasons_pos.append("durasi sangat ideal untuk TikTok/Reels/Shorts")
        elif 15 <= duration < 20 or 45 < duration <= 60:
            duration_score = 8
        elif duration < 15 and duration >= 8:
            duration_score = 6
        else:
            duration_score = 4

        # ----------------------------------------------------
        # 6. Pengurang / Penalti (Maks -15 poin)
        # ----------------------------------------------------
        penalty = 0

        # Penalti jika kalimat gantung di akhir
        if is_hanging:
            penalty += 6

        # Deteksi jeda hening antar segmen di dalam klip
        max_silence = 0.0
        for i in range(len(segments) - 1):
            silence_gap = segments[i + 1].start - segments[i].end
            if silence_gap > max_silence:
                max_silence = silence_gap

        if max_silence > 3.0:
            penalty += 8
        elif max_silence > 1.8:
            penalty += 4

        penalty = min(15, penalty)

        # ----------------------------------------------------
        # Total Skor Akhir (0 - 100)
        # ----------------------------------------------------
        raw_total = hook_score + context_score + value_score + clarity_score + duration_score - penalty
        final_score = max(0, min(100, raw_total))

        # Bentuk alasan ringkas
        if reasons_pos:
            alasan = "Kandidat ini " + ", ".join(reasons_pos[:2]) + "."
        else:
            alasan = "Alur ucapan terhubung secara wajar dan konteks kalimat utuh."

        if is_hanging:
            alasan += " Catatan: kalimat penutup mungkin sedikit bersambung."

        breakdown = ScoreBreakdown(
            hook_score=hook_score,
            context_score=context_score,
            value_score=value_score,
            clarity_score=clarity_score,
            duration_score=duration_score,
            penalty=penalty
        )

        return final_score, breakdown, alasan

    @classmethod
    def generate_candidates(
        cls,
        transcription: TranscriptionResult,
        min_duration: int = 15,
        max_duration: int = 60,
        target_clips: int = 5
    ) -> List[MomentCandidate]:
        """
        Membentuk kandidat-kandidat momen dari segmen transkripsi dengan sliding window
        berbasis kalimat utuh, menilainya, dan mengeliminasi overlap tinggi.
        """
        segments = transcription.segments
        if not segments:
            return []

        total_dur = transcription.duration
        raw_candidates: List[MomentCandidate] = []

        # Jika durasi video pendek (< min_duration), jadikan seluruh segmen sebagai 1 kandidat
        if total_dur < min_duration or len(segments) <= 2:
            skor, breakdown, alasan = cls.score_window(segments, total_dur)
            full_txt = " ".join(s.text.strip() for s in segments)
            return [
                MomentCandidate(
                    id=str(uuid.uuid4())[:8],
                    start=segments[0].start,
                    end=segments[-1].end,
                    duration=round(segments[-1].end - segments[0].start, 2),
                    judul=cls._generate_title(full_txt),
                    skor=skor,
                    alasan=alasan,
                    status=CandidateStatus.MENUNGGU,
                    text=full_txt,
                    breakdown=breakdown
                )
            ]

        # Sliding window berbasis segmen kalimat
        n = len(segments)
        for i in range(n):
            current_window: List[TranscriptSegment] = []
            for j in range(i, n):
                current_window.append(segments[j])
                win_dur = current_window[-1].end - current_window[0].start

                # Jika durasi masuk dalam jendela yang diizinkan
                if min_duration <= win_dur <= max_duration:
                    skor, breakdown, alasan = cls.score_window(current_window, total_dur)
                    win_text = " ".join(s.text.strip() for s in current_window)

                    cand = MomentCandidate(
                        id=str(uuid.uuid4())[:8],
                        start=round(current_window[0].start, 2),
                        end=round(current_window[-1].end, 2),
                        duration=round(win_dur, 2),
                        judul=cls._generate_title(win_text),
                        skor=skor,
                        alasan=alasan,
                        status=CandidateStatus.MENUNGGU,
                        text=win_text,
                        breakdown=breakdown
                    )
                    raw_candidates.append(cand)

                # Jika sudah melampaui max_duration, hentikan perluasan window dari titik i
                if win_dur > max_duration:
                    break

        # Jika tidak ada yang masuk rentang durasi ketat (misal segmen jarang), ambil window terbaik
        if not raw_candidates:
            # Fallback gabungkan beberapa segmen pertama
            skor, breakdown, alasan = cls.score_window(segments, total_dur)
            win_text = " ".join(s.text.strip() for s in segments)
            return [
                MomentCandidate(
                    id=str(uuid.uuid4())[:8],
                    start=segments[0].start,
                    end=segments[-1].end,
                    duration=round(segments[-1].end - segments[0].start, 2),
                    judul=cls._generate_title(win_text),
                    skor=skor,
                    alasan=alasan,
                    status=CandidateStatus.MENUNGGU,
                    text=win_text,
                    breakdown=breakdown
                )
            ]

        # Urutkan kandidat berdasarkan skor tertinggi
        raw_candidates.sort(key=lambda c: c.skor, reverse=True)

        # Deduplikasi: Buang kandidat yang memiliki overlap waktu tinggi (> 60%) dengan kandidat skor lebih tinggi
        selected: List[MomentCandidate] = []
        for cand in raw_candidates:
            has_major_overlap = False
            for sel in selected:
                overlap = cls._calculate_overlap(cand.start, cand.end, sel.start, sel.end)
                if overlap > 0.55:  # Overlap lebih dari 55%
                    has_major_overlap = True
                    break

            if not has_major_overlap:
                selected.append(cand)

            if len(selected) >= target_clips:
                break

        # Jika deduplikasi menghasilkan terlalu sedikit klip, tambahkan kandidat terbaik berikutnya dengan toleransi lebih longgar
        if len(selected) < min(target_clips, 3) and len(raw_candidates) > len(selected):
            for cand in raw_candidates:
                if cand not in selected and all(cand.id != s.id for s in selected):
                    selected.append(cand)
                    if len(selected) >= target_clips:
                        break

        # Urutkan kandidat terpilih berdasarkan waktu mulai kronologis atau tetap skor
        return selected

