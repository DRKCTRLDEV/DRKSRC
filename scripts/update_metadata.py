#!/usr/bin/env python3
import sys
import json
import os
import logging
import requests
import plistlib
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

class AppInfoExtractor:
    def __init__(self, base_dir: str = '.'):
        self.base_dir = os.path.abspath(base_dir)
        self.apps_dir = os.path.join(self.base_dir, 'Apps')
        self.logger = logging.getLogger(__name__)

    def load_json_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        try:
            if not os.path.exists(file_path):
                return None
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error reading {file_path}: {e}")
            return None

    def save_json_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error writing {file_path}: {e}")
            return False

    def download_and_extract_app_info(self, app_name: str) -> Dict[str, Any]:
        try:
            app_path = os.path.join(self.apps_dir, app_name)
            app_data = self.load_json_file(os.path.join(app_path, 'app.json'))
            if not app_data:
                return {"success": False, "message": "Failed to load app data"}

            versions = app_data.get("versions", [])
            if not versions:
                return {"success": False, "message": "No versions found"}

            latest_version = versions[0]
            download_url = latest_version.get("downloadURL")
            if not download_url:
                return {"success": False, "message": "No download URL found"}

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                ipa_path = temp_dir_path / f"{app_name}.ipa"
                
                # Download IPA
                self.logger.info(f"Downloading {download_url}")
                response = requests.get(download_url, stream=True, timeout=30)
                if response.status_code != 200:
                    return {"success": False, "message": f"Failed to download IPA (HTTP {response.status_code})"}
                
                with open(ipa_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Extract IPA
                self.logger.info(f"Extracting {ipa_path.name}")
                result = subprocess.run(
                    ["unzip", "-q", str(ipa_path), "-d", str(temp_dir_path)],
                    capture_output=True
                )
                if result.returncode != 0:
                    return {"success": False, "message": f"Failed to extract IPA: {result.stderr.decode()}"}

                # Find app bundle
                payload_dir = temp_dir_path / "Payload"
                app_bundle = next(payload_dir.glob("*.app"), None)
                if not app_bundle:
                    return {"success": False, "message": "No .app bundle found"}

                # Process app bundle
                info_plist_path = app_bundle / "Info.plist"
                if not info_plist_path.exists():
                    return {"success": False, "message": "Info.plist not found"}

                with open(info_plist_path, 'rb') as f:
                    info_plist = plistlib.load(f)

                # Extract icon
                icon_path = self.extract_app_icon(app_bundle, app_name)
                if icon_path:
                    app_data["iconURL"] = f"Apps/{app_name}/icon.png"

                # Update app metadata
                self.update_app_metadata(app_data, info_plist)

                if self.save_json_file(os.path.join(app_path, 'app.json'), app_data):
                    return {
                        "success": True,
                        "message": "App info updated successfully",
                        "data": {
                            "bundleIdentifier": app_data["bundleIdentifier"],
                            "name": app_data ["name"],
                            "version": app_data["version"],
                            "iconURL": app_data.get("iconURL", "")
                        }
                    }

            return {"success": False, "message": "Failed to update app info"}

        except Exception as e:
            self.logger.error(f"Error processing {app_name}: {str(e)}")
            return {"success": False, "message": str(e)}

    def update_app_metadata(self, app_data: Dict[str, Any], 
                          info_plist: Dict) -> None:
        app_data["bundleIdentifier"] = info_plist.get("CFBundleIdentifier")
        app_data["name"] = info_plist.get("CFBundleDisplayName") or info_plist.get("CFBundleName")
        app_data["version"] = info_plist.get("CFBundleShortVersionString")
        app_data["minOSVersion"] = info_plist.get("MinimumOSVersion", "14.0")

        developer_name = info_plist.get("CFBundleIdentifier", "").split(".")[0]
        app_data["developerName"] = developer_name

        privacy_info = {}
        privacy_keys = [
            "NSContactsUsageDescription",
            "NSLocationUsageDescription",
            "NSMicrophoneUsageDescription",
            "NSCameraUsageDescription",
            "NSPhotoLibraryUsageDescription",
            "NSBluetoothAlwaysUsageDescription",
            "NSBluetoothPeripheralUsageDescription",
            "NSFaceIDUsageDescription",
            "NSMotionUsageDescription",
            "NSSpeechRecognitionUsageDescription",
            "NSHealthShareUsageDescription",
            "NSHealthUpdateUsageDescription",
            "NSAppleMusicUsageDescription",
            "NSRemindersUsageDescription",
            "NSCalendarsUsageDescription",
            "NSHomeKitUsageDescription",
            "NSLocalNetworkUsageDescription",
            "NSUserTrackingUsageDescription"
        ]
        
        for key in privacy_keys:
            if value := info_plist.get(key):
                privacy_info[key] = value

        app_data["appPermissions"] = {
            "privacy": privacy_info
        }

        if category := info_plist.get("LSApplicationCategoryType"):
            app_data["category"] = self.map_application_category(category)

    def map_application_category(self, category: str) -> str:
        category_map = {
            "public.app-category.utilities": "Utilities",
            "public.app-category.games": "Games",
            "public.app-category.productivity": "Productivity",
            "public.app-category.social-networking": "Social Networking",
            "public.app-category.photo-video": "Photo & Video",
            "public.app-category.entertainment": "Entertainment",
            "public.app-category.health-fitness": "Health & Fitness",
            "public.app-category.education": "Education",
            "public.app-category.business": "Business",
            "public.app-category.music": "Music",
            "public.app-category.news": "News",
            "public.app-category.travel": "Travel",
            "public.app-category.finance": "Finance",
            "public.app-category.weather": "Weather",
            "public.app-category.shopping": "Shopping",
            "public.app-category.food-drink": "Food & Drink",
            "public.app-category.lifestyle": "Lifestyle",
            "public.app-category.sports": "Sports",
            "public.app-category.reference": "Reference",
            "public.app-category.medical": "Medical",
            "public.app-category.developer-tools": "Developer Tools",
            "public.app-category.books": "Books",
            "public.app-category.navigation": "Navigation",
            "public.app-category.magazines-newspapers": "Magazines & Newspapers",
            "public.app-category.kids": "Kids",
            "public.app-category.other": "Other"
        }
        return category_map.get(category, "Unknown")

    def extract_app_icon(self, app_bundle: Path, app_name: str) -> Optional[str]:
        try:
            icon_files = list(app_bundle.glob("AppIcon*.png"))
            if not icon_files:
                self.logger.warning("No AppIcon*.png files found")
                return None

            # Find the highest quality icon file
            icon_file = max(icon_files, key=lambda f: f.stat().st_size)
            self.logger.info(f"Processing icon: {icon_file.name}")

            # Convert to PNG and save
            output_path = os.path.join(self.apps_dir, app_name, "icon.png")
            with Image.open(icon_file) as img:
                img.convert("RGBA").save(output_path, "PNG")

            return output_path
        except Exception as e:
            self.logger.error(f"Failed to process icon: {str(e)}")
            return None

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        extractor = AppInfoExtractor()
        logger.info("Starting app info extraction")
        
        updated = []
        failed = []
        
        target_app = sys.argv[1] if len(sys.argv) > 1 else None

        for app_dir in os.listdir (extractor.apps_dir):
            app_path = os.path.join(extractor.apps_dir, app_dir)
            
            if not os.path.isdir(app_path):
                continue
            if target_app and app_dir != target_app:
                continue

            result = extractor.download_and_extract_app_info(app_dir)
            if result["success"]:
                updated.append(app_dir)
            else:
                failed.append((app_dir, result["message"]))
        
        logger.info(f"Successfully processed {len(updated)} apps")
        if failed:
            logger.error(f"Failed to process {len(failed)} apps:")
            for app, reason in failed:
                logger.error(f" - {app}: {reason}")
        
        return 0 if not failed else 1

    except Exception as e:
        logger.error(f"Fatal error during extraction: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())