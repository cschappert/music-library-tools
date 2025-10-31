#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


def get_flac_metadata(flac_path: Path) -> dict[str, str]:
    """Extract track number and title from FLAC metadata.

    Args:
        flac_path: Path to the FLAC file

    Returns:
        Dictionary with 'track' and 'title' keys, or empty dict on error
    """
    try:
        result = subprocess.run(
            ["metaflac", "--export-tags-to=-", str(flac_path)],
            capture_output=True,
            text=True,
            check=True,
        )

        metadata: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                key_lower = key.lower()
                if key_lower == "tracknumber":
                    # Handle track numbers like "01" or "1/12" (track/total)
                    track = value.split("/")[0].strip()
                    # Pad to 2 digits if needed
                    metadata["track"] = track.zfill(2)
                elif key_lower == "title":
                    metadata["title"] = value.strip()

        return metadata
    except subprocess.CalledProcessError as e:
        print(f"Error reading metadata from {flac_path}: {e}", file=sys.stderr)
        return {}


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are problematic in filenames.

    Args:
        name: The string to sanitize

    Returns:
        Sanitized string safe for use in filenames
    """
    # Replace problematic characters with safe alternatives
    replacements = {
        "/": "_",
        "\\": "_",
        ":": "_",
        "*": "_",
        "?": "_",
        '"': "'",
        "<": "_",
        ">": "_",
        "|": "_",
    }

    for char, replacement in replacements.items():
        name = name.replace(char, replacement)

    # Remove any other control characters
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)

    # Clean up multiple spaces and trim
    name = re.sub(r"\s+", " ", name).strip()

    # Remove trailing period if present (problematic on Windows)
    if name.endswith("."):
        name = name.rstrip(".")

    return name


def rename_flac_file(flac_path: Path, dry_run: bool = False) -> bool:
    """Rename a FLAC file based on its metadata.

    Args:
        flac_path: Path to the FLAC file
        dry_run: If True, only print what would be done without actually renaming

    Returns:
        True if renamed (or would be renamed in dry_run), False otherwise
    """
    metadata = get_flac_metadata(flac_path)

    if "track" not in metadata or "title" not in metadata:
        print(f"  ✗ Skipping (missing track or title metadata): {flac_path.name}")
        return False

    # Create new filename: "{track} {title}.flac"
    track = metadata["track"]
    title = sanitize_filename(metadata["title"])
    new_filename = f"{track} {title}.flac"

    # Check if already has the correct name
    if flac_path.name == new_filename:
        print(f"  ✓ Already correct: {flac_path.name}")
        return False

    new_path = flac_path.parent / new_filename

    # Check if target file already exists
    if new_path.exists():
        print(f"  ✗ Target already exists: {flac_path.name} --> {new_filename}")
        return False

    if dry_run:
        print(f"  [DRY RUN] Would rename: {flac_path.name} --> {new_filename}")
        return True
    else:
        try:
            flac_path.rename(new_path)
            print(f"  ✓ Renamed: {flac_path.name} � {new_filename}")
            return True
        except OSError as e:
            print(f"  ✗ Error renaming {flac_path.name}: {e}", file=sys.stderr)
            return False


def main() -> None:
    """Find all FLAC files and rename them based on metadata."""
    music_dir: Path = Path.cwd()

    print(f"Scanning for FLAC files in: {music_dir}")
    print(f"Target format: {{track}} {{title}}.flac\n")

    # Find all FLAC files (case-insensitive)
    flac_files: list[Path] = []
    for pattern in ["*.flac", "*.FLAC", "*.Flac"]:
        flac_files.extend(music_dir.rglob(pattern))

    if not flac_files:
        print("No FLAC files found.")
        return

    print(f"Found {len(flac_files)} FLAC file(s)\n")

    # Ask user if they want to do a dry run first
    response = input("Do you want to do a dry run first? (y/n): ").strip().lower()
    dry_run = response in ["y", "yes"]

    if dry_run:
        print("\n--- DRY RUN MODE (no actual changes will be made) ---\n")

    # Process each FLAC file
    renamed: int = 0
    skipped: int = 0
    errors: int = 0

    for flac_file in sorted(flac_files):
        relative_path = flac_file.relative_to(music_dir)
        print(f"\n{relative_path.parent}/")

        result = rename_flac_file(flac_file, dry_run=dry_run)
        if result:
            renamed += 1
        else:
            # Check if it was skipped or had an error
            metadata = get_flac_metadata(flac_file)
            if "track" not in metadata or "title" not in metadata:
                errors += 1
            else:
                skipped += 1

    # Summary
    print(f"\n{'='*60}")
    if dry_run:
        print(f"DRY RUN complete - no files were actually renamed")
    else:
        print(f"Renaming complete!")
    print(f"  Renamed: {renamed}")
    print(f"  Skipped (already correct): {skipped}")
    print(f"  Errors/missing metadata: {errors}")
    print(f"  Total: {len(flac_files)}")
    print(f"{'='*60}")

    if dry_run:
        response = (
            input("\nDo you want to proceed with actual renaming? (y/n): ")
            .strip()
            .lower()
        )
        if response in ["y", "yes"]:
            print("\n--- ACTUAL RENAMING ---\n")
            renamed = 0
            for flac_file in sorted(flac_files):
                relative_path = flac_file.relative_to(music_dir)
                print(f"\n{relative_path.parent}/")
                if rename_flac_file(flac_file, dry_run=False):
                    renamed += 1
            print(f"\n Renamed {renamed} file(s)")


if __name__ == "__main__":
    # Check if metaflac is available
    try:
        subprocess.run(["metaflac", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: metaflac not found. Please install flac package.")
        print("  sudo apt install flac")
        sys.exit(1)

    main()
