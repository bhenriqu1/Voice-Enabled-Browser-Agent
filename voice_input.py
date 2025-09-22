"""
Voice input module using Deepgram for speech-to-text conversion (Deepgram SDK v4)
"""
import asyncio
import inspect
import logging
from typing import Optional, Callable, Tuple

from deepgram import DeepgramClient, LiveTranscriptionEvents
from config import settings

# Try to import pyaudio, but make it optional
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError as e:
    logging.warning(f"PyAudio not available: {e}. Voice input will be limited.")
    PYAUDIO_AVAILABLE = False
    pyaudio = None

logger = logging.getLogger(__name__)


class VoiceInputHandler:
    """Handles live voice input capture and transcription using Deepgram (v4 websocket)."""

    def __init__(self):
        self.deepgram = DeepgramClient(settings.deepgram_api_key)
        self.is_listening: bool = False
        self.audio_stream = None
        self.websocket = None
        self._on_transcription_callback: Optional[Callable[[str], None]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # main loop for thread-safe dispatch

    async def start_listening(self, on_transcription: Callable[[str], None]) -> None:
        """Start listening for voice input and transcribe it."""
        try:
            if not PYAUDIO_AVAILABLE:
                raise Exception("PyAudio is not available. Please install it or use file-based input.")

            # Capture main loop for thread-safe callback dispatch
            self._loop = asyncio.get_running_loop()

            # Save callback
            self._on_transcription_callback = on_transcription

            # Configure audio stream (16kHz mono PCM)
            self.audio_stream = pyaudio.PyAudio()
            stream = self.audio_stream.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024,
            )

            # Deepgram v4 live options must be a plain dict
            options = {
                "model": "nova-2",
                "language": settings.voice_language,
                "smart_format": True,
                "interim_results": True,
                "encoding": "linear16",   # matches PyAudio paInt16
                "sample_rate": 16000,
                "channels": 1,
            }

            # Start live transcription using websocket API (v1)
            self.websocket = self.deepgram.listen.websocket.v("1")

            # Attach event handlers — Deepgram v4 passes (client, payload, ...)
            self.websocket.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
            self.websocket.on(LiveTranscriptionEvents.Error, self._on_error)
            self.websocket.on(LiveTranscriptionEvents.Close, self._on_close)

            # Start the connection
            if not self.websocket.start(options):
                raise Exception("Failed to start Deepgram connection")

            self.is_listening = True
            logger.info("Voice input started. Speak now...")

            # Start audio streaming loop (until stop_listening)
            await self._stream_audio(stream)

        except Exception as e:
            logger.error(f"Error starting voice input: {e}")
            await self.stop_listening()
            raise

    def _ws_connected(self) -> bool:
        """Handle SDK variations for the 'connected' check."""
        if not self.websocket:
            return False
        attr = getattr(self.websocket, "is_connected", None)
        if callable(attr):
            return bool(attr())
        if attr is not None:
            return bool(attr)
        return bool(getattr(self.websocket, "connected", False))

    async def _stream_audio(self, stream) -> None:
        """Stream audio data to Deepgram."""
        try:
            while self.is_listening:
                data = stream.read(1024, exception_on_overflow=False)
                if self._ws_connected():
                    self.websocket.send(data)
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error streaming audio: {e}")
        finally:
            try:
                stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    # -------- Event handlers (Deepgram v4 signatures) --------

    def _extract_final_transcript(self, result) -> Tuple[bool, str]:
        """
        Accepts either Deepgram v4 typed LiveResultResponse or a dict.
        Returns (is_final, transcript_text).
        """
        # Typed-object path
        try:
            is_final = bool(getattr(result, "is_final"))
            channel = getattr(result, "channel", None)
            if channel and hasattr(channel, "alternatives") and channel.alternatives:
                transcript = (channel.alternatives[0].transcript or "").strip()
            else:
                transcript = ""
            return is_final, transcript
        except Exception:
            # Dict-like fallback
            if isinstance(result, dict):
                is_final = bool(result.get("is_final", False))
                alts = (result.get("channel", {}) or {}).get("alternatives", []) or []
                transcript = (alts[0].get("transcript", "") if alts else "").strip()
                return is_final, transcript
            return False, ""

    def _dispatch_transcript(self, transcript: str) -> None:
        """
        Runs the on_transcription callback on the main asyncio loop, even though
        this handler is called from a background thread. Supports sync or async callbacks.
        """
        cb = self._on_transcription_callback
        if not cb:
            return

        loop = self._loop
        if loop is None:
            # Fallback if not set (shouldn't happen)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop_policy().get_event_loop()

        if inspect.iscoroutinefunction(cb):
            asyncio.run_coroutine_threadsafe(cb(transcript), loop)
        else:
            loop.call_soon_threadsafe(cb, transcript)

    def _on_transcript(self, _client, result, *args, **kwargs) -> None:
        """Handle transcription results from Deepgram."""
        try:
            is_final, transcript = self._extract_final_transcript(result)
            if is_final and transcript:
                logger.info(f"Transcription: {transcript}")
                self._dispatch_transcript(transcript)
        except Exception as e:
            logger.error(f"Error processing transcript: {e}")

    def _on_error(self, _client, error, *args, **kwargs) -> None:
        logger.error(f"Deepgram error: {error}")

    def _on_close(self, _client=None, *args, **kwargs) -> None:
        logger.info("Deepgram websocket closed.")

    async def stop_listening(self) -> None:
        """Stop listening for voice input and clean up resources."""
        self.is_listening = False

        if self.websocket:
            try:
                self.websocket.finish()
            except Exception:
                pass
            self.websocket = None

        if self.audio_stream:
            try:
                self.audio_stream.terminate()
            except Exception:
                pass
            self.audio_stream = None

        logger.info("Voice input stopped")


class VoiceRecorder:
    """Simple voice recorder for testing and manual input."""

    def __init__(self):
        if not PYAUDIO_AVAILABLE:
            raise Exception("PyAudio is not available. Cannot create voice recorder.")
        self.audio = pyaudio.PyAudio()

    def record_audio(self, duration: int = 5) -> bytes:
        """Record audio for specified duration (returns raw PCM 16-bit mono @16k)."""
        stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024,
        )
        frames = []
        for _ in range(0, int(16000 / 1024 * duration)):
            data = stream.read(1024)
            frames.append(data)
        try:
            stream.stop_stream()
        finally:
            stream.close()
        return b"".join(frames)

    def cleanup(self):
        """Clean up audio resources"""
        self.audio.terminate()


async def transcribe_audio_file(audio_data: bytes) -> str:
    """Transcribe audio data using Deepgram prerecorded API."""
    try:
        deepgram = DeepgramClient(settings.deepgram_api_key)
        response = deepgram.listen.prerecorded.v("1").transcribe_file(
            audio_data,
            {
                "model": "nova-2",
                "language": settings.voice_language,
                "smart_format": True,
            },
        )
        transcript = response.results.channels[0].alternatives[0].transcript
        return transcript.strip()
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        return ""
