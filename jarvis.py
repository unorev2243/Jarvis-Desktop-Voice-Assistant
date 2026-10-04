import jarvis_v2 as j

# Movie-inspired choice: deep male US English, local/offline.
j.VOICE = j.MODEL / "en_US-norman-medium.onnx"
j.VOICE_JSON = j.MODEL / "en_US-norman-medium.onnx.json"
j.VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/norman/medium/en_US-norman-medium.onnx?download=true"
j.VOICE_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/norman/medium/en_US-norman-medium.onnx.json?download=true"

if __name__ == "__main__":
    j.init_dirs()
    raise SystemExit(j.App().run())
