#!/usr/bin/env python3
import sys
import json
import logging
import requests
import plistlib
import zipfile
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

class AppInfoExtractor:
    CATEGORY_MAP = {
        "public.app-category.utilities": "Utilities",
        "public.app-category.games": "Games",
        # ... rest of category mappings ...
    }

    def __init__(self, base_dir: Path = Path.cwd()):
        self.base_dir = base_dir.resolve()
        self.apps_dir = self.base_dir / 'Apps'
        self.logger = logging.getLogger(self.__class__.__name__)
        self.session = self._create_http_session()

    def _create_http_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=['GET']
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _load_json(self, file_path: Path) -> Optional[Dict[str, Any]]:
        try:
            if not file_path.exists():
                return None
            return json.loads(file_path.read_text(encoding='utf-8'))
        except Exception as e:
            self.logger.error(f"Error reading {file_path}: {e}")
            return None

    def _save_json(self, file_path: Path, data: Dict[str, Any]) -> bool:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
            return True
        except Exception as e:
            self.logger.error(f"Error writing {file_path}: {e}")
            return False

    def process_app(self, app_name: str) -> Dict[str, Any]:
        app_path = self.apps_dir / app_name
        app_data = self._load_json(app_path / 'app.json')
        
        if not app_data:
            return {"success": False, "message": "Failed to load app data"}
        
        if not (url := self._get_latest_version_url(app_data)):
            return {"success": False, "message": "No valid download URL found"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ipa_path = temp_path / f"{app_name}.ipa"
            
            if not self._download_ipa(url, ipa_path):
                return {"success": False, "message": "IPA download failed"}
            
            if not self._extract_ipa(ipa_path, temp_path):
                return {"success": False, "message": "IPA extraction failed"}
            
            if not (app_bundle := self._find_app_bundle(temp_path)):
                return {"success": False, "message": "No .app bundle found"}
            
            info_plist_path = app_bundle / "Info.plist"
            if not info_plist_path.exists():
                return {"success": False, "message": "Info.plist not found"}

            with info_plist_path.open('rb') as f:
                info_plist = plistlib.load(f)

            icon_path = self._extract_app_icon(app_bundle, app_name)
            if icon_path:
                app_data["icon"] = f"Apps/{app_name}/icon.png"

            self._update_app_metadata(app_data, info_plist)

            if self._save_json(app_path / 'app.json', app_data):
                return {
                    "success": True,
                    "message": "App info updated successfully",
                    "data": {
                        "bundleIdentifier": app_data["bundleIdentifier"],
                        "name": app_data["name"],
                        "icon": app_data.get("icon", "")
                    }
                }

        return {"success": False, "message": "Failed to update app info"}

    def _get_latest_version_url(self, app_data: Dict[str, Any]) -> Optional[str]:
        versions = app_data.get("versions", [])
        return versions[0].get("url") if versions else None

    def _download_ipa(self, url: str, ipa_path: Path) -> bool:
        self.logger.info(f"Downloading {url}")
        try:
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            with ipa_path.open('wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            self.logger.error(f"Failed to download IPA: {e}")
            return False

    def _extract_ipa(self, ipa_path: Path, temp_path: Path) -> bool:
        self.logger.info(f"Extracting {ipa_path.name}")
        try:
            with zipfile.ZipFile(ipa_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)
            return True
        except Exception as e:
            self.logger.error(f"Failed to extract IPA: {e}")
            return False

    def _find_app_bundle(self, temp_path: Path) -> Optional[Path]:
        payload_dir = temp_path / "Payload"
        return next(payload_dir.glob("*.app"), None)

    def _update_app_metadata(self, app_data: Dict[str, Any], info_plist: Dict) -> None:
        app_data["bundleIdentifier"] = info_plist.get("CFBundleIdentifier")
        app_data["name"] = info_plist.get("CFBundleDisplayName") or info_plist.get("CFBundleName")
        if category := info_plist.get("LSApplicationCategoryType"):
            app_data["category"] = self.CATEGORY_MAP.get(category, "Unknown")

    def _extract_app_icon(self, app_bundle: Path, app_name: str) -> Optional[str]:
        try:
            icon_files = list(app_bundle.glob("AppIcon*.png"))
            if not icon_files:
                self.logger.warning("No AppIcon*.png files found")
                return None

            icon_file = max(icon_files, key=lambda f: f.stat().st_size)
            self.logger.info(f"Processing icon: {icon_file.name}")

            output_path = self.apps_dir / app_name / "icon.png"
            with Image.open(icon_file) as img:
                img.convert("RGBA").save(output_path, "PNG")

            return str(output_path)
        except Exception as e:
            self.logger.error(f"Failed to process icon: {e}")
            return None

def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        extractor = AppInfoExtractor()
        logger.info("Starting app info extraction")

        updated: List[str] = []
        failed: List[Tuple[str, str]] = []

        target_app = sys.argv[1] if len(sys.argv) > 1 else None

        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(extractor.process_app, app_dir): app_dir
                for app_dir in extractor.apps_dir.iterdir()
                if app_dir.is_dir() and (not target_app or app_dir.name == target_app)
            }
            for future in futures:
                app_dir = futures[future]
                try:
                    result = future.result()
                    if result["success"]:
                        updated.append(app_dir.name)
                    else:
                        failed.append((app_dir.name, result["message"]))
                except Exception as e:
                    failed.append((app_dir.name, str(e)))

        logger.info(f"Successfully processed {len(updated)} apps")
        if failed:
            logger.error(f"Failed to process {len(failed)} apps:")
            for app, reason in failed:
                logger.error(f" - {app}: {reason}")

        return 0 if not failed else 1

    except Exception as e:
        logger.error(f"Fatal error during extraction: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())