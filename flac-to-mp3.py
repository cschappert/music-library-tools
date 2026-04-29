#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

# --- Configuration ---
MUSIC_DIR = Path("/media/chris/EXTREME SSD/Music/FLAC")
OUTPUT_DIR = Path("/media/chris/EXTREME SSD/Music_mp3")
# Max pixels on the longest side for output embedded art; never upscaled
ART_MAX_PX = 700
# ---------------------


def has_embedded_art(flac_path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(flac_path),
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() != ""


def convert_flac_to_mp3(
    flac_path: Path, music_dir: Path, output_base: Path
) -> bool | None:
    """Convert a FLAC file to MP3 with specific quality settings.

    Args:
        flac_path: Path to the source FLAC file
        music_dir: Base directory of the source FLAC library
        output_base: Base directory for converted files

    Returns:
        True if conversion succeeded, False if it failed, None if skipped
    """
    relative_path: Path = flac_path.relative_to(music_dir)

    # Create output file path with .mp3 extension
    output_file: Path = output_base / relative_path.with_suffix(".mp3")

    if (
        output_file.exists()
        and output_file.stat().st_mtime >= flac_path.stat().st_mtime
    ):
        return None

    # Create output directory structure
    output_dir: Path = output_base / relative_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # FFmpeg command
    ffmpeg_cmd: list[str] = [
        "ffmpeg",
        "-y",
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
    ]

    if has_embedded_art(flac_path):
        ffmpeg_cmd += [
            "-vf",
            # Scale down to max ART_MAX_PX on the longest side; never upscale
            f"scale='if(gte(iw,ih),min({ART_MAX_PX},iw),-1)':'if(gt(ih,iw),min({ART_MAX_PX},ih),-1)'",
            "-c:v",
            "mjpeg",
            "-q:v",
            "3",
        ]
    else:
        ffmpeg_cmd += ["-vn"]

    # Add the output file path to the end of the ffmpeg command
    ffmpeg_cmd.append(str(output_file))

    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {flac_path}: {e.stderr}", file=sys.stderr)
        return False


def remove_orphaned_mp3s(music_dir: Path, output_base: Path) -> None:
    """Remove MP3s in output_base that have no corresponding FLAC in music_dir."""
    print(f"\nScanning for orphaned MP3s in: {output_base}")

    removed: int = 0

    for mp3_file in output_base.rglob("*.mp3"):
        relative_path: Path = mp3_file.relative_to(output_base)

        # Check all case variants
        if not any(
            (music_dir / relative_path.with_suffix(ext)).exists()
            for ext in [".flac", ".FLAC", ".Flac"]
        ):
            print(f"  Removing orphan: {relative_path}")
            mp3_file.unlink()
            removed += 1

    print(f"  Removed {removed} orphaned MP3(s)")


def main() -> None:
    """Find all FLAC files and convert them to MP3."""
    parser = argparse.ArgumentParser(description="Convert FLAC files to MP3.")
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove MP3s in the output directory that no longer have a source FLAC",
    )
    args = parser.parse_args()

    music_dir: Path = MUSIC_DIR
    output_base: Path = OUTPUT_DIR

    print(f"Scanning for FLAC files in: {music_dir}")
    print(f"Output directory: {output_base}\n")

    # Find all FLAC files (case-insensitive)
    flac_files: list[Path] = []
    for pattern in ["*.flac", "*.FLAC", "*.Flac"]:
        flac_files.extend(music_dir.rglob(pattern))

    if not flac_files:
        print("No FLAC files found.")
        if args.remove:
            print(
                "  --remove skipped for safety: no source files found in input directory."
            )
        return

    print(f"Found {len(flac_files)} FLAC file(s) to convert\n")

    # Convert each FLAC file
    successful: int = 0
    failed: int = 0
    skipped: int = 0

    for i, flac_file in enumerate(flac_files, 1):
        relative_path: Path = flac_file.relative_to(music_dir)
        print(f"[{i}/{len(flac_files)}] {relative_path}")

        result = convert_flac_to_mp3(flac_file, music_dir, output_base)
        if result is None:
            skipped += 1
            print(f"  - Skipped (up to date)\n")
        elif result:
            successful += 1
            print(f"  ✓ Success\n")
        else:
            failed += 1
            print(f"  ✗ Failed\n")

    # Summary
    print(f"\n{'='*60}")
    print(f"Conversion complete!")
    print(f"  Successful: {successful}")
    print(f"  Skipped:    {skipped}")
    print(f"  Failed:     {failed}")
    print(f"  Total:      {len(flac_files)}")
    print(f"{'='*60}")

    if args.remove:
        remove_orphaned_mp3s(music_dir, output_base)


if __name__ == "__main__":
    # Check if ffmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ffmpeg not found. Please install ffmpeg.")
        print("  sudo apt install ffmpeg")
        sys.exit(1)

    main()
