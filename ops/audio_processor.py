"""
Audio Processor for Agent OS

Handles Speech-to-Text (STT) and Text-to-Speech (TTS) operations.
Supports multiple audio formats: wav, mp3, ogg, m4a.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Configure logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"audio_processor_{logging.getLevelName(logging.INFO).lower()}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AudioProcessorError(Exception):
    """Base exception for audio processor errors"""
    pass


class APIKeyMissingError(AudioProcessorError):
    """API key is missing"""
    pass


class FileError(AudioProcessorError):
    """File operation error"""
    pass


# ===== Dependencies =====

WHISPER_AVAILABLE = False
try:
    import whisper
    WHISPER_AVAILABLE = True
    logger.info("Local Whisper model available")
except ImportError:
    logger.warning("Local Whisper model not available")

OPENAI_AVAILABLE = False
try:
    import openai
    OPENAI_AVAILABLE = True
    logger.info("OpenAI API available")
except ImportError:
    logger.warning("OpenAI API not available")

GTTS_AVAILABLE = False
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
    logger.info("gTTS available")
except ImportError:
    logger.warning("gTTS not available")

PYDUB_AVAILABLE = False
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
    logger.info("pydub available")
except ImportError:
    logger.warning("pydub not available")


# ===== Speech-to-Text =====

def transcribe_audio(
    audio_path: str,
    language: str = "ja",
    model: Optional[str] = None,
    use_local: bool = True
) -> Dict[str, Any]:
    """
    Transcribe audio file to text using Whisper.

    Args:
        audio_path: Path to audio file
        language: Language code (default: "ja" for Japanese)
        model: Model name for local whisper ("base", "small", "medium", "large")
        use_local: Use local Whisper model (fallback to API if False or unavailable)

    Returns:
        Dict with keys:
        - ok: True if transcription succeeded
        - text: Transcribed text
        - duration: Audio duration in seconds
        - language: Detected language
        - error: Error message (if failed)
    """
    logger.info(f"Transcribing audio: {audio_path} (language={language})")

    # Validate file
    path = Path(audio_path)
    if not path.exists():
        return {
            "ok": False,
            "text": None,
            "error": f"File not found: {audio_path}"
        }

    result = {
        "ok": False,
        "text": None,
        "duration": None,
        "language": language,
        "error": None,
    }

    try:
        # Get audio info first
        info = get_audio_info(audio_path)
        if not info["ok"]:
            result["error"] = info["error"]
            return result
        result["duration"] = info["duration"]

        # Try local Whisper first
        if use_local and WHISPER_AVAILABLE:
            logger.info("Using local Whisper model")
            model_name = model or "base"
            whisper_model = whisper.load_model(model_name)

            # Transcribe
            transcript = whisper_model.transcribe(
                str(path),
                language=language if language else None
            )

            result["ok"] = True
            result["text"] = transcript["text"].strip()
            if "language" in transcript:
                result["language"] = transcript["language"]

            logger.info(f"Transcription successful: {len(result['text'])} characters")
            return result

        # Try OpenAI Whisper API
        elif OPENAI_AVAILABLE and os.environ.get("OPENAI_API_KEY"):
            logger.info("Using OpenAI Whisper API")

            with open(path, "rb") as audio_file:
                transcript = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language if language else None
                )

            result["ok"] = True
            result["text"] = transcript.text.strip()

            logger.info(f"Transcription successful: {len(result['text'])} characters")
            return result

        else:
            # No available transcription method
            if not WHISPER_AVAILABLE and not (OPENAI_AVAILABLE and os.environ.get("OPENAI_API_KEY")):
                result["error"] = "No transcription method available. Install whisper or set OPENAI_API_KEY"
            elif use_local and not WHISPER_AVAILABLE:
                result["error"] = "Local Whisper not available. Install with: pip install openai-whisper"
            elif not os.environ.get("OPENAI_API_KEY"):
                result["error"] = "OPENAI_API_KEY not set"

            logger.error(result["error"])
            return result

    except Exception as e:
        error_msg = f"Transcription failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Text-to-Speech =====

def synthesize_speech(
    text: str,
    output_path: str,
    voice: str = "default",
    use_gtts: bool = True
) -> Dict[str, Any]:
    """
    Synthesize text to speech.

    Args:
        text: Text to synthesize
        output_path: Path to save audio file
        voice: Voice name (for gTTS: "ja", "en", etc.; for OpenAI: voice ID)
        use_gtts: Use gTTS (fallback to OpenAI if False or unavailable)

    Returns:
        Dict with keys:
        - ok: True if synthesis succeeded
        - path: Path to generated audio file
        - duration: Audio duration in seconds (if available)
        - error: Error message (if failed)
    """
    logger.info(f"Synthesizing speech: {len(text)} chars -> {output_path}")

    # Create output directory if needed
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "ok": False,
        "path": output_path,
        "duration": None,
        "error": None,
    }

    try:
        # Try gTTS first
        if use_gtts and GTTS_AVAILABLE:
            logger.info("Using gTTS")

            # Determine language from voice
            lang = voice if voice in ["ja", "en", "es", "fr", "de"] else "ja"

            # Create gTTS object
            tts = gTTS(text=text, lang=lang, slow=False)

            # Save to file
            tts.save(str(output_file))

            result["ok"] = True

            # Get duration
            info = get_audio_info(output_path)
            if info["ok"]:
                result["duration"] = info["duration"]

            logger.info(f"Speech synthesized successfully: {result['duration']:.2f}s")
            return result

        # Try OpenAI TTS API
        elif OPENAI_AVAILABLE and os.environ.get("OPENAI_API_KEY"):
            logger.info("Using OpenAI TTS API")

            # Map voice names
            voice_map = {
                "default": "alloy",
                "male": "echo",
                "female": "nova",
                "shimmer": "shimmer",
            }
            openai_voice = voice_map.get(voice, voice)

            if openai_voice not in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]:
                openai_voice = "alloy"

            # Generate speech
            response = openai.audio.speech.create(
                model="tts-1",
                voice=openai_voice,
                input=text
            )

            # Save to file
            response.stream_to_file(str(output_file))

            result["ok"] = True

            # Get duration
            info = get_audio_info(output_path)
            if info["ok"]:
                result["duration"] = info["duration"]

            logger.info(f"Speech synthesized successfully: {result['duration']:.2f}s")
            return result

        else:
            # No available synthesis method
            if not GTTS_AVAILABLE and not (OPENAI_AVAILABLE and os.environ.get("OPENAI_API_KEY")):
                result["error"] = "No TTS method available. Install gTTS or set OPENAI_API_KEY"
            elif use_gtts and not GTTS_AVAILABLE:
                result["error"] = "gTTS not available. Install with: pip install gtts"
            elif not os.environ.get("OPENAI_API_KEY"):
                result["error"] = "OPENAI_API_KEY not set"

            logger.error(result["error"])
            return result

    except Exception as e:
        error_msg = f"Speech synthesis failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Audio Info =====

def get_audio_info(audio_path: str) -> Dict[str, Any]:
    """
    Get audio file information.

    Args:
        audio_path: Path to audio file

    Returns:
        Dict with keys:
        - ok: True if info retrieved
        - duration: Duration in seconds
        - format: Audio format (mp3, wav, ogg, etc.)
        - sample_rate: Sample rate in Hz
        - channels: Number of audio channels
        - error: Error message (if failed)
    """
    logger.info(f"Getting audio info: {audio_path}")

    # Validate file
    path = Path(audio_path)
    if not path.exists():
        return {
            "ok": False,
            "duration": None,
            "format": None,
            "sample_rate": None,
            "channels": None,
            "error": f"File not found: {audio_path}"
        }

    result = {
        "ok": False,
        "duration": None,
        "format": None,
        "sample_rate": None,
        "channels": None,
        "error": None,
    }

    try:
        # Try with pydub
        if PYDUB_AVAILABLE:
            audio = AudioSegment.from_file(str(path))

            result["ok"] = True
            result["duration"] = len(audio) / 1000.0  # milliseconds to seconds
            result["format"] = path.suffix.lower().lstrip(".")
            result["sample_rate"] = audio.frame_rate
            result["channels"] = audio.channels

            logger.info(f"Audio info: {result['duration']:.2f}s, {result['format']}, {result['sample_rate']}Hz")
            return result

        # Fallback: use file size and basic format detection
        else:
            result["ok"] = True
            result["duration"] = None  # Cannot determine without pydub
            result["format"] = path.suffix.lower().lstrip(".")
            result["sample_rate"] = None
            result["channels"] = None

            logger.info(f"Basic audio info: {result['format']} (duration unknown without pydub)")
            return result

    except Exception as e:
        error_msg = f"Failed to get audio info: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Audio Conversion =====

def convert_audio(
    input_path: str,
    output_path: str,
    format: str
) -> Dict[str, Any]:
    """
    Convert audio file to different format.

    Args:
        input_path: Path to input audio file
        output_path: Path to save converted audio
        format: Target format (mp3, wav, ogg, m4a, etc.)

    Returns:
        Dict with keys:
        - ok: True if conversion succeeded
        - path: Path to converted file
        - duration: Duration in seconds
        - error: Error message (if failed)
    """
    logger.info(f"Converting audio: {input_path} -> {output_path} ({format})")

    # Validate input file
    input_file = Path(input_path)
    if not input_file.exists():
        return {
            "ok": False,
            "path": None,
            "duration": None,
            "error": f"Input file not found: {input_path}"
        }

    # Create output directory if needed
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "ok": False,
        "path": output_path,
        "duration": None,
        "error": None,
    }

    try:
        if not PYDUB_AVAILABLE:
            result["error"] = "pydub not available. Install with: pip install pydub"
            return result

        # Load audio
        audio = AudioSegment.from_file(str(input_file))

        # Convert based on format
        format = format.lower().lstrip(".")

        if format == "mp3":
            audio.export(str(output_file), format="mp3")
        elif format == "wav":
            audio.export(str(output_file), format="wav")
        elif format == "ogg":
            audio.export(str(output_file), format="ogg")
        elif format == "m4a":
            audio.export(str(output_file), format="mp4")
        elif format == "flac":
            audio.export(str(output_file), format="flac")
        else:
            result["error"] = f"Unsupported format: {format}"
            return result

        result["ok"] = True
        result["duration"] = len(audio) / 1000.0

        logger.info(f"Audio converted successfully: {result['duration']:.2f}s")
        return result

    except Exception as e:
        error_msg = f"Audio conversion failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Helper Functions =====

def is_audio_file(file_path: str) -> bool:
    """
    Check if a file is a supported audio format.

    Args:
        file_path: Path to file

    Returns:
        True if supported audio format
    """
    supported_extensions = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma"}
    return Path(file_path).suffix.lower() in supported_extensions


def get_supported_formats() -> list:
    """
    Get list of supported audio formats.

    Returns:
        List of format names
    """
    return ["mp3", "wav", "ogg", "m4a", "flac", "aac"]


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Audio Processor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # transcribe
    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe audio to text")
    transcribe_parser.add_argument("input", help="Input audio file")
    transcribe_parser.add_argument("--language", default="ja", help="Language code")
    transcribe_parser.add_argument("--model", help="Whisper model name")
    transcribe_parser.add_argument("--use-api", action="store_true", help="Use OpenAI API instead of local")

    # synthesize
    synthesize_parser = subparsers.add_parser("synthesize", help="Synthesize text to speech")
    synthesize_parser.add_argument("text", help="Text to synthesize")
    synthesize_parser.add_argument("output", help="Output audio file")
    synthesize_parser.add_argument("--voice", default="default", help="Voice name")
    synthesize_parser.add_argument("--use-api", action="store_true", help="Use OpenAI API instead of gTTS")

    # info
    info_parser = subparsers.add_parser("info", help="Get audio file info")
    info_parser.add_argument("input", help="Input audio file")

    # convert
    convert_parser = subparsers.add_parser("convert", help="Convert audio format")
    convert_parser.add_argument("input", help="Input audio file")
    convert_parser.add_argument("output", help="Output audio file")
    convert_parser.add_argument("--format", required=True, help="Target format")

    args = parser.parse_args()

    result = {}

    if args.command == "transcribe":
        result = transcribe_audio(
            args.input,
            language=args.language,
            model=args.model,
            use_local=not args.use_api
        )
        if result["ok"]:
            print(f"Transcription ({result['language']}):")
            print(result["text"])
        else:
            print(f"Error: {result['error']}")

    elif args.command == "synthesize":
        result = synthesize_speech(
            args.text,
            args.output,
            voice=args.voice,
            use_gtts=not args.use_api
        )
        if result["ok"]:
            print(f"Speech synthesized: {result['path']} ({result['duration']:.2f}s)")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "info":
        result = get_audio_info(args.input)
        if result["ok"]:
            print(f"Format: {result['format']}")
            print(f"Duration: {result['duration']:.2f}s" if result['duration'] else "Duration: unknown")
            print(f"Sample rate: {result['sample_rate']}Hz" if result['sample_rate'] else "Sample rate: unknown")
            print(f"Channels: {result['channels']}" if result['channels'] else "Channels: unknown")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "convert":
        result = convert_audio(args.input, args.output, args.format)
        if result["ok"]:
            print(f"Converted: {result['path']} ({result['duration']:.2f}s)")
        else:
            print(f"Error: {result['error']}")

    import sys
    sys.exit(0 if result.get("ok", True) else 1)


if __name__ == "__main__":
    main()
