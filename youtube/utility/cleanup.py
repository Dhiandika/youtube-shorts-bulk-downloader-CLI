#!/usr/bin/env python3
"""
Cleanup script for incomplete YouTube downloads.
Based on internet_cleanup.py reference.
"""
import os
import glob

def cleanup_incomplete_downloads(downloads_dir: str):
    """Clean up incomplete download files (.part, .ytdl, .temp files)"""

    if not os.path.exists(downloads_dir):
        # Silent is better if dir doesn't exist yet
        return 0, 0

    print(f"  [CLEANUP] Checking {downloads_dir} for junk...")

    # Patterns for incomplete files
    cleanup_patterns = [
        "*.part",
        "*.ytdl",
        "*.temp",
        "*.part-Frag*",
        "*.f*.mp4.part*",
        "*.f*.mp4.ytdl"
    ]

    cleaned_files = []

    for pattern in cleanup_patterns:
        pattern_path = os.path.join(downloads_dir, "**", pattern)
        files = glob.glob(pattern_path, recursive=True)

        for file_path in files:
            try:
                os.remove(file_path)
                cleaned_files.append(os.path.basename(file_path))
            except Exception as e:
                pass

    if cleaned_files:
        print(f"  [CLEANUP] Removed {len(cleaned_files)} partial files.")
    
    return len(cleaned_files)
