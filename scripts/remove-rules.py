#!/usr/bin/env python3
import os
import argparse
import glob

def remove_rules_files(apps=None):
    # Get the root directory (assuming script is in ./scripts/)
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    apps_dir = os.path.join(root_dir, 'Apps')
    
    if not os.path.exists(apps_dir):
        print("Apps directory not found!")
        return
    
    # If specific apps are provided, only process those
    if apps and apps.strip():
        target_apps = [app.strip() for app in apps.split(',')]
    else:
        # Otherwise, process all apps
        target_apps = [d for d in os.listdir(apps_dir) if os.path.isdir(os.path.join(apps_dir, d))]
    
    files_removed = 0
    
    for app in target_apps:
        app_path = os.path.join(apps_dir, app)
        if not os.path.exists(app_path):
            print(f"Warning: App directory '{app}' not found")
            continue
            
        # Look for both .rules and .rules.yaml files
        patterns = [
            os.path.join(app_path, '*.rules'),
            os.path.join(app_path, '*.rules.yaml')
        ]
        
        for pattern in patterns:
            for file_path in glob.glob(pattern):
                try:
                    os.remove(file_path)
                    print(f"Removed: {os.path.relpath(file_path, root_dir)}")
                    files_removed += 1
                except Exception as e:
                    print(f"Error removing {file_path}: {str(e)}")
    
    if files_removed == 0:
        print("No rules files found to remove")
    else:
        print(f"Total files removed: {files_removed}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Remove .rules and .rules.yaml files from Apps directories"
    )
    parser.add_argument(
        "--apps",
        type=str,
        default="",
        help="Comma-separated list of app names to process (leave empty for all)"
    )
    
    args = parser.parse_args()
    remove_rules_files(args.apps)