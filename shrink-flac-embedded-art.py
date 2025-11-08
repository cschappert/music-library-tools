#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def extract_embedded_art(flac_path: Path, output_path: Path) -> bool:
    """Extract embedded art from a FLAC file.

    Args:
        flac_path: Path to the FLAC file
        output_path: Path where the extracted image should be saved

    Returns:
        True if extraction succeeded, False otherwise
    """
    try:
        subprocess.run(
            ["metaflac", "--export-picture-to=" + str(output_path), str(flac_path)],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        # No embedded art or error extracting
        return False


def get_image_dimensions(image_path: Path) -> tuple[int, int] | None:
    """Get the dimensions of an image file.

    Args:
        image_path: Path to the image file

    Returns:
        Tuple of (width, height) in pixels, or None if unable to determine
    """
    try:
        result = subprocess.run(
            ["identify", "-format", "%w %h", str(image_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        width, height = result.stdout.strip().split()
        return (int(width), int(height))
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Warning: Could not get dimensions of {image_path}: {e}", file=sys.stderr)
        return None


def is_baseline_jpeg(image_path: Path) -> bool:
    """Check if an image is a baseline JPEG (not progressive).

    Args:
        image_path: Path to the image file

    Returns:
        True if it's a baseline JPEG, False if progressive or can't determine
    """
    try:
        result = subprocess.run(
            ["identify", "-verbose", str(image_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        # If "Interlace: None", it's baseline. If "Interlace: JPEG" or "Interlace: Line", it's progressive
        if "Interlace: None" in result.stdout:
            return True
        elif "Interlace: JPEG" in result.stdout or "Interlace: Line" in result.stdout:
            return False
        # If we can't determine, assume it needs processing
        return False
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not check interlacing of {image_path}: {e}", file=sys.stderr)
        return False


def resize_to_baseline_jpeg(
    input_path: Path, output_path: Path, size: int = 150
) -> bool:
    """Resize image to baseline JPEG with specified dimensions.

    Args:
        input_path: Path to input image
        output_path: Path for output JPEG
        size: Target size (will create size x size image)

    Returns:
        True if conversion succeeded, False otherwise
    """
    try:
        subprocess.run(
            [
                "convert",
                str(input_path),
                "-resize",
                f"{size}x{size}",
                "-quality",
                "85",
                "-interlace",
                "none",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error resizing image: {e}", file=sys.stderr)
        return False


def remove_embedded_art(flac_path: Path) -> bool:
    """Remove all embedded pictures from a FLAC file.

    Args:
        flac_path: Path to the FLAC file

    Returns:
        True if removal succeeded, False otherwise
    """
    try:
        subprocess.run(
            ["metaflac", "--remove", "--block-type=PICTURE", str(flac_path)],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error removing embedded art: {e}", file=sys.stderr)
        return False


def embed_art(flac_path: Path, image_path: Path) -> bool:
    """Embed image into a FLAC file.

    Args:
        flac_path: Path to the FLAC file
        image_path: Path to the image to embed

    Returns:
        True if embedding succeeded, False otherwise
    """
    try:
        subprocess.run(
            [
                "metaflac",
                "--import-picture-from=" + str(image_path),
                str(flac_path),
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error embedding art: {e}", file=sys.stderr)
        return False


def process_album_directory(
    album_dir: Path, dry_run: bool = False
) -> tuple[int, int, int]:
    """Process all FLAC files in an album directory.

    Extracts art from the first FLAC, resizes it once, then re-embeds into all FLACs.

    Args:
        album_dir: Path to the album directory
        dry_run: If True, only show what would be done

    Returns:
        Tuple of (processed, skipped, errors) counts
    """
    # Find all FLAC files in this directory (not recursive)
    flac_files: list[Path] = list(album_dir.glob("*.flac")) + list(
        album_dir.glob("*.FLAC")
    )

    if not flac_files:
        return (0, 0, 0)

    # Create temporary files for extracted and resized art
    temp_dir = tempfile.mkdtemp()
    extracted_path = Path(temp_dir) / "extracted"
    resized_path = Path(temp_dir) / "resized.jpg"

    try:
        # Extract art from first FLAC file (all FLACs in album should have same art)
        if not extract_embedded_art(flac_files[0], extracted_path):
            print(f"  → No embedded art found, skipping album")
            return (0, len(flac_files), 0)

        # Check dimensions of extracted art
        dimensions = get_image_dimensions(extracted_path)
        if dimensions:
            width, height = dimensions
            max_dim = max(width, height)

            # If already 150x150 or smaller, check if it's baseline JPEG
            if max_dim <= 150:
                is_baseline = is_baseline_jpeg(extracted_path)
                if is_baseline:
                    print(f"  → Art is already {width}x{height} baseline JPEG, skipping album")
                    return (0, len(flac_files), 0)
                else:
                    print(f"  → Art is {width}x{height} but progressive, will convert to baseline")
            else:
                print(f"  → Art is {width}x{height}, will resize to 150x150")
        else:
            print(f"  → Could not determine art dimensions, will process anyway")

        if dry_run:
            print(
                f"  [DRY RUN] Would resize and re-embed art in {len(flac_files)} file(s)"
            )
            return (len(flac_files), 0, 0)

        # Resize to 150x150 baseline JPEG once for the whole album
        if not resize_to_baseline_jpeg(extracted_path, resized_path, size=150):
            print(f"  ✗ Failed to resize art")
            return (0, 0, len(flac_files))

        # Process all FLAC files in the album
        processed = 0
        errors = 0

        for flac_file in flac_files:
            # Remove old embedded art
            if not remove_embedded_art(flac_file):
                print(f"    ✗ Failed to remove old art: {flac_file.name}")
                errors += 1
                continue

            # Embed new resized art
            if not embed_art(flac_file, resized_path):
                print(f"    ✗ Failed to embed new art: {flac_file.name}")
                errors += 1
                continue

            print(f"    ✓ {flac_file.name}")
            processed += 1

        if processed > 0:
            print(f"  ✓ Resized and re-embedded art (150x150) in {processed} file(s)")

        return (processed, 0, errors)

    finally:
        # Clean up temporary files
        if extracted_path.exists():
            extracted_path.unlink()
        if resized_path.exists():
            resized_path.unlink()
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass


def main() -> None:
    """Find all album directories and resize their embedded art."""
    music_dir: Path = Path.cwd()

    print(f"\nScanning for FLAC files in: {music_dir}")
    print(f"Target art size: 150x150 baseline JPEG\n")

    # Find all FLAC files (case-insensitive)
    flac_files: list[Path] = []
    for pattern in ["*.flac", "*.FLAC", "*.Flac"]:
        flac_files.extend(music_dir.rglob(pattern))

    if not flac_files:
        print("No FLAC files found.")
        return

    # Find all unique album directories
    album_dirs: set[Path] = set()
    for flac_file in flac_files:
        album_dirs.add(flac_file.parent)

    print(f"Found {len(flac_files)} FLAC file(s) in {len(album_dirs)} album(s)\n")

    # Ask user if they want to do a dry run first
    response = input("Do you want to do a dry run first? (y/n): ").strip().lower()
    dry_run = response in ["y", "yes"]

    if dry_run:
        print("\n--- DRY RUN MODE (no actual changes will be made) ---\n")

    # Process each album directory
    total_processed: int = 0
    total_skipped: int = 0
    total_errors: int = 0

    for i, album_dir in enumerate(sorted(album_dirs), 1):
        relative_path = album_dir.relative_to(music_dir)
        print(f"\n[{i}/{len(album_dirs)}] {relative_path}/")

        try:
            processed, skipped, errors = process_album_directory(album_dir, dry_run)
            total_processed += processed
            total_skipped += skipped
            total_errors += errors
        except Exception as e:
            print(f"  ✗ Error: {e}")
            # Count all files in this album as errors
            flac_count = len(list(album_dir.glob("*.flac")) + list(album_dir.glob("*.FLAC")))
            total_errors += flac_count

    # Summary
    print(f"\n{'='*60}")
    if dry_run:
        print(f"DRY RUN complete - no changes were actually made")
    else:
        print(f"Processing complete!")
    print(f"  Processed: {total_processed}")
    print(f"  Skipped (no art): {total_skipped}")
    print(f"  Errors: {total_errors}")
    print(f"  Total files: {len(flac_files)}")
    print(f"  Total albums: {len(album_dirs)}")
    print(f"{'='*60}\n")

    if dry_run:
        response = (
            input("Do you want to proceed with actual processing? (y/n): ")
            .strip()
            .lower()
        )
        if response in ["y", "yes"]:
            print("\n--- ACTUAL PROCESSING ---\n")
            total_processed = 0
            for i, album_dir in enumerate(sorted(album_dirs), 1):
                relative_path = album_dir.relative_to(music_dir)
                print(f"\n[{i}/{len(album_dirs)}] {relative_path}/")
                try:
                    processed, _, _ = process_album_directory(album_dir, dry_run=False)
                    total_processed += processed
                except Exception as e:
                    print(f"  ✗ Error: {e}")

            print(f"\n✓ Processed {total_processed} file(s) in {len(album_dirs)} album(s)\n")


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
        subprocess.run(["convert", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ImageMagick not found. Please install imagemagick package.")
        print("  sudo apt install imagemagick")
        sys.exit(1)

    main()
