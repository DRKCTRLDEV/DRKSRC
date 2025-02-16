#!/usr/bin/env python3
import json
import os
import logging
import requests
from typing import Dict, Any, List
from packaging import version
from datetime import datetime
import random
import subprocess

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

class RepoUpdater:
    """Minimal repository manager for automated updates"""
    
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
            
            for repo_url in repos:
                if "github.com" not in repo_url:
                    continue
                    
                parts = repo_url.rstrip('/').split('/')
                owner, repo = parts[-2], parts[-1]
                
                response = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/releases",
                    timeout=10
                )
                if response.status_code != 200:
                    continue
                    
                for release in response.json():
                    for asset in release.get('assets', []):
                        if asset['name'].lower().endswith(('.ipa', '.tipa')):
                            version_info = {
                                "version": release['tag_name'].lstrip('v'),
                                "date": release['published_at'].split('T')[0],
                                "size": asset['size'],
                                "downloadURL": asset['browser_download_url'],
                                "minOSVersion": "14.0",
                                "maxOSVersion": "17.0",
                                "localizedDescription": app_data.get("localizedDescription", "")
                            }
                            if version_info["downloadURL"] not in existing_urls:
                                new_versions.append(version_info)
                                existing_urls.add(version_info["downloadURL"])

            if new_versions:
                all_versions = existing_versions + new_versions
                try:
                    all_versions.sort(key=lambda x: version.parse(x['version']), reverse=True)
                except:
                    all_versions.sort(key=lambda x: x['version'], reverse=True)
                
                app_data["versions"] = all_versions
                if self.save_json_file(os.path.join(self.apps_dir, app_name, 'app.json'), app_data):
                    return {
                        "success": True,
                        "message": f"Added {len(new_versions)} new version(s)",
                        "data": {"new_versions": new_versions}
                    }
            
            return {"success": True, "message": "No new versions found"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}

    def compile_repository(self) -> Dict[str, Any]:
        """Compile all apps into repository file"""
        try:
            repo_info = self.load_json_file(os.path.join(self.base_dir, 'repo-info.json'))
            if not repo_info:
                return {"success": False, "message": "Could not load repo-info.json"}

            apps = []
            for app_name in os.listdir(self.apps_dir):
                app_dir = os.path.join(self.apps_dir, app_name)
                if not os.path.isdir(app_dir):
                    continue

                if app_data := self.load_json_file(os.path.join(app_dir, 'app.json')):
                    repo_app_data = app_data.copy()
                    repo_app_data.pop('repository', None)
                    apps.append(repo_app_data)

            repo_data = {
                **repo_info,
                "featuredApps": self.get_weekly_featured_apps(),
                "apps": apps,
                "news": []
            }
            
            if self.save_json_file(os.path.join(self.base_dir, 'repo.json'), repo_data):
                return {"success": True, "message": "Repository compiled successfully"}
            return {"success": False, "message": "Failed to save repo.json"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}

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
        
        # Compile repository
        result = repo.compile_repository()
        if not result["success"]:
            raise Exception(f"Failed to compile repository: {result['message']}")
        
        logger.info("Repository update completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Error updating repository: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
