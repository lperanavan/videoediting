"""
Tape Type Detection Module
Advanced video analysis for determining original tape format
"""

import os
import re
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from datetime import datetime

class TapeDetector:
    """Advanced tape type detection using multiple analysis methods"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Enhanced tape signatures with more characteristics
        self.tape_signatures = {
            "VHS": {
                "resolutions": ["720x480", "720x576", "352x240", "352x288"],
                "frame_rates": ["29.97", "25.00", "23.976"],
                "keywords": ["vhs", "vcr", "composite", "analog"],
                "interlaced": True,
                "typical_bitrate_range": (1000, 8000),
                "aspect_ratios": ["4:3", "1.33"],
                "audio_channels": [1, 2],
                "quality_indicators": {
                    "noise_level": "high",
                    "color_bleeding": True,
                    "dropout_likelihood": "high"
                },
                "year_range": (1976, 2008)
            },
            "MiniDV": {
                "resolutions": ["720x480", "720x576"],
                "frame_rates": ["29.97", "25.00"],
                "keywords": ["dv", "minidv", "digital", "ieee1394"],
                "interlaced": True,
                "typical_bitrate_range": (25000, 25000),
                "aspect_ratios": ["4:3", "16:9"],
                "audio_channels": [2],
                "quality_indicators": {
                    "noise_level": "low",
                    "color_bleeding": False,
                    "dropout_likelihood": "low"
                },
                "year_range": (1995, 2010)
            },
            "Hi8": {
                "resolutions": ["720x480", "720x576", "352x240"],
                "frame_rates": ["29.97", "25.00"],
                "keywords": ["hi8", "8mm", "analog", "sony"],
                "interlaced": True,
                "typical_bitrate_range": (2000, 10000),
                "aspect_ratios": ["4:3"],
                "audio_channels": [1, 2],
                "quality_indicators": {
                    "noise_level": "medium",
                    "color_bleeding": True,
                    "dropout_likelihood": "medium"
                },
                "year_range": (1989, 2007)
            },
            "Betamax": {
                "resolutions": ["720x480", "720x576"],
                "frame_rates": ["29.97", "25.00"],
                "keywords": ["beta", "betamax", "sony"],
                "interlaced": True,
                "typical_bitrate_range": (3000, 12000),
                "aspect_ratios": ["4:3"],
                "audio_channels": [1, 2],
                "quality_indicators": {
                    "noise_level": "medium",
                    "color_bleeding": True,
                    "dropout_likelihood": "medium"
                },
                "year_range": (1975, 2002)
            },
            "Digital8": {
                "resolutions": ["720x480", "720x576"],
                "frame_rates": ["29.97", "25.00"],
                "keywords": ["digital8", "d8", "sony"],
                "interlaced": True,
                "typical_bitrate_range": (25000, 25000),
                "aspect_ratios": ["4:3", "16:9"],
                "audio_channels": [2],
                "quality_indicators": {
                    "noise_level": "low",
                    "color_bleeding": False,
                    "dropout_likelihood": "low"
                },
                "year_range": (1999, 2007)
            },
            "Super8": {
                "resolutions": ["1440x1080", "1920x1080", "720x480"],
                "frame_rates": ["18.00", "24.00", "29.97"],
                "keywords": ["super8", "8mm", "film", "kodak"],
                "interlaced": False,
                "typical_bitrate_range": (5000, 20000),
                "aspect_ratios": ["4:3", "16:9"],
                "audio_channels": [0, 1, 2],
                "quality_indicators": {
                    "noise_level": "medium",
                    "grain": True,
                    "flicker": True
                },
                "year_range": (1965, 1990)
            }
        }
        
        # Common filename patterns
        self.filename_patterns = {
            r'vhs|vcr': 'VHS',
            r'minidv|mini.?dv|dv': 'MiniDV',
            r'hi.?8|8mm(?!.*digital)': 'Hi8',
            r'beta(?:max)?': 'Betamax',
            r'digital.?8|d8': 'Digital8',
            r'super.?8|s8': 'Super8'
        }
    
    def detect_from_files(self, file_paths: List[str]) -> str:
        """Detect tape type from a list of video files using multiple methods"""
        if not file_paths:
            self.logger.warning("No files provided for tape detection")
            return "Unknown"
        
        # Analyze all files and aggregate results
        detection_results = []
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                self.logger.warning(f"File not found: {file_path}")
                continue
                
            result = self._analyze_single_file(file_path)
            if result:
                detection_results.append(result)
        
        if not detection_results:
            self.logger.warning("No valid files could be analyzed")
            return "VHS"  # Default fallback
        
        # Aggregate results and determine best match
        final_result = self._aggregate_detection_results(detection_results)
        
        self.logger.info(f"Final tape type detection: {final_result['tape_type']} "
                        f"(confidence: {final_result['confidence']:.2f})")
        
        return final_result['tape_type']
    
    def _analyze_single_file(self, file_path: str) -> Optional[Dict]:
        """Analyze a single file for tape type indicators"""
        self.logger.debug(f"Analyzing file: {file_path}")
        
        try:
            # Get technical metadata
            metadata = self._get_video_metadata(file_path)
            if not metadata:
                return None
            
            # Perform different types of analysis
            filename_analysis = self._analyze_filename(file_path)
            metadata_analysis = self._analyze_metadata(metadata)
            quality_analysis = self._analyze_quality_indicators(file_path, metadata)
            
            # Combine all analyses
            result = {
                'file_path': file_path,
                'filename_hint': filename_analysis,
                'metadata_scores': metadata_analysis,
                'quality_indicators': quality_analysis,
                'final_metadata': metadata
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error analyzing file {file_path}: {e}")
            return None
    
    def _get_video_metadata(self, file_path: str) -> Optional[Dict]:
        """Extract comprehensive video metadata using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                '-show_chapters',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                self.logger.warning(f"ffprobe failed for {file_path}: {result.stderr}")
                return None
                
            data = json.loads(result.stdout)
            
            # Extract video stream info
            video_stream = None
            audio_streams = []
            
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video' and not video_stream:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio':
                    audio_streams.append(stream)
            
            if not video_stream:
                return None
            
            # Extract file creation/modification times
            format_info = data.get('format', {})
            file_stats = os.stat(file_path)
            
            return {
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'frame_rate': video_stream.get('r_frame_rate', ''),
                'avg_frame_rate': video_stream.get('avg_frame_rate', ''),
                'bit_rate': int(video_stream.get('bit_rate', 0)) // 1000 if video_stream.get('bit_rate') else 0,
                'codec': video_stream.get('codec_name', ''),
                'pix_fmt': video_stream.get('pix_fmt', ''),
                'field_order': video_stream.get('field_order', 'progressive'),
                'duration': float(format_info.get('duration', 0)),
                'file_size': int(format_info.get('size', 0)),
                'audio_channels': len(audio_streams),
                'audio_codecs': [stream.get('codec_name') for stream in audio_streams],
                'creation_time': format_info.get('tags', {}).get('creation_time'),
                'file_modified': datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                'container_format': format_info.get('format_name', ''),
                'chapters': len(data.get('chapters', []))
            }
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, 
                json.JSONDecodeError, FileNotFoundError, OSError) as e:
            self.logger.warning(f"Failed to get metadata for {file_path}: {e}")
            return None
    
    def _analyze_filename(self, file_path: str) -> Optional[str]:
        """Analyze filename for tape type hints"""
        filename = os.path.basename(file_path).lower()
        
        # Check explicit patterns
        for pattern, tape_type in self.filename_patterns.items():
            if re.search(pattern, filename):
                self.logger.debug(f"Filename pattern match: {pattern} -> {tape_type}")
                return tape_type
        
        return None
    
    def _analyze_metadata(self, metadata: Dict) -> Dict[str, float]:
        """Analyze technical metadata against tape signatures"""
        scores = {}
        
        for tape_type, signature in self.tape_signatures.items():
            score = 0.0
            max_score = 0.0
            
            # Resolution matching
            resolution = f"{metadata.get('width', 0)}x{metadata.get('height', 0)}"
            max_score += 3.0
            if resolution in signature['resolutions']:
                score += 3.0
            elif any(abs(metadata.get('width', 0) - int(res.split('x')[0])) < 50 and
                    abs(metadata.get('height', 0) - int(res.split('x')[1])) < 50
                    for res in signature['resolutions']):
                score += 1.5  # Close match
            
            # Frame rate matching
            max_score += 2.0
            frame_rate = self._parse_frame_rate(metadata.get('frame_rate', ''))
            if frame_rate:
                if any(abs(frame_rate - float(sig_fps)) < 0.5 
                      for sig_fps in signature['frame_rates']):
                    score += 2.0
                elif any(abs(frame_rate - float(sig_fps)) < 2.0 
                        for sig_fps in signature['frame_rates']):
                    score += 1.0
            
            # Interlacing
            max_score += 2.0
            is_interlaced = metadata.get('field_order', 'progressive') != 'progressive'
            if is_interlaced == signature.get('interlaced', False):
                score += 2.0
            
            # Bitrate range
            max_score += 1.5
            bitrate = metadata.get('bit_rate', 0)
            if bitrate > 0:
                min_br, max_br = signature['typical_bitrate_range']
                if min_br <= bitrate <= max_br:
                    score += 1.5
                elif bitrate < min_br * 2 and bitrate > min_br * 0.5:
                    score += 0.75  # Reasonable range
            
            # Audio channels
            max_score += 1.0
            audio_channels = metadata.get('audio_channels', 0)
            if audio_channels in signature.get('audio_channels', []):
                score += 1.0
            
            # Normalize score
            scores[tape_type] = (score / max_score) if max_score > 0 else 0.0
        
        return scores
    
    def _analyze_quality_indicators(self, file_path: str, metadata: Dict) -> Dict:
        """Analyze video quality indicators (simplified version)"""
        # This is a simplified implementation
        # In a full implementation, you might analyze actual video frames
        
        indicators = {
            'estimated_noise_level': 'unknown',
            'likely_analog_source': False,
            'compression_artifacts': 'unknown'
        }
        
        # Simple heuristics based on metadata
        bitrate = metadata.get('bit_rate', 0)
        resolution = metadata.get('width', 0) * metadata.get('height', 0)
        
        if bitrate > 0 and resolution > 0:
            bitrate_per_pixel = bitrate / resolution * 1000  # bits per pixel per second
            
            if bitrate_per_pixel < 0.1:
                indicators['estimated_noise_level'] = 'high'
                indicators['likely_analog_source'] = True
            elif bitrate_per_pixel < 0.2:
                indicators['estimated_noise_level'] = 'medium'
            else:
                indicators['estimated_noise_level'] = 'low'
        
        # Check for interlacing (common in older formats)
        if metadata.get('field_order', 'progressive') != 'progressive':
            indicators['likely_analog_source'] = True
        
        return indicators
    
    def _parse_frame_rate(self, frame_rate_str: str) -> Optional[float]:
        """Parse frame rate string to float"""
        if not frame_rate_str:
            return None
            
        try:
            if '/' in frame_rate_str:
                num, den = map(float, frame_rate_str.split('/'))
                return round(num / den, 3) if den != 0 else None
            else:
                return float(frame_rate_str)
        except (ValueError, ZeroDivisionError):
            return None
    
    def _aggregate_detection_results(self, results: List[Dict]) -> Dict:
        """Aggregate detection results from multiple files"""
        # Collect all scores
        all_scores = {}
        filename_votes = {}
        
        for result in results:
            # Metadata scores
            for tape_type, score in result['metadata_scores'].items():
                if tape_type not in all_scores:
                    all_scores[tape_type] = []
                all_scores[tape_type].append(score)
            
            # Filename hints
            filename_hint = result.get('filename_hint')
            if filename_hint:
                filename_votes[filename_hint] = filename_votes.get(filename_hint, 0) + 1
        
        # Calculate average scores
        final_scores = {}
        for tape_type, scores in all_scores.items():
            final_scores[tape_type] = sum(scores) / len(scores)
        
        # Boost scores based on filename votes
        total_files = len(results)
        for tape_type, votes in filename_votes.items():
            if tape_type in final_scores:
                filename_confidence = votes / total_files
                final_scores[tape_type] += filename_confidence * 0.5  # Boost by up to 0.5
        
        # Find best match
        if not final_scores:
            return {'tape_type': 'VHS', 'confidence': 0.0, 'scores': {}}
        
        best_tape_type = max(final_scores.items(), key=lambda x: x[1])
        
        return {
            'tape_type': best_tape_type[0],
            'confidence': best_tape_type[1],
            'scores': final_scores,
            'filename_votes': filename_votes
        }
    
    def get_processing_preset(self, tape_type: str) -> str:
        """Get the appropriate processing preset for the detected tape type"""
        preset_mapping = {
            "VHS": "VHS_Cleanup",
            "MiniDV": "MiniDV_Enhance", 
            "Hi8": "Hi8_Restore",
            "Betamax": "Betamax_Enhance",
            "Digital8": "Digital8_Process",
            "Super8": "Super8_FilmLook"
        }
        
        return preset_mapping.get(tape_type, "VHS_Cleanup")  # Default to VHS
    
    def get_recommended_settings(self, tape_type: str) -> Dict:
        """Get recommended processing settings for the tape type"""
        if tape_type not in self.tape_signatures:
            tape_type = "VHS"  # Default
            
        signature = self.tape_signatures[tape_type]
        
        return {
            "deinterlace": signature.get("interlaced", True),
            "noise_reduction": signature["quality_indicators"].get("noise_level", "medium"),
            "color_correction": signature["quality_indicators"].get("color_bleeding", True),
            "stabilization": tape_type in ["VHS", "Hi8", "Betamax"],
            "sharpening": "light" if tape_type in ["VHS", "Betamax"] else "none",
            "audio_enhancement": signature.get("audio_channels", [2])[0] == 1
        }