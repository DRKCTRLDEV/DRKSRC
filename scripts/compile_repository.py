#!/usr/bin/env python3
import argparse
from collections import defaultdict
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import random
import sys
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN environment variable not set")
    sys.exit(1)

CONFIG = {
    "NO_ICON_PATH": "https://raw.githubusercontent.com/DRKCTRLDEV/DRKSRC/main/static/assets/DRKSRC (No-Icon).png",
    "OUTPUT_FILES": {
        "altstore": "altstore.json",
        "trollapps": "trollapps.json",
        "scarlet": "scarlet.json"
    }
}

def configure_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

class RepoCompiler:
    def __init__(self, root_dir: str = '.', featured_count: int = 5, output_dir: str = '.'):
        self.root_dir = Path(root_dir).resolve()
        self.apps_dir = self.root_dir / 'Apps'
        self.output_dir = Path(output_dir).resolve()
        self.featured_count = featured_count
        self.logger = configure_logging()

    def load_config(self, path: Path) -> Optional[Dict]:
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            self.logger.error(f"Failed to load {path}: {e}")
            return None

    def save_config(self, path: Path, data: Dict, dry_run: bool = False) -> bool:
        if dry_run:
            self.logger.info(f"Dry run: Would save to {path}")
            return True
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            self.logger.info(f"Saved to {path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save {path}: {e}")
            return False

    def _load_app_data(self, target_fmt: str) -> Tuple[List[Dict], List[str]]:
        if not self.apps_dir.exists():
            self.logger.error(f"Apps directory not found: {self.apps_dir}")
            return [], []

        apps, bundle_ids = [], []
        for app_dir in sorted(self.apps_dir.iterdir()):
            if not app_dir.is_dir():
                self.logger.debug(f"Skipping non-directory: {app_dir}")
                continue

            app_config = self.load_config(app_dir / 'app.json')
            if not app_config or not (bid := app_config.get("bundleID")):
                self.logger.warning(f"Skipping invalid app config in {app_dir}")
                continue
            app_config.setdefault("name", "Unnamed App")
            apps.append(app_config)
            bundle_ids.append(bid)
            self.logger.info(f"Loaded app: {app_config['name']} ({bid})")

        if not bundle_ids:
            self.logger.warning("No valid apps found")
            return apps, []

        current_week = datetime.now().isocalendar().week
        # Seed random with year and week to ensure featured apps are consistent within a week but change weekly
        random.seed(f"{datetime.now().year}-{current_week}")
        featured = random.sample(bundle_ids, min(self.featured_count, len(bundle_ids)))
        random.seed()

        self.logger.info(f"Loaded {len(apps)} apps")
        return apps, featured

    def compile_repos(self, target_fmt: Optional[str] = None, verbose: bool = False) -> Dict:
        self.logger.info(f"Compiling for: {target_fmt or 'all'}")
        repo_config = self.load_config(self.root_dir / 'repo-info.json')
        if not repo_config:
            return {'success': False, 'error': 'Missing/invalid repo config'}

        apps, featured = self._load_app_data(target_fmt)
        if not apps:
            return {'success': False, 'error': 'No valid apps found'}

        formats = {
            'altstore': (self.output_dir / CONFIG["OUTPUT_FILES"]["altstore"], self._format_altstore),
            'trollapps': (self.output_dir / CONFIG["OUTPUT_FILES"]["trollapps"], self._format_trollapps),
            'scarlet': (self.output_dir / CONFIG["OUTPUT_FILES"]["scarlet"], self._format_scarlet)
        }

        target_fmt = target_fmt.lower() if target_fmt else None
        if target_fmt and target_fmt in formats:
            formats = {target_fmt: formats[target_fmt]}
        elif target_fmt:
            return {'success': False, 'error': f'Invalid format: {target_fmt}'}

        for fmt, (path, formatter) in formats.items():
            repo_data = formatter(repo_config, apps, featured) if fmt != 'scarlet' else formatter(repo_config, apps)
            if not self.save_config(path, repo_data):
                return {'success': False, 'error': f'Failed to save {path.name}'}

        self.logger.info("Compilation completed")
        return {'success': True}

    def _format_altstore(self, repo_config: Dict, apps: List[Dict], featured: List[str]) -> Dict:
        return {
            "name": repo_config.get("name", "Unnamed Repository"),
            "subtitle": repo_config.get("subtitle", ""),
            "description": repo_config.get("description", ""),
            "iconURL": repo_config.get("iconURL", ""),
            "headerURL": repo_config.get("headerURL", ""),
            "website": repo_config.get("website", ""),
            "tintColor": repo_config.get("tintColor", ""),
            "featuredApps": featured,
            "apps": [self._create_entry(app, 'altstore') for app in apps],
        }

    def _format_trollapps(self, repo_config: Dict, apps: List[Dict], featured: List[str]) -> Dict:
        return {
            "name": repo_config.get("name", "Unnamed Repository"),
            "subtitle": repo_config.get("subtitle", ""),
            "description": repo_config.get("description", ""),
            "iconURL": repo_config.get("iconURL", ""),
            "headerURL": repo_config.get("headerURL", ""),
            "website": repo_config.get("website", ""),
            "tintColor": repo_config.get("tintColor", ""),
            "featuredApps": featured,
            "apps": [self._create_entry(app, 'trollapps') for app in apps],
            "news": []  # Added empty news array
        }

    def _format_scarlet(self, repo_config: Dict, apps: List[Dict]) -> Dict:
        categories = defaultdict(list)
        for app in apps:
            category = app.get("category", "Other")
            categories[category].append(self._create_entry(app, 'scarlet'))

        return {
            "META": {
                "repoName": repo_config.get("name", "Unnamed Repository"),
                "repoIcon": repo_config.get("iconURL", ""),
            },
            **categories
        }

    def _create_entry(self, app: Dict, fmt: str) -> Dict:
        icon = app.get('icon')
        if not icon:
            icon = CONFIG["NO_ICON_PATH"]

        if fmt == 'scarlet':
            versions = app.get('versions', [{}])
            version_data = versions[0] if versions else {}
            entry = {
                'name': app.get('name', 'Unnamed App'),
                'version': version_data.get('version', 'Unknown'),
                'down': version_data.get('url', ''),
                'category': app.get('category', 'Other'),
                'description': app.get('description', ''),
                'bundleID': app.get('bundleID', 'Unknown'),
                'icon': icon
            }
            if app.get('scarletDebs'):
                entry['debs'] = app['scarletDebs']
            if app.get('devName'):
                entry['dev'] = app['devName']
            if app.get('screenshots'):
                entry['screenshots'] = app['screenshots'][:4]  # Limit to 4 screenshots
            if 'scarletBackup' in app:
                entry['enableBackup'] = app['scarletBackup']
            return entry

        entry = {
            'name': app.get('name', 'Unnamed App'),
            'bundleIdentifier': app.get('bundleID', 'Unknown'),
            'developerName': app.get('devName', 'Unknown Developer'),
            'subtitle': app.get('subtitle', ''),
            'localizedDescription': app.get('description', ''),
            'iconURL': icon,
        }
        if fmt != 'trollapps':  # Only include category for non-TrollApps formats
            entry['category'] = app.get('category', 'Other')
        entry['versions'] = [self._format_version(v, fmt) for v in app.get('versions', [])]
        if fmt == 'altstore':
            entry['screenshots'] = app.get('screenshots', [])[:4]  # Limit to 4 screenshots
        elif fmt == 'trollapps':
            entry['screenshotURLs'] = app.get('screenshots', [])[:4]  # Limit to 4 screenshots
            entry['appPermissions'] = {}  # Added empty appPermissions object
        return entry

    def _format_version(self, version: Dict, fmt: str) -> Dict:
        version_entry = {
            "version": version.get("version", "Unknown"),
            "date": version.get("date", ""),
            "downloadURL": version.get("url", ""),
            "size": version.get("size", 0)
        }
        return version_entry

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--format', type=str, choices=['altstore', 'trollapps', 'scarlet'])
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    compiler = RepoCompiler()
    result = compiler.compile_repos(args.format, args.verbose)
    logger = configure_logging(args.verbose)
    if not result['success']:
        logger.error(f"Compilation Failed: {result['error']}")
        sys.exit(1)
    logger.info("Compilation Completed")