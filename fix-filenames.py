#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


def get_flac_metadata(flac_path: Path) -> dict[str, str]:
    """Extract metadata from FLAC file.

    Args:
        flac_path: Path to the FLAC file

    Returns:
        Dictionary with metadata keys (track, title, album, date/year), or empty dict on error
    """
    try:
        result = subprocess.run(
            ["metaflac", "--export-tags-to=-", str(flac_path)],
            capture_output=True,
            text=True,
            check=True,
        )

        metadata: dict[str, str] = {}
        date_value: str | None = None

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
                elif key_lower == "album":
                    metadata["album"] = value.strip()
                elif key_lower == "year":
                    # Prefer year tag - this takes priority
                    metadata["year"] = value.strip()
                elif key_lower == "date":
                    # Store date for potential fallback
                    date_value = value.strip()

        # If no year tag was found, try to extract year from date
        if "year" not in metadata and date_value:
            year_match = re.match(r"(\d{4})", date_value)
            if year_match:
                metadata["year"] = year_match.group(1)

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

    # Remove leading dots (creates hidden files on Unix/Linux)
    name = name.lstrip(".")

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
            print(f"  ✓ Renamed: {flac_path.name} --> {new_filename}")
            return True
        except OSError as e:
            print(f"  ✗ Error renaming {flac_path.name}: {e}", file=sys.stderr)
            return False


def get_album_metadata_from_directory(album_dir: Path) -> dict[str, str]:
    """Get album metadata by reading the first FLAC file in a directory.

    Args:
        album_dir: Path to the album directory

    Returns:
        Dictionary with 'year' and 'album' keys, or empty dict if not found
    """
    # Find first FLAC file in directory
    for pattern in ["*.flac", "*.FLAC", "*.Flac"]:
        flac_files = list(album_dir.glob(pattern))
        if flac_files:
            # Get metadata from first FLAC (all should have same album/year)
            metadata = get_flac_metadata(flac_files[0])
            return {
                "year": metadata.get("year", ""),
                "album": metadata.get("album", ""),
            }
    return {}


def rename_album_directory(album_dir: Path, dry_run: bool = False) -> bool:
    """Rename an album directory based on metadata.

    Args:
        album_dir: Path to the album directory
        dry_run: If True, only print what would be done without actually renaming

    Returns:
        True if renamed (or would be renamed in dry_run), False otherwise
    """
    metadata = get_album_metadata_from_directory(album_dir)

    if "year" not in metadata or "album" not in metadata:
        print(
            f"  ✗ Skipping directory (missing year or album metadata): {album_dir.name}"
        )
        return False

    if not metadata["year"] or not metadata["album"]:
        print(
            f"  ✗ Skipping directory (empty year or album metadata): {album_dir.name}"
        )
        return False

    # Create new directory name: "{year} {album}"
    year = metadata["year"]
    album = sanitize_filename(metadata["album"])
    new_dirname = f"{year} {album}"

    # Check if already has the correct name
    if album_dir.name == new_dirname:
        print(f"  ✓ Directory already correct: {album_dir.name}")
        return False

    new_path = album_dir.parent / new_dirname

    # Check if target directory already exists
    if new_path.exists():
        print(f"  ✗ Target directory already exists: {album_dir.name} → {new_dirname}")
        return False

    if dry_run:
        print(f"  [DRY RUN] Would rename directory: {album_dir.name} → {new_dirname}")
        return True
    else:
        try:
            album_dir.rename(new_path)
            print(f"  ✓ Renamed directory: {album_dir.name} → {new_dirname}")
            return True
        except OSError as e:
            print(
                f"  ✗ Error renaming directory {album_dir.name}: {e}", file=sys.stderr
            )
            return False


def main() -> None:
    """Find all FLAC files and rename them and their directories based on metadata."""
    music_dir: Path = Path.cwd()

    print(f"Scanning for FLAC files in: {music_dir}")
    print(f"Target file format: {{track}} {{title}}.flac")
    print(f"Target directory format: {{year}} {{album}}\n")

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

    # Process files and directories
    files_renamed: int = 0
    files_skipped: int = 0
    files_errors: int = 0
    dirs_renamed: int = 0
    dirs_skipped: int = 0
    dirs_errors: int = 0

    # First, rename all FLAC files
    print("=== RENAMING FILES ===\n")
    for flac_file in sorted(flac_files):
        relative_path = flac_file.relative_to(music_dir)
        print(f"\n{relative_path.parent}/")

        result = rename_flac_file(flac_file, dry_run=dry_run)
        if result:
            files_renamed += 1
        else:
            # Check if it was skipped or had an error
            metadata = get_flac_metadata(flac_file)
            if "track" not in metadata or "title" not in metadata:
                files_errors += 1
            else:
                files_skipped += 1

    # Then, rename album directories
    print("\n\n=== RENAMING DIRECTORIES ===\n")
    for album_dir in sorted(album_dirs):
        relative_path = album_dir.relative_to(music_dir)
        print(f"\n{relative_path}/")

        result = rename_album_directory(album_dir, dry_run=dry_run)
        if result:
            dirs_renamed += 1
        else:
            # Check if it was skipped or had an error
            metadata = get_album_metadata_from_directory(album_dir)
            if not metadata.get("year") or not metadata.get("album"):
                dirs_errors += 1
            else:
                dirs_skipped += 1

    # Summary
    print(f"\n{'='*60}")
    if dry_run:
        print(f"DRY RUN complete - no changes were actually made")
    else:
        print(f"Renaming complete!")
    print(f"\nFiles:")
    print(f"  Renamed: {files_renamed}")
    print(f"  Skipped (already correct): {files_skipped}")
    print(f"  Errors/missing metadata: {files_errors}")
    print(f"  Total: {len(flac_files)}")
    print(f"\nDirectories:")
    print(f"  Renamed: {dirs_renamed}")
    print(f"  Skipped (already correct): {dirs_skipped}")
    print(f"  Errors/missing metadata: {dirs_errors}")
    print(f"  Total: {len(album_dirs)}")
    print(f"{'='*60}")

    if dry_run:
        response = (
            input("\nDo you want to proceed with actual renaming? (y/n): ")
            .strip()
            .lower()
        )
        if response in ["y", "yes"]:
            print("\n--- ACTUAL RENAMING ---\n")

            # Rename files
            print("=== RENAMING FILES ===\n")
            files_renamed = 0
            for flac_file in sorted(flac_files):
                relative_path = flac_file.relative_to(music_dir)
                print(f"\n{relative_path.parent}/")
                if rename_flac_file(flac_file, dry_run=False):
                    files_renamed += 1

            # Rename directories
            print("\n\n=== RENAMING DIRECTORIES ===\n")
            dirs_renamed = 0
            for album_dir in sorted(album_dirs):
                relative_path = album_dir.relative_to(music_dir)
                print(f"\n{relative_path}/")
                if rename_album_directory(album_dir, dry_run=False):
                    dirs_renamed += 1
            print(
                f"\n✓ Renamed {files_renamed} file(s) and {dirs_renamed} directory(ies)"
            )


if __name__ == "__main__":
    # Check if metaflac is available
    try:
        subprocess.run(["metaflac", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: metaflac not found. Please install flac package.")
        print("  sudo apt install flac")
        sys.exit(1)

    main()
