import json
import logging
import os
from typing import Optional
from PIL import Image

class AssetManager:
    def __init__(self, apps_root: str):
        self.apps_root = apps_root
        self.logger = self._init_logger()

    def _init_logger(self) -> logging.Logger:
        logger = logging.getLogger("AssetManager")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        return logger

    def manage_icons(self, target: Optional[str] = None):
        """Manage icons and screenshots for all apps or a specific target app."""
        for app in os.listdir(self.apps_root):
            path = os.path.join(self.apps_root, app)
            config_path = os.path.join(path, 'app.json')

            if not self._valid_app_path(path, config_path, target):
                continue

            self._update_icon(app, config_path)
            self._update_screenshots(app, config_path)

    def _valid_app_path(self, path: str, config: str, target: Optional[str]) -> bool:
        """Check if the path is valid and matches the target if specified."""
        return os.path.isdir(path) and os.path.isfile(config) and (not target or os.path.basename(path) == target)

    def _update_icon(self, app_name: str, config_path: str):
        """Update the icon URL in the app's config."""
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            self.logger.error(f"Error reading config for {app_name}: {str(e)}")
            return

        icon_url = self._convert_and_get_icon_url(app_name, os.path.dirname(config_path))
        if icon_url:
            data['icon'] = icon_url
            self._save_config(config_path, data)
            self.logger.info(f"Updated icon for {app_name}: {icon_url}")
        else:
            self.logger.info(f"No icon found for {app_name}")

    def _update_screenshots(self, app_name: str, config_path: str):
        """Update the screenshots list in the app's config."""
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            self.logger.error(f"Error reading config for {app_name}: {str(e)}")
            return

        screenshot_urls = self._convert_and_get_screenshot_urls(app_name, os.path.dirname(config_path))
        if screenshot_urls:
            data['screenshots'] = screenshot_urls
            self._save_config(config_path, data)
            self.logger.info(f"Updated screenshots for {app_name}: {len(screenshot_urls)} found")
        else:
            self.logger.info(f"No screenshots found for {app_name}")

    def _convert_and_get_icon_url(self, app_name: str, app_dir: str) -> str:
        """Convert icon to PNG 128x128 and return URL, skipping if already correct."""
        preferred_icon_path = os.path.join(app_dir, 'icon.png')

        # Check if icon.png exists
        if os.path.isfile(preferred_icon_path):
            try:
                with Image.open(preferred_icon_path) as img:
                    if img.size == (128, 128):
                        # Already 128x128, no need to process
                        return f"https://raw.githubusercontent.com/DRKCTRLDEV/DRKSRC/main/Apps/{app_name}/icon.png"
                    else:
                        # Resize to 128x128
                        img_resized = img.resize((128, 128), Image.Resampling.LANCZOS)
                        # Convert to RGB to match original behavior (optional: keep transparency if desired)
                        if img_resized.mode in ('RGBA', 'LA') or (img_resized.mode == 'P' and 'transparency' in img_resized.info):
                            img_resized = img_resized.convert('RGB')
                        img_resized.save(preferred_icon_path, 'PNG')
                        return f"https://raw.githubusercontent.com/DRKCTRLDEV/DRKSRC/main/Apps/{app_name}/icon.png"
            except Exception as e:
                self.logger.error(f"Failed to process existing icon.png for {app_name}: {str(e)}")
                # Proceed to look for other icons

        # Look for other icon files
        other_extensions = ['.jpg', '.jpeg', '.webp']
        for ext in other_extensions:
            icon_path = os.path.join(app_dir, f'icon{ext}')
            if os.path.isfile(icon_path):
                try:
                    with Image.open(icon_path) as img:
                        # Convert to RGB to match original behavior
                        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                            img = img.convert('RGB')
                        # Resize to 128x128
                        img_resized = img.resize((128, 128), Image.Resampling.LANCZOS)
                        # Save as PNG for lossless quality
                        img_resized.save(preferred_icon_path, 'PNG')
                        # Remove original
                        os.remove(icon_path)
                        return f"https://raw.githubusercontent.com/DRKCTRLDEV/DRKSRC/main/Apps/{app_name}/icon.png"
                except Exception as e:
                    self.logger.error(f"Failed to convert icon{ext} for {app_name}: {str(e)}")
                    continue

        return ""

    def _convert_and_get_screenshot_urls(self, app_name: str, app_dir: str) -> list:
        """Convert screenshots to PNG with progressive naming, max 4, and return list of URLs."""
        screenshots_dir = os.path.join(app_dir, 'screenshots')
        if not os.path.isdir(screenshots_dir):
            return []

        supported_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        screenshot_files = []
        
        # Collect all valid screenshot files
        for filename in os.listdir(screenshots_dir):
            if any(filename.lower().endswith(ext) for ext in supported_extensions):
                screenshot_files.append(filename)
        
        if not screenshot_files:
            return []
            
        # Limit to 4 screenshots
        screenshot_files = sorted(screenshot_files)[:4]
        new_screenshot_urls = []
        
        # Convert and rename each screenshot
        for i, filename in enumerate(screenshot_files, 1):
            input_path = os.path.join(screenshots_dir, filename)
            new_filename = f"IMG_{i}.png"
            output_path = os.path.join(screenshots_dir, new_filename)
            
            try:
                # Open and convert the image
                with Image.open(input_path) as img:
                    # Convert to RGB to match original behavior (optional: keep transparency if desired)
                    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                        img = img.convert('RGB')
                    # Save as PNG for lossless quality, keeping original dimensions
                    img.save(output_path, 'PNG')
                
                # Add URL to list
                base_url = f"https://raw.githubusercontent.com/DRKCTRLDEV/DRKSRC/main/Apps/{app_name}/screenshots"
                new_screenshot_urls.append(f"{base_url}/{new_filename}")
                
                # Remove original if different from new file
                if input_path != output_path and os.path.exists(input_path):
                    os.remove(input_path)
                    
            except Exception as e:
                self.logger.error(f"Failed to convert screenshot {filename} for {app_name}: {str(e)}")
                continue

        return new_screenshot_urls

    def _save_config(self, path: str, data: dict):
        """Save the updated config data."""
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4)
        except (IOError, PermissionError) as e:
            self.logger.error(f"Failed to save config {path}: {str(e)}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage app assets")
    parser.add_argument("--apps", type=str, help="Comma-separated list of app names")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    apps_dir = os.path.join(current_dir, "..", "Apps")
    manager = AssetManager(apps_dir)
    targets = args.apps.split(",") if args.apps else [None]
    for target in targets:
        manager.manage_icons(target.strip() if target else None)