"""
Video Processing Automation Tool - Main Application
Shadow PC automation for tape-to-digital video conversion
Author: vniroshan
Date: 2025-08-11
"""

import os
import sys
import time
import signal
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional
import json

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from queue_manager import QueueManager
from gdrive_handler import GDriveHandler
from premiere_automation import PremiereAutomation
from topaz_handler import TopazHandler
from tape_detector import TapeDetector
from utils.logger import setup_logging
from utils.config_manager import ConfigManager
from utils.shadow_pc_optimizer import ShadowPCOptimizer

def can_setup_signal():
    # Only setup signal in main thread of main interpreter
    return threading.current_thread() is threading.main_thread()

class VideoProcessorApp:
    """Main application class for video processing automation"""
    
    def __init__(self, config_path: str = "config/app_settings.json", setup_signals: bool = True):
        """Initialize the video processor application with enhanced optimization support"""
        # Setup logging first
        setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # Load and validate configuration
        self.config_manager = ConfigManager(config_path)
        
        # Initialize Shadow PC optimizer
        self.shadow_optimizer = ShadowPCOptimizer(self.config_manager.get_config())
        
        # Apply optimizations to configuration
        optimized_config = self.shadow_optimizer.apply_optimizations_to_config(
            self.config_manager.get_config()
        )
        self.config_manager.config = optimized_config
        self.config = optimized_config
        
        # Log optimization results
        if self.shadow_optimizer.is_shadow_pc():
            self.logger.info("Shadow PC environment detected - optimizations applied")
        
        if self.shadow_optimizer.has_gpu_acceleration():
            gpu_info = self.shadow_optimizer.get_gpu_info()
            self.logger.info(f"GPU acceleration available: {gpu_info}")
        
        # Validate configuration
        if not self.config_manager.is_valid():
            validation_errors = self.config_manager.get_validation_errors()
            for error in validation_errors:
                self.logger.warning(f"Configuration warning: {error}")
        
        # Setup directories
        self.setup_directories()
        
        # Initialize components with optimized config
        self.queue_manager = QueueManager(self.config.get("queue", {}))
        self.gdrive_handler = GDriveHandler(self.config.get("gdrive", {}))
        self.premiere_automation = PremiereAutomation(self.config.get("premiere", {}))
        self.topaz_handler = TopazHandler(self.config.get("topaz", {}))
        self.tape_detector = TapeDetector(self.config.get("detection", {}))
        
        # Application state
        self.running = False
        self.current_job = None
        self.shutdown_event = threading.Event()
        
        # Setup signal handlers for graceful shutdown (only if allowed)
        if setup_signals and can_setup_signal():
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("Video Processor Application initialized with optimizations")
    
    def setup_directories(self):
        """Create necessary directories"""
        directories = self.config.get("directories", {})
        for dir_name, dir_path in directories.items():
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Directory ready: {dir_path}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
        self.shutdown()
    
    def start_processing(self):
        """Start the main processing loop"""
        self.logger.info("Starting Video Processor Application")
        self.running = True
        
        try:
            while self.running and not self.shutdown_event.is_set():
                self.process_queue()
                
                # Wait for shutdown event or timeout
                if self.shutdown_event.wait(timeout=self.config.get("processing", {}).get("polling_interval", 30)):
                    break
                    
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def run_processing_loop(self):
        """Entry point for running in a thread from web_ui.py"""
        self.start_processing()
    
    def process_queue(self):
        """Process pending jobs from the queue"""
        try:
            max_concurrent = self.config.get("processing", {}).get("max_concurrent_jobs", 1)
            pending_jobs = self.queue_manager.get_pending_jobs(limit=max_concurrent)
            
            if not pending_jobs:
                self.logger.debug("No pending jobs found")
                return
            
            for job in pending_jobs:
                if not self.running or self.shutdown_event.is_set():
                    break
                    
                self.logger.info(f"Processing job: {job['job_id']}")
                self.process_single_job(job)
                
        except Exception as e:
            self.logger.error(f"Error processing queue: {e}", exc_info=True)
    
    def process_single_job(self, job: Dict):
        """Process a single video job with enhanced error handling and resource management"""
        job_id = job['job_id']
        self.current_job = job_id
        
        # Initialize resource tracking
        temp_files = []
        opened_resources = []
        
        try:
            # Update job status to processing
            self.queue_manager.update_job_status(job_id, "processing", 
                                               started_at=time.time())
            
            # Validate job data
            if not self._validate_job_data(job):
                raise Exception("Invalid job data")
            
            # Step 1: Download source files with validation
            self.logger.info(f"[{job_id}] Downloading source files")
            local_files = self._download_with_validation(job, temp_files)
            
            if not local_files:
                raise Exception("Failed to download source files")
            
            # Step 2: Detect tape type if not specified
            tape_type = self._detect_or_validate_tape_type(job, local_files)
            
            # Step 3: Process with Premiere Pro
            self.logger.info(f"[{job_id}] Processing with Premiere Pro ({tape_type})")
            
            try:
                premiere_output = self.premiere_automation.process_videos(
                    local_files, 
                    tape_type,
                    self.config["directories"]["output"],
                    job_id=job_id
                )
                temp_files.extend(premiere_output)
                
            except Exception as e:
                self.logger.error(f"[{job_id}] Premiere Pro processing failed: {e}")
                if self.config.get("processing", {}).get("fallback_to_ffmpeg", True):
                    self.logger.info(f"[{job_id}] Falling back to FFmpeg processing")
                    premiere_output = self._fallback_ffmpeg_processing(local_files, tape_type, job_id)
                    temp_files.extend(premiere_output)
                else:
                    raise Exception(f"Premiere Pro processing failed: {e}")
            
            if not premiere_output:
                raise Exception("No output files generated from video processing")
            
            # Step 4: Enhance with Topaz (if enabled and requested)
            final_output = self._process_with_topaz(job, premiere_output, temp_files)
            
            # Step 5: Upload results back to Google Drive
            upload_urls = self._upload_results(job, final_output)
            
            # Step 6: Update job status to completed
            self.queue_manager.update_job_status(
                job_id, 
                "completed", 
                completed_at=time.time(),
                output_files=upload_urls,
                processed_tape_type=tape_type
            )
            
            self.logger.info(f"[{job_id}] Job completed successfully")
            
        except Exception as e:
            error_msg = f"Error processing job: {str(e)}"
            self.logger.error(f"[{job_id}] {error_msg}", exc_info=True)
            
            # Update job status to failed with detailed error information
            self.queue_manager.update_job_status(
                job_id, 
                "failed", 
                failed_at=time.time(),
                error_message=error_msg,
                error_type=type(e).__name__
            )
            
        finally:
            # Always cleanup resources
            self._cleanup_job_resources(job_id, temp_files, opened_resources)
            self.current_job = None

    def _validate_job_data(self, job: Dict) -> bool:
        """Validate job data structure and required fields"""
        required_fields = ['job_id', 'source_files']
        
        for field in required_fields:
            if field not in job:
                self.logger.error(f"Missing required field in job: {field}")
                return False
        
        if not isinstance(job['source_files'], list) or not job['source_files']:
            self.logger.error("Job must have non-empty source_files list")
            return False
        
        return True

    def _download_with_validation(self, job: Dict, temp_files: List[str]) -> List[str]:
        """Download files with validation and error handling"""
        try:
            local_files = self.gdrive_handler.download_files(
                job['source_files'], 
                self.config["directories"]["input"]
            )
            
            if local_files:
                temp_files.extend(local_files)
                
                # Validate downloaded files
                validated_files = []
                for file_path in local_files:
                    if self._validate_downloaded_file(file_path):
                        validated_files.append(file_path)
                    else:
                        self.logger.warning(f"Downloaded file failed validation: {file_path}")
                
                return validated_files
            
            return []
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return []

    def _validate_downloaded_file(self, file_path: str) -> bool:
        """Validate a downloaded file"""
        try:
            if not os.path.exists(file_path):
                return False
            
            # Check file size
            if os.path.getsize(file_path) == 0:
                self.logger.error(f"Downloaded file is empty: {file_path}")
                return False
            
            # Basic format validation could be added here
            return True
            
        except Exception as e:
            self.logger.error(f"File validation error: {e}")
            return False

    def _detect_or_validate_tape_type(self, job: Dict, local_files: List[str]) -> str:
        """Detect or validate tape type with error handling"""
        tape_type = job.get('tape_type')
        
        if not tape_type or tape_type == "auto":
            try:
                self.logger.info(f"[{job['job_id']}] Detecting tape type")
                tape_type = self.tape_detector.detect_from_files(local_files)
                self.logger.info(f"[{job['job_id']}] Detected tape type: {tape_type}")
                
                # Update job with detected tape type
                self.queue_manager.update_job_status(job['job_id'], "processing", 
                                                   detected_tape_type=tape_type)
            except Exception as e:
                self.logger.warning(f"Tape detection failed: {e}, defaulting to VHS")
                tape_type = "VHS"  # Default fallback
        
        return tape_type

    def _fallback_ffmpeg_processing(self, local_files: List[str], tape_type: str, job_id: str) -> List[str]:
        """Fallback FFmpeg processing when Premiere Pro fails"""
        processed_files = []
        output_dir = self.config["directories"]["output"]
        
        try:
            import subprocess
            
            for i, input_file in enumerate(local_files):
                output_name = f"{job_id}_fallback_{i}_{tape_type.lower()}.mp4"
                output_file = os.path.join(output_dir, output_name)
                
                # Basic FFmpeg command with tape-specific settings
                cmd = [
                    'ffmpeg', '-i', input_file,
                    '-c:v', 'libx264',
                    '-crf', '18',
                    '-preset', 'medium',
                    '-c:a', 'aac',
                    '-b:a', '192k'
                ]
                
                # Add tape-specific filters
                if tape_type.upper() in ['VHS', 'BETAMAX', 'HI8']:
                    cmd.extend(['-filter:v', 'yadif=0:0:0'])  # Deinterlace
                
                cmd.extend(['-y', output_file])
                
                self.logger.info(f"Running FFmpeg fallback: {' '.join(cmd)}")
                
                result = subprocess.run(cmd, capture_output=True, text=True, 
                                      timeout=self.config.get("processing", {}).get("ffmpeg_timeout", 3600))
                
                if result.returncode == 0 and os.path.exists(output_file):
                    processed_files.append(output_file)
                    self.logger.info(f"FFmpeg fallback successful: {output_file}")
                else:
                    self.logger.error(f"FFmpeg fallback failed: {result.stderr}")
                    
        except Exception as e:
            self.logger.error(f"FFmpeg fallback error: {e}")
        
        return processed_files

    def _process_with_topaz(self, job: Dict, premiere_output: List[str], temp_files: List[str]) -> List[str]:
        """Process with Topaz if enabled and requested"""
        final_output = premiere_output
        processing_options = job.get('processing_options', {})
        
        if (self.config.get("topaz", {}).get("enabled", False) and 
            processing_options.get('topaz_enhancement', False)):
            
            try:
                self.logger.info(f"[{job['job_id']}] Enhancing with Topaz Video AI")
                topaz_output = self.topaz_handler.enhance_videos(
                    premiere_output,
                    self.config["directories"]["output"],
                    job_id=job['job_id']
                )
                
                if topaz_output:
                    final_output = topaz_output
                    temp_files.extend(topaz_output)
                else:
                    self.logger.warning("Topaz enhancement failed, using Premiere output")
                    
            except Exception as e:
                self.logger.error(f"Topaz enhancement failed: {e}")
                # Continue with Premiere output
        
        return final_output

    def _upload_results(self, job: Dict, final_output: List[str]) -> List[str]:
        """Upload results with error handling"""
        try:
            self.logger.info(f"[{job['job_id']}] Uploading processed videos to Google Drive")
            return self.gdrive_handler.upload_files(
                final_output,
                job.get('output_folder_id'),
                job_id=job['job_id']
            )
        except Exception as e:
            self.logger.error(f"Upload failed: {e}")
            return []

    def _cleanup_job_resources(self, job_id: str, temp_files: List[str], opened_resources: List):
        """Enhanced cleanup of job resources"""
        try:
            # Close any opened resources
            for resource in opened_resources:
                try:
                    if hasattr(resource, 'close'):
                        resource.close()
                except Exception as e:
                    self.logger.warning(f"Error closing resource: {e}")
            
            # Clean up temporary files if enabled
            if self.config.get("processing", {}).get("cleanup_temp_files", True):
                self._cleanup_job_files(*[temp_files])
            
            self.logger.debug(f"[{job_id}] Resource cleanup completed")
            
        except Exception as e:
            self.logger.error(f"[{job_id}] Error during resource cleanup: {e}")
    
    def _cleanup_job_files(self, *file_lists):
        """Clean up temporary files after processing"""
        for file_list in file_lists:
            if isinstance(file_list, list):
                for file_path in file_list:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            self.logger.debug(f"Cleaned up file: {file_path}")
                    except Exception as e:
                        self.logger.warning(f"Failed to cleanup file {file_path}: {e}")
    
    def get_status(self) -> Dict:
        """Get current application status"""
        return {
            "running": self.running,
            "current_job": self.current_job,
            "queue_stats": self.queue_manager.get_queue_stats(),
            "config": {
                "directories": self.config.get("directories", {}),
                "processing": self.config.get("processing", {}),
                "topaz_enabled": self.config.get("topaz", {}).get("enabled", False)
            }
        }
    
    def shutdown(self):
        """Gracefully shutdown the application"""
        if not self.running:
            return
            
        self.logger.info("Shutting down Video Processor Application")
        self.running = False
        self.shutdown_event.set()
        
        # Close component connections
        components = [
            self.premiere_automation,
            self.topaz_handler,
            self.gdrive_handler
        ]
        
        for component in components:
            if hasattr(component, 'close'):
                try:
                    component.close()
                except Exception as e:
                    self.logger.error(f"Error closing component {component}: {e}")
        
        self.logger.info("Shutdown complete")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Video Processing Automation Tool')
    parser.add_argument('--config', default='config/app_settings.json',
                       help='Configuration file path')
    parser.add_argument('--single-run', action='store_true',
                       help='Process queue once and exit')
    parser.add_argument('--daemon', action='store_true',
                       help='Run as daemon process')
    
    args = parser.parse_args()
    
    app = VideoProcessorApp(args.config, setup_signals=True)
    
    if args.single_run:
        app.process_queue()
    else:
        app.start_processing()

if __name__ == "__main__":
    main()