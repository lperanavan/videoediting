"""
Web UI Dashboard for Video Processing Tool
Real-time monitoring and control interface
"""

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
from datetime import datetime
import logging
from pathlib import Path
import sys
import os
import json
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import project modules with error handling
try:
    from queue_manager import QueueManager
    from main import VideoProcessorApp
    from gdrive_handler import GDriveHandler
    from utils.logger import setup_logging
    from utils.config_manager import ConfigManager
except ImportError as e:
    logger.error(f"Import Error: {e}")
    raise

# Initialize logging
setup_logging()

app = Flask(__name__, template_folder="templates")
app.config['SECRET_KEY'] = 'vniroshan_video_processor_2025_08_11'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global variables
config_path = os.path.join(project_root, "config", "app_settings.json")
config_manager = ConfigManager(config_path)
config = config_manager.get_config()
queue_manager = QueueManager(config.get("queue", {}))
gdrive = GDriveHandler(config.get("gdrive", {}))
processor_app = None
processing_thread = None
is_processing = False

class ProgressTracker:
    """Real-time progress tracking with WebSocket updates"""
    def __init__(self):
        self.current_job = None
        self.progress = 0
        self.status = "idle"
        self.logs = []
        self.max_logs = 200
        self.current_step = ""
        self.estimated_completion = None

    def update_progress(self, job_id, progress, status, message="", step="", eta=None):
        """Update progress and broadcast to all connected clients"""
        self.current_job = job_id
        self.progress = progress
        self.status = status
        self.current_step = step
        self.estimated_completion = eta

        if message:
            self.add_log(message)

        # Broadcast to all connected clients
        socketio.emit('progress_update', {
            'job_id': job_id,
            'progress': progress,
            'status': status,
            'message': message,
            'step': step,
            'eta': eta,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })

    def add_log(self, message, level="INFO"):
        """Add log entry and broadcast to clients"""
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': level,
            'message': message
        }

        self.logs.append(log_entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

        socketio.emit('log_update', log_entry)

    def get_status(self):
        """Get current status summary"""
        return {
            'current_job': self.current_job,
            'progress': self.progress,
            'status': self.status,
            'step': self.current_step,
            'eta': self.estimated_completion,
            'is_processing': is_processing
        }

progress_tracker = ProgressTracker()

# -------- Web Routes --------

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/status')
def get_status():
    """Get comprehensive system status"""
    try:
        # Get queue stats with fallback
        try:
            queue_stats = queue_manager.get_queue_stats()
        except:
            queue_stats = {
                'pending_count': 0,
                'completed_count': 0,
                'failed_count': 0,
                'total_jobs': 0
            }

        # Get processor status with fallback
        try:
            processor_status = processor_app.get_status() if processor_app else {}
        except:
            processor_status = {'status': 'unknown'}

        # Get progress tracker status with fallback
        try:
            processing_status = progress_tracker.get_status()
        except:
            processing_status = {
                'current_job': None,
                'progress': 0,
                'status': 'idle',
                'step': '',
                'eta': None,
                'is_processing': False
            }

        return jsonify({
            'success': True,
            'processing': processing_status,
            'queue': queue_stats,
            'system': processor_status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'processing': {
                'current_job': None,
                'progress': 0,
                'status': 'error',
                'step': '',
                'eta': None,
                'is_processing': False
            },
            'queue': {
                'pending_count': 0,
                'completed_count': 0,
                'failed_count': 0,
                'total_jobs': 0
            },
            'system': {'status': 'error'},
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/queue')
def get_queue():
    """Get queue information"""
    try:
        queue_stats = queue_manager.get_queue_stats() if hasattr(queue_manager, 'get_queue_stats') else {
            'pending_count': 0,
            'completed_count': 0,
            'failed_count': 0,
            'total_jobs': 0
        }

        # Get jobs with proper error handling
        try:
            pending_jobs = queue_manager.get_pending_jobs(limit=50)
        except:
            pending_jobs = []

        try:
            recent_jobs = queue_manager.get_jobs_by_status("completed", limit=20)
        except:
            recent_jobs = []

        try:
            failed_jobs = queue_manager.get_jobs_by_status("failed", limit=10)
        except:
            failed_jobs = []

        # Format job data to ensure all required fields are present
        def format_job(job):
            if isinstance(job, dict):
                return {
                    'job_id': job.get('job_id', 'unknown'),
                    'status': job.get('status', 'unknown'),
                    'tape_type': job.get('tape_type', 'Unknown'),
                    'created_at': job.get('created_at', ''),
                    'progress': job.get('progress', 0),
                    'is_manual': job.get('is_manual', False),
                    'drive_link': job.get('drive_link', '') if job.get('is_manual') else ''
                }
            return None

        # Filter out None values and format jobs
        pending_jobs = [format_job(job) for job in pending_jobs if job]
        recent_jobs = [format_job(job) for job in recent_jobs if job]
        failed_jobs = [format_job(job) for job in failed_jobs if job]

        return jsonify({
            'success': True,
            'pending_jobs': pending_jobs,
            'recent_completed': recent_jobs,
            'recent_jobs': recent_jobs,  # alias for front-end code expecting recent_jobs
            'recent_failed': failed_jobs,
            'stats': queue_stats,
            'pending_count': len(pending_jobs),
            'total_jobs': len(pending_jobs) + len(recent_jobs) + len(failed_jobs)
        })
    except Exception as e:
        logger.error(f"Error getting queue: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'pending_jobs': [],
            'recent_completed': [],
            'recent_failed': [],
            'stats': {
                'pending_count': 0,
                'completed_count': 0,
                'failed_count': 0,
                'total_jobs': 0
            },
            'pending_count': 0,
            'total_jobs': 0
        }), 500

@app.route('/api/logs')
def get_logs():
    """Get recent log entries"""
    try:
        limit = request.args.get('limit', 100, type=int)
        return jsonify({
            'success': True,
            'logs': progress_tracker.logs[-limit:]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs/<job_id>')
def get_job_details(job_id):
    """Get detailed information about a specific job"""
    try:
        job = queue_manager.get_job(job_id)
        if job:
            return jsonify({'success': True, 'job': job})
        else:
            return jsonify({'success': False, 'error': 'Job not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/add_test_job', methods=['POST'])
def add_test_job():
    """Add a test job to the queue"""
    try:
        data = request.get_json() or {}
        tape_type = data.get('tape_type', 'VHS')

        job_id = queue_manager.add_test_job(tape_type)
        progress_tracker.add_log(f"Added test job: {job_id} ({tape_type})")

        return jsonify({'success': True, 'job_id': job_id})
    except Exception as e:
        logger.error(f"Error adding test job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/add_manual_job', methods=['POST'])
def add_manual_job():
    """Add a manual job using Google Drive link"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        if not data.get('drive_link'):
            return jsonify({'success': False, 'error': 'drive_link is required'}), 400

        job_data = {
            "customer_id": data.get('customer_id', 'manual_user'),
            "tape_type": data.get('tape_type'),  # Can be None, will be detected later
            "drive_link": data.get('drive_link'),
            "source_files": [],  # Empty list for manual jobs
            "is_manual": True,
            "processing_options": {
                "topaz_enhancement": data.get('topaz_enhancement', False),
                "output_resolution": data.get('output_resolution', '1080p'),
                "premiere_preset": data.get('premiere_preset', 'auto'),
                "custom_settings": data.get('custom_settings', {})
            },
            "output_folder_id": data.get('output_folder_id', 'processed_videos'),
            "priority": data.get('priority', 3),
            "metadata": {
                "added_via": "web_ui_manual",
                "user_agent": request.headers.get('User-Agent', 'unknown'),
                "original_drive_link": data.get('drive_link')  # Store the original link
            }
        }

        job_id = queue_manager.add_job(job_data)
        progress_tracker.add_log(
            f"Added manual job: {job_id} - Drive link processing"
        )

        return jsonify({'success': True, 'job_id': job_id})
    except Exception as e:
        logger.error(f"Error adding manual job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
        if not data.get('drive_link'):
            return jsonify({'success': False, 'error': 'drive_link is required'}), 400
        
        # If tape_type is not provided, it will be detected automatically
        tape_type = data.get('tape_type')
        drive_link = data['drive_link']
        
        job_data = {
            "customer_id": data.get('customer_id', 'manual_process'),
            "tape_type": tape_type,  # Can be None, will be detected later
            "drive_link": drive_link,
            "is_manual": True,
            "processing_options": {
                "topaz_enhancement": data.get('topaz_enhancement', False),
                "output_resolution": data.get('output_resolution', '1080p'),
                "premiere_preset": data.get('premiere_preset', 'auto'),
                "custom_settings": data.get('custom_settings', {})
            },
            "output_folder_id": data.get('output_folder_id', 'processed_videos'),
            "priority": data.get('priority', 3),  # Higher priority for manual jobs
            "metadata": {
                "added_via": "web_ui_manual",
                "user_agent": request.headers.get('User-Agent', 'unknown')
            }
        }

        job_id = queue_manager.add_job(job_data)
        progress_tracker.add_log(
            f"Added manual job: {job_id} (Drive link: {drive_link})"
        )

        return jsonify({'success': True, 'job_id': job_id})
    except Exception as e:
        logger.error(f"Error adding manual job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/add_job', methods=['POST'])
def add_job():
    """Add a custom job to the queue"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # For manual jobs with drive_link
        if data.get('drive_link'):
            job_data = {
                "customer_id": data.get('customer_id', 'manual_user'),
                "tape_type": data.get('tape_type'),
                "drive_link": data.get('drive_link'),
                "is_manual": True,
                "processing_options": {
                    "topaz_enhancement": data.get('topaz_enhancement', False),
                    "output_resolution": data.get('output_resolution', '1080p'),
                    "premiere_preset": data.get('premiere_preset', 'auto'),
                    "custom_settings": data.get('custom_settings', {})
                },
                "output_folder_id": data.get('output_folder_id', 'processed_videos'),
                "priority": data.get('priority', 3),
                "metadata": {
                    "added_via": "web_ui_manual",
                    "user_agent": request.headers.get('User-Agent', 'unknown')
                }
            }
            job_id = queue_manager.add_job(job_data)
            progress_tracker.add_log(f"Added manual job: {job_id} (Drive link: {data['drive_link']})")
            return jsonify({'success': True, 'job_id': job_id})

        # For automated jobs with source_files
        if not data.get('source_files'):
            return jsonify({'success': False, 'error': 'Either drive_link or source_files is required'}), 400

        job_data = {
            "customer_id": data.get('customer_id', 'vniroshan@shadowpc.com'),
            "tape_type": data.get('tape_type', 'VHS'),
            "source_files": data['source_files'],
            "processing_options": {
                "topaz_enhancement": data.get('topaz_enhancement', False),
                "output_resolution": data.get('output_resolution', '1080p'),
                "premiere_preset": data.get('premiere_preset', 'auto'),
                "custom_settings": data.get('custom_settings', {})
            },
            "output_folder_id": data.get('output_folder_id', 'processed_videos'),
            "priority": data.get('priority', 5),
            "metadata": {
                "added_via": "web_ui",
                "user_agent": request.headers.get('User-Agent', 'unknown')
            }
        }

        job_id = queue_manager.add_job(job_data)
        progress_tracker.add_log(
            f"Added custom job: {job_id} ({job_data['tape_type']}) - "
            f"{len(job_data['source_files'])} file(s)"
        )

        return jsonify({'success': True, 'job_id': job_id})
    except Exception as e:
        logger.error(f"Error adding custom job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/start_processing', methods=['POST'])
def start_processing():
    """Start the processing engine"""
    global processing_thread, is_processing, processor_app

    if is_processing:
        return jsonify({'success': False, 'error': 'Processing already running'})

    try:
        # Collect current pending jobs (not mandatory to have any to start)
        jobs = getattr(queue_manager, 'get_all_jobs', lambda: [])()
        pending_jobs = [job for job in jobs if job.get('status') == 'pending']

        is_processing = True
        logger.info("Starting video processing engine...")
        config_path = os.path.join(project_root, "config", "app_settings.json")
        processor_app = VideoProcessorApp(config_path)
        logger.info("Processing engine initialized successfully")

        original_process_single_job = processor_app.process_single_job

        def enhanced_process_single_job(job):
            job_id = job['job_id']
            tape_type = job.get('tape_type')
            is_manual = job.get('is_manual', False)
            drive_link = job.get('drive_link')

            try:
                logger.info(f"Starting job {job_id}")
                progress_tracker.update_progress(
                    job_id, 0, "starting",
                    f"Starting job {job_id}",
                    "Initializing"
                )

                # Handle manual jobs (Google Drive)
                if is_manual and drive_link:
                    try:
                        # Auto-detect tape type if not specified
                        if not tape_type:
                            progress_tracker.update_progress(
                                job_id, 5, "detecting",
                                f"Detecting tape type for job {job_id}",
                                "Tape Detection"
                            )
                            filename = os.path.basename(drive_link)
                            tape_types = ['VHS', 'MiniDV', 'Hi8', 'Betamax', 'Digital8', 'Super8']
                            for t_type in tape_types:
                                if t_type.lower() in filename.lower():
                                    tape_type = t_type
                                    break
                            if not tape_type:
                                tape_type = 'VHS'  # Default to VHS if detection fails
                            
                            logger.info(f"Job {job_id}: Detected tape type as {tape_type}")
                            job['tape_type'] = tape_type
                            progress_tracker.update_progress(
                                job_id, 10, "detected",
                                f"Detected tape type: {tape_type}",
                                "Tape Detection"
                            )
                    except Exception as e:
                        error_msg = f"Failed to detect tape type: {str(e)}"
                        logger.error(error_msg)
                        progress_tracker.update_progress(
                            job_id, 0, "failed",
                            error_msg,
                            "Error"
                        )
                        raise
                    # Extract file ID and set as source so original processor downloads it
                    try:
                        file_id = gdrive._extract_file_id_from_url(drive_link) if hasattr(gdrive, '_extract_file_id_from_url') else None
                        if file_id:
                            job['source_files'] = [file_id]
                            # Set output folder to parent of original file if available
                            if hasattr(gdrive, 'get_file_parent'):
                                parent_id = gdrive.get_file_parent(file_id)
                                if parent_id:
                                    job['output_folder_id'] = parent_id
                        else:
                            raise ValueError("Could not extract file ID from Drive link")
                    except Exception as e:
                        error_msg = f"Failed to prepare manual job download: {e}"
                        progress_tracker.update_progress(
                            job_id, 0, "failed",
                            error_msg,
                            "Error"
                        )
                        queue_manager.update_job_status(job_id, "failed", error=error_msg)
                        return

                # Start the actual processing for all jobs (manual and automated)
                # Validate source files exist
                if not job.get('source_files'):
                    error_msg = "No source files available for processing"
                    progress_tracker.update_progress(
                        job_id, 0, "failed",
                        error_msg,
                        "Error"
                    )
                    job['error'] = error_msg
                    queue_manager.update_job_status(job_id, "failed", error=error_msg)
                    return

                try:
                    # Analysis phase
                    progress_tracker.update_progress(
                        job_id, 25, "analyzing",
                        "Analyzing video files...",
                        "Analysis"
                    )

                    # Processing with Premiere Pro
                    progress_tracker.update_progress(
                        job_id, 30, "processing",
                        f"Processing with Adobe Premiere Pro ({tape_type} preset)...",
                        "Premiere Pro"
                    )

                    # Call the original processing function
                    try:
                        result = original_process_single_job(job)
                    except Exception as e:
                        error_msg = f"Processing failed: {str(e)}"
                        progress_tracker.update_progress(
                            job_id, 0, "failed",
                            error_msg,
                            "Error"
                        )
                        job['error'] = error_msg
                        queue_manager.update_job_status(job_id, "failed", error=error_msg)
                        return

                    # Topaz enhancement progress placeholders (actual handled in original processing if enabled)
                    # (Let original process handle real enhancement & upload.)

                    # Mark job as completed
                    progress_tracker.update_progress(
                        job_id, 100, "completed",
                        f"Job {job_id} completed successfully!",
                        "Complete"
                    )
                    queue_manager.update_job_status(job_id, "completed")
                    return result

                except Exception as e:
                    error_msg = f"Job failed: {str(e)}"
                    progress_tracker.update_progress(
                        job_id, 0, "failed",
                        error_msg,
                        "Error"
                    )
                    job['error'] = error_msg
                    queue_manager.update_job_status(job_id, "failed", error=error_msg)
                    raise

                return result

            except Exception as e:
                progress_tracker.update_progress(
                    job_id, 0, "failed",
                    f"Job {job_id} failed: {str(e)}",
                    "Error"
                )
                raise

        # Attach enhanced processor to processor_app for possible direct calls
        processor_app.enhanced_process_single_job = enhanced_process_single_job

        def run_processing_loop():
            logger.info("Starting processing loop")
            while is_processing:
                try:
                    # Get pending jobs
                    pending_jobs = queue_manager.get_pending_jobs(limit=1)
                    if pending_jobs:
                        job = pending_jobs[0]
                        try:
                            # Update job status to processing
                            queue_manager.update_job_status(job['job_id'], "processing")
                            # Process the job
                            enhanced_process_single_job(job)
                        except Exception as e:
                            logger.error(f"Error processing job {job['job_id']}: {str(e)}")
                            queue_manager.update_job_status(job['job_id'], "failed", error=str(e))
                    else:
                        # No jobs to process, wait a bit
                        time.sleep(5)
                except Exception as e:
                    logger.error(f"Error in processing loop: {str(e)}")
                    time.sleep(5)

        progress_tracker.add_log("Starting processing engine...")
        processing_thread = threading.Thread(target=run_processing_loop, daemon=True)
        processing_thread.start()

        queue_stats = queue_manager.get_queue_stats()
        progress_tracker.add_log(
            f"Processing engine started. {queue_stats.get('pending', 0)} jobs pending."
        )

        start_msg = 'Processing started successfully'
        if not pending_jobs:
            start_msg += ' (waiting for jobs...)'
        return jsonify({'success': True, 'message': start_msg})
    except Exception as e:
        is_processing = False
        logger.error(f"Error starting processing: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stop_processing', methods=['POST'])
def stop_processing():
    """Stop the processing engine"""
    global is_processing, processor_app, processing_thread

    try:
        # Set flag to stop the processing loop
        is_processing = False
        
        # Wait for the processing thread to finish (with timeout)
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=5.0)
        
        # Stop the processor app if it exists
        if processor_app:
            processor_app.running = False

        progress_tracker.update_progress(
            None, 0, "stopped",
            "Processing engine stopped by user",
            "Stopped"
        )
        progress_tracker.add_log("Processing engine stopped")

        return jsonify({'success': True, 'message': 'Processing stopped successfully'})
    except Exception as e:
        logger.error(f"Error stopping processing: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete_job/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """Delete a job from the queue"""
    try:
        success = queue_manager.delete_job(job_id)
        if success:
            progress_tracker.add_log(f"Deleted job: {job_id}")
            return jsonify({'success': True, 'message': f'Job {job_id} deleted'})
        else:
            return jsonify({'success': False, 'error': 'Job not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# -------- SocketIO Events --------

@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.remote_addr}")
    emit('progress_update', progress_tracker.get_status())
    emit('log_update', {"message": "Connected to server", "level": "INFO", "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client disconnected: {request.remote_addr}")

# -------- Queue Processing --------

def process_queue():
    """Process all jobs in the queue"""
    global is_processing, processor_app

    try:
        while True:
            jobs = queue_manager.get_all_jobs()
            pending_jobs = [job for job in jobs if job['status'] == 'pending']
            
            if not pending_jobs:
                logger.info("No more pending jobs in queue")
                break

            for job in pending_jobs:
                try:
                    processor_app.enhanced_process_single_job(job)
                except Exception as e:
                    logger.error(f"Error processing job {job['job_id']}: {str(e)}")
                    continue

    except Exception as e:
        logger.error(f"Queue processing error: {str(e)}")
    finally:
        is_processing = False
        logger.info("Queue processing completed")

# -------- Main Entrypoint --------

if __name__ == '__main__':
    print("="*50)
    print("🚀 Shadow PC Video Processing Web UI")
    print("📱 Access dashboard at: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop")
    print("="*50)
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)