#!/usr/bin/env python3
import sys
import json
import os
import logging
import requests
from typing import Dict, Any, List
from packaging import version
from datetime import datetime
import random
import subprocess
from extract_permissions import update_app_permissions

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

class RepoUpdater:
    """Repository manager for multiple format generation"""
    
    def __init__(self, base_dir: str = '.'):
        self.base_dir = os.path.abspath(base_dir)
        self.apps_dir = os.path.join(self.base_dir, 'Apps')
        self.logger = logging.getLogger(__name__)
    
    def load_json_file(self, file_path: str) -> Dict[str, Any] | None:
        """Load and parse a JSON file"""
        try:
            if not os.path.exists(file_path):
                return None
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error reading {file_path}: {e}")
            return None

    def save_json_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """Save data to a JSON file"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error writing {file_path}: {e}")
            return False

    def get_weekly_featured_apps(self) -> List[str]:
        """Get 5 random bundle IDs for featured apps section"""
        try:
            apps = [d for d in os.listdir(self.apps_dir) 
                   if os.path.isdir(os.path.join(self.apps_dir, d))]
            
            # Get current week number for consistent selection
            current_week = datetime.now().isocalendar()[1]
            year = datetime.now().year
            random.seed(f"{year}-{current_week}")
            
            bundle_ids = []
            for app_name in apps:
                if app_data := self.load_json_file(os.path.join(self.apps_dir, app_name, 'app.json')):
                    if bundle_id := app_data.get("bundleIdentifier"):
                        bundle_ids.append(bundle_id)
            
            featured = bundle_ids[:5] if len(bundle_ids) <= 5 else random.sample(bundle_ids, 5)
            random.seed()  # Reset random seed
            return featured
            
        except Exception as e:
            self.logger.error(f"Error getting featured apps: {str(e)}")
            return []

    def update_app_versions(self, app_name: str) -> Dict[str, Any]:
        """Update an app's versions from GitHub"""
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
            unique_versions = set()  # To track unique version strings
            
            for repo_url in repos:
                if "github.com" not in repo_url:
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
                if response.status_code != 200:
                    self.logger.error(f"Failed to fetch releases for {repo_url}: {response.status_code}")
                    continue
                
                for release in response.json():
                    # Track if we've added a version for this release
                    release_version = release['tag_name']  # Use the raw version string
                    release_date = release['published_at']  # Get the release date
                    if release_version in unique_versions:
                        continue  # Skip if we've already added this version
                    
                    # Add the version to the set to track uniqueness
                    unique_versions.add(release_version)
                    
                    # Find the first valid asset (ipa/tipa)
                    for asset in release.get('assets', []):
                        if asset['name'].lower().endswith(('.ipa', '.tipa')):
                            version_info = {
                                "version": release_version,  # Use the raw version string
                                "date": release_date.split('T')[0],  # Store the date in YYYY-MM-DD format
                                "size": asset['size'],
                                "downloadURL": asset['browser_download_url'],
                                "minOSVersion": "14.0",
                                "maxOSVersion": "17.0",
                                "localizedDescription": app_data.get("localizedDescription", "")
                            }
                            if version_info["downloadURL"] not in existing_urls:
                                new_versions.append(version_info)
                                existing_urls.add(version_info["downloadURL"])
                            break  # Exit after adding the first valid asset

                if new_versions:
                    # Sort all versions by date (latest first)
                    all_versions = existing_versions + new_versions
                    all_versions.sort(key=lambda x: x['date'], reverse=True)  # Sort by date
                    
                    # Keep only the latest 5 versions
                    app_data["versions"] = all_versions[:5]
                    
                    # Save the updated app_data
                    if self.save_json_file(os.path.join(self.apps_dir, app_name, 'app.json'), app_data):
                        return {
                            "success": True,
                            "message": f"Added {len(new_versions)} new version(s), pruned to 5 most recent",
                            "data": {"new_versions": new_versions}
                        }
            
            return {"success": True, "message": "No new versions found"}
            
        except Exception as e:
            self.logger.error(f"Error updating versions for {app_name}: {str(e)}")
            return {"success": False, "message": str(e)}

    def compile_all_formats(self) -> Dict[str, Any]:
        """Compile repository into all supported formats"""
        try:
            repo_info = self.load_json_file(os.path.join(self.base_dir, 'repo-info.json'))
            if not repo_info:
                return {"success": False, "message": "Could not load repo-info.json"}

            # Base data preparation
            featured_apps = self.get_weekly_featured_apps()
            apps = []
            for app_name in os.listdir(self.apps_dir):
                if not os.path.isdir(os.path.join(self.apps_dir, app_name)):
                    continue
                    
                if app_data := self.load_json_file(os.path.join(self.apps_dir, app_name, 'app.json')):
                    app_data.pop('repository', None)  # Remove repository from app data
                    apps.append(app_data)

            # Generate formats
            formats = {
                'altstore.json': self._generate_altstore_format,
                'trollapps.json': self._generate_trollapps_format,
                'scarlet.json': self._generate_scarlet_format,
                'esign.json': self._generate_esign_format
            }

            # Save all formats
            for filename, generator in formats.items():
                data = generator(repo_info, apps, featured_apps)
                if not self.save_json_file(os.path.join(self.base_dir, filename), data):
                    return {"success": False, "message": f"Failed to save {filename}"}

            return {"success": True, "message": "All repository formats compiled successfully"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _generate_altstore_format(self, repo_info: Dict, apps: List, featured_apps: List) -> Dict:
        """Generate AltStore format"""
        return {
            "name": repo_info.get("name"),
            "identifier": repo_info.get("identifier"),
            "subtitle": repo_info.get("subtitle"),
            "iconURL": repo_info.get("iconURL"),
            "website": repo_info.get("website"),
            "sourceURL": "https://raw.githubusercontent.com/DRKCTRL/DRKSRC/main/altstore.json",
            "tintColor": repo_info.get("tintColor", "").lstrip("#"),
            "featuredApps": featured_apps,
            "crypto": repo_info.get("crypto", {}),
            "apps": [
                self._convert_app_to_single_version(app, repo_info, strip_tint=True)
                for app in apps if app.get("versions")
            ]
        }

    def _generate_trollapps_format(self, repo_info: Dict, apps: List, featured_apps: List) -> Dict:
        """Generate TrollApps format"""
        return {
            "name": repo_info.get("name"),
            "subtitle": repo_info.get("subtitle"),
            "description": repo_info.get("description"),
            "iconURL": repo_info.get("iconURL"),
            "headerURL": repo_info.get("headerURL"),
            "website": repo_info.get("website"),
            "tintColor": repo_info.get("tintColor"),  # Keep original format with #
            "featuredApps": featured_apps,
            "apps": [
                {
                    "name": app.get("name", ""),
                    "bundleIdentifier": app.get("bundleIdentifier", ""),
                    "developerName": app.get("developerName", ""),
                    "subtitle": app.get("subtitle", ""),
                    "localizedDescription": app.get("localizedDescription", ""),
                    "iconURL": app.get("iconURL", ""),
                    "tintColor": repo_info.get("tintColor"),  # Keep original format with #
                    "screenshotURLs": app.get("screenshotURLs", []),
                    "versions": [
                        {
                            "version": ver.get("version", ""),
                            "date": ver.get("date", ""),
                            "localizedDescription": app.get("localizedDescription", ""),
                            "downloadURL": ver.get("downloadURL", ""),
                            "size": ver.get("size", 0),
                            "minOSVersion": "14.0",
                            "maxOSVersion": "17.0"
                        }
                        for ver in app.get("versions", [])
                    ],
                    "appPermissions": {}
                }
                for app in apps
            ],
            "news": []
        }

    def _generate_scarlet_format(self, repo_info: Dict, apps: List, featured_apps: List) -> Dict:
        """Generate Scarlet format"""
        scarlet_data = {
            "META": {
                "repoName": repo_info.get("name", "DRKSRC"),
                "repoIcon": repo_info.get("iconURL", "")
            },
            "Tweaked": [],
            "Games": [],
            "Emulators": [],
            "Other": []
        }

        # Map apps to Scarlet format
        for app in apps:
            scarlet_app = {
                "name": app.get("name", ""),
                "version": app.get("versions", [{}])[0].get("version", "") if app.get("versions") else "",
                "icon": app.get("iconURL", ""),
                "down": app.get("versions", [{}])[0].get("downloadURL", "") if app.get("versions") else "",
                "category": app.get("category", "Other"),
                "banner": repo_info.get("headerURL", ""),
                "description": app.get("localizedDescription", ""),
                "bundleID": app.get("bundleIdentifier", ""),
                "contact": {
                    "web": repo_info.get("website", "")
                },
                "screenshots": app.get("screenshotURLs", [])
            }
            
            # Add app to appropriate category
            category = "Tweaked" if app.get("category") == "utilities" else "Other"
            scarlet_data[category].append(scarlet_app)

        return scarlet_data

    def _generate_esign_format(self, repo_info: Dict, apps: List, featured_apps: List) -> Dict:
        """Generate ESign format"""
        return {
            "name": repo_info.get("name"),
            "identifier": repo_info.get("identifier"),
            "subtitle": repo_info.get("subtitle"),
            "iconURL": repo_info.get("iconURL"),
            "website": repo_info.get("website"),
            "sourceURL": "https://raw.githubusercontent.com/DRKCTRL/DRKSRC/main/esign.json",
            "tintColor": repo_info.get("tintColor", "").lstrip("#"),  # Remove # for ESign
            "featuredApps": featured_apps,
            "apps": [
                self._convert_app_to_single_version(app, repo_info, strip_tint=True)
                for app in apps if app.get("versions")
            ]
        }

    def _convert_app_to_single_version(self, app: Dict, repo_info: Dict, strip_tint: bool = False) -> Dict:
        """Convert multi-version app to single version format"""
        latest_version = app.get("versions", [{}])[0] if app.get("versions") else {}
        tint_color = repo_info.get("tintColor", "")
        if strip_tint:
            tint_color = tint_color.lstrip("#")
            
        return {
            "name": app.get("name", ""),
            "bundleIdentifier": app.get("bundleIdentifier", ""),
            "developerName": app.get("developerName", ""),
            "version": latest_version.get("version", ""),
            "versionDate": latest_version.get("date", ""),
            "downloadURL": latest_version.get("downloadURL", ""),
            "localizedDescription": app.get("localizedDescription", ""),
            "iconURL": app.get("iconURL", ""),
            "tintColor": tint_color,
            "size": latest_version.get("size", 0),
            "screenshotURLs": app.get("screenshotURLs", [])
        }

def main():
    """Main function to update repository"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        repo = RepoUpdater()
        logger.info("Starting repository update")
        
        # Update app versions
        updated = []        
        failed = []
        for app in os.listdir(repo.apps_dir):
            if os.path.isdir(os.path.join(repo.apps_dir, app)):
                result = repo.update_app_versions(app)
                if result["success"] and result.get("data", {}).get("new_versions"):
                    updated.append(app)
                elif not result["success"]:
                    failed.append(app)
        
        logger.info(f"Updated versions for {len(updated)} apps")
        if failed:
            logger.warning(f"Failed to update {len(failed)} apps")
        
        # Compile all repository formats
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