#!/usr/bin/env python3
import sys
import json
import os
import logging
import plistlib
import subprocess
import requests
import tempfile
from pathlib import Path
from typing import Dict, Tuple, Optional, List

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

class PermissionManager:
    def __init__(self, apps_root: str = '.'):
        self.apps_root = Path(apps_root).resolve()
        self.logger = logging.getLogger(self.__class__.__name__)

    def manage(self, action: str, app_name: Optional[str] = None) -> bool:
        targets = [app_name] if app_name else self._get_all_apps()
        processed = []
        failed = []
        
        self.logger.info(f"Starting permission {action} for {len(targets)} apps")

        for target in targets:
            try:
                app_path = self.apps_root / target
                if not self._valid_app_dir(app_path):
                    self.logger.warning(f"Skipping invalid app: {target}")
                    continue

                result = self._process_app(action, app_path)
                
                if result['success']:
                    processed.append(target)
                    self.logger.info(f"{target}: {result['message']}")
                else:
                    failed.append((target, result['message']))
                    
            except Exception as e:
                failed.append((target, str(e)))
                self.logger.error(f"{target}: Error - {str(e)}")

        self._log_summary(processed, failed)
        return len(failed) == 0

    def _process_app(self, action: str, app_path: Path) -> Dict:
        config_file = app_path / 'app.json'
        if not config_file.exists():
            return {"success": False, "message": "app.json not found"}

        with open(config_file, 'r') as f:
            app_data = json.load(f)

        if action == 'update':
            return self._update_app_permissions(app_data, config_file)
        elif action == 'remove':
            return self._remove_app_permissions(app_data, config_file)
        else:
            raise ValueError(f"Invalid action: {action}")

    def _update_app_permissions(self, app_data: Dict, config_file: Path) -> Dict:
        ipa_url = self._get_latest_ipa_url(app_data)
        if not ipa_url:
            return {"success": False, "message": "No valid IPA URL"}

        entitlements, privacy = self._extract_from_ipa(ipa_url)
        
        app_data['permissions'] = {
            'entitlements': entitlements,
            'privacy': privacy
        }

        with open(config_file, 'w') as f:
            json.dump(app_data, f, indent=2)

        return {"success": True, "message": "Updated permissions"}

    def _remove_app_permissions(self, app_data: Dict, config_file: Path) -> Dict:
        if 'permissions' not in app_data:
            return {"success": True, "message": "No permissions to remove"}
        
        removed_count = len(app_data['permissions'].get('entitlements', {})) + \
                        len(app_data['permissions'].get('privacy', {}))
        
        del app_data['permissions']
        with open(config_file, 'w') as f:
            json.dump(app_data, f, indent=2)
        
        msg = f"Removed {removed_count} permissions"
        return {"success": True, "message": msg}

    def _get_all_apps(self) -> List[str]:
        return [d.name for d in self.apps_root.iterdir() if d.is_dir()]

    def _valid_app_dir(self, app_path: Path) -> bool:
        return app_path.is_dir() and (app_path / 'app.json').exists()

    def _get_latest_ipa_url(self, app_data: Dict) -> Optional[str]:
        versions = app_data.get('versions', [])
        return versions[0].get('url') if versions else None

    def _extract_from_ipa(self, ipa_url: str) -> Tuple[Dict, Dict]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            ipa_file = tmp_path / 'app.ipa'

            self._download_ipa(ipa_url, ipa_file)
            self._extract_ipa(ipa_file, tmp_path)
            
            app_bundle = self._find_app_bundle(tmp_path)
            return (
                self._extract_entitlements(app_bundle),
                self._extract_privacy(app_bundle)
            )

    def _download_ipa(self, url: str, dest: Path):
        self.logger.debug(f"Downloading IPA from {url}")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def _extract_ipa(self, ipa_file: Path, dest_dir: Path):
        self.logger.debug("Extracting IPA")
        result = subprocess.run(
            ['unzip', '-q', str(ipa_file), '-d', str(dest_dir)],
            capture_output=True
        )
        if result.returncode != 0:
            raise Exception(f"IPA extraction failed: {result.stderr.decode()}")

    def _find_app_bundle(self, tmp_path: Path) -> Path:
        payload = tmp_path / 'Payload'
        app_bundles = list(payload.glob('*.app'))
        
        if not app_bundles:
            raise Exception("No .app bundle found")
        if len(app_bundles) > 1:
            raise Exception("Multiple .app bundles found")
            
        return app_bundles[0]

    def _extract_entitlements(self, app_bundle: Path) -> Dict:
        prov_file = app_bundle / 'embedded.mobileprovision'
        if not prov_file.exists():
            return {}

        try:
            result = subprocess.run(
                ['security', 'cms', '-D', '-i', str(prov_file)],
                capture_output=True, check=True
            )
            return plistlib.loads(result.stdout).get('Entitlements', {})
        except Exception as e:
            self.logger.warning(f"Entitlement extraction failed: {str(e)}")
            return {}

    def _extract_privacy(self, app_bundle: Path) -> Dict:
        plist_file = app_bundle / 'Info.plist'
        if not plist_file.exists():
            return {}

        with open(plist_file, 'rb') as f:
            plist = plistlib.load(f)

        privacy_keys = [
            'NSContactsUsageDescription',
            'NSLocationUsageDescription',
            'NSMicrophoneUsageDescription',
            'NSCameraUsageDescription',
            'NSPhotoLibraryUsageDescription',
            'NSBluetoothAlwaysUsageDescription',
            'NSBluetoothPeripheralUsageDescription',
            'NSFaceIDUsageDescription',
            'NSMotionUsageDescription',
            'NSSpeechRecognitionUsageDescription',
            'NSHealthShareUsageDescription',
            'NSHealthUpdateUsageDescription',
            'NSAppleMusicUsageDescription',
            'NSRemindersUsageDescription',
            'NSCalendarsUsageDescription',
            'NSHomeKitUsageDescription',
            'NSLocalNetworkUsageDescription',
            'NSUserTrackingUsageDescription'
        ]
        return {k: plist.get(k) for k in privacy_keys if k in plist}

    def _log_summary(self, processed: List[str], failed: List[tuple]):
        self.logger.info("\n=== Operation Summary ===")
        self.logger.info(f"Successfully processed: {len(processed)}")
        self.logger.info(f"Failed: {len(failed)}")
        
        if failed:
            self.logger.info("\nFailed apps:")
            for app, reason in failed:
                self.logger.info(f" - {app}: {reason}")

def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    if len(sys.argv) < 2 or sys.argv[1] not in ('update', 'remove'):
        logger.error("Usage: manage_permissions.py <action> [app_name]")
        logger.error("Actions: update, remove")
        sys.exit(1)

    action = sys.argv[1].lower()
    app_name = sys.argv[2] if len(sys.argv) > 2 else None

    manager = PermissionManager('Apps')
    success = manager.manage(action, app_name)

    if success:
        logger.info("\nOperation completed successfully")
    else:
        logger.info("\nOperation completed with errors")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    sys.exit(main())