#!/usr/bin/env python3
import argparse
import json
import os
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

NO_ICON_PATH = 'https://raw.githubusercontent.com/DRKCTRL/DRKSRC/main/static/assets/no-icon.png'

class RepoCompiler:
    def __init__(self, root_dir: str = '.', featured_count: int = 5):
        self.root_dir = os.path.abspath(root_dir)
        self.apps_dir = os.path.join(self.root_dir, 'Apps')
        self.featured_count = featured_count
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def load_config(self, path: str) -> Optional[Dict]:
        try:
            if not os.path.exists(path):
                self.logger.warning(f"Config file does not exist: {path}")
                return None
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file: {path} - {e}")
            return None
        except Exception as e:
            self.logger.error(f"Config read error: {path} - {e}")
            return None

    def save_config(self, path: str, data: Dict) -> bool:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Config write error: {path} - {e}")
            return False

    def _load_app_data(self, target_fmt: str) -> tuple[List[Dict], List[str]]:
        try:
            if not os.path.exists(self.apps_dir):
                self.logger.error(f"Apps directory does not exist: {self.apps_dir}")
                return [], []
            
            apps = []
            bundle_ids = []
            
            for app_dir in sorted(os.listdir(self.apps_dir)):
                path = os.path.join(self.apps_dir, app_dir)
                if not os.path.isdir(path):
                    continue
                
                app_config = self.load_config(os.path.join(path, 'app.json'))
                if app_config and (bid := app_config.get("bundleID")):
                    apps.append(app_config)
                    bundle_ids.append(bid)
                    self.logger.info(f"Loaded app: {app_config.get('name', 'Unnamed')} with bundle ID: {bid}")
                else:
                    self.logger.warning(f"App config missing or invalid in {path}")

            if not bundle_ids:
                self.logger.warning("No valid apps found for featured selection")
                return apps, []

            current_week = datetime.now().isocalendar()[1]
            random.seed(f"{datetime.now().year}-{current_week}")
            featured = random.sample(bundle_ids, min(self.featured_count, len(bundle_ids)))
            random.seed()
            
            self.logger.info(f"Total apps loaded: {len(apps)}")
            return apps, featured
        
        except Exception as e:
            self.logger.error(f"App data error: {e}")
            return [], []

    def compile_repos(self, target_fmt: Optional[str] = None) -> Dict:
        repo_config = self.load_config(os.path.join(self.root_dir, 'repo-info.json'))
        if not repo_config:
            return {'success': False, 'error': 'Missing or invalid repo config'}

        apps, featured = self._load_app_data(target_fmt)
        if not apps:
            return {'success': False, 'error': 'No valid apps found to compile'}

        formats = {
            'altstore': ('altstore.json', self._format_altstore),
            'trollapps': ('trollapps.json', self._format_trollapps),
            'scarlet': ('scarlet.json', self._format_scarlet)
        }

        if target_fmt and (target_fmt := target_fmt.lower()) in formats:
            formats = {target_fmt: formats[target_fmt]}
        elif target_fmt:
            return {'success': False, 'error': f'Invalid format: {target_fmt}'}

        for fmt, (filename, formatter) in formats.items():
            repo_data = formatter(repo_config, apps) if fmt == 'scarlet' else formatter(repo_config, apps, featured)
            if not self.save_config(os.path.join(self.root_dir, filename), repo_data):
                return {'success': False, 'error': f'Failed to save {filename}'}

        return {'success': True}

    def _format_altstore(self, repo_config: Dict, apps: List[Dict], featured: List[str]) -> Dict:
        return {
            "name": repo_config.get("name"),
            "subtitle": repo_config.get("subtitle"),
            "description": repo_config.get("description"),
            "iconURL": repo_config.get("iconURL"),
            "headerURL": repo_config.get("headerURL"),
            "website": repo_config.get("website"),
            "tintColor": repo_config.get("tintColor"),
            "featuredApps": featured,
            "apps": [self._create_entry(app, 'altstore') for app in apps],
        }

    def _format_trollapps(self, repo_config: Dict, apps: List[Dict], featured: List[str]) -> Dict:
        return {
            "name": repo_config.get("name"),
            "subtitle": repo_config.get("subtitle"),
            "description": repo_config.get("description"),
            "iconURL": repo_config.get("iconURL"),
            "headerURL": repo_config.get("headerURL"),
            "website": repo_config.get("website"),
            "tintColor": repo_config.get("tintColor"),
            "featuredApps": featured,
            "apps": [self._create_entry(app, 'trollapps') for app in apps],
        }

    def _format_scarlet(self, repo_config: Dict, apps: List[Dict]) -> Dict:
        categories = defaultdict(list)

        for app in apps:
            category = app.get("category", "Other")
            categories[category].append(self._create_entry(app, 'scarlet'))

        return {
            "META": {
                "repoName": repo_config.get("name"),
                "repoIcon": repo_config.get("iconURL"),
            },
            **categories
        }

    def _create_entry(self, app: Dict, fmt: str) -> Dict:
        if fmt == 'scarlet':
            entry = {
                'name': app.get('name', 'Unnamed App'),
                'version': app.get('versions', [{}])[0].get('version', 'Unknown'),
                'down': app.get('versions', [{}])[0].get('url', ''),
                'category': app.get('category', 'Other'),
                'description': app.get('description', ''),
                'bundleID': app.get('bundleID', 'Unknown')
            }
            if app.get('icon'):
                entry['icon'] = app.get('icon')
            if app.get('scarletDebs'):
                entry['debs'] = app.get('scarletDebs')
            if app.get('screenshots'):
                entry['screenshots'] = app.get('screenshots')
            if app.get('dev'):
                entry['dev'] = app.get('dev')
            if 'scarletBackup' in app:
                entry['enableBackup'] = app.get('scarletBackup')
            return entry
        
        entry = {
            'name': app.get('name', 'Unnamed App'),
            'bundleIdentifier': app.get('bundleID', 'Unknown'),
            'developerName': app.get('devName', 'Unknown Developer'),
            'subtitle': app.get('subtitle'),
            'localizedDescription': app.get('description', ''),
            'iconURL': app.get('icon') if app.get('icon') else NO_ICON_PATH,
            'category': app.get('category', 'Other'),
            'screenshots': app.get('screenshots', []),
            'versions': [self._format_version(v) for v in app.get('versions', [])],
            'appPermissions': {'entitlements': {}, 'privacy': {}}
        }
        if fmt == 'altstore':
            entry['screenshots'] = app.get('screenshots', [])
        elif fmt == 'trollapps':
            entry['screenshotURLs'] = app.get('screenshots', [])
        return entry

    def _format_version(self, version: Dict) -> Dict:
        return {
            "version": version.get("version", "Unknown"),
            "date": version.get("date"),
            "downloadURL": version.get("url", ""),
            "size": version.get("size", 0),
            "minOSVersion": "13.0",
            "maxOSVersion": "18.0"
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile repository files for different formats.")
    parser.add_argument('--format', type=str, choices=['altstore', 'trollapps', 'scarlet'], 
                        help="Specify the output format (altstore, trollapps, scarlet). If omitted, compiles all formats.")
    args = parser.parse_args()

    configure_logging()
    compiler = RepoCompiler()
    result = compiler.compile_repos(target_fmt=args.format)
    if not result.get("success"):
        logging.error(f"Compilation failed: {result.get('error')}")
        sys.exit(1)
    logging.info("Compilation completed successfully.")