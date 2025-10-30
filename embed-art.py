#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TextIO


def has_embedded_art(flac_path: Path) -> bool:
    """Check if a FLAC file has embedded album art."""
    try:
        result = subprocess.run(
            ["metaflac", "--list", "--block-type=PICTURE", str(flac_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        # If there's output, there's embedded art
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error checking for embedded cover in {flac_path}: {e}")
        return True  # return True and leave this file alone


def ensure_baseline_jpeg(image_path: Path) -> Path:
    """Convert image to baseline JPEG using ImageMagick if needed.

    Returns the path to a baseline JPEG. If conversion was needed, returns
    a temporary file path that should be cleaned up by the caller.

    Handles:
    - PNG files: converts to baseline JPEG
    - Progressive JPEGs: converts to baseline JPEG
    - Baseline JPEGs: returns as-is
    """
    suffix_lower: str = image_path.suffix.lower()

    # If it's a PNG, always convert to baseline JPEG
    if suffix_lower == ".png":
        try:
            temp_fd, temp_path = tempfile.mkstemp(suffix=".jpg")
            print(f"  Created temporary file: {temp_path}")
            os.close(temp_fd)

            subprocess.run(
                [
                    "convert",
                    str(image_path),
                    "-interlace",
                    "none",
                    "-quality",
                    "95",
                    temp_path,
                ],
                check=True,
                capture_output=True,
            )
            print(f"  Converted PNG to baseline JPEG")
            return Path(temp_path)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Warning: Could not convert PNG {image_path}: {e}")
            return image_path

    # If not a JPEG, return as-is
    if suffix_lower not in [".jpg", ".jpeg"]:
        return image_path

    # For JPEGs, check if progressive
    try:
        result = subprocess.run(
            ["identify", "-verbose", str(image_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        if "Interlace: JPEG" in result.stdout or "Interlace: Line" in result.stdout:
            # It's progressive, convert it to baseline
            temp_fd, temp_path = tempfile.mkstemp(suffix=".jpg")
            print(f"  Created temporary file: {temp_path}")
            os.close(temp_fd)

            subprocess.run(
                [
                    "convert",
                    str(image_path),
                    "-interlace",
                    "none",
                    "-quality",
                    "95",
                    temp_path,
                ],
                check=True,
                capture_output=True,
            )
            print(f"  Converted progressive JPEG to baseline")
            return Path(temp_path)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: Could not check/convert {image_path}: {e}")

    return image_path


def embed_cover(flac_path: Path, cover_path: Path) -> bool:
    """Embed cover.jpg into a FLAC file as baseline JPEG."""
    baseline_cover: Path = ensure_baseline_jpeg(cover_path)
    temp_created: bool = baseline_cover != cover_path

    try:
        subprocess.run(
            [
                "metaflac",
                "--import-picture-from=" + str(baseline_cover),
                str(flac_path),
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error embedding cover in {flac_path}: {e}")
        return False
    finally:
        # Clean up temp file if created
        if temp_created and baseline_cover.exists():
            baseline_cover.unlink()


def process_album_directory(album_dir: Path, log_file: TextIO) -> None:
    """Process all FLACs in an album directory."""
    flac_files: list[Path] = list(album_dir.glob("*.flac")) + list(
        album_dir.glob("*.FLAC")
    )

    if not flac_files:
        return

    print(f"\nProcessing: {album_dir}")

    # Check if any FLAC needs album art
    flacs_without_art: list[Path] = []
    for flac in flac_files:
        if not has_embedded_art(flac):
            flacs_without_art.append(flac)

    if not flacs_without_art:
        print(f"  ✓ All FLACs have embedded art")
        return

    # Look for cover image (JPEG or PNG)
    cover_candidates: list[str] = [
        "cover.jpg",
        "Cover.jpg",
        "cover.JPG",
        "cover.png",
        "Cover.png",
        "cover.PNG",
        "folder.jpg",
        "Folder.jpg",
        "folder.png",
        "Folder.png",
    ]
    cover_path: Path | None = None
    for candidate in cover_candidates:
        potential_cover: Path = album_dir / candidate
        if potential_cover.exists():
            cover_path = potential_cover
            break

    if cover_path:
        print(f"  Found cover: {cover_path.name}")
        print(f"  Embedding art in {len(flacs_without_art)} file(s)...")
        for flac in flacs_without_art:
            if embed_cover(flac, cover_path):
                print(f"    ✓ {flac.name}")
            else:
                print(f"    ✗ Failed: {flac.name}")
                log_file.write(f"{flac}\n")
    else:
        print(f"  ✗ No cover image found - logging {len(flacs_without_art)} file(s)")
        for flac in flacs_without_art:
            log_file.write(f"{flac}\n")


def main() -> None:
    music_dir: Path = Path(".")
    log_path: Path = Path("missing_album_art.log")

    print(f"Scanning for FLAC files in: {music_dir.absolute()}")
    print(f"Log file: {log_path.absolute()}\n")

    # Find all directories that contain FLAC files
    album_dirs: set[Path] = set()
    for flac_file in music_dir.rglob("*.flac"):
        album_dirs.add(flac_file.parent)
    for flac_file in music_dir.rglob("*.FLAC"):
        album_dirs.add(flac_file.parent)

    print(f"Found {len(album_dirs)} album directories with FLAC files\n")

    with open(log_path, "w") as log_file:
        log_file.write("# FLACs without embedded art and no cover.jpg found\n")
        log_file.write("# Generated by embed_album_art.py\n\n")

        for album_dir in sorted(album_dirs):
            process_album_directory(album_dir, log_file)

    print(f"\n✓ Done! Check {log_path} for FLACs that need manual attention.")


if __name__ == "__main__":
    # Check if metaflac is available
    try:
        subprocess.run(["metaflac", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: metaflac not found. Please install flac package.")
        print("  sudo apt install flac")
        sys.exit(1)

    # Check if ImageMagick is available
    try:
        subprocess.run(["identify", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ImageMagick not found. Please install imagemagick package.")
        print("  sudo apt install imagemagick")
        sys.exit(1)

    main()
