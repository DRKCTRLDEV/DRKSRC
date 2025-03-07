#!/usr/bin/env python3
import argparse
import json
import os
import logging
import random
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Configuration Constants
CONFIG = {
    "NO_ICON_PATH": "https://raw.githubusercontent.com/DRKCTRL/DRKSRC/main/static/assets/no-icon.png",
    "DEFAULT_MIN_OS": "13.0",
    "DEFAULT_MAX_OS": "18.0",
    "OUTPUT_FILES": {
        "altstore": "altstore.json",
        "trollapps": "trollapps.json",
        "scarlet": "scarlet.json"
    }
}

def configure_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure logging with customizable verbosity."""
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

class RepoCompiler:
    def __init__(self, root_dir: str = '.', featured_count: int = 5, output_dir: str = '.'):
        """Initialize the RepoCompiler.

        Args:
            root_dir: Directory containing repo-info.json and Apps folder.
            featured_count: Number of apps to feature.
            output_dir: Directory to save compiled JSON files.
        """
        self.root_dir = os.path.abspath(root_dir)
        self.apps_dir = os.path.join(self.root_dir, 'Apps')
        self.output_dir = os.path.abspath(output_dir)
        self.featured_count = featured_count
        self.logger = logging.getLogger(self.__class__.__name__)

    def load_config(self, path: str) -> Optional[Dict]:
        """Load a JSON config file safely."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.warning(f"Config file not found: {path}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {path}: {e}")
            return None
        except PermissionError as e:
            self.logger.error(f"Permission denied for {path}: {e}")
            return None

    def save_config(self, path: str, data: Dict, dry_run: bool = False) -> bool:
        """Save a JSON config file, optionally simulating the write."""
        if dry_run:
            self.logger.info(f"Dry run: Would save to {path}")
            return True
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Failed to write {path}: {e}")
            return False

    def _load_app_data(self, target_fmt: str) -> Tuple[List[Dict], List[str]]:
        """Load app data from the Apps directory."""
        if not os.path.exists(self.apps_dir):
            self.logger.error(f"Apps directory not found: {self.apps_dir}")
            return [], []

        apps = []
        bundle_ids = []

        for app_dir in sorted(os.listdir(self.apps_dir)):
            path = os.path.join(self.apps_dir, app_dir)
            if not os.path.isdir(path):
                continue

            app_config = self.load_config(os.path.join(path, 'app.json'))
            if not app_config or not (bid := app_config.get("bundleID")):
                self.logger.warning(f"Skipping invalid app config in {path}")
                continue
            if not app_config.get("name"):
                self.logger.warning(f"App in {path} missing name, using default")
                app_config["name"] = "Unnamed App"
            apps.append(app_config)
            bundle_ids.append(bid)
            self.logger.info(f"Loaded app: {app_config['name']} ({bid})")

        if not bundle_ids:
            self.logger.warning("No valid apps found for featured selection")
            return apps, []

        current_week = datetime.now().isocalendar()[1]
        random.seed(f"{datetime.now().year}-{current_week}")
        featured = random.sample(bundle_ids, min(self.featured_count, len(bundle_ids)))
        random.seed()

        self.logger.info(f"Total apps loaded: {len(apps)}")
        return apps, featured

    def compile_repos(self, target_fmt: Optional[str] = None, dry_run: bool = False) -> Dict:
        """Compile repository files for specified or all formats."""
        repo_config = self.load_config(os.path.join(self.root_dir, 'repo-info.json'))
        if not repo_config:
            return {'success': False, 'error': 'Missing or invalid repo config'}

        apps, featured = self._load_app_data(target_fmt)
        if not apps:
            return {'success': False, 'error': 'No valid apps found'}

        formats = {
            'altstore': (CONFIG["OUTPUT_FILES"]["altstore"], self._format_altstore),
            'trollapps': (CONFIG["OUTPUT_FILES"]["trollapps"], self._format_trollapps),
            'scarlet': (CONFIG["OUTPUT_FILES"]["scarlet"], self._format_scarlet)
        }

        if target_fmt and (target_fmt := target_fmt.lower()) in formats:
            formats = {target_fmt: formats[target_fmt]}
        elif target_fmt:
            return {'success': False, 'error': f'Invalid format: {target_fmt}'}

        for fmt, (filename, formatter) in formats.items():
            repo_data = formatter(repo_config, apps) if fmt == 'scarlet' else formatter(repo_config, apps, featured)
            output_path = os.path.join(self.output_dir, filename)
            if not self.save_config(output_path, repo_data, dry_run):
                return {'success': False, 'error': f'Failed to save {filename}'}

        return {'success': True}

    def _format_altstore(self, repo_config: Dict, apps: List[Dict], featured: List[str]) -> Dict:
        """Format repository data for AltStore."""
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
        """Format repository data for TrollApps."""
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
        """Format repository data for Scarlet."""
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
        """Create an app entry for a specific format."""
        if fmt == 'scarlet':
            versions = app.get('versions', [{}])
            version_data = versions[0] if versions else {}
            entry = {
                'name': app.get('name', 'Unnamed App'),
                'version': version_data.get('version', 'Unknown'),
                'down': version_data.get('url', ''),
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
            'iconURL': app.get('icon') if app.get('icon') else CONFIG["NO_ICON_PATH"],
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
        """Format a version entry for an app."""
        return {
            "version": version.get("version", "Unknown"),
            "date": version.get("date"),
            "downloadURL": version.get("url", ""),
            "size": version.get("size", 0),
            "minOSVersion": CONFIG["DEFAULT_MIN_OS"],
            "maxOSVersion": CONFIG["DEFAULT_MAX_OS"]
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile repository files for different formats.")
    parser.add_argument('-f', '--format', type=str, choices=['altstore', 'trollapps', 'scarlet'],
                        help="Output format (if omitted, compiles all).")
    parser.add_argument('--output-dir', type=str, default='.',
                        help="Directory to save output JSON files.")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed logging.")
    parser.add_argument('--quiet', action='store_true', help="Suppress non-error logs.")
    parser.add_argument('--dry-run', action='store_true', help="Simulate without writing files.")
    args = parser.parse_args()

    configure_logging(verbose=args.verbose, quiet=args.quiet)
    compiler = RepoCompiler(output_dir=args.output_dir)
    result = compiler.compile_repos(target_fmt=args.format, dry_run=args.dry_run)
    if not result.get("success"):
        logging.error(f"Compilation failed: {result.get('error')}")
        sys.exit(1)
    logging.info("Compilation completed successfully.")