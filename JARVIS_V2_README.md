# JARVIS Desktop Assistant

A tray-first Windows voice assistant with a cinematic orb interface.

## Controls
- Hold **Ctrl+Shift** to talk.
- Release the keys to stop recording.
- When Windows appears to have a text input focused, JARVIS pastes cleaned dictation there automatically.
- Otherwise it answers in the overlay and speaks the response.

## Voice
The default voice engine is local **Piper TTS** using the high-quality `en_US-lessac-high` model. Piper is a fast local neural TTS engine for Windows, and the application downloads the model on first run rather than requiring a subscription.

## AI brain
The included build can use a local Ollama endpoint. Configure the model in `%LOCALAPPDATA%\JARVIS\config.json`. Without Ollama, the assistant still handles common Windows actions, URL opening, web search, date/time and dictation.

## Provider hooks
The architecture is deliberately provider-neutral so ElevenLabs or Higgsfield can be added as premium voice backends later without replacing the UI or automation layer.

## Build
The GitHub Actions workflow builds a Windows `JARVIS.exe` artifact on pushes to the JARVIS v2 branch.
