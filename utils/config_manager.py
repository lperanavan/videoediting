import json
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

class ConfigManager:
    """
    Enhanced configuration manager with validation and Windows-specific optimizations
    """
    def __init__(self, config_path="config/app_settings.json"):
        self.config_path = config_path
        self.config = {}
        self.logger = logging.getLogger(__name__)
        self.validation_errors = []
        self.windows_optimizations = sys.platform == "win32"
        
        self.load_config()
        self.validate_config()
        if self.windows_optimizations:
            self.apply_windows_optimizations()

    def load_config(self):
        """Load configuration with error handling"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding='utf-8') as f:
                    self.config = json.load(f)
                self.logger.info(f"Configuration loaded from {self.config_path}")
            else:
                self.config = self._get_default_config()
                self.logger.warning(f"Configuration file not found at {self.config_path}, using defaults")
                self._save_default_config()
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file: {e}")
            self.config = self._get_default_config()
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            self.config = self._get_default_config()

    def validate_config(self) -> bool:
        """Validate configuration and check dependencies"""
        self.validation_errors = []
        
        # Validate required sections
        required_sections = ['directories', 'processing', 'queue', 'logging']
        for section in required_sections:
            if section not in self.config:
                self.validation_errors.append(f"Missing required section: {section}")
        
        # Validate directories
        self._validate_directories()
        
        # Validate dependencies
        self._validate_dependencies()
        
        # Validate processing settings
        self._validate_processing_settings()
        
        # Log validation results
        if self.validation_errors:
            for error in self.validation_errors:
                self.logger.warning(f"Config validation: {error}")
            return False
        else:
            self.logger.info("Configuration validation passed")
            return True

    def _validate_directories(self):
        """Validate directory settings"""
        directories = self.config.get('directories', {})
        
        for dir_name, dir_path in directories.items():
            if not dir_path:
                self.validation_errors.append(f"Empty directory path for {dir_name}")
                continue
            
            try:
                # Create directory if it doesn't exist
                Path(dir_path).mkdir(parents=True, exist_ok=True)
                
                # Check if directory is writable
                if not os.access(dir_path, os.W_OK):
                    self.validation_errors.append(f"Directory {dir_name} is not writable: {dir_path}")
                    
            except Exception as e:
                self.validation_errors.append(f"Cannot create/access directory {dir_name}: {e}")

    def _validate_dependencies(self):
        """Validate external dependencies"""
        # Check FFmpeg
        import shutil
        if not shutil.which('ffmpeg'):
            self.validation_errors.append("FFmpeg not found in PATH")
        
        # Check Windows-specific dependencies
        if self.windows_optimizations:
            self._validate_windows_dependencies()

    def _validate_windows_dependencies(self):
        """Validate Windows-specific dependencies"""
        # Check COM availability
        try:
            import win32com.client
            import pythoncom
        except ImportError:
            self.validation_errors.append("pywin32 not installed - required for Windows COM automation")
        
        # Check Premiere Pro if enabled
        if self.config.get('premiere', {}).get('enabled', False):
            premiere_paths = [
                r"C:\Program Files\Adobe\Adobe Premiere Pro 2023",
                r"C:\Program Files\Adobe\Adobe Premiere Pro 2024",
                r"C:\Program Files\Adobe\Adobe Premiere Pro 2025"
            ]
            
            premiere_found = any(os.path.exists(path) for path in premiere_paths)
            if not premiere_found:
                self.validation_errors.append("Adobe Premiere Pro not found in standard installation paths")
        
        # Check Topaz Video AI if enabled
        if self.config.get('topaz', {}).get('enabled', False):
            topaz_path = self.config.get('topaz', {}).get('application_path', '')
            if not os.path.exists(topaz_path):
                self.validation_errors.append(f"Topaz Video AI not found at: {topaz_path}")

    def _validate_processing_settings(self):
        """Validate processing settings"""
        processing = self.config.get('processing', {})
        
        max_concurrent = processing.get('max_concurrent_jobs', 1)
        if not isinstance(max_concurrent, int) or max_concurrent < 1:
            self.validation_errors.append("max_concurrent_jobs must be a positive integer")
        
        polling_interval = processing.get('polling_interval', 30)
        if not isinstance(polling_interval, (int, float)) or polling_interval < 1:
            self.validation_errors.append("polling_interval must be a positive number")

    def apply_windows_optimizations(self):
        """Apply Windows-specific optimizations"""
        if not self.windows_optimizations:
            return
        
        self.logger.info("Applying Windows-specific optimizations")
        
        # Optimize for Shadow PC if detected
        if self._is_shadow_pc():
            self.logger.info("Shadow PC environment detected - applying optimizations")
            self._apply_shadow_pc_optimizations()
        
        # Set Windows-specific paths
        self._set_windows_paths()
        
        # Configure for Windows performance
        self._configure_windows_performance()

    def _is_shadow_pc(self) -> bool:
        """Detect if running on Shadow PC"""
        try:
            # Check for Shadow PC indicators
            import subprocess
            
            # Check system info for Shadow indicators
            result = subprocess.run(['systeminfo'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                system_info = result.stdout.lower()
                shadow_indicators = ['shadow', 'parsec', 'gpu pass-through', 'virtualization']
                
                for indicator in shadow_indicators:
                    if indicator in system_info:
                        return True
            
            # Check GPU info for indicators
            try:
                import psutil
                # This is a simplified check - in reality you'd want more sophisticated detection
                return False  # Default to False for now
            except ImportError:
                pass
                
        except Exception as e:
            self.logger.debug(f"Could not detect Shadow PC environment: {e}")
        
        return False

    def _apply_shadow_pc_optimizations(self):
        """Apply Shadow PC specific optimizations"""
        # Reduce concurrent jobs for network stability
        processing = self.config.setdefault('processing', {})
        processing['max_concurrent_jobs'] = min(processing.get('max_concurrent_jobs', 1), 1)
        
        # Increase timeouts for network operations
        self.config.setdefault('gdrive', {})['download_timeout'] = 7200  # 2 hours
        self.config.setdefault('gdrive', {})['upload_timeout'] = 7200    # 2 hours
        
        # Enable network-aware file handling
        processing['network_aware_mode'] = True
        processing['chunk_processing'] = True
        
        self.logger.info("Applied Shadow PC optimizations")

    def _set_windows_paths(self):
        """Set Windows-specific default paths"""
        # Update Adobe Premiere Pro path
        premiere_config = self.config.setdefault('premiere', {})
        if not premiere_config.get('application_path'):
            premiere_paths = [
                r"C:\Program Files\Adobe\Adobe Premiere Pro 2025\Adobe Premiere Pro.exe",
                r"C:\Program Files\Adobe\Adobe Premiere Pro 2024\Adobe Premiere Pro.exe",
                r"C:\Program Files\Adobe\Adobe Premiere Pro 2023\Adobe Premiere Pro.exe"
            ]
            
            for path in premiere_paths:
                if os.path.exists(path):
                    premiere_config['application_path'] = path
                    break

    def _configure_windows_performance(self):
        """Configure Windows-specific performance settings"""
        processing = self.config.setdefault('processing', {})
        
        # Set Windows-optimized processing options
        processing.setdefault('use_hardware_acceleration', True)
        processing.setdefault('memory_optimization', True)
        processing.setdefault('io_optimization', True)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "version": "1.0.0",
            "directories": {
                "input": "input_videos",
                "output": "output_videos",
                "temp": "temp",
                "presets": "presets",
                "logs": "logs"
            },
            "processing": {
                "max_concurrent_jobs": 1,
                "polling_interval": 30,
                "cleanup_temp_files": True,
                "auto_detect_tape_type": True,
                "fallback_to_ffmpeg": True,
                "use_hardware_acceleration": sys.platform == "win32",
                "network_aware_mode": False
            },
            "queue": {
                "queue_file": "queue.json",
                "backup_file": "queue_backup.json",
                "max_failed_retries": 3,
                "cleanup_completed_days": 30
            },
            "gdrive": {
                "enabled": False,
                "credentials_file": "config/gdrive_credentials.json",
                "upload_timeout": 3600,
                "download_timeout": 3600,
                "chunk_size": 1048576
            },
            "premiere": {
                "enabled": False,
                "presets_directory": "presets",
                "temp_project_directory": "temp/premiere_projects",
                "export_format": "H.264",
                "export_quality": "High",
                "connection_timeout": 30,
                "export_timeout": 3600
            },
            "topaz": {
                "enabled": False,
                "application_path": r"C:\Program Files\Topaz Labs LLC\Topaz Video AI\Topaz Video AI.exe",
                "temp_directory": "temp/topaz",
                "timeout": 7200
            },
            "detection": {
                "ffmpeg_path": "ffmpeg",
                "analysis_timeout": 120,
                "confidence_threshold": 0.6,
                "use_filename_hints": True
            },
            "web_ui": {
                "host": "0.0.0.0",
                "port": 5000,
                "debug": False,
                "secret_key": "change_this_secret_key"
            },
            "logging": {
                "level": "INFO",
                "file": "logs/video_processor.log",
                "max_size_mb": 10,
                "backup_count": 5
            }
        }

    def _save_default_config(self):
        """Save default configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
            self.logger.info(f"Default configuration saved to {self.config_path}")
        except Exception as e:
            self.logger.error(f"Failed to save default configuration: {e}")

    def get(self, key, default=None):
        """Get configuration value with dot notation support"""
        if '.' in key:
            keys = key.split('.')
            value = self.config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        return self.config.get(key, default)
        
    def get_config(self):
        """Return the complete configuration dictionary"""
        return self.config

    def update_config(self, updates: Dict[str, Any]):
        """Update configuration with new values"""
        def deep_update(base_dict, update_dict):
            for key, value in update_dict.items():
                if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                    deep_update(base_dict[key], value)
                else:
                    base_dict[key] = value
        
        deep_update(self.config, updates)
        self.save_config()

    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
            self.logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")

    def get_validation_errors(self) -> List[str]:
        """Get list of validation errors"""
        return self.validation_errors.copy()

    def is_valid(self) -> bool:
        """Check if configuration is valid"""
        return len(self.validation_errors) == 0