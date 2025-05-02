#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def convert_ios_png(input_path):
    """Convert iOS-optimized PNG to standard PNG by removing CgBI chunk."""
    try:
        with open(input_path, "rb") as f:
            data = f.read()
        if b"CgBI" not in data:
            return False
        offset = 8
        while offset < len(data):
            chunk_length = int.from_bytes(data[offset:offset+4], "big")
            chunk_type = data[offset+4:offset+8]
            if chunk_type == b"CgBI":
                new_data = data[:offset] + data[offset + chunk_length + 12:]
                with open(input_path, "wb") as f:
                    f.write(new_data)
                return True
            offset += chunk_length + 12
            if offset >= len(data):
                break
        return False
    except Exception as e:
        print(f"Error converting {input_path}: {e}")
        return False

def main():
    apps_dir = Path("Apps")
    if not apps_dir.exists():
        print("Error: Apps directory not found")
        sys.exit(1)

    converted = False
    for root, _, files in os.walk(apps_dir):
        if "icon.png" in files:
            path = os.path.join(root, "icon.png")
            if convert_ios_png(path):
                print(f"Converted iOS-optimized PNG: {path}")
                converted = True

    if not converted:
        print("No iOS-optimized PNGs found")

if __name__ == "__main__":
    main() 