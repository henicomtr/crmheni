"""
Admin bildirim sesini (notify.wav) yeniden üretmek için yerel script.

Kullanım:
    python tools/generate_notify_wav.py

Ses parametrelerini değiştirdikten sonra:
1. Bu scripti çalıştır
2. templates/admin_layout.html içindeki ?v= numarasını artır
3. Commit + push
"""

import wave, struct, math, os

# --- Ses parametreleri ---
SAMPLE_RATE = 22050
# (frekans_hz, başlangıç_saniye, süre_saniye)
TONES = [
    (880, 0.0,  0.22),
    (660, 0.30, 0.22),
]
TOTAL_DURATION = 0.60
AMPLITUDE = 0.55
# -------------------------

def generate(output_path):
    total_frames = int(SAMPLE_RATE * TOTAL_DURATION)
    samples = []

    for i in range(total_frames):
        s = 0.0
        for freq, start_sec, dur_sec in TONES:
            sf = int(start_sec * SAMPLE_RATE)
            ef = sf + int(dur_sec * SAMPLE_RATE)
            if sf <= i < ef:
                ti = i - sf
                fade_in  = min(ti / (SAMPLE_RATE * 0.02), 1.0)
                fade_out = min((ef - i) / (SAMPLE_RATE * 0.04), 1.0)
                s += math.sin(2 * math.pi * freq * ti / SAMPLE_RATE) * AMPLITUDE * fade_in * fade_out
        samples.append(max(-32767, min(32767, int(s * 32767))))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    print(f"Oluşturuldu: {output_path} ({os.path.getsize(output_path)} bytes)")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    generate(os.path.join(root, "static", "sounds", "notify.wav"))
