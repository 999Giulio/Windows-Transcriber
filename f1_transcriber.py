"""F1 Radio Live Transcriber (revised for lower latency and better audio capture)

Captures Windows output audio with WASAPI loopback and displays local Whisper
transcriptions in an always-on-top window.

Run on Windows with:
    python f1_transcriber_improved.py
"""

import os
import queue
import threading
import tkinter as tk
from collections import deque

import numpy as np
import pyaudiowpatch as pyaudio
from faster_whisper import WhisperModel

# ----------------------------- Settings ---------------------------------
# English-only model is a good balance for F1 broadcasts. If it is still too
# slow on this PC, change to "tiny.en" for speed (with a possible accuracy loss).
MODEL_SIZE = "base.en"
LANGUAGE = "en"
WHISPER_RATE = 16000
CHUNK_SECONDS = 0.1

# More sensitive than the original settings, so quieter syllables are less
# likely to be discarded. If it segments constantly on background noise,
# increase SILENCE_THRESHOLD slightly (e.g. to 0.005).
SILENCE_THRESHOLD = 0.004
SILENCE_SECONDS = 0.45
MIN_SPEECH_SECONDS = 0.3
MAX_SEGMENT_SECONDS = 7
PRE_ROLL_SECONDS = 0.3
MAX_LINES_ON_SCREEN = 5

# Keep all captured segments rather than silently dropping words if the model
# temporarily falls behind. If the model is consistently slower than real time,
# choose MODEL_SIZE = "tiny.en" above.
audio_queue = queue.Queue()
text_queue = queue.Queue()
stop_event = threading.Event()


def find_loopback_device(p):
    """Find the loopback device corresponding to Windows' default output."""
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if speakers.get("isLoopbackDevice"):
        return speakers
    for loopback in p.get_loopback_device_info_generator():
        if speakers["name"] in loopback["name"]:
            return loopback
    raise RuntimeError(
        "No loopback device found for the default speakers. "
        "Check Windows Settings > System > Sound and select your usual output."
    )


def to_whisper_format(raw_bytes, channels, source_rate):
    """Convert 16-bit audio to mono float32 at Whisper's expected 16 kHz."""
    samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if source_rate != WHISPER_RATE and len(samples):
        new_length = max(1, int(len(samples) * WHISPER_RATE / source_rate))
        old_x = np.linspace(0, 1, num=len(samples), endpoint=False)
        new_x = np.linspace(0, 1, num=new_length, endpoint=False)
        samples = np.interp(new_x, old_x, samples).astype(np.float32)
    return samples


def capture_loop():
    """Capture output audio and send speech-like segments to the model."""
    p = pyaudio.PyAudio()
    stream = None
    try:
        device = find_loopback_device(p)
        channels = int(device["maxInputChannels"])
        rate = int(device["defaultSampleRate"])
        frames_per_chunk = max(1, int(rate * CHUNK_SECONDS))

        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            frames_per_buffer=frames_per_chunk,
            input=True,
            input_device_index=device["index"],
        )

        pre_roll_chunks = max(1, int(PRE_ROLL_SECONDS / CHUNK_SECONDS))
        pre_roll = deque(maxlen=pre_roll_chunks)
        segment = []
        silent_chunks = 0
        silence_limit = max(1, int(SILENCE_SECONDS / CHUNK_SECONDS))
        max_chunks = max(1, int(MAX_SEGMENT_SECONDS / CHUNK_SECONDS))
        min_chunks = max(1, int(MIN_SPEECH_SECONDS / CHUNK_SECONDS))

        while not stop_event.is_set():
            raw = stream.read(frames_per_chunk, exception_on_overflow=False)
            chunk = to_whisper_format(raw, channels, rate)
            loudness = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0

            if not segment:
                if loudness > SILENCE_THRESHOLD:
                    # Keep a little audio before the threshold crossing to help
                    # preserve the beginnings of quieter words.
                    segment = list(pre_roll)
                    segment.append(chunk)
                    silent_chunks = 0
                    pre_roll.clear()
                else:
                    pre_roll.append(chunk)
                    continue
            else:
                segment.append(chunk)
                if loudness > SILENCE_THRESHOLD:
                    silent_chunks = 0
                else:
                    silent_chunks += 1

            segment_finished = (
                silent_chunks >= silence_limit or len(segment) >= max_chunks
            )
            if segment_finished:
                speech_chunks = len(segment) - silent_chunks
                if speech_chunks >= min_chunks:
                    audio_queue.put(np.concatenate(segment).astype(np.float32, copy=False))
                segment = []
                silent_chunks = 0
                pre_roll.clear()

    except Exception as error:
        text_queue.put(f"[Audio error] {error}")
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        p.terminate()


def transcribe_loop():
    """Transcribe each captured segment."""
    text_queue.put("Loading English speech model (first run downloads it)...")
    try:
        cpu_threads = max(2, min(8, os.cpu_count() or 4))
        model = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
            num_workers=1,
        )
    except Exception as error:
        text_queue.put(f"[Model error] {error}")
        return

    text_queue.put("Listening for PC audio...")
    while not stop_event.is_set():
        try:
            audio = audio_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            segments, _info = model.transcribe(
                audio,
                language=LANGUAGE,
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = " ".join(part.text.strip() for part in segments).strip()
            if text:
                text_queue.put(text)
        except Exception as error:
            text_queue.put(f"[Transcription error] {error}")


class Overlay:
    def __init__(self, root):
        self.root = root
        self.lines = []
        root.title("F1 Radio Live Transcriber")
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.9)
        root.configure(bg="#111111")
        root.geometry("760x210+100+100")

        self.label = tk.Label(
            root,
            text="Starting...",
            bg="#111111",
            fg="#ffffff",
            font=("Segoe UI", 15),
            justify="left",
            anchor="sw",
            wraplength=730,
            padx=12,
            pady=10,
        )
        self.label.pack(fill="both", expand=True)
        self.label.bind("<ButtonPress-1>", self.start_drag)
        self.label.bind("<B1-Motion>", self.do_drag)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    def start_drag(self, event):
        self._dx, self._dy = event.x, event.y

    def do_drag(self, event):
        x = self.root.winfo_x() + event.x - self._dx
        y = self.root.winfo_y() + event.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def poll(self):
        updated = False
        while True:
            try:
                self.lines.append(text_queue.get_nowait())
                updated = True
            except queue.Empty:
                break
        if updated:
            self.lines = self.lines[-MAX_LINES_ON_SCREEN:]
            self.label.config(text="\n".join(self.lines))
        self.root.after(100, self.poll)

    def close(self):
        stop_event.set()
        self.root.destroy()


def main():
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=transcribe_loop, daemon=True).start()
    root = tk.Tk()
    Overlay(root)
    root.mainloop()


if __name__ == "__main__":
    main()
