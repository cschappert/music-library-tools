#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def convert_flac_to_mp3(flac_path: Path, output_base: Path) -> bool:
    """Convert a FLAC file to MP3 with specific quality settings.

    Args:
        flac_path: Path to the source FLAC file
        output_base: Base directory for converted files

    Returns:
        True if conversion succeeded, False otherwise
    """
    # Get relative path from current directory
    try:
        relative_path: Path = flac_path.relative_to(Path.cwd())
    except ValueError:
        # If file is not relative to cwd, use absolute path
        relative_path = flac_path

    # Create output directory structure
    output_dir: Path = output_base / relative_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create output file path with .mp3 extension
    output_file: Path = output_base / relative_path.with_suffix(".mp3")

    # FFmpeg command
    ffmpeg_cmd: list[str] = [
        "ffmpeg",
        "-i",
        str(flac_path),
        # Resample audio to 44100Hz using SoXR resampler
        "-af",
        "aresample=44100:resampler=soxr",
        # Use LAME MP3 encoder with highest quality (V0)
        "-c:a",
        "libmp3lame",
        "-q:a",
        "0",
        # Map audio stream, optional video stream (embedded art), and all metadata
        "-map",
        "0:a",
        "-map",
        "0:v?",
        "-map_metadata",
        "0",
        # Use ID3v2.3 tags
        "-id3v2_version",
        "3",
        # Scale embedded artwork to max 320px (preserving aspect ratio)
        # NOTE: May fail if flac file lacks embedded art (still need to test)
        "-vf",
        "scale='if(gt(iw,ih),320,-1)':'if(gt(ih,iw),320,-1)'",
        # Encode artwork as MJPEG with quality 3 (higher quality)
        "-c:v",
        "mjpeg",
        "-q:v",
        "3",
        # Output file
        str(output_file),
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {flac_path}: {e.stderr}", file=sys.stderr)
        return False


def main() -> None:
    """Find all FLAC files and convert them to MP3."""
    music_dir: Path = Path.cwd()
    # TODO: make output path customizable or at least add a timestamp to prevent
    # overwriting the results of previous conversions
    output_base: Path = Path("/home/chris/Music/converted")

    print(f"Scanning for FLAC files in: {music_dir}")
    print(f"Output directory: {output_base}\n")

    # Find all FLAC files (case-insensitive)
    flac_files: list[Path] = []
    for pattern in ["*.flac", "*.FLAC", "*.Flac"]:
        flac_files.extend(music_dir.rglob(pattern))

    if not flac_files:
        print("No FLAC files found.")
        return

    print(f"Found {len(flac_files)} FLAC file(s) to convert\n")

    # Convert each FLAC file
    successful: int = 0
    failed: int = 0

    for i, flac_file in enumerate(flac_files, 1):
        relative_path: Path = flac_file.relative_to(music_dir)
        print(f"[{i}/{len(flac_files)}] Converting: {relative_path}")

        if convert_flac_to_mp3(flac_file, output_base):
            successful += 1
            print(f"  ✓ Success\n")
        else:
            failed += 1
            print(f"  ✗ Failed\n")

    # Summary
    print(f"\n{'='*60}")
    print(f"Conversion complete!")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(flac_files)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    # Check if ffmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ffmpeg not found. Please install ffmpeg.")
        print("  sudo apt install ffmpeg")
        sys.exit(1)

    main()
