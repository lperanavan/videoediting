import json
import os

class ConfigManager:
    """
    Loads and manages configuration files for the Video Processor App.
    """
    def __init__(self, config_path="config/app_settings.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def get(self, key, default=None):
        return self.config.get(key, default)
        
    def get_config(self):
        """Return the complete configuration dictionary"""
        return self.config