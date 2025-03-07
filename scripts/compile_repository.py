import sys
import os
import json
import logging
import requests
import yaml
import argparse
from typing import Dict, Optional, List, Set
from requests.exceptions import RequestException
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

class VersionManager:
    def __init__(self, apps_root: str, keep_versions: int = 10, max_workers: int = 4):
        if not isinstance(keep_versions, int) or keep_versions < 1:
            raise ValueError("keep_versions must be a positive integer")
        self.apps_root = apps_root
        self.keep_versions = keep_versions
        self.max_workers = max_workers
        self.logger = self._init_logger()
        self.token = os.environ.get("GITHUB_TOKEN")
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'token {self.token}'})

    def _init_logger(self) -> logging.Logger:
        logger = logging.getLogger("VersionManager")
        logger.setLevel(logging.INFO)
        if not logger.handlers:  # Avoid duplicate handlers
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
        return logger

    def manage(self, action: str, targets: Optional[List[str]] = None, keep: Optional[int] = None):
        self.keep_versions = max(1, keep or self.keep_versions)
        targets = set(targets or []) or {None}
        apps = [d for d in os.listdir(self.apps_root) if os.path.isdir(os.path.join(self.apps_root, d))]
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._process_app, app, action)
                for app in apps
                if not targets or app in targets
            ]
            for future in futures:
                future.result()  # Raise any exceptions

    def _process_app(self, app: str, action: str):
        path = os.path.join(self.apps_root, app)
        config_path = os.path.join(path, 'app.json')
        if not os.path.isfile(config_path):
            return

        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            self.logger.error(f"Failed to load config for {app}: {str(e)}")
            return

        if not self._valid_repo(data.get('gitURLs')):
            return

        if action == 'update':
            result = self._fetch_new_versions(data, path)
            if result['success']:
                data['versions'] = result['versions']
                self._save_config(config_path, data)
                self.logger.info(f"Updated {app}: {result['message']}")
            else:
                self.logger.error(f"Failed to update {app}: {result['message']}")
        elif action == 'remove':
            data['versions'] = []
            self._save_config(config_path, data)
            self.logger.info(f"Removed versions for {app}")

    @lru_cache(maxsize=128)
    def _load_rules(self, app_dir: str) -> Dict:
        rules_path = os.path.join(app_dir, '.rules.yaml')
        if not os.path.exists(rules_path):
            template = {
                'preferred_extensions': ['.tipa', '.ipa'],
                'excluded_extensions': ['.zip', '.tar.gz', '.deb'],
                'exclude_patterns': ['debug', 'beta'],
                'strip_v_prefix': True,
                'replace_chars': {'-': '.', '_': '.'},
                'remove_chars': ['-beta', '-alpha', '-dev']
            }
            try:
                with open(rules_path, 'w') as f:
                    yaml.dump(template, f, default_flow_style=False)
                self.logger.info(f"Created rules template for {os.path.basename(app_dir)}")
            except (IOError, PermissionError) as e:
                self.logger.error(f"Failed to create rules for {os.path.basename(app_dir)}: {str(e)}")
            return {}
        try:
            with open(rules_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError):
            return {}

    def _fetch_new_versions(self, data: Dict, app_dir: str) -> Dict:
        if not self.token:
            return {'success': False, 'message': 'Missing GitHub token', 'versions': []}

        repos = data.get('gitURLs', [])
        repos = [repos] if isinstance(repos, str) else repos
        existing: Set[str] = {v['url'] for v in data.get('versions', [])}
        versions: Dict[str, Dict] = {}
        rules = self._load_rules(app_dir)

        for repo in repos:
            if not self._valid_gh_url(repo):
                continue
            owner, repo_name = repo.rstrip('/').split('/')[-2:]
            url = f'https://api.github.com/repos/{owner}/{repo_name}/releases'
            
            try:
                releases = self._fetch_all_pages(url)
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
            except RequestException as e:
                return {'success': False, 'message': f"API error: {str(e)}", 'versions': []}

        sorted_versions = sorted(versions.values(), key=lambda x: x['date'], reverse=True)[:self.keep_versions]
        new_count = len(versions) - (len(data.get('versions', [])) - len(existing & set(versions.keys())))
        return {
            'success': True,
            'message': f"Added {new_count} versions" if new_count > 0 else "No new versions",
            'versions': sorted_versions
        }

    def _fetch_all_pages(self, url: str) -> List[Dict]:
        results = []
        while url:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            results.extend(response.json())
            url = response.links.get('next', {}).get('url')
        return results

    def _should_include_asset(self, asset: Dict, rules: Dict) -> bool:
        name = asset['name'].lower()
        return (
            not any(name.endswith(ext) for ext in rules.get('excluded_extensions', [])) and
            not any(pat.lower() in name for pat in rules.get('exclude_patterns', [])) and
            (not rules.get('preferred_extensions') or 
             any(name.endswith(ext) for ext in rules['preferred_extensions']))
        )

    def _format_version_number(self, version: str, rules: Dict) -> str:
        if rules.get('strip_v_prefix', False) and version.lower().startswith('v'):
            version = version[1:]
        for char in rules.get('remove_chars', []):
            version = version.replace(char, '')
        for char, repl in rules.get('replace_chars', {}).items():
            version = version.replace(char, repl)
        return version.strip()

    def _save_config(self, path: str, data: Dict):
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4)
        except (IOError, PermissionError) as e:
            self.logger.error(f"Failed to save config {path}: {str(e)}")

    def _valid_repo(self, repo) -> bool:
        repos = [repo] if isinstance(repo, str) else repo or []
        return any(self._valid_gh_url(u) for u in repos)

    @staticmethod
    def _valid_gh_url(url: str) -> bool:
        return url.startswith(("https://github.com/", "http://github.com/"))

def int_or_float_to_int(value: str) -> int:
    try:
        num = float(value)
        if not num.is_integer():
            raise ValueError
        return int(num)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid keep value: {value}. Must be a positive integer.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage app versions")
    parser.add_argument("action", choices=["update", "remove"], help="Action to perform")
    parser.add_argument("--keep", type=int_or_float_to_int, default=5, help="Number of versions to keep")
    parser.add_argument("--apps", type=str, help="Comma-separated list of app names")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    manager = VersionManager(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Apps"))
    targets = [t.strip() for t in args.apps.split(",")] if args.apps else None
    manager.manage(args.action, targets, args.keep)