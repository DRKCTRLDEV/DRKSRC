#!/usr/bin/env python3
import sys
import json
import os
import logging
import requests
import plistlib
import subprocess
import tempfile
import PIL
from PIL import Image
from pathlib import Path
from urllib.parse import urlparse

from typing import Dict, Any, List, Optional
from datetime import datetime
import random
from collections import defaultdict

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

class RepoUpdater:    
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

    def _load_apps_and_featured(self) -> tuple[List[Dict[str, Any]], List[str]]:
        try:
            apps = []
            bundle_ids = []
            for app_name in os.listdir(self.apps_dir):
                app_path = os.path.join(self.apps_dir, app_name)
                if os.path.isdir(app_path):
                    if app_data := self.load_json_file(os.path.join(app_path, 'app.json')):
                        apps.append(app_data)
                        if bundle_id := app_data.get("bundleIdentifier"):
                            bundle_ids.append(bundle_id)

            current_week = datetime.now().isocalendar()[1]
            year = datetime.now().year
            random.seed(f"{year}-{current_week}")
            featured = bundle_ids[:5] if len(bundle_ids) <= 5 else random.sample(bundle_ids, 5)
            random.seed()
            return apps, featured
            
        except Exception as e:
            self.logger.error(f"Error loading apps: {str(e)}")
            return [], []

    def update_app_versions(self, app_name: str) -> Dict[str, Any]:
        try:
            app_data = self.load_json_file(os.path.join(self.apps_dir, app_name, 'app.json'))
            if not app_data:
                return {"success": False, "message": "Failed to load app data"}
            
            repos = app_data.get("repository", [])
            if not repos:
                return {"success": False, "message": "No GitHub repository found"}

            repos = [repos] if isinstance(repos, str) else repos
            new_versions = []
            existing_versions = app_data.get("versions", [])
            existing_urls = {v.get("downloadURL", "") for v in existing_versions}
            
            for repo_url in repos:
                if "github.com" not in repo_url:
                    self.logger.error(f"Invalid repository URL: {repo_url}")
                    continue
                
                parts = repo_url.rstrip('/').split('/')
                owner, repo = parts[-2], parts[-1]
                
                headers = {}
                if repo_token := os.environ.get('REPO_TOKEN'):
                    headers['Authorization'] = f'token {repo_token}'
                
                response = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/releases",
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 404:
                    self.logger.error(f"Repository not found: {repo_url}")
                    continue
                elif response.status_code != 200:
                    self.logger.error(f"Failed to fetch releases for {repo_url}: {response.status_code}")
                    continue
                
                for release in response.json():
                    release_version = release['tag_name']
                    release_date = release['published_at']
                    
                    for asset in release.get('assets', []):
                        if asset['name'].lower().endswith(('.tipa', '.ipa')):
                            version_info = {
                                "version": release_version,
                                "date": release_date.split('T')[0],
                                "size": asset['size'],
                                "downloadURL": asset['browser_download_url']
                            }

                            if version_info["downloadURL"] not in existing_urls:
                                new_versions.append(version_info)
                                existing_urls.add(version_info["downloadURL"])

            if new_versions:
                all_versions = existing_versions + new_versions
                all_versions = self.remove_duplicate_versions(all_versions)
                all_versions.sort(key=lambda x: x['date'], reverse=True)
                app_data["versions"] = all_versions[:5]
                if self.save_json_file(os.path.join(self.apps_dir, app_name, 'app.json'), app_data):
                    return {
                        "success": True,
                        "message": f"Added {len(new_versions)} new version(s), pruned to 5 most recent",
                        "data": {"new_versions": new_versions}
                    }
            
            return {"success": True, "message": "No new versions found"}
            
        except Exception as e:
            self.logger.error(f"Error updating versions for {app _name}: {str(e)}")
            return {"success": False, "message": str(e)}

    def remove_duplicate_versions(self, versions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique_versions = []
        for version in versions:
            version_key = (version.get("version"), version.get("downloadURL"))
            if version_key not in seen:
                seen.add(version_key)
                unique_versions.append(version)
        return unique_versions

    def compile_all_formats(self) -> Dict[str, Any]:
        try:
            repo_info = self.load_json_file(os.path.join(self.base_dir, 'repo-info.json'))
            if not repo_info:
                return {"success": False, "message": "Could not load repo-info.json"}

            apps, featured_apps = self._load_apps_and_featured()

            formats = {
                'altstore.json': lambda ri, a, fa: self._generate_repo_format(ri, a, fa, "altstore"),
                'trollapps.json': lambda ri, a, fa: self._generate_repo_format(ri, a, fa, "trollapps")
            }

            for filename, generator in formats.items():
                data = generator(repo_info, apps, featured_apps)
                if not self.save_json_file(os.path.join(self.base_dir, filename), data):
                    return {"success": False, "message": f"Failed to save {filename}"}

            return {"success": True, "message": "All repository formats compiled successfully"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _generate_repo_format(self, repo_info: Dict, apps: List, featured_apps: List, format_type: str) -> Dict:
        app_entry_func = lambda app: self._create_app_entry(app, format_type)
        return {
            "name": repo_info.get("name"),
            "subtitle": repo_info.get("subtitle"),
            "description": repo_info.get("description"),
            "iconURL": repo_info.get("iconURL"),
            "headerURL": repo_info.get("headerURL"),
            "website": repo_info.get("website"),
            "tintColor": repo_info.get("tintColor"),
            "featuredApps": featured_apps,
            "apps": [app_entry_func(app) for app in apps]
        }

    def _create_app_entry(self, app: Dict, format_type: str) -> Dict:
        return {
            "name": app.get("name"),
            "bundleIdentifier": app.get("bundleIdentifier"),
            "developerName": app.get("developerName"),
            "subtitle": app.get("subtitle"),
            "localizedDescription": app.get("localizedDescription"),
            "iconURL": app.get("iconURL"),
            "category": app.get("category"),
            "screenshots" if format_type == "altstore" else "screenshotURLs": app.get("screenshots", []),
            "versions": [
                {
                    "version": ver.get("version", ""),
                    "date": ver.get("date", ""),
                    "downloadURL": ver.get("downloadURL", ""),
                    "size": ver.get("size", 0),
                    "minOSVersion": "14.0",
                    "maxOSVersion": "17.0"
                }
                for ver in app.get("versions", [])
            ],
            "appPermissions": app.get("appPermissions", {})
        }

    def download_and_extract_app_info(self, app_name: str) -> Dict[str, Any]:
        try:
            app_data = self.load_json_file(os.path.join(self.apps_dir, app_name, 'app.json'))
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
                self.logger.info(f"Downloading {download_url} to {ipa_path}")
                response = requests.get(download_url, stream=True, timeout=30)
                if response.status_code != 200:
                    self.logger.error(f"Failed to download {download_url}: {response.status_code}")
                    return {"success": False, "message": f"Failed to download {download_url}"}
                with open(ipa_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                self.logger.info(f"Extracting {ipa_path}")
                subprocess.run(["unzip", "-q", str(ipa_path), "-d", str(temp_dir_path)], check=True)

                payload_dir = temp_dir_path / "Payload"
                app_bundle = next(payload_dir.glob("*.app"), None)
                if not app_bundle:
                    return {"success": False, "message": "No .app bundle found"}

                info_plist_path = app_bundle / "Info.plist"
                if not info_plist_path.exists():
                    return {"success": False, "message": "Info.plist not found"}

                with open(info_plist_path, 'rb') as f:
                    info_plist = plistlib.load(f)

                # Call the new method to update app data
                update_result = self.update_app_data(app_data, info_plist, app_bundle, app_name)
                return update_result

        except Exception as e:
            self.logger.error(f"Error processing {app_name}: {str(e)}")
            return {"success": False, "message": str(e)}

    def update_app_data(self, app_data: Dict[str, Any], info_plist: Dict[str, Any], app_bundle: Path, app_name: str) -> Dict[str, Any]:
        try:
            # Extract app icon
            icon_path = self.extract_app_icon(app_bundle, app_name)
            if icon_path:
                app_data["iconURL"] = f"Apps/{app_name}/icon.jpg"

            # Update app data from Info.plist
            app_data["bundleIdentifier"] = info_plist.get("CFBundleIdentifier")
            app_data["name"] = info_plist.get("CFBundleName") or info_plist.get("CFBundleDisplayName")
            app_data["version"] = info_plist.get("CFBundleShortVersionString")
            app_data["minOSVersion"] = info_plist.get("MinimumOSVersion", "14.0")
            app_data["maxOSVersion"] = info_plist.get("MaximumOSVersion", "17.0")
            app_data["developerName"] = info_plist.get("CFBundleIdentifier")  # Update as needed
            app_data["appPermissions"] = self.extract_app_permissions(info_plist)

            # Save the updated app data
            if self.save_json_file(os.path.join(self.apps_dir, app_name, 'app.json'), app_data):
                return {
                    "success": True,
                    "message": "App info updated successfully",
                    "data": {
                        "bundleIdentifier": app_data["bundleIdentifier"],
                        "name": app_data["name"],
                        "version": app_data["version"],
                        "minOSVersion": app_data["minOSVersion"],
                        "maxOSVersion": app_data["maxOSVersion"],
                        "developerName": app_data["developerName"],
                        "iconURL": app_data["iconURL"]
                    }
                }

            return {"success": False, "message": "Failed to save updated app info"}

        except Exception as e:
            self.logger.error(f"Error updating app data for {app_name}: {str(e)}")
            return {"success": False, "message": str(e)}

    def extract_app_icon(self, app_bundle: Path, app_name: str) -> Optional[str]:
        try:
            icon_files = list(app_bundle.glob("AppIcon*.png"))
            if not icon_files:
                return None
            icon_file = max(icon_files, key=lambda f: f.stat().st_size)
            icon_path = os.path.join(self.apps_dir, app_name, "icon.jpg")
            with Image.open(icon_file) as img:
                img.convert("RGB").save(icon_path, "JPEG")

            return icon_path
        except Exception as e:
            self.logger.error(f"Error extracting app icon: {str(e)}")
            return None

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        repo = RepoUpdater()
        logger.info("Starting repository update")
        updated = []        
        failed = []
        for app in os.listdir(repo.apps_dir):
            if os.path.isdir(os.path.join(repo.apps_dir, app)):
                result = repo.download_and_extract_app_info(app)
                if result["success"]:
                    updated.append(app)
                else:
                    failed.append(app)
        
        logger.info(f"Updated info for {len(updated)} apps")
        if failed:
            logger.warning(f"Failed to update {len(failed)} apps")
        
        result = repo.compile_all_formats()
        if not result["success"]:
            raise Exception(f"Failed to compile repositories: {result['message']}")
        
        logger.info("Repository update completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Error updating repository: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())