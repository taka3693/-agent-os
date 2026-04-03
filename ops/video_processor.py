"""
Video Processor for Agent OS

Handles video analysis including frame extraction, audio extraction,
and comprehensive video understanding using vision and audio processing.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Configure logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"video_processor_{logging.getLevelName(logging.INFO).lower()}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class VideoProcessorError(Exception):
    """Base exception for video processor errors"""
    pass


class FFmpegNotFoundError(VideoProcessorError):
    """ffmpeg not found"""
    pass


class FileError(VideoProcessorError):
    """File operation error"""
    pass


# ===== Dependencies =====

FFMPEG_AVAILABLE = False
try:
    subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True,
        check=True
    )
    FFMPEG_AVAILABLE = True
    logger.info("ffmpeg is available")
except (subprocess.CalledProcessError, FileNotFoundError):
    logger.warning("ffmpeg not found")


VISION_AVAILABLE = False
try:
    # Dynamic import to avoid circular dependency
    vision_processor = __import__("ops.vision_processor", fromlist=["analyze_image"])
    VISION_AVAILABLE = True
    logger.info("vision_processor is available")
except (ImportError, AttributeError):
    logger.warning("vision_processor not available")


AUDIO_AVAILABLE = False
try:
    audio_processor = __import__("ops.audio_processor", fromlist=["transcribe_audio"])
    AUDIO_AVAILABLE = True
    logger.info("audio_processor is available")
except (ImportError, AttributeError):
    logger.warning("audio_processor not available")


# ===== Video Info =====

def get_video_info(video_path: str) -> Dict[str, Any]:
    """
    Get video file information using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        Dict with keys:
        - ok: True if info retrieved
        - duration: Duration in seconds
        - resolution: Tuple of (width, height)
        - fps: Frames per second
        - format: Video format/container
        - codec: Video codec
        - has_audio: Whether video has audio track
        - error: Error message (if failed)
    """
    logger.info(f"Getting video info: {video_path}")

    # Validate file
    path = Path(video_path)
    if not path.exists():
        return {
            "ok": False,
            "duration": None,
            "resolution": None,
            "fps": None,
            "format": None,
            "codec": None,
            "has_audio": False,
            "error": f"File not found: {video_path}"
        }

    result = {
        "ok": False,
        "duration": None,
        "resolution": None,
        "fps": None,
        "format": None,
        "codec": None,
        "has_audio": False,
        "error": None,
    }

    if not FFMPEG_AVAILABLE:
        result["error"] = "ffmpeg/ffprobe not available"
        return result

    try:
        # Use ffprobe to get video info
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,r_frame_rate",
            "-show_entries", "format=duration,format_name",
            "-of", "json",
            str(path)
        ]

        output = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        info = json.loads(output)

        # Parse duration
        duration = float(info.get("format", {}).get("duration", 0))
        result["duration"] = duration

        # Parse resolution
        streams = info.get("streams", [])
        if streams:
            stream = streams[0]
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            result["resolution"] = (width, height)
            result["codec"] = stream.get("codec_name")

            # Parse FPS
            fps_str = stream.get("r_frame_rate", "")
            if fps_str:
                num, den = fps_str.split("/")
                result["fps"] = float(num) / float(den) if int(den) > 0 else 0

        # Parse format
        result["format"] = info.get("format", {}).get("format_name", "")

        # Check for audio
        audio_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_name",
            "-of", "json",
            str(path)
        ]
        try:
            audio_output = subprocess.run(audio_cmd, capture_output=True, text=True, check=True).stdout
            audio_info = json.loads(audio_output)
            result["has_audio"] = len(audio_info.get("streams", [])) > 0
        except:
            result["has_audio"] = False

        result["ok"] = True
        logger.info(f"Video info: {duration:.2f}s, {result['resolution']}, {result['fps']:.2f}fps")

    except subprocess.CalledProcessError as e:
        error_msg = f"ffprobe failed: {e.stderr}"
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"Failed to get video info: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Frame Extraction =====

def extract_frames(
    video_path: str,
    output_dir: Optional[str] = None,
    interval_sec: float = 1.0,
    max_frames: int = 10,
    start_time: float = 0.0,
    end_time: Optional[float] = None
) -> Dict[str, Any]:
    """
    Extract frames from video at specified intervals.

    Args:
        video_path: Path to video file
        output_dir: Directory to save frames (defaults to temp directory)
        interval_sec: Interval between frames in seconds
        max_frames: Maximum number of frames to extract
        start_time: Start time in seconds
        end_time: End time in seconds (None = end of video)

    Returns:
        Dict with keys:
        - ok: True if extraction succeeded
        - frames: List of frame file paths
        - count: Number of frames extracted
        - output_dir: Directory where frames were saved
        - error: Error message (if failed)
    """
    logger.info(f"Extracting frames from: {video_path} (interval={interval_sec}s, max={max_frames})")

    # Validate file
    path = Path(video_path)
    if not path.exists():
        return {
            "ok": False,
            "frames": [],
            "count": 0,
            "output_dir": None,
            "error": f"File not found: {video_path}"
        }

    result = {
        "ok": False,
        "frames": [],
        "count": 0,
        "output_dir": None,
        "error": None,
    }

    if not FFMPEG_AVAILABLE:
        result["error"] = "ffmpeg not available"
        return result

    # Create output directory
    if output_dir is None:
        output_dir = PROJECT_ROOT / "state" / "temp" / "frames" / path.stem
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get video duration
        info = get_video_info(video_path)
        if not info["ok"]:
            result["error"] = info["error"]
            return result

        duration = info["duration"]
        if end_time is None:
            end_time = duration

        # Calculate timestamps
        timestamps = []
        current_time = start_time
        while current_time < end_time and len(timestamps) < max_frames:
            timestamps.append(current_time)
            current_time += interval_sec

        if not timestamps:
            result["error"] = "No frames to extract (invalid time range)"
            return result

        # Extract frames using ffmpeg
        frames = []
        for i, timestamp in enumerate(timestamps):
            output_file = output_dir / f"frame_{i:04d}.jpg"

            cmd = [
                "ffmpeg",
                "-ss", str(timestamp),
                "-i", str(path),
                "-vframes", "1",
                "-q:v", "2",  # High quality
                "-y",  # Overwrite
                str(output_file)
            ]

            subprocess.run(cmd, capture_output=True, check=True)

            if output_file.exists():
                frames.append(str(output_file))

        result["ok"] = True
        result["frames"] = frames
        result["count"] = len(frames)
        result["output_dir"] = str(output_dir)

        logger.info(f"Extracted {len(frames)} frames to {output_dir}")

    except subprocess.CalledProcessError as e:
        error_msg = f"ffmpeg failed: {e.stderr.decode() if e.stderr else str(e)}"
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"Frame extraction failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Audio Extraction =====

def extract_audio(
    video_path: str,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract audio track from video file.

    Args:
        video_path: Path to video file
        output_path: Path to save audio file (defaults to video_path + .wav)

    Returns:
        Dict with keys:
        - ok: True if extraction succeeded
        - path: Path to extracted audio file
        - duration: Audio duration in seconds
        - error: Error message (if failed)
    """
    logger.info(f"Extracting audio from: {video_path}")

    # Validate file
    path = Path(video_path)
    if not path.exists():
        return {
            "ok": False,
            "path": None,
            "duration": None,
            "error": f"File not found: {video_path}"
        }

    result = {
        "ok": False,
        "path": None,
        "duration": None,
        "error": None,
    }

    if not FFMPEG_AVAILABLE:
        result["error"] = "ffmpeg not available"
        return result

    # Determine output path
    if output_path is None:
        output_path = path.with_suffix(".wav")
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Extract audio using ffmpeg
        cmd = [
            "ffmpeg",
            "-i", str(path),
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # WAV codec
            "-ar", "16000",  # 16kHz sample rate (good for speech)
            "-ac", "1",  # Mono
            "-y",  # Overwrite
            str(output_path)
        ]

        subprocess.run(cmd, capture_output=True, check=True)

        # Get duration
        if output_path.exists():
            info_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
                capture_output=True,
                text=True,
                check=True
            )
            duration = float(info_result.stdout.strip())
            result["duration"] = duration

        result["ok"] = True
        result["path"] = str(output_path)

        logger.info(f"Audio extracted: {output_path} ({duration:.2f}s)")

    except subprocess.CalledProcessError as e:
        error_msg = f"ffmpeg failed: {e.stderr.decode() if e.stderr else str(e)}"
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"Audio extraction failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Video Analysis =====

def analyze_video(
    video_path: str,
    prompt: str = "この動画を説明して",
    frame_interval: float = 2.0,
    max_frames: int = 5,
    transcribe_audio: bool = True,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze video by extracting frames, transcribing audio, and generating a combined description.

    Args:
        video_path: Path to video file
        prompt: Analysis prompt for LLM
        frame_interval: Interval between frames to analyze (seconds)
        max_frames: Maximum number of frames to analyze
        transcribe_audio: Whether to transcribe audio track
        model: Model name for vision/audio analysis

    Returns:
        Dict with keys:
        - ok: True if analysis succeeded
        - analysis: Combined video description
        - frames_analyzed: Number of frames analyzed
        - frame_analyses: List of individual frame analyses
        - transcript: Audio transcript (if available)
        - video_info: Video information
        - error: Error message (if failed)
    """
    logger.info(f"Analyzing video: {video_path}")

    result = {
        "ok": False,
        "analysis": None,
        "frames_analyzed": 0,
        "frame_analyses": [],
        "transcript": None,
        "video_info": None,
        "error": None,
    }

    try:
        # Get video info
        video_info = get_video_info(video_path)
        if not video_info["ok"]:
            result["error"] = f"Failed to get video info: {video_info['error']}"
            return result
        result["video_info"] = video_info

        # Extract frames
        frames_result = extract_frames(
            video_path,
            interval_sec=frame_interval,
            max_frames=max_frames
        )

        if not frames_result["ok"]:
            result["error"] = f"Failed to extract frames: {frames_result['error']}"
            return result

        # Analyze frames with vision processor
        frame_analyses = []
        if VISION_AVAILABLE:
            logger.info(f"Analyzing {len(frames_result['frames'])} frames...")

            for i, frame_path in enumerate(frames_result["frames"]):
                logger.info(f"Analyzing frame {i+1}/{len(frames_result['frames'])}: {frame_path}")

                # Build frame-specific prompt
                frame_prompt = f"{prompt}\n\nこれは動画の{i+1}枚目のフレーム（{i*frame_interval:.1f}秒目）です。"

                try:
                    analysis_result = vision_processor.analyze_image(frame_path, frame_prompt)
                    if analysis_result.get("ok"):
                        frame_analyses.append({
                            "frame": frame_path,
                            "timestamp": i * frame_interval,
                            "description": analysis_result.get("description", "")
                        })
                except Exception as e:
                    logger.warning(f"Failed to analyze frame {i}: {e}")

            result["frames_analyzed"] = len(frame_analyses)
            result["frame_analyses"] = frame_analyses

        # Transcribe audio if available and requested
        transcript = None
        if transcribe_audio and video_info.get("has_audio") and AUDIO_AVAILABLE:
            logger.info("Transcribing audio...")

            # Extract audio
            audio_path = video_path.replace(Path(video_path).suffix, ".tmp.wav")
            audio_result = extract_audio(video_path, audio_path)

            if audio_result["ok"]:
                # Transcribe
                transcript_result = audio_processor.transcribe_audio(audio_path, language="ja")
                if transcript_result.get("ok"):
                    transcript = transcript_result["text"]
                    result["transcript"] = transcript

                # Clean up temporary audio file
                try:
                    Path(audio_path).unlink()
                except:
                    pass

        # Generate combined analysis
        analysis_parts = []

        # Add video info
        if video_info:
            info_text = f"動画情報: {video_info['duration']:.1f}秒"
            if video_info.get("resolution"):
                info_text += f", 解像度: {video_info['resolution'][0]}x{video_info['resolution'][1]}"
            if video_info.get("fps"):
                info_text += f", FPS: {video_info['fps']:.1f}"
            analysis_parts.append(info_text)

        # Add frame analyses
        if frame_analyses:
            frame_descriptions = [f"{i+1}. ({f['timestamp']:.1f}s) {f['description']}" for i, f in enumerate(frame_analyses)]
            analysis_parts.append("フレーム分析:")
            analysis_parts.extend(frame_descriptions)

        # Add transcript
        if transcript:
            analysis_parts.append("音声転写:")
            analysis_parts.append(transcript)

        # Combine
        result["analysis"] = "\n".join(analysis_parts)
        result["ok"] = True

        logger.info(f"Video analysis complete: {len(frame_analyses)} frames, audio={'yes' if transcript else 'no'}")

    except Exception as e:
        error_msg = f"Video analysis failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Helper Functions =====

def is_video_file(file_path: str) -> bool:
    """
    Check if a file is a supported video format.

    Args:
        file_path: Path to file

    Returns:
        True if supported video format
    """
    supported_extensions = {
        ".mp4", ".avi", ".mov", ".mkv", ".webm",
        ".flv", ".wmv", ".m4v", ".mpeg", ".mpg"
    }
    return Path(file_path).suffix.lower() in supported_extensions


def get_supported_formats() -> list:
    """
    Get list of supported video formats.

    Returns:
        List of format names
    """
    return ["mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "m4v", "mpeg", "mpg"]


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Video Processor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # info
    info_parser = subparsers.add_parser("info", help="Get video file info")
    info_parser.add_argument("input", help="Input video file")

    # extract-frames
    frames_parser = subparsers.add_parser("extract-frames", help="Extract frames from video")
    frames_parser.add_argument("input", help="Input video file")
    frames_parser.add_argument("--output", help="Output directory")
    frames_parser.add_argument("--interval", type=float, default=1.0, help="Interval in seconds")
    frames_parser.add_argument("--max", type=int, default=10, help="Maximum frames")

    # extract-audio
    audio_parser = subparsers.add_parser("extract-audio", help="Extract audio from video")
    audio_parser.add_argument("input", help="Input video file")
    audio_parser.add_argument("--output", help="Output audio file")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze video")
    analyze_parser.add_argument("input", help="Input video file")
    analyze_parser.add_argument("--prompt", default="この動画を説明して", help="Analysis prompt")
    analyze_parser.add_argument("--interval", type=float, default=2.0, help="Frame interval")
    analyze_parser.add_argument("--max-frames", type=int, default=5, help="Max frames to analyze")
    analyze_parser.add_argument("--no-audio", action="store_true", help="Skip audio transcription")

    args = parser.parse_args()

    result = {}

    if args.command == "info":
        result = get_video_info(args.input)
        if result["ok"]:
            print(f"Format: {result['format']}")
            print(f"Duration: {result['duration']:.2f}s")
            print(f"Resolution: {result['resolution']}")
            print(f"FPS: {result['fps']:.2f}")
            print(f"Codec: {result['codec']}")
            print(f"Has audio: {'Yes' if result['has_audio'] else 'No'}")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "extract-frames":
        result = extract_frames(
            args.input,
            output_dir=args.output,
            interval_sec=args.interval,
            max_frames=args.max
        )
        if result["ok"]:
            print(f"Extracted {result['count']} frames to: {result['output_dir']}")
            for frame in result["frames"]:
                print(f"  - {frame}")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "extract-audio":
        result = extract_audio(args.input, args.output)
        if result["ok"]:
            print(f"Audio extracted: {result['path']} ({result['duration']:.2f}s)")
        else:
            print(f"Error: {result['error']}")

    elif args.command == "analyze":
        result = analyze_video(
            args.input,
            prompt=args.prompt,
            frame_interval=args.interval,
            max_frames=args.max_frames,
            transcribe_audio=not args.no_audio
        )
        if result["ok"]:
            print("=== Video Analysis ===")
            print(f"\n{result['analysis']}")
            print(f"\n--- Details ---")
            print(f"Frames analyzed: {result['frames_analyzed']}")
            print(f"Audio transcribed: {'Yes' if result['transcript'] else 'No'}")
        else:
            print(f"Error: {result['error']}")

    import sys
    sys.exit(0 if result.get("ok", True) else 1)


if __name__ == "__main__":
    main()
