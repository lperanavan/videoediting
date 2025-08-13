"""
File utilities for Video Processing Automation
Common file operations and helpers
"""

import os
import shutil
import hashlib
import mimetypes
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import logging
import time

logger = logging.getLogger(__name__)

def ensure_directory(path: str) -> bool:
    """Ensure directory exists, create if necessary"""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False

def safe_filename(filename: str, max_length: int = 255) -> str:
    """Create a safe filename by removing invalid characters"""
    import re
    
    # Replace invalid characters
    safe_chars = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove leading/trailing dots and spaces
    safe_chars = safe_chars.strip('. ')
    
    # Limit length
    if len(safe_chars) > max_length:
        name, ext = os.path.splitext(safe_chars)
        safe_chars = name[:max_length-len(ext)] + ext
    
    return safe_chars or "unnamed_file"

def get_file_hash(filepath: str, algorithm: str = "md5") -> Optional[str]:
    """Calculate file hash"""
    try:
        hash_func = getattr(hashlib, algorithm)()
        
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate hash for {filepath}: {e}")
        return None

def get_file_info(filepath: str) -> Dict:
    """Get comprehensive file information"""
    try:
        stat = os.stat(filepath)
        mime_type, encoding = mimetypes.guess_type(filepath)
        
        return {
            "path": filepath,
            "name": os.path.basename(filepath),
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "mime_type": mime_type,
            "encoding": encoding,
            "extension": Path(filepath).suffix.lower(),
            "is_video": mime_type and mime_type.startswith('video/') if mime_type else False
        }
    except Exception as e:
        logger.error(f"Failed to get file info for {filepath}: {e}")
        return {}

def cleanup_old_files(directory: str, days: int = 7, pattern: str = "*") -> int:
    """Clean up old files in directory"""
    try:
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        cleaned_count = 0
        
        for file_path in Path(directory).glob(pattern):
            if file_path.is_file():
                if file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"Cleaned up old file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete {file_path}: {e}")
        
        logger.info(f"Cleaned up {cleaned_count} old files from {directory}")
        return cleaned_count
        
    except Exception as e:
        logger.error(f"Error cleaning up directory {directory}: {e}")
        return 0

def copy_with_progress(src: str, dst: str, callback=None) -> bool:
    """Copy file with progress callback"""
    try:
        src_size = os.path.getsize(src)
        copied = 0
        
        with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
            while True:
                chunk = fsrc.read(64 * 1024)  # 64KB chunks
                if not chunk:
                    break
                    
                fdst.write(chunk)
                copied += len(chunk)
                
                if callback:
                    progress = (copied / src_size) * 100
                    callback(progress)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to copy {src} to {dst}: {e}")
        return False

def get_video_files(directory: str, recursive: bool = True) -> List[str]:
    """Get all video files in directory"""
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}
    video_files = []
    
    try:
        path = Path(directory)
        pattern = "**/*" if recursive else "*"
        
        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                video_files.append(str(file_path))
        
        return sorted(video_files)
        
    except Exception as e:
        logger.error(f"Error scanning directory {directory}: {e}")
        return []

def get_disk_usage(path: str) -> Dict:
    """Get disk usage information"""
    try:
        if os.name == 'nt':  # Windows
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(path),
                ctypes.pointer(free_bytes),
                ctypes.pointer(total_bytes),
                None
            )
            
            total = total_bytes.value
            free = free_bytes.value
            used = total - free
            
        else:  # Unix-like
            statvfs = os.statvfs(path)
            total = statvfs.f_frsize * statvfs.f_blocks
            free = statvfs.f_frsize * statvfs.f_available
            used = total - free
        
        return {
            "total": total,
            "used": used,
            "free": free,
            "percent_used": (used / total) * 100 if total > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Failed to get disk usage for {path}: {e}")
        return {"total": 0, "used": 0, "free": 0, "percent_used": 0}