#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Dict, Any

def process_app_directory(app_dir: Path) -> None:
    """Process an individual app directory to clear icon data"""
    # Process app.json
    app_json = app_dir / "app.json"
    if not app_json.exists():
        print(f"⚠️  app.json not found in {app_dir}")
        return

    try:
        # Load and modify JSON
        with open(app_json, 'r', encoding='utf-8') as f:
            data: Dict[str, Any] = json.load(f)
        
        # Clear icon key if exists
        if 'icon' in data:
            print(f"🗑️  Clearing icon URL in {app_dir.name}")
            data['icon'] = ""  # Set to an empty string
            
            # Save modified JSON
            with open(app_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in {app_json}")
        return

    # Remove icon.png if exists
    icon_png = app_dir / "icon.png"
    if icon_png.exists():
        print(f"🔥 Deleting {icon_png}")
        os.remove(icon_png)

def main():
    # Adjust the path to the Apps directory
    repo_root = Path("..").resolve()  # Move one level up to the repo root
    apps_dir = repo_root / "Apps"
    
    if not apps_dir.exists():
        print(f"❌ Apps directory not found at {apps_dir}")
        return

    print(f"🔍 Scanning {apps_dir}...")
    for app_dir in apps_dir.iterdir():
        if app_dir.is_dir():
            print(f"\n📂 Processing {app_dir.name}")
            process_app_directory(app_dir)
    
    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    main()