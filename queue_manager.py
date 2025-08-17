"""
Queue Manager for Video Processing Jobs
Handles job creation, status tracking, and queue operations
"""

import json
import os
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import logging
from pathlib import Path

class QueueManager:
    """Manages the video processing job queue using JSON file storage"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.queue_file = self.config.get("queue_file", "queue.json")
        self.backup_file = self.config.get("backup_file", "queue_backup.json")
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        
        # Ensure queue file exists
        self._initialize_queue_file()
        
        self.logger.info(f"Queue Manager initialized with file: {self.queue_file}")
    
    def _initialize_queue_file(self):
        """Initialize queue file if it doesn't exist"""
        if not os.path.exists(self.queue_file):
            initial_data = {
                "jobs": [],
                "metadata": {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "version": "1.0"
                }
            }
            self._save_queue(initial_data)
            self.logger.info(f"Created new queue file: {self.queue_file}")
    
    def _load_queue(self) -> Dict:
        """Load job queue from file with error handling"""
        with self.lock:
            try:
                if os.path.exists(self.queue_file):
                    with open(self.queue_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    # Validate structure
                    if not isinstance(data, dict) or "jobs" not in data:
                        raise ValueError("Invalid queue file structure")
                    
                    # Validate and fix jobs
                    for job in data["jobs"]:
                        # Ensure each job has required fields with default values
                        if "job_id" not in job:
                            job["job_id"] = str(uuid.uuid4())
                        if "status" not in job:
                            job["status"] = "pending"
                        if "created_at" not in job:
                            job["created_at"] = datetime.now(timezone.utc).isoformat()
                        if "updated_at" not in job:
                            job["updated_at"] = job.get("created_at", datetime.now(timezone.utc).isoformat())
                        if "progress" not in job:
                            job["progress"] = 0
                        if "customer_id" not in job:
                            job["customer_id"] = "unknown"
                        if "source_files" not in job:
                            job["source_files"] = []
                        if "tape_type" not in job:
                            job["tape_type"] = "unknown"
                        if "processing_options" not in job:
                            job["processing_options"] = {}
                        if "metadata" not in job:
                            job["metadata"] = {}
                        if "is_manual" not in job:
                            job["is_manual"] = False
                        if "error" not in job:
                            job["error"] = None
                    
                    # Save the fixed data back to the file
                    self._save_queue(data)
                    
                    return data
                    
            except (json.JSONDecodeError, ValueError, FileNotFoundError) as e:
                self.logger.error(f"Error loading queue file: {e}")
                
                # Try to load backup
                if os.path.exists(self.backup_file):
                    try:
                        self.logger.info("Attempting to load backup queue file")
                        with open(self.backup_file, 'r', encoding='utf-8') as f:
                            return json.load(f)
                    except Exception as backup_error:
                        self.logger.error(f"Backup file also corrupted: {backup_error}")
                
                # Return empty queue if all else fails
                self.logger.warning("Creating new empty queue")
                return {"jobs": [], "metadata": {"created_at": datetime.now(timezone.utc).isoformat()}}
    
    def _save_queue(self, data: Dict):
        """Save job queue to file with backup"""
        with self.lock:
            try:
                # Create backup of current file
                if os.path.exists(self.queue_file):
                    import shutil
                    shutil.copy2(self.queue_file, self.backup_file)
                
                # Save new data
                data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
                
                # Write to temporary file first, then rename (atomic operation)
                temp_file = f"{self.queue_file}.tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str, ensure_ascii=False)
                
                # Atomic rename
                if os.name == 'nt':  # Windows
                    if os.path.exists(self.queue_file):
                        os.remove(self.queue_file)
                os.rename(temp_file, self.queue_file)
                
            except Exception as e:
                self.logger.error(f"Failed to save queue: {e}")
                # Clean up temp file if it exists
                temp_file = f"{self.queue_file}.tmp"
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                raise
    
    def add_job(self, job_data: Dict) -> str:
        """Add a new job to the queue"""
        job_id = str(uuid.uuid4())
        
        # For manual jobs with drive_link, we don't require source_files
        if not job_data.get('is_manual') and 'source_files' not in job_data:
            raise ValueError("Missing required field: source_files")
        
        # Create base job structure with all required fields
        job = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "customer_id": job_data.get('customer_id', 'unknown'),
            "tape_type": job_data.get('tape_type', 'auto'),
            "source_files": job_data.get('source_files', []),
            "drive_link": job_data.get('drive_link'),
            "is_manual": job_data.get('is_manual', False),
            "processing_options": job_data.get('processing_options', {}),
            "output_folder_id": job_data.get('output_folder_id'),
            "priority": job_data.get('priority', 5),  # 1-10, lower is higher priority
            "metadata": job_data.get('metadata', {}),
            "error": None
        }
        
        queue_data = self._load_queue()
        queue_data["jobs"].append(job)
        self._save_queue(queue_data)
        
        self.logger.info(f"Added new job to queue: {job_id}")
        return job_id
    
    def get_pending_jobs(self, limit: int = 10) -> List[Dict]:
        """Get pending jobs from the queue, sorted by priority and creation time"""
        queue_data = self._load_queue()
        
        pending_jobs = [
            job for job in queue_data["jobs"] 
            if job["status"] == "pending"
        ]
        
        # Sort by priority (lower number = higher priority), then by creation time
        pending_jobs.sort(key=lambda x: (x.get("priority", 5), x["created_at"]))
        
        return pending_jobs[:limit]

    def get_all_jobs(self) -> List[Dict]:
        """Return a shallow copy list of all jobs in the queue.
        Added to support web UI start processing route which expects this helper.
        """
        queue_data = self._load_queue()
        # Return copies to avoid accidental external mutation
        return [job.copy() for job in queue_data.get("jobs", [])]
    
    def get_jobs_by_status(self, status: str, limit: int = None) -> List[Dict]:
        """Get jobs by status"""
        queue_data = self._load_queue()
        
        # Filter jobs by status and ensure all required fields are present
        jobs = []
        for job in queue_data["jobs"]:
            if job.get("status") == status:
                # Ensure all required fields are present
                validated_job = {
                    "job_id": job.get("job_id", str(uuid.uuid4())),
                    "status": job.get("status", "unknown"),
                    "progress": job.get("progress", 0),
                    "created_at": job.get("created_at", datetime.now(timezone.utc).isoformat()),
                    "updated_at": job.get("updated_at", job.get("created_at")),
                    "customer_id": job.get("customer_id", "unknown"),
                    "tape_type": job.get("tape_type", "unknown"),
                    "source_files": job.get("source_files", []),
                    "drive_link": job.get("drive_link"),
                    "is_manual": job.get("is_manual", False),
                    "processing_options": job.get("processing_options", {}),
                    "output_folder_id": job.get("output_folder_id"),
                    "priority": job.get("priority", 5),
                    "metadata": job.get("metadata", {}),
                    "error": job.get("error")
                }
                jobs.append(validated_job)
        
        # Sort by update time (most recent first)
        jobs.sort(key=lambda x: x.get("updated_at", x["created_at"]), reverse=True)
        
        return jobs[:limit] if limit else jobs
    
    def update_job_status(self, job_id: str, status: str, **kwargs):
        """Update job status and additional fields"""
        queue_data = self._load_queue()
        
        job_found = False
        for job in queue_data["jobs"]:
            if job["job_id"] == job_id:
                job["status"] = status
                job["updated_at"] = datetime.now(timezone.utc).isoformat()
                
                # Add timestamp for status changes
                if status == "processing" and "started_at" not in job:
                    job["started_at"] = datetime.now(timezone.utc).isoformat()
                elif status == "completed" and "completed_at" not in job:
                    job["completed_at"] = datetime.now(timezone.utc).isoformat()
                elif status == "failed" and "failed_at" not in job:
                    job["failed_at"] = datetime.now(timezone.utc).isoformat()
                
                # Add any additional fields
                for key, value in kwargs.items():
                    if key.endswith('_at') and isinstance(value, (int, float)):
                        # Convert timestamp to ISO format
                        job[key] = datetime.fromtimestamp(value, timezone.utc).isoformat()
                    else:
                        job[key] = value
                
                job_found = True
                break
        
        if job_found:
            self._save_queue(queue_data)
            self.logger.info(f"Updated job {job_id} status to {status}")
        else:
            self.logger.warning(f"Job {job_id} not found in queue")
            raise ValueError(f"Job {job_id} not found")
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get a specific job by ID"""
        queue_data = self._load_queue()
        
        for job in queue_data["jobs"]:
            if job["job_id"] == job_id:
                return job.copy()  # Return a copy to prevent accidental modification
        
        return None
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job from the queue"""
        queue_data = self._load_queue()
        
        initial_count = len(queue_data["jobs"])
        queue_data["jobs"] = [
            job for job in queue_data["jobs"] 
            if job["job_id"] != job_id
        ]
        
        if len(queue_data["jobs"]) < initial_count:
            self._save_queue(queue_data)
            self.logger.info(f"Deleted job: {job_id}")
            return True
        else:
            self.logger.warning(f"Job {job_id} not found for deletion")
            return False
    
    def get_queue_stats(self) -> Dict:
        """Get queue statistics"""
        queue_data = self._load_queue()
        jobs = queue_data.get("jobs", [])
        
        stats = {
            "total_jobs": len(jobs),
            "pending": len([j for j in jobs if j.get("status") == "pending"]),
            "processing": len([j for j in jobs if j.get("status") == "processing"]),
            "completed": len([j for j in jobs if j.get("status") == "completed"]),
            "failed": len([j for j in jobs if j.get("status") == "failed"])
        }
        
        # Calculate processing times for completed jobs
        completed_jobs = [j for j in jobs if j["status"] == "completed"]
        if completed_jobs:
            processing_times = []
            for job in completed_jobs:
                if "started_at" in job and "completed_at" in job:
                    try:
                        start = datetime.fromisoformat(job["started_at"].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(job["completed_at"].replace('Z', '+00:00'))
                        processing_times.append((end - start).total_seconds())
                    except:
                        continue
            
            if processing_times:
                stats["avg_processing_time"] = sum(processing_times) / len(processing_times)
                stats["min_processing_time"] = min(processing_times)
                stats["max_processing_time"] = max(processing_times)
        
        return stats
    
    def cleanup_old_jobs(self, days: int = 30):
        """Remove jobs older than specified days"""
        if days <= 0:
            return
            
        queue_data = self._load_queue()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        original_count = len(queue_data["jobs"])
        queue_data["jobs"] = [
            job for job in queue_data["jobs"]
            if datetime.fromisoformat(job["created_at"].replace('Z', '+00:00')) > cutoff_date
        ]
        
        removed_count = original_count - len(queue_data["jobs"])
        if removed_count > 0:
            self._save_queue(queue_data)
            self.logger.info(f"Cleaned up {removed_count} old jobs (older than {days} days)")
    
    def add_test_job(self, tape_type: str = "VHS") -> str:
        """Add a test job for development purposes"""
        test_job = {
            "customer_id": "vniroshan@test.com",
            "tape_type": tape_type,
            "source_files": [
                f"test_{tape_type.lower()}_video.mp4"
            ],
            "processing_options": {
                "topaz_enhancement": False,
                "output_resolution": "1080p",
                "premiere_preset": f"{tape_type}_Cleanup"
            },
            "output_folder_id": "test_output_folder",
            "metadata": {
                "test_job": True,
                "created_by": "test_runner"
            }
        }
        
        return self.add_job(test_job)