#!/usr/bin/env python3
import sys
import json
import os
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict  # Importing defaultdict

def configure_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# Define the path to the no-icon.png file
NO_ICON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'https://raw.githubusercontent.com/DRKCTRL/DRKSRC/main/static/assets/no-icon.png'))

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
        except Exception as e:
            self.logger.error(f"Config read error: {path} - {e}")
            return None

    def save_config(self, path: str, data: Dict) -> bool:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Config write error: {path} - {e}")
            return False

    def _load_app_data(self, target_fmt: str) -> tuple[List[Dict], List[str]]:
        try:
            apps = []
            bundle_ids = []
            
            for app_dir in os.listdir(self.apps_dir):
                path = os.path.join(self.apps_dir, app_dir)
                if not os.path.isdir(path):
                    continue
                
                app_config = self.load_config(os.path.join(path, 'app.json'))
                if app_config and (bid := app_config.get("bundleID")):
                    apps.append(app_config)
                    bundle_ids.append(bid)
                    self.logger.info(f"Loaded app: {app_config['name']} with bundle ID: {bid}")
                else:
                    self.logger.warning(f"App config missing or invalid in {path}")

            current_week = datetime.now().isocalendar()[1]
            random.seed(f"{datetime.now().year}-{current_week}")
            featured = random.sample(bundle_ids, min(self.featured_count, len(bundle_ids))) if bundle_ids else []
            random.seed()
            
            self.logger.info(f"Total apps loaded: {len(apps)}")
            
            return apps, featured
        
        except Exception as e:
            self.logger.error(f"App data error: {e}")
            return [], []

    def compile_repos(self, target_fmt: Optional[str] = None) -> Dict:
        repo_config = self.load_config(os.path.join(self.root_dir, 'repo-info.json'))
        if not repo_config:
            return {'success': False, 'error': 'Missing repo config'}

        apps, featured = self._load_app_data(target_fmt)
        if not apps:
            return {'success': False, 'error': 'No apps found to compile'}

        formats = {'altstore': ('altstore.json', self._format_altstore),
                  'trollapps': ('trollapps.json', self._format_trollapps),
                  'scarlet': ('scarlet.json', self._format_scarlet)}

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
        entry = {
            'name': app.get('name'),
            'bundleIdentifier': app.get('bundleID'),
            'developerName': app.get('devName'),
            'subtitle': app.get('subtitle'),
            'localizedDescription': app.get('description'),
            'iconURL': app.get('icon') if app.get('icon') else NO_ICON_PATH,
            'category': app.get('category'),
            'versions': [self._format_version(v) for v in app.get('versions', [])],
            'appPermissions': {'entitlements': {}, 'privacy': {}}
        }
        if fmt == 'altstore':
            entry['screenshots'] = app.get('screenshots', [])
        elif fmt == 'trollapps':
            entry['screenshotURLs'] = app.get('screenshots', [])
        elif fmt == 'scarlet':
            entry.update({
                'version': app.get('versions', [{}])[0].get('version'),
                'down': app.get('versions', [{}])[0].get('url'),
                'dev': app.get('devName'),
                'description': app.get('description'),
                'bundleID': app.get('bundleID'),
                'icon': app.get('icon') if app.get('icon') else NO_ICON_PATH
            })
        return entry

    def _format_version(self, version: Dict) -> Dict:
        return {
            "version": version.get("version"),
            "date": version.get("date"),
            "downloadURL": version.get("url"),
            "size": version.get("size"),
            "minOSVersion": "13.0",
            "maxOSVersion": "18.0"
        }

if __name__ == "__main__":
    configure_logging()
    compiler = RepoCompiler()
    result = compiler.compile_repos(target_fmt=sys.argv[1] if len(sys.argv) > 1 else None)
    if not result.get("success"):
        logging.error(f"Compilation failed: {result.get('error')}")
        sys.exit(1)
    logging.info("Compilation completed successfully.")