import sys
import os
import json
import logging
import requests
import yaml
import argparse
from typing import Dict, Optional
from requests.exceptions import RequestException

class VersionManager:
    def __init__(self, apps_root: str, keep_versions: int = 10):
        """
        Initialize VersionManager with root directory and version retention count.

        Args:
            apps_root: Directory containing app subdirectories.
            keep_versions: Number of versions to retain (default: 10).

        Raises:
            ValueError: If keep_versions is not a positive integer.
        """
        if not isinstance(keep_versions, int) or keep_versions < 1:
            raise ValueError("keep_versions must be a positive integer")
        self.apps_root = apps_root
        self.keep_versions = keep_versions
        self.logger = self._init_logger()

    def _init_logger(self) -> logging.Logger:
        """Initialize and return a configured logger."""
        logger = logging.getLogger("VersionManager")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        return logger

    def manage(self, action: str, target: Optional[str] = None, keep: Optional[int] = None):
        """
        Manage versions for apps based on the specified action.

        Args:
            action: 'update' or 'remove'.
            target: Specific app to target (optional).
            keep: Override default number of versions to keep (optional).
        """
        self.keep_versions = max(1, keep or self.keep_versions)
        for app in os.listdir(self.apps_root):
            path = os.path.join(self.apps_root, app)
            config_path = os.path.join(path, 'app.json')

            if not self._valid_app_path(path, config_path, target):
                continue

            if action == 'update':
                self._update_versions(app, config_path)
            elif action == 'remove':
                self._remove_versions(app, config_path)

    def _valid_app_path(self, path: str, config: str, target: Optional[str]) -> bool:
        """Check if the path is a valid app directory with a config file."""
        return os.path.isdir(path) and os.path.isfile(config) and (not target or os.path.basename(path) == target)

    def _update_versions(self, app: str, config: str):
        """Update versions for the specified app."""
        self._process_versions(app, config, update=True)

    def _remove_versions(self, app: str, config: str):
        """Remove versions for the specified app."""
        self._process_versions(app, config, update=False)

    def _process_versions(self, app: str, config: str, update: bool):
        """Process app versions based on the update flag."""
        try:
            with open(config, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Config file not found for {app}")
            return
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in config for {app}")
            return
        except PermissionError:
            self.logger.error(f"Permission denied accessing config for {app}")
            return

        if not self._valid_repo(data.get('gitURLs')):
            return

        if update:
            result = self._fetch_new_versions(data, os.path.dirname(config))
            if not result['success']:
                self.logger.error(f"Failed to update {app}: {result['message']}")
                return
            data['versions'] = result['versions']
            self.logger.info(f"Successfully updated {app}: {result['message']}")
        else:
            data['versions'] = []
            self.logger.info(f"Removed all versions for {app}")

        self._save_config(config, data)

    def _fetch_new_versions(self, data: Dict, app_dir: str) -> Dict:
        """
        Fetch new release versions from GitHub repositories.

        Args:
            data: Configuration data from app.json.
            app_dir: Directory path of the app.

        Returns:
            Dict with success status, message, and list of versions.
        """
        repos = data.get('gitURLs', [])
        repos = [repos] if isinstance(repos, str) else repos
        existing = {v['url'] for v in data.get('versions', [])}
        versions = {}
        rules = self._load_rules(app_dir)

        token = os.environ.get("REPO_TOKEN")
        if not token:
            self.logger.error("GitHub token (REPO_TOKEN) not set in environment")
            return {'success': False, 'message': 'Missing GitHub token', 'versions': []}
        headers = {'Authorization': f'token {token}'}

        for repo in repos:
            if not self._valid_gh_url(repo):
                continue
            owner, repo_name = repo.rstrip('/').split('/')[-2:]
            url = f'https://api.github.com/repos/{owner}/{repo_name}/releases'

            while url:
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    releases = response.json()
                    for release in releases:
                        for asset in release.get('assets', []):
                            if self._should_include_asset(asset, rules):
                                version = {
                                    'version': self._format_version_number(release['tag_name'], rules),
                                    'date': release['published_at'].split('T')[0],
                                    'size': asset['size'],
                                    'url': asset['browser_download_url']
                                }
                                if version['url'] not in existing:
                                    versions[version['url']] = version
                    url = response.links.get('next', {}).get('url')
                except RequestException as e:
                    self.logger.error(f"API error for {repo}: {str(e)}")
                    return {'success': False, 'message': f"API error: {str(e)}", 'versions': []}

        sorted_versions = sorted(versions.values(), key=lambda x: x['date'], reverse=True)[:self.keep_versions]
        new_count = len(versions) - (len(data.get('versions', [])) - len(existing & set(versions.keys())))
        return {
            'success': True,
            'message': f"Added {new_count} versions" if new_count > 0 else "No new versions",
            'versions': sorted_versions
        }

    def _load_rules(self, app_dir: str) -> Dict:
        """
        Load rules from .rules.yaml file, creating a template if absent.

        Args:
            app_dir: Directory containing the rules file.

        Returns:
            Dict of rules or empty dict if invalid/absent.
        """
        rules_path = os.path.join(app_dir, '.rules.yaml')
        if not os.path.exists(rules_path):
            template = {
                'preferred_extensions': ['.tipa', '.ipa', '.deb'],
                'excluded_extensions': ['.zip', '.tar.gz'],
                'exclude_patterns': ['debug', 'beta'],
                'strip_v_prefix': True,
                'replace_chars': {'-': '.', '_': '.'},
                'remove_chars': ['-beta', '-alpha', '-dev']
            }
            try:
                with open(rules_path, 'w') as f:
                    yaml.dump(template, f, default_flow_style=False)
                self.logger.info(f"Created template rules file for {os.path.basename(app_dir)}")
            except (IOError, PermissionError) as e:
                self.logger.error(f"Failed to create rules template for {os.path.basename(app_dir)}: {str(e)}")
            return {}
        
        try:
            with open(rules_path, 'r') as f:
                rules = yaml.safe_load(f) or {}
            return rules if isinstance(rules, dict) else {}
        except (yaml.YAMLError, IOError) as e:
            self.logger.error(f"Failed to load rules for {os.path.basename(app_dir)}: {str(e)}")
            return {}

    def _should_include_asset(self, asset: Dict, rules: Dict) -> bool:
        """Determine if an asset should be included based on rules."""
        name = asset['name'].lower()
        if rules.get('excluded_extensions') and any(name.endswith(ext) for ext in rules['excluded_extensions']):
            return False
        if rules.get('exclude_patterns') and any(pattern.lower() in name for pattern in rules['exclude_patterns']):
            return False
        if rules.get('preferred_extensions'):
            return any(name.endswith(ext) for ext in rules['preferred_extensions'])
        return name.endswith(('.tipa', '.ipa'))

    def _format_version_number(self, version: str, rules: Dict) -> str:
        """Format version string according to rules."""
        if rules.get('strip_v_prefix', False) and version.lower().startswith('v'):
            version = version[1:]
        if rules.get('remove_chars'):
            for char in rules['remove_chars']:
                version = version.replace(char, '')
        if rules.get('replace_chars'):
            for char, replacement in rules['replace_chars'].items():
                version = version.replace(char, replacement)
        return version.strip()

    def _save_config(self, path: str, data: Dict):
        """Save updated configuration to file."""
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4)
        except (IOError, PermissionError) as e:
            self.logger.error(f"Failed to save config {path}: {str(e)}")

    def _valid_repo(self, repo) -> bool:
        """Validate repository information."""
        if not repo:
            self.logger.warning("No repository information provided")
            return False
        repos = repo if isinstance(repo, list) else [repo]
        valid = any(self._valid_gh_url(u) for u in repos)
        if not valid:
            self.logger.warning(f"Invalid GitHub URLs found: {repos}")
        return valid

    def _valid_gh_url(self, url: str) -> bool:
        """Check if a URL is a valid GitHub URL."""
        return url.startswith(("https://github.com/", "http://github.com/"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage app versions")
    parser.add_argument("action", choices=["update", "remove"], help="Action to perform")
    parser.add_argument("--keep", type=int, default=5, help="Number of versions to keep")
    parser.add_argument("--apps", type=str, help="Comma-separated list of app names")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    apps_dir = os.path.join(current_dir, "..", "Apps")
    manager = VersionManager(apps_dir)
    targets = args.apps.split(",") if args.apps else [None]
    for target in targets:
        manager.manage(args.action, target.strip() if target else None, args.keep)