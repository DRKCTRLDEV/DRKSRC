import zipfile
import plistlib
import os
import struct
import shutil
import json
import requests
from PIL import Image
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
import sys

load_dotenv()

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN environment variable not set")
    sys.exit(1)

def is_ios_optimized_png(data):
    """Check if the PNG is iOS-optimized by looking for CgBI chunk."""
    if len(data) < 8:
        return False
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return False
    offset = 8
    while offset < len(data):
        chunk_length = struct.unpack('>I', data[offset:offset+4])[0]
        chunk_type = data[offset+4:offset+8]
        if chunk_type == b'CgBI':
            return True
        offset += chunk_length + 12
        if offset >= len(data):
            break
    return False

def convert_ios_optimized_png(input_path, output_path):
    """Convert iOS-optimized PNG to standard PNG by removing CgBI chunk and fixing color format."""
    with open(input_path, 'rb') as f:
        data = f.read()
    
    if not is_ios_optimized_png(data):
        shutil.copy(input_path, output_path)
        return True
    
    # Find CgBI chunk
    offset = 8
    while offset < len(data):
        chunk_length = struct.unpack('>I', data[offset:offset+4])[0]
        chunk_type = data[offset+4:offset+8]
        
        if chunk_type == b'CgBI':
            # Remove CgBI chunk
            new_data = data[:offset] + data[offset + chunk_length + 12:]
            
            # Write modified PNG
            with open(output_path, 'wb') as f:
                f.write(new_data)
            return True
            
        offset += chunk_length + 12
        if offset >= len(data):
            break
    
    return False

def extract_highest_quality_icon(ipa_path, output_path):
    """
    Extract the highest quality icon from an IPA or TIPA file, handling iOS-optimized PNGs.
    
    Args:
        ipa_path (str): Path to the IPA or TIPA file
        output_path (str): Path to save the extracted icon
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Extract IPA/TIPA (zip-based)
        with zipfile.ZipFile(ipa_path, 'r') as z:
            z.extractall(temp_dir)
        
        # Find Info.plist
        plist_path = None
        for root, _, files in os.walk(temp_dir):
            if 'Info.plist' in files:
                plist_path = os.path.join(root, 'Info.plist')
                break
        
        if not plist_path:
            raise FileNotFoundError("Info.plist not found in IPA/TIPA file")
        
        # Parse Info.plist
        with open(plist_path, 'rb') as f:
            plist = plistlib.load(f)
        
        # Get icon files from CFBundleIcons or CFBundleIconFiles
        icon_files = []
        if 'CFBundleIcons' in plist:
            primary_icon = plist['CFBundleIcons'].get('CFBundlePrimaryIcon', {})
            icon_files = primary_icon.get('CFBundleIconFiles', [])
        elif 'CFBundleIconFiles' in plist:
            icon_files = plist.get('CFBundleIconFiles', [])
        
        if not icon_files:
            raise KeyError("No icon files found in Info.plist")
        
        # Search for icon files
        largest_icon = None
        largest_size = 0
        icon_temp_path = None
        
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if any(icon_name in file for icon_name in icon_files):
                    if file.endswith('.png'):
                        full_path = os.path.join(root, file)
                        try:
                            with open(full_path, 'rb') as f:
                                data = f.read()
                                if is_ios_optimized_png(data):
                                    # Save to temp for conversion
                                    icon_temp_path = os.path.join(temp_dir, 'temp_icon.png')
                                    if convert_ios_optimized_png(full_path, icon_temp_path):
                                        with Image.open(icon_temp_path) as img:
                                            width, height = img.size
                                            size = width * height
                                            if size > largest_size:
                                                largest_size = size
                                                largest_icon = icon_temp_path
                                else:
                                    with Image.open(full_path) as img:
                                        width, height = img.size
                                        size = width * height
                                        if size > largest_size:
                                            largest_size = size
                                            largest_icon = full_path
                        except Exception as e:
                            print(f"Error processing {file}: {e}")
        
        if not largest_icon:
            raise FileNotFoundError("No valid icon files found")
        
        # Copy the final icon
        shutil.copy(largest_icon, output_path)
        print(f"Icon extracted to {output_path}")
    
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)

def download_file(url, output_path):
    """Download a file from URL to the specified path."""
    headers = {}
    
    # Add GitHub token if the URL is from GitHub
    if 'raw.githubusercontent.com' in url:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    
    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()
    
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def get_latest_version_url(app_json_path):
    """Get the URL of the latest version from app.json."""
    with open(app_json_path, 'r') as f:
        app_data = json.load(f)
    
    if not app_data.get('versions'):
        return None
    
    # Sort versions by date in descending order
    versions = sorted(app_data['versions'], key=lambda x: x['date'], reverse=True)
    return versions[0]['url']

def process_app_json(app_json_path, output_dir):
    """Process a single app.json file and extract its icon."""
    try:
        # Get the latest version URL
        ipa_url = get_latest_version_url(app_json_path)
        if not ipa_url:
            print(f"No versions found in {app_json_path}")
            return
        
        # Create temp directory for IPA
        temp_dir = tempfile.mkdtemp()
        ipa_path = os.path.join(temp_dir, 'temp.ipa')
        
        try:
            # Download IPA
            print(f"Downloading IPA from {ipa_url}")
            download_file(ipa_url, ipa_path)
            
            # Get app directory path
            app_dir = os.path.dirname(app_json_path)
            output_path = os.path.join(app_dir, 'icon.png')
            
            # Extract icon
            extract_highest_quality_icon(ipa_path, output_path)
            
        finally:
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        print(f"Error processing {app_json_path}: {e}")

def process_all_apps(apps_dir, output_dir, target_apps=None):
    """Process app.json files in the Apps directory, optionally filtering by target apps."""
    # Walk through Apps directory
    for root, _, files in os.walk(apps_dir):
        if 'app.json' in files:
            app_dir = os.path.basename(root)
            if target_apps and app_dir not in target_apps:
                continue
            app_json_path = os.path.join(root, 'app.json')
            process_app_json(app_json_path, output_dir)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract icons from IPAs listed in app.json files")
    parser.add_argument("--apps-dir", default="Apps", help="Directory containing app.json files")
    parser.add_argument("--output-dir", default="static/icons", help="Directory to save extracted icons (deprecated)")
    parser.add_argument("--apps", help="Comma-separated list of app names to process")
    args = parser.parse_args()
    
    try:
        target_apps = [app.strip() for app in args.apps.split(",")] if args.apps else None
        process_all_apps(args.apps_dir, args.output_dir, target_apps)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)