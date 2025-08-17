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

def can_setup_signal():
    # Only setup signal in main thread of main interpreter
    return threading.current_thread() is threading.main_thread()

class VideoProcessorApp:
    """Main application class for video processing automation"""
    
    def __init__(self, config_path: str = "config/app_settings.json", setup_signals: bool = True):
        """Initialize the video processor application"""
        # Setup logging first
        setup_logging()
        self.logger = logging.getLogger(__name__)

        # Load configuration
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.get_config()

        # Project root (folder containing this file)
        self.project_root = Path(__file__).parent.resolve()

        # Setup directories (will rewrite any relative or token paths to absolute under project root)
        self.setup_directories()

        # Initialize components
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

        self.logger.info("Video Processor Application initialized")
    
    def setup_directories(self):
        """Create necessary directories"""
        directories = self.config.get("directories", {})
        resolved = {}
        for dir_name, dir_path in directories.items():
            try:
                # Support token replacement
                if isinstance(dir_path, str):
                    dir_path = dir_path.replace('{PROJECT_ROOT}', str(self.project_root))
                p = Path(dir_path)
                # If relative, anchor to project root
                if not p.is_absolute():
                    p = self.project_root / p
                # If absolute with a drive letter that doesn't exist on this machine, fallback to project root
                if p.is_absolute() and p.drive and not Path(p.drive + '\\').exists():
                    fallback = Path(__file__).parent / p.relative_to(p.anchor)
                    self.logger.warning(
                        f"Drive {p.drive} not found. Falling back directory '{dir_name}' to '{fallback}' instead of '{dir_path}'"
                    )
                    p = fallback
                p.mkdir(parents=True, exist_ok=True)
                resolved[dir_name] = str(p)
                self.logger.debug(f"Directory ready: {p}")
            except Exception as e:
                self.logger.error(f"Failed to prepare directory {dir_name} ({dir_path}): {e}")
        # Update config with resolved paths so rest of app uses them
        if resolved:
            self.config["directories"].update(resolved)
    
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
        """Process a single video job"""
        job_id = job['job_id']
        self.current_job = job_id
        
        try:
            # Update job status to processing
            self.queue_manager.update_job_status(job_id, "processing", 
                                               started_at=time.time())
            
            # Step 1: Download source files
            self.logger.info(f"[{job_id}] Downloading source files")
            local_files = self.gdrive_handler.download_files(
                job['source_files'], 
                self.config["directories"]["input"]
            )
            
            if not local_files:
                raise Exception("Failed to download source files")
            
            # Step 2: Detect tape type if not specified
            tape_type = job.get('tape_type')
            if not tape_type or tape_type == "auto":
                self.logger.info(f"[{job_id}] Detecting tape type")
                tape_type = self.tape_detector.detect_from_files(local_files)
                self.logger.info(f"[{job_id}] Detected tape type: {tape_type}")
                
                # Update job with detected tape type
                self.queue_manager.update_job_status(job_id, "processing", 
                                                   detected_tape_type=tape_type)
            
            # Step 3: Process with Premiere Pro
            self.logger.info(f"[{job_id}] Processing with Premiere Pro ({tape_type})")
            premiere_output = self.premiere_automation.process_videos(
                local_files, 
                tape_type,
                self.config["directories"]["output"],
                job_id=job_id,
                processing_options=job.get('processing_options')
            )
            
            # Step 4: Enhance with Topaz (if enabled and requested)
            final_output = premiere_output
            processing_options = job.get('processing_options', {})
            
            if (self.config.get("topaz", {}).get("enabled", False) and 
                processing_options.get('topaz_enhancement', False)):
                
                self.logger.info(f"[{job_id}] Enhancing with Topaz Video AI")
                final_output = self.topaz_handler.enhance_videos(
                    premiere_output,
                    self.config["directories"]["output"],
                    job_id=job_id
                )
            
            # Step 5: Upload results back to Google Drive
            self.logger.info(f"[{job_id}] Uploading processed videos to Google Drive")
            upload_urls = self.gdrive_handler.upload_files(
                final_output,
                job.get('output_folder_id') or 
                self.config.get('gdrive', {}).get('default_output_folder_id') or 
                self.config.get('gdrive', {}).get('output_folder_id'),  # legacy fallback
                job_id=job_id
            )
            
            if not upload_urls:
                # Treat missing uploads as failure (so user can see problem) instead of silent success
                raise Exception("No files were uploaded. Check Google Drive folder sharing / quota.")

            # Step 6: Update job status to completed
            self.queue_manager.update_job_status(
                job_id, 
                "completed", 
                completed_at=time.time(),
                output_files=upload_urls,
                processed_tape_type=tape_type
            )
            
            # Step 7: Cleanup temporary files
            if self.config.get("processing", {}).get("cleanup_temp_files", True):
                self._cleanup_job_files(local_files, premiere_output, final_output)
            
            self.logger.info(f"[{job_id}] Job completed successfully")
            
        except Exception as e:
            self.logger.error(f"[{job_id}] Error processing job: {e}", exc_info=True)
            self.queue_manager.update_job_status(
                job_id, 
                "failed", 
                failed_at=time.time(),
                error_message=str(e)
            )
        finally:
            self.current_job = None
    
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