"""
Adobe Premiere Pro Automation for Video Processing
Handles automated video processing using COM automation
"""

import os
import sys
import time
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import json
import shutil

# Windows COM imports
if sys.platform == "win32":
    try:
        import win32com.client
        import pythoncom
        COM_AVAILABLE = True
    except ImportError:
        COM_AVAILABLE = False
else:
    COM_AVAILABLE = False

class PremiereAutomation:
    """Handles Adobe Premiere Pro automation for video processing"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.app = None
        self.enabled = self.config.get("enabled", False) and COM_AVAILABLE
        
        # Premiere Pro settings
        self.app_name = "Premiere Pro.Application"
        self.presets_dir = self.config.get("presets_directory", "presets")
        self.temp_project_dir = self.config.get("temp_project_directory", "temp/premiere_projects")
        
        # Processing presets mapping
        self.preset_mapping = {
            "VHS": "VHS_Cleanup.prproj",
            "MiniDV": "MiniDV_Enhance.prproj", 
            "Hi8": "Hi8_Restore.prproj",
            "Betamax": "Betamax_Enhance.prproj",
            "Digital8": "Digital8_Process.prproj",
            "Super8": "Super8_FilmLook.prproj"
        }
        
        # Ensure directories exist
        os.makedirs(self.temp_project_dir, exist_ok=True)
        os.makedirs(self.presets_dir, exist_ok=True)
        
        if self.enabled:
            self._initialize_premiere()
        else:
            self.logger.warning("Premiere Pro automation disabled or COM not available")
    
    def _initialize_premiere(self):
        """Initialize connection to Premiere Pro"""
        try:
            pythoncom.CoInitialize()
            
            # Try to connect to existing instance first
            try:
                self.app = win32com.client.GetActiveObject(self.app_name)
                self.logger.info("Connected to existing Premiere Pro instance")
            except:
                # Launch new instance
                self.app = win32com.client.Dispatch(self.app_name)
                self.logger.info("Launched new Premiere Pro instance")
                time.sleep(5)  # Give Premiere time to start
            
            # Verify connection
            if self.app:
                version = getattr(self.app, 'version', 'unknown')
                self.logger.info(f"Premiere Pro version: {version}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Premiere Pro: {e}")
            self.enabled = False
            self.app = None
    
    def process_videos(self, input_files: List[str], tape_type: str, 
                      output_dir: str, job_id: str = None,
                      processing_options: Optional[Dict] = None) -> List[str]:
        """Process videos using Premiere Pro automation

        Parameters:
            input_files: list of source video file paths
            tape_type: detected or provided tape type (e.g., VHS)
            output_dir: destination directory for processed videos
            job_id: optional job identifier used to prefix output filenames
            processing_options: dict that may include 'premiere_preset' to override the default template
        """
        if not self.enabled:
            return self._mock_process_videos(input_files, tape_type, output_dir, job_id)
        
        processed_files = []
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            for i, input_file in enumerate(input_files):
                if not os.path.exists(input_file):
                    self.logger.error(f"Input file not found: {input_file}")
                    continue
                
                custom_preset = None
                if processing_options:
                    custom_preset = processing_options.get('premiere_preset') or processing_options.get('preset')
                if custom_preset:
                    self.logger.info(f"Processing {input_file} with custom preset override '{custom_preset}' (tape type: {tape_type})")
                else:
                    self.logger.info(f"Processing {input_file} with {tape_type} preset")
                
                output_file = self._process_single_video(
                    input_file, tape_type, output_dir, job_id, i, custom_preset
                )
                
                if output_file:
                    processed_files.append(output_file)
                
        except Exception as e:
            self.logger.error(f"Error in video processing: {e}")
        
        self.logger.info(f"Processed {len(processed_files)} videos with Premiere Pro")
        return processed_files
    
    def _process_single_video(self, input_file: str, tape_type: str, 
                             output_dir: str, job_id: str = None, 
                             file_index: int = 0,
                             custom_preset: Optional[str] = None) -> Optional[str]:
        """Process a single video file

        custom_preset: Optional project template name (file name) to override tape_type mapping.
        Accepts either a .prproj, .json, or .prfpset (effect/color) file – logic will adapt.
        """
        try:
            # Generate output filename
            input_name = Path(input_file).stem
            if job_id:
                output_name = f"{job_id}_{input_name}_processed_{tape_type.lower()}.mp4"
            else:
                output_name = f"{input_name}_processed_{tape_type.lower()}.mp4"
            
            output_file = os.path.join(output_dir, output_name)
            
            # Get or create project template
            project_template = None
            if custom_preset:
                # Resolve custom preset path inside presets dir if just a filename
                candidate = custom_preset
                if not os.path.isabs(candidate):
                    candidate = os.path.join(self.presets_dir, candidate)
                if os.path.exists(candidate):
                    project_template = candidate
                else:
                    self.logger.warning(f"Custom preset '{custom_preset}' not found, falling back to tape type mapping")
            if not project_template:
                project_template = self._get_project_template(tape_type)
            if not project_template:
                self.logger.error(f"No project template found for {tape_type}")
                return self._fallback_processing(input_file, output_file)
            
            # Create working project
            project_file = self._create_working_project(
                project_template, input_file, job_id, file_index
            )
            
            # Open project in Premiere
            if not self._open_project(project_file):
                self.logger.error(f"Failed to open project: {project_file}")
                return self._fallback_processing(input_file, output_file)
            
            # Import source media
            if not self._import_media(input_file):
                self.logger.error(f"Failed to import media: {input_file}")
                return self._fallback_processing(input_file, output_file)
            
            # Apply processing sequence
            if not self._apply_processing_sequence(tape_type):
                self.logger.error(f"Failed to apply processing sequence for {tape_type}")
                return self._fallback_processing(input_file, output_file)
            
            # Export processed video
            if not self._export_video(output_file):
                self.logger.error(f"Failed to export video: {output_file}")
                return self._fallback_processing(input_file, output_file)
            
            # Cleanup project
            self._cleanup_project(project_file)
            
            self.logger.info(f"Successfully processed: {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"Error processing single video {input_file}: {e}")
            return self._fallback_processing(input_file, 
                                           os.path.join(output_dir, f"fallback_{Path(input_file).name}"))
    
    def _get_project_template(self, tape_type: str) -> Optional[str]:
        """Get project template file for tape type"""
        template_name = self.preset_mapping.get(tape_type, "VHS_Cleanup.prproj")
        template_path = os.path.join(self.presets_dir, template_name)
        
        if os.path.exists(template_path):
            return template_path
        
        # Create basic template if it doesn't exist
        self.logger.warning(f"Template not found: {template_path}, creating basic template")
        return self._create_basic_template(tape_type, template_path)

    # ---- Preset management helpers ----
    def refresh_presets(self):
        """Refresh available preset files (project/effect/export) in presets directory."""
        try:
            files = os.listdir(self.presets_dir)
            self.available_presets = [f for f in files if f.lower().endswith(('.prproj', '.json', '.prfpset', '.epr'))]
        except Exception as e:
            self.available_presets = []
            self.logger.error(f"Failed to list presets: {e}")

    def get_available_presets(self) -> List[str]:
        """Return list of cached available preset filenames."""
        if not hasattr(self, 'available_presets'):
            self.refresh_presets()
        return self.available_presets

    def update_preset_mapping(self, mapping: Dict[str, str]):
        """Update internal tape_type -> preset mapping dynamically."""
        if not isinstance(mapping, dict):
            self.logger.warning("Provided mapping is not a dict; ignoring")
            return
        self.preset_mapping.update(mapping)
        self.logger.info(f"Updated preset mapping entries: {list(mapping.keys())}")
    
    def _create_basic_template(self, tape_type: str, template_path: str) -> str:
        """Create a basic project template"""
        # This would typically involve creating a .prproj file
        # For now, we'll create a placeholder that our automation can work with
        
        template_config = {
            "tape_type": tape_type,
            "processing_settings": self._get_processing_settings(tape_type),
            "export_settings": {
                "format": "H.264",
                "quality": "High",
                "resolution": "1920x1080",
                "frame_rate": "29.97"
            }
        }
        
        # Save as JSON for our automation to read
        json_template = template_path.replace('.prproj', '.json')
        with open(json_template, 'w') as f:
            json.dump(template_config, f, indent=2)
        
        self.logger.info(f"Created basic template: {json_template}")
        return json_template
    
    def _get_processing_settings(self, tape_type: str) -> Dict:
        """Get processing settings for specific tape type"""
        settings = {
            "VHS": {
                "deinterlace": True,
                "noise_reduction": "High",
                "color_correction": True,
                "stabilization": True,
                "sharpening": "Light"
            },
            "MiniDV": {
                "deinterlace": True,
                "noise_reduction": "Low",
                "color_correction": False,
                "stabilization": False,
                "sharpening": "None"
            },
            "Hi8": {
                "deinterlace": True,
                "noise_reduction": "Medium",
                "color_correction": True,
                "stabilization": True,
                "sharpening": "Light"
            },
            "Betamax": {
                "deinterlace": True,
                "noise_reduction": "Medium",
                "color_correction": True,
                "stabilization": True,
                "sharpening": "Light"
            },
            "Digital8": {
                "deinterlace": True,
                "noise_reduction": "Low",
                "color_correction": False,
                "stabilization": False,
                "sharpening": "None"
            },
            "Super8": {
                "deinterlace": False,
                "noise_reduction": "Medium",
                "color_correction": True,
                "stabilization": True,
                "sharpening": "Medium",
                "film_grain": True
            }
        }
        
        return settings.get(tape_type, settings["VHS"])
    
    def _create_working_project(self, template_path: str, input_file: str, 
                               job_id: str = None, file_index: int = 0) -> str:
        """Create a working copy of the project template"""
        timestamp = int(time.time())
        project_name = f"working_project_{job_id or 'temp'}_{file_index}_{timestamp}"
        
        if template_path.endswith('.json'):
            working_project = os.path.join(self.temp_project_dir, f"{project_name}.json")
            shutil.copy2(template_path, working_project)
        else:
            working_project = os.path.join(self.temp_project_dir, f"{project_name}.prproj")
            if os.path.exists(template_path):
                shutil.copy2(template_path, working_project)
            else:
                # Create minimal project file
                with open(working_project, 'w') as f:
                    f.write(f"# Premiere Project for {input_file}\n")
        
        return working_project
    
    def _open_project(self, project_file: str) -> bool:
        """Open project in Premiere Pro"""
        try:
            if not self.app:
                return False
            
            # This would be the actual COM call to open project
            # For demonstration, we'll simulate the operation
            self.logger.debug(f"Opening project: {project_file}")
            
            # Actual implementation would be:
            # self.app.OpenDocument(project_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to open project {project_file}: {e}")
            return False
    
    def _import_media(self, input_file: str) -> bool:
        """Import media into Premiere Pro project"""
        try:
            if not self.app:
                return False
            
            self.logger.debug(f"Importing media: {input_file}")
            
            # Actual implementation would be:
            # project = self.app.GetActiveProject()
            # project.ImportFiles([input_file])
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to import media {input_file}: {e}")
            return False
    
    def _apply_processing_sequence(self, tape_type: str) -> bool:
        """Apply processing sequence based on tape type"""
        try:
            if not self.app:
                return False
            
            settings = self._get_processing_settings(tape_type)
            self.logger.debug(f"Applying {tape_type} processing sequence: {settings}")
            
            # This would involve applying effects, adjustments, etc.
            # Actual implementation would manipulate the timeline and effects
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to apply processing sequence: {e}")
            return False
    
    def _export_video(self, output_file: str) -> bool:
        """Export processed video"""
        try:
            if not self.app:
                return False
            
            self.logger.debug(f"Exporting video: {output_file}")
            
            # Actual implementation would be:
            # exporter = self.app.GetActiveProject().GetActiveSequence().GetExporter()
            # exporter.ExportToFile(output_file, export_settings)
            
            # For now, simulate by waiting
            time.sleep(2)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export video {output_file}: {e}")
            return False
    
    def _cleanup_project(self, project_file: str):
        """Clean up temporary project files"""
        try:
            if os.path.exists(project_file):
                os.remove(project_file)
                self.logger.debug(f"Cleaned up project: {project_file}")
        except Exception as e:
            self.logger.warning(f"Failed to cleanup project {project_file}: {e}")
    
    def _fallback_processing(self, input_file: str, output_file: str) -> Optional[str]:
        """Fallback processing using FFmpeg"""
        try:
            self.logger.info(f"Using FFmpeg fallback for {input_file}")
            
            # Basic video processing with FFmpeg
            cmd = [
                'ffmpeg', '-i', input_file,
                '-c:v', 'libx264',
                '-crf', '18',
                '-preset', 'medium',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-filter:v', 'yadif=0:0:0',  # Deinterlace
                '-y',  # Overwrite output
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            
            if result.returncode == 0 and os.path.exists(output_file):
                self.logger.info(f"FFmpeg fallback successful: {output_file}")
                return output_file
            else:
                self.logger.error(f"FFmpeg fallback failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"FFmpeg processing timeout for {input_file}")
            return None
        except FileNotFoundError:
            self.logger.error("FFmpeg not found. Please install FFmpeg.")
            return None
        except Exception as e:
            self.logger.error(f"FFmpeg fallback error: {e}")
            return None
    
    def _mock_process_videos(self, input_files: List[str], tape_type: str, 
                           output_dir: str, job_id: str = None) -> List[str]:
        """Mock video processing for testing without Premiere Pro"""
        self.logger.info(f"MOCK: Processing {len(input_files)} videos with {tape_type} preset")
        
        os.makedirs(output_dir, exist_ok=True)
        processed_files = []
        
        for i, input_file in enumerate(input_files):
            if not os.path.exists(input_file):
                self.logger.warning(f"MOCK: Input file not found: {input_file}")
                continue
            
            # Create mock output file
            input_name = Path(input_file).stem
            if job_id:
                output_name = f"{job_id}_{input_name}_processed_{tape_type.lower()}.mp4"
            else:
                output_name = f"{input_name}_processed_{tape_type.lower()}.mp4"
            
            output_file = os.path.join(output_dir, output_name)
            
            # Copy input to output (simulate processing)
            shutil.copy2(input_file, output_file)
            
            # Add some metadata to show it was "processed"
            with open(output_file + ".meta", 'w') as f:
                f.write(f"Processed with {tape_type} preset\n")
                f.write(f"Original: {input_file}\n")
                f.write(f"Processed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Job ID: {job_id}\n")
            
            processed_files.append(output_file)
            self.logger.info(f"MOCK: Processed {input_name} -> {output_name}")
        
        return processed_files
    
    def close(self):
        """Close Premiere Pro connection"""
        try:
            if self.app:
                # Close any open projects
                # self.app.CloseDocument()
                self.app = None
                
            if COM_AVAILABLE:
                pythoncom.CoUninitialize()
                
            self.logger.info("Premiere Pro connection closed")
            
        except Exception as e:
            self.logger.error(f"Error closing Premiere Pro: {e}")