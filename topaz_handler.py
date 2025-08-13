"""
Topaz Video AI Handler for Enhanced Video Processing
Integrates with Topaz Video AI for advanced video enhancement
"""

import os
import sys
import time
import logging
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import shutil

class TopazHandler:
    """Handles Topaz Video AI processing for video enhancement"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Topaz configuration
        self.enabled = self.config.get("enabled", False)
        self.topaz_path = self.config.get("application_path", 
                                        r"C:\Program Files\Topaz Labs LLC\Topaz Video AI\Topaz Video AI.exe")
        self.temp_dir = self.config.get("temp_directory", "temp/topaz")
        self.models_dir = self.config.get("models_directory", "")
        
        # Processing models for different tape types
        self.enhancement_models = {
            "VHS": {
                "model": "Artemis",
                "settings": {
                    "noise_reduction": 0.8,
                    "sharpening": 0.6,
                    "deblur": 0.4,
                    "grain_reduction": 0.7
                }
            },
            "MiniDV": {
                "model": "Iris",
                "settings": {
                    "noise_reduction": 0.3,
                    "sharpening": 0.4,
                    "deblur": 0.2,
                    "grain_reduction": 0.2
                }
            },
            "Hi8": {
                "model": "Artemis",
                "settings": {
                    "noise_reduction": 0.6,
                    "sharpening": 0.5,
                    "deblur": 0.5,
                    "grain_reduction": 0.6
                }
            },
            "Betamax": {
                "model": "Artemis",
                "settings": {
                    "noise_reduction": 0.7,
                    "sharpening": 0.5,
                    "deblur": 0.4,
                    "grain_reduction": 0.6
                }
            },
            "Digital8": {
                "model": "Iris",
                "settings": {
                    "noise_reduction": 0.3,
                    "sharpening": 0.3,
                    "deblur": 0.2,
                    "grain_reduction": 0.2
                }
            },
            "Super8": {
                "model": "Gaia",
                "settings": {
                    "noise_reduction": 0.5,
                    "sharpening": 0.6,
                    "deblur": 0.3,
                    "grain_preservation": True,
                    "film_grain": 0.3
                }
            }
        }
        
        # Create temp directory
        os.makedirs(self.temp_dir, exist_ok=True)
        
        if self.enabled:
            self._verify_installation()
        else:
            self.logger.warning("Topaz Video AI enhancement disabled")
    
    def _verify_installation(self):
        """Verify Topaz Video AI installation"""
        if not os.path.exists(self.topaz_path):
            self.logger.error(f"Topaz Video AI not found at: {self.topaz_path}")
            self.enabled = False
            return
        
        try:
            # Try to get version info
            cmd = [self.topaz_path, '--version']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger.info(f"Topaz Video AI detected: {result.stdout.strip()}")
            else:
                self.logger.warning("Could not verify Topaz Video AI version")
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self.logger.warning(f"Topaz Video AI verification failed: {e}")
            # Don't disable - it might still work
    
    def enhance_videos(self, input_files: List[str], output_dir: str, 
                      job_id: str = None, tape_type: str = "VHS") -> List[str]:
        """Enhance videos using Topaz Video AI"""
        if not self.enabled:
            return self._mock_enhance_videos(input_files, output_dir, job_id, tape_type)
        
        enhanced_files = []
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            for i, input_file in enumerate(input_files):
                if not os.path.exists(input_file):
                    self.logger.error(f"Input file not found: {input_file}")
                    continue
                
                self.logger.info(f"Enhancing {input_file} with Topaz Video AI ({tape_type})")
                
                enhanced_file = self._enhance_single_video(
                    input_file, tape_type, output_dir, job_id, i
                )
                
                if enhanced_file:
                    enhanced_files.append(enhanced_file)
                else:
                    # If enhancement fails, use original file
                    enhanced_files.append(input_file)
                
        except Exception as e:
            self.logger.error(f"Error in Topaz enhancement: {e}")
            # Return original files if enhancement fails
            return input_files
        
        self.logger.info(f"Enhanced {len(enhanced_files)} videos with Topaz Video AI")
        return enhanced_files
    
    def _enhance_single_video(self, input_file: str, tape_type: str, 
                             output_dir: str, job_id: str = None, 
                             file_index: int = 0) -> Optional[str]:
        """Enhance a single video file with Topaz Video AI"""
        try:
            # Generate output filename
            input_name = Path(input_file).stem
            if job_id:
                output_name = f"{job_id}_{input_name}_enhanced_{tape_type.lower()}.mp4"
            else:
                output_name = f"{input_name}_enhanced_{tape_type.lower()}.mp4"
            
            output_file = os.path.join(output_dir, output_name)
            
            # Get enhancement settings for tape type
            enhancement_config = self.enhancement_models.get(tape_type, 
                                                           self.enhancement_models["VHS"])
            
            # Create Topaz command
            success = self._run_topaz_enhancement(input_file, output_file, enhancement_config)
            
            if success and os.path.exists(output_file):
                self.logger.info(f"Successfully enhanced: {output_file}")
                return output_file
            else:
                self.logger.error(f"Topaz enhancement failed for: {input_file}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error enhancing single video {input_file}: {e}")
            return None
    
    def _run_topaz_enhancement(self, input_file: str, output_file: str, 
                              config: Dict) -> bool:
        """Run Topaz Video AI enhancement"""
        try:
            # Create settings file for this job
            settings_file = self._create_settings_file(config)
            
            # Build Topaz command
            cmd = [
                self.topaz_path,
                '--input', input_file,
                '--output', output_file,
                '--model', config['model'],
                '--settings', settings_file,
                '--progress',  # Show progress
                '--overwrite'  # Overwrite existing files
            ]
            
            # Add model-specific parameters
            settings = config.get('settings', {})
            for param, value in settings.items():
                if isinstance(value, bool):
                    if value:
                        cmd.extend([f'--{param.replace("_", "-")}'])
                else:
                    cmd.extend([f'--{param.replace("_", "-")}', str(value)])
            
            self.logger.debug(f"Running Topaz command: {' '.join(cmd)}")
            
            # Run Topaz Video AI
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )
            
            # Monitor progress
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # Parse progress if available
                    if 'progress:' in output.lower():
                        self.logger.debug(f"Topaz progress: {output.strip()}")
            
            # Wait for completion
            return_code = process.wait()
            
            if return_code == 0:
                self.logger.info("Topaz enhancement completed successfully")
                return True
            else:
                stderr = process.stderr.read()
                self.logger.error(f"Topaz enhancement failed (code {return_code}): {stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("Topaz enhancement timeout")
            process.kill()
            return False
        except Exception as e:
            self.logger.error(f"Topaz enhancement error: {e}")
            return False
        finally:
            # Cleanup settings file
            if 'settings_file' in locals() and os.path.exists(settings_file):
                try:
                    os.remove(settings_file)
                except:
                    pass
    
    def _create_settings_file(self, config: Dict) -> str:
        """Create temporary settings file for Topaz"""
        timestamp = int(time.time())
        settings_file = os.path.join(self.temp_dir, f"topaz_settings_{timestamp}.json")
        
        # Create Topaz-compatible settings
        topaz_settings = {
            "model": config["model"],
            "parameters": config.get("settings", {}),
            "output_format": "mp4",
            "quality": "high"
        }
        
        with open(settings_file, 'w') as f:
            json.dump(topaz_settings, f, indent=2)
        
        return settings_file
    
    def _mock_enhance_videos(self, input_files: List[str], output_dir: str, 
                           job_id: str = None, tape_type: str = "VHS") -> List[str]:
        """Mock video enhancement for testing without Topaz Video AI"""
        self.logger.info(f"MOCK: Enhancing {len(input_files)} videos with Topaz AI ({tape_type})")
        
        os.makedirs(output_dir, exist_ok=True)
        enhanced_files = []
        
        for i, input_file in enumerate(input_files):
            if not os.path.exists(input_file):
                self.logger.warning(f"MOCK: Input file not found: {input_file}")
                continue
            
            # Create mock enhanced file
            input_name = Path(input_file).stem
            if job_id:
                output_name = f"{job_id}_{input_name}_enhanced_{tape_type.lower()}.mp4"
            else:
                output_name = f"{input_name}_enhanced_{tape_type.lower()}.mp4"
            
            output_file = os.path.join(output_dir, output_name)
            
            # Copy input to output (simulate enhancement)
            shutil.copy2(input_file, output_file)
            
            # Add enhancement metadata
            with open(output_file + ".topaz", 'w') as f:
                f.write(f"Enhanced with Topaz Video AI\n")
                f.write(f"Model: {self.enhancement_models.get(tape_type, {}).get('model', 'Artemis')}\n")
                f.write(f"Tape Type: {tape_type}\n")
                f.write(f"Original: {input_file}\n")
                f.write(f"Enhanced at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Job ID: {job_id}\n")
            
            enhanced_files.append(output_file)
            self.logger.info(f"MOCK: Enhanced {input_name} -> {output_name}")
            
            # Simulate processing time
            time.sleep(1)
        
        return enhanced_files
    
    def get_available_models(self) -> List[str]:
        """Get list of available Topaz models"""
        if not self.enabled:
            return ["Artemis", "Iris", "Gaia"]  # Mock models
        
        try:
            cmd = [self.topaz_path, '--list-models']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                models = result.stdout.strip().split('\n')
                return [model.strip() for model in models if model.strip()]
            
        except Exception as e:
            self.logger.warning(f"Could not get Topaz models: {e}")
        
        # Return default models
        return list(set(config["model"] for config in self.enhancement_models.values()))
    
    def estimate_processing_time(self, input_file: str, tape_type: str = "VHS") -> int:
        """Estimate processing time in seconds"""
        if not os.path.exists(input_file):
            return 0
        
        try:
            # Get video duration and size for estimation
            file_size = os.path.getsize(input_file) / (1024 * 1024)  # MB
            
            # Rough estimation: 1MB = 30 seconds processing time for Topaz
            # This varies greatly based on hardware and model
            base_time = int(file_size * 30)
            
            # Adjust based on tape type complexity
            complexity_multipliers = {
                "VHS": 1.5,      # High noise, needs more processing
                "Hi8": 1.3,
                "Betamax": 1.3,
                "MiniDV": 1.0,   # Clean digital source
                "Digital8": 1.0,
                "Super8": 1.8    # Film grain and complex restoration
            }
            
            multiplier = complexity_multipliers.get(tape_type, 1.2)
            estimated_time = int(base_time * multiplier)
            
            return max(estimated_time, 60)  # Minimum 1 minute
            
        except Exception as e:
            self.logger.warning(f"Could not estimate processing time: {e}")
            return 300  # Default 5 minutes
    
    def close(self):
        """Clean up Topaz handler"""
        try:
            # Clean up temp directory
            if os.path.exists(self.temp_dir):
                for file in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, file)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except:
                        pass
            
            self.logger.info("Topaz handler cleanup complete")
            
        except Exception as e:
            self.logger.error(f"Error during Topaz cleanup: {e}")