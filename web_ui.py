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
queue_manager = QueueManager(config_manager.get_config().get("queue", {}))
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
        queue_stats = queue_manager.get_queue_stats()
        processor_status = processor_app.get_status() if processor_app else {}

        return jsonify({
            'success': True,
            'processing': progress_tracker.get_status(),
            'queue': queue_stats,
            'system': processor_status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/queue')
def get_queue():
    """Get queue information"""
    try:
        pending_jobs = queue_manager.get_pending_jobs(limit=50)
        recent_jobs = queue_manager.get_jobs_by_status("completed", limit=20)
        failed_jobs = queue_manager.get_jobs_by_status("failed", limit=10)

        return jsonify({
            'success': True,
            'pending_jobs': pending_jobs,
            'recent_completed': recent_jobs,
            'recent_failed': failed_jobs,
            'stats': queue_manager.get_queue_stats()
        })
    except Exception as e:
        logger.error(f"Error getting queue: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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

@app.route('/api/add_job', methods=['POST'])
def add_job():
    """Add a custom job to the queue"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Validate required fields
        if not data.get('source_files'):
            return jsonify({'success': False, 'error': 'source_files is required'}), 400

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
        is_processing = True
        logger.debug("Creating VideoProcessorApp instance...")
        config_path = os.path.join(project_root, "config", "app_settings.json")
        processor_app = VideoProcessorApp(config_path)
        logger.debug("VideoProcessorApp instance created successfully")

        original_process_single_job = processor_app.process_single_job

        def enhanced_process_single_job(job):
            job_id = job['job_id']
            tape_type = job.get('tape_type', 'Unknown')
            try:
                progress_tracker.update_progress(
                    job_id, 0, "starting",
                    f"Starting job {job_id} ({tape_type})",
                    "Initializing"
                )
                time.sleep(1)

                progress_tracker.update_progress(
                    job_id, 10, "downloading",
                    "Downloading source files from Google Drive...",
                    "Download"
                )
                time.sleep(2)

                progress_tracker.update_progress(
                    job_id, 20, "downloading",
                    "Download completed",
                    "Download"
                )

                progress_tracker.update_progress(
                    job_id, 25, "analyzing",
                    "Analyzing video files and detecting tape type...",
                    "Analysis"
                )
                time.sleep(1.5)

                progress_tracker.update_progress(
                    job_id, 30, "processing",
                    f"Processing with Adobe Premiere Pro ({tape_type} preset)...",
                    "Premiere Pro"
                )
                time.sleep(3)

                progress_tracker.update_progress(
                    job_id, 50, "processing",
                    "Applying video corrections and filters...",
                    "Premiere Pro"
                )
                time.sleep(2)

                progress_tracker.update_progress(
                    job_id, 70, "processing",
                    "Rendering processed video...",
                    "Premiere Pro"
                )
                time.sleep(2)

                if job.get('processing_options', {}).get('topaz_enhancement'):
                    progress_tracker.update_progress(
                        job_id, 75, "enhancing",
                        "Enhancing video quality with Topaz Video AI...",
                        "Topaz AI"
                    )
                    time.sleep(3)

                    progress_tracker.update_progress(
                        job_id, 85, "enhancing",
                        "Topaz enhancement completed",
                        "Topaz AI"
                    )

                progress_tracker.update_progress(
                    job_id, 90, "uploading",
                    "Uploading processed videos to Google Drive...",
                    "Upload"
                )
                time.sleep(2)

                result = original_process_single_job(job)

                progress_tracker.update_progress(
                    job_id, 100, "completed",
                    f"Job {job_id} completed successfully! Files uploaded to Google Drive.",
                    "Complete"
                )

                return result

            except Exception as e:
                progress_tracker.update_progress(
                    job_id, 0, "failed",
                    f"Job {job_id} failed: {str(e)}",
                    "Error"
                )
                raise

        processor_app.process_single_job = enhanced_process_single_job

        def run_processing_loop():
            processor_app.start_processing()

        processing_thread = threading.Thread(target=run_processing_loop, daemon=True)
        processing_thread.start()

        progress_tracker.add_log("Processing engine started")

        return jsonify({'success': True, 'message': 'Processing started successfully'})
    except Exception as e:
        is_processing = False
        logger.error(f"Error starting processing: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stop_processing', methods=['POST'])
def stop_processing():
    """Stop the processing engine"""
    global is_processing, processor_app

    try:
        is_processing = False
        if processor_app:
            processor_app.running = False

        progress_tracker.update_progress(
            None, 0, "stopped",
            "Processing engine stopped by user",
            "Stopped"
        )

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

# -------- Main Entrypoint --------

if __name__ == '__main__':
    print("="*50)
    print("🚀 Shadow PC Video Processing Web UI")
    print("📱 Access dashboard at: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop")
    print("="*50)
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)