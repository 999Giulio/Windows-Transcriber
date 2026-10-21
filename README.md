# F1 Radio Live Transcriber

A Windows desktop prototype that captures audio playing through your PC and displays speech recognized by Faster-Whisper in a small, always-on-top window. It is intended for experimenting with live transcription of F1 broadcasts and other English audio.

> **Current limitation:** The app transcribes the audio mix coming from your selected Windows output device. It does not isolate Formula 1 team radio from commentary, and transcription may lag or miss words—especially when the audio is noisy or the CPU cannot keep up.

## Features

- Captures Windows output audio using WASAPI loopback through PyAudioWPatch.
- Converts captured audio into mono 16 kHz samples for the speech-recognition model.
- Uses an RMS loudness threshold and silence timing to split audio into segments.
- Keeps a short pre-roll buffer to help preserve the beginning of speech.
- Transcribes English audio locally with Faster-Whisper using the `base.en` model on the CPU.
- Displays recent transcription lines in a movable, semi-transparent, always-on-top Tkinter window.
- Uses separate threads and queues for audio capture, transcription, and display updates.

## Requirements

- Windows 10 or Windows 11
- 64-bit Python 3.10 or newer recommended
- An internet connection on first launch so Faster-Whisper can download the selected model
- A working Windows audio output device

`tkinter` is normally included with the standard Windows Python installer. The Python packages used by this project are listed in `requirements.txt`.

## Setup

Open PowerShell or Command Prompt in this project folder.

### 1. (Recommended) Create a virtual environment

```powershell
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If you are using Command Prompt instead, activate it with:

```cmd
.venv\Scripts\activate.bat
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Run the app

```powershell
python f1_transcriber.py
```

On first launch, the app downloads the Faster-Whisper model. The floating window should show a loading message and then indicate that it is listening for PC audio. Play audio through your normal Windows output device to test it. Close the overlay window to stop the app.

## How it works

1. **Capture:** The audio thread finds the loopback device associated with the default Windows output and reads small audio chunks.
2. **Prepare:** NumPy converts the raw samples to floating-point audio, downmixes stereo to mono when needed, and resamples to 16 kHz.
3. **Segment:** The app measures each chunk's RMS loudness. A threshold and silence timer decide when a segment is ready; a maximum segment length prevents a segment from continuing indefinitely. A short pre-roll buffer can retain audio from just before speech is detected.
4. **Transcribe:** A worker thread pulls audio segments from `audio_queue` and passes them to Faster-Whisper.
5. **Display:** Recognized text is placed in `text_queue` and the Tkinter window periodically checks the queue and updates its text.

The queues allow audio capture to continue while the model is busy. They do not make transcription instantaneous; if the model processes audio more slowly than it arrives, the app can fall behind.

## Configuration

The main settings are near the top of `f1_transcriber.py`:

| Setting | What it controls |
| --- | --- |
| `MODEL_SIZE` | Speech model. `base.en` is the current default; `tiny.en` may be faster but can be less accurate. |
| `LANGUAGE` | Transcription language (`en` by default). |
| `SILENCE_THRESHOLD` | RMS loudness threshold used during segmentation. A lower value captures quieter audio but may include more background noise. |
| `SILENCE_SECONDS` | Approximate quiet time before a segment ends. |
| `MAX_SEGMENT_SECONDS` | Maximum length of one audio segment before it is submitted for transcription. |
| `PRE_ROLL_SECONDS` | Audio retained immediately before speech is detected. |
| `MAX_LINES_ON_SCREEN` | Number of recent messages shown in the overlay. |

Changes to the threshold and timing values may affect both latency and missed/false speech detection. Adjust one setting at a time and test it with representative audio.

## Troubleshooting

### No audio is detected

- Make sure Windows is playing audio through the output device you expect.
- In **Settings → System → Sound**, check your selected output device.
- Restart the app after changing the default output device.

### Transcription is slow or falls behind

- Try changing `MODEL_SIZE` from `"base.en"` to `"tiny.en"` for faster processing, with a possible accuracy trade-off.
- Close other CPU-intensive applications.
- Keep in mind that the program processes system audio, including commentary and other sounds, rather than isolating team radio.

### Too many words are missed or background noise triggers segments

- Adjust `SILENCE_THRESHOLD` slightly. Lower values can help capture quieter speech but can also cause unwanted segments; higher values can filter more noise but may miss quiet words.
- Check the volume of the Windows output and the source broadcast.

### Model download or package errors

- Check your internet connection on first launch.
- Make sure your virtual environment is activated before installing and running the program.
- Re-run `python -m pip install -r requirements.txt` from the project folder.

## Project status

This is a personal learning project and prototype. Its transcription timing and accuracy have not been benchmarked systematically, and results depend on the broadcast audio, the selected output device, and the PC's performance.

## Privacy

Audio is captured from the selected Windows output and processed by the local Faster-Whisper model. The script does not include code to upload recorded audio to a remote transcription service. The model files are downloaded separately on first use.

