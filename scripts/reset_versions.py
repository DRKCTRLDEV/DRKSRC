import os
import json
import logging

class VersionResetter:
    def __init__(self, apps_dir: str):
        self.apps_dir = apps_dir
        self.logger = self.setup_logger()

    def setup_logger(self):
        logger = logging.getLogger("VersionResetter")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        return logger

    def reset_versions(self):
        for app_name in os.listdir(self.apps_dir):
            app_path = os.path.join(self.apps_dir, app_name)
            app_json_path = os.path.join(app_path, 'app.json')

            if os.path.isdir(app_path) and os.path.isfile(app_json_path):
                self.logger.info(f"Checking {app_name} for valid repository...")
                self.reset_app_versions(app_json_path)

    def reset_app_versions(self, app_json_path: str):
        try:
            with open(app_json_path, 'r') as file:
                app_data = json.load(file)

            repository = app_data.get("repository")
            if not repository:
                self.logger.warning(f"Skipping {app_json_path}: No repository field found")
                return

            if not self.is_valid_repository(repository):
                self.logger.warning(f"Skipping {app_json_path}: Invalid repository '{repository}'")
                return

            app_data['versions'] = []

            with open(app_json_path, 'w') as file:
                json.dump(app_data, file, indent=4)

            self.logger.info(f"Successfully reset versions for {app_json_path}")
        except Exception as e:
            self.logger.error(f"Error resetting versions for {app_json_path}: {str(e)}")

    def is_valid_repository(self, repository: str) -> bool:
        if not repository or not isinstance(repository, str):
            return False
        return repository.startswith("https://github.com/")

if __name__ == "__main__":
    current_directory = os.path.dirname(os.path.abspath(__file__))  
    apps_directory = os.path.join(current_directory, "..", "Apps")

    version_resetter = VersionResetter(apps_directory)
    version_resetter.reset_versions()