"""
Custom logging utilities for Video Processing Automation
Enhanced logging with file rotation and structured output
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
import json

def setup_logging(log_level="INFO", log_file="video_processor.log", 
                 max_bytes=10*1024*1024, backup_count=5):
    """Setup comprehensive logging configuration"""
    
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Full path for log file
    log_path = log_dir / log_file
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # Custom formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler
    error_log_path = log_dir / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_path, maxBytes=5*1024*1024, backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # JSON structured log handler
    json_log_path = log_dir / "structured.jsonl"
    json_handler = JSONLogHandler(json_log_path)
    json_handler.setLevel(logging.INFO)
    root_logger.addHandler(json_handler)
    
    logging.info(f"Logging initialized - Level: {log_level}, File: {log_path}")
    return root_logger

class JSONLogHandler(logging.Handler):
    """Custom handler for JSON structured logging"""
    
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
    
    def emit(self, record):
        try:
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            
            # Add exception info if present
            if record.exc_info:
                log_entry['exception'] = self.format(record)
            
            # Write to file
            with open(self.filename, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception:
            self.handleError(record)