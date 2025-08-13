"""
Shadow PC Specific Optimizations
Handles GPU acceleration detection, network-aware file handling, and Shadow PC hardware optimizations
"""

import os
import sys
import logging
import subprocess
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json

class ShadowPCOptimizer:
    """Handles Shadow PC specific optimizations and hardware detection"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.is_windows = sys.platform == "win32"
        self.shadow_pc_detected = False
        self.gpu_info = {}
        self.network_info = {}
        
        # Initialize optimizations
        self._detect_shadow_pc_environment()
        self._detect_gpu_capabilities()
        self._analyze_network_conditions()

    def _detect_shadow_pc_environment(self) -> bool:
        """Detect if running on Shadow PC platform"""
        try:
            if not self.is_windows:
                return False
            
            self.logger.info("Detecting Shadow PC environment...")
            
            # Check multiple indicators for Shadow PC
            indicators = []
            
            # 1. Check system manufacturer/model
            try:
                result = subprocess.run(['wmic', 'computersystem', 'get', 'manufacturer,model'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    system_info = result.stdout.lower()
                    if 'shadow' in system_info or 'blade' in system_info:
                        indicators.append("system_info")
            except Exception as e:
                self.logger.debug(f"Could not check system info: {e}")
            
            # 2. Check GPU virtualization indicators
            try:
                result = subprocess.run(['wmic', 'path', 'win32_VideoController', 'get', 'name'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    gpu_info = result.stdout.lower()
                    virtualization_indicators = ['parsec', 'citrix', 'vmware', 'hyper-v', 'virtual']
                    for indicator in virtualization_indicators:
                        if indicator in gpu_info:
                            indicators.append("gpu_virtualization")
                            break
            except Exception as e:
                self.logger.debug(f"Could not check GPU info: {e}")
            
            # 3. Check network adapter for virtual adapters
            try:
                result = subprocess.run(['wmic', 'path', 'win32_NetworkAdapter', 'get', 'name'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    network_info = result.stdout.lower()
                    virtual_adapters = ['parsec', 'shadow', 'virtual']
                    for adapter in virtual_adapters:
                        if adapter in network_info:
                            indicators.append("virtual_network")
                            break
            except Exception as e:
                self.logger.debug(f"Could not check network adapters: {e}")
            
            # 4. Check for Shadow-specific processes or services
            try:
                result = subprocess.run(['tasklist', '/fi', 'imagename eq Shadow*'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0 and 'Shadow' in result.stdout:
                    indicators.append("shadow_process")
            except Exception as e:
                self.logger.debug(f"Could not check processes: {e}")
            
            # 5. Check registry for Shadow PC indicators (if accessible)
            self._check_registry_indicators(indicators)
            
            # Determine if we're on Shadow PC
            self.shadow_pc_detected = len(indicators) >= 2
            
            if self.shadow_pc_detected:
                self.logger.info(f"Shadow PC environment detected (indicators: {indicators})")
            else:
                self.logger.info("Shadow PC environment not detected")
            
            return self.shadow_pc_detected
            
        except Exception as e:
            self.logger.error(f"Error detecting Shadow PC environment: {e}")
            return False

    def _check_registry_indicators(self, indicators: List[str]):
        """Check Windows registry for Shadow PC indicators"""
        try:
            import winreg
            
            # Check for Shadow-related registry keys
            shadow_paths = [
                r"SOFTWARE\Shadow",
                r"SOFTWARE\Parsec",
                r"SYSTEM\CurrentControlSet\Services\Shadow",
            ]
            
            for path in shadow_paths:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                    winreg.CloseKey(key)
                    indicators.append("registry_shadow")
                    break
                except FileNotFoundError:
                    continue
                except Exception as e:
                    self.logger.debug(f"Registry check error for {path}: {e}")
                    
        except ImportError:
            self.logger.debug("winreg not available for registry checks")
        except Exception as e:
            self.logger.debug(f"Registry check error: {e}")

    def _detect_gpu_capabilities(self):
        """Detect GPU hardware acceleration capabilities"""
        try:
            self.logger.info("Detecting GPU capabilities...")
            
            if not self.is_windows:
                return
            
            # Get GPU information
            try:
                result = subprocess.run(['wmic', 'path', 'win32_VideoController', 'get', 
                                       'name,driverversion,adapterram'], 
                                      capture_output=True, text=True, timeout=15)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines[1:]:  # Skip header
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 2:
                                gpu_name = ' '.join(parts[:-2]) if len(parts) > 2 else parts[0]
                                self.gpu_info['name'] = gpu_name.strip()
                                break
                
            except Exception as e:
                self.logger.debug(f"Could not get detailed GPU info: {e}")
            
            # Check for NVIDIA GPU and NVENC support
            self._check_nvidia_capabilities()
            
            # Check for AMD GPU and VCE support
            self._check_amd_capabilities()
            
            # Check for Intel Quick Sync
            self._check_intel_capabilities()
            
            self.logger.info(f"GPU capabilities detected: {self.gpu_info}")
            
        except Exception as e:
            self.logger.error(f"Error detecting GPU capabilities: {e}")

    def _check_nvidia_capabilities(self):
        """Check NVIDIA GPU capabilities"""
        try:
            # Try to run nvidia-smi
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version', 
                                   '--format=csv,noheader'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                info = result.stdout.strip().split(',')
                if len(info) >= 2:
                    self.gpu_info['nvidia'] = {
                        'name': info[0].strip(),
                        'driver_version': info[1].strip(),
                        'nvenc_supported': True  # Assume NVENC support for modern drivers
                    }
                    self.logger.info("NVIDIA GPU with NVENC support detected")
                    
        except FileNotFoundError:
            # nvidia-smi not found, check if NVIDIA GPU is present another way
            gpu_name = self.gpu_info.get('name', '').lower()
            if 'nvidia' in gpu_name or 'geforce' in gpu_name or 'quadro' in gpu_name:
                self.gpu_info['nvidia'] = {'name': gpu_name, 'nvenc_supported': True}
        except Exception as e:
            self.logger.debug(f"NVIDIA check error: {e}")

    def _check_amd_capabilities(self):
        """Check AMD GPU capabilities"""
        try:
            gpu_name = self.gpu_info.get('name', '').lower()
            if 'amd' in gpu_name or 'radeon' in gpu_name:
                self.gpu_info['amd'] = {
                    'name': gpu_name,
                    'vce_supported': True  # Assume VCE support for modern AMD GPUs
                }
                self.logger.info("AMD GPU with VCE support detected")
        except Exception as e:
            self.logger.debug(f"AMD check error: {e}")

    def _check_intel_capabilities(self):
        """Check Intel Quick Sync capabilities"""
        try:
            gpu_name = self.gpu_info.get('name', '').lower()
            if 'intel' in gpu_name:
                self.gpu_info['intel'] = {
                    'name': gpu_name,
                    'quicksync_supported': True  # Assume Quick Sync for Intel GPUs
                }
                self.logger.info("Intel GPU with Quick Sync support detected")
        except Exception as e:
            self.logger.debug(f"Intel check error: {e}")

    def _analyze_network_conditions(self):
        """Analyze network conditions for optimization"""
        try:
            self.logger.info("Analyzing network conditions...")
            
            # Test network latency and bandwidth
            self.network_info = {
                'latency_ms': self._test_network_latency(),
                'bandwidth_mbps': self._estimate_bandwidth(),
                'is_high_latency': False,
                'is_low_bandwidth': False
            }
            
            # Classify network conditions
            latency = self.network_info.get('latency_ms', 0)
            bandwidth = self.network_info.get('bandwidth_mbps', 100)
            
            self.network_info['is_high_latency'] = latency > 50  # > 50ms
            self.network_info['is_low_bandwidth'] = bandwidth < 10  # < 10 Mbps
            
            if self.shadow_pc_detected:
                # Shadow PC typically has higher latency
                self.network_info['shadow_pc_network'] = True
                
            self.logger.info(f"Network analysis complete: {self.network_info}")
            
        except Exception as e:
            self.logger.error(f"Error analyzing network conditions: {e}")

    def _test_network_latency(self) -> float:
        """Test network latency to common servers"""
        try:
            if not self.is_windows:
                return 0.0
            
            # Ping Google DNS for latency test
            result = subprocess.run(['ping', '-n', '3', '8.8.8.8'], 
                                  capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                output = result.stdout
                # Parse average latency from ping output
                for line in output.split('\n'):
                    if 'Average' in line:
                        import re
                        match = re.search(r'(\d+)ms', line)
                        if match:
                            return float(match.group(1))
            
            return 0.0
            
        except Exception as e:
            self.logger.debug(f"Latency test error: {e}")
            return 0.0

    def _estimate_bandwidth(self) -> float:
        """Estimate available bandwidth"""
        try:
            # This is a simplified estimation
            # In a real implementation, you might use speedtest-cli or similar
            return 100.0  # Default assumption of 100 Mbps
            
        except Exception as e:
            self.logger.debug(f"Bandwidth estimation error: {e}")
            return 100.0

    def get_optimization_settings(self) -> Dict:
        """Get recommended optimization settings based on detected environment"""
        settings = {}
        
        # Base settings
        settings['detected_environment'] = {
            'shadow_pc': self.shadow_pc_detected,
            'gpu_acceleration': bool(self.gpu_info),
            'network_optimized': self.network_info.get('is_high_latency', False)
        }
        
        # Processing optimizations
        processing_opts = {}
        
        if self.shadow_pc_detected:
            # Shadow PC specific optimizations
            processing_opts.update({
                'max_concurrent_jobs': 1,  # Single job to avoid network congestion
                'chunk_processing': True,
                'network_aware_mode': True,
                'timeout_multiplier': 2.0,  # Increase timeouts
                'prefer_local_processing': True
            })
        
        # GPU acceleration settings
        if self.gpu_info.get('nvidia'):
            processing_opts.update({
                'use_nvenc': True,
                'hardware_acceleration': 'nvidia',
                'gpu_memory_optimization': True
            })
        elif self.gpu_info.get('amd'):
            processing_opts.update({
                'use_vce': True,
                'hardware_acceleration': 'amd'
            })
        elif self.gpu_info.get('intel'):
            processing_opts.update({
                'use_quicksync': True,
                'hardware_acceleration': 'intel'
            })
        
        # Network optimizations
        if self.network_info.get('is_high_latency'):
            processing_opts.update({
                'connection_timeout': 60,
                'retry_attempts': 3,
                'chunk_size_mb': 1  # Smaller chunks for high latency
            })
        
        if self.network_info.get('is_low_bandwidth'):
            processing_opts.update({
                'upload_compression': True,
                'progressive_upload': True,
                'bandwidth_throttling': True
            })
        
        settings['processing'] = processing_opts
        
        # FFmpeg optimizations
        ffmpeg_opts = []
        
        if self.gpu_info.get('nvidia'):
            ffmpeg_opts.extend([
                '-hwaccel', 'nvdec',
                '-c:v', 'h264_nvenc'
            ])
        elif self.gpu_info.get('amd'):
            ffmpeg_opts.extend([
                '-hwaccel', 'dxva2',
                '-c:v', 'h264_amf'
            ])
        elif self.gpu_info.get('intel'):
            ffmpeg_opts.extend([
                '-hwaccel', 'qsv',
                '-c:v', 'h264_qsv'
            ])
        
        settings['ffmpeg_options'] = ffmpeg_opts
        
        return settings

    def apply_optimizations_to_config(self, config: Dict) -> Dict:
        """Apply optimizations to existing configuration"""
        optimizations = self.get_optimization_settings()
        
        # Update processing settings
        processing = config.setdefault('processing', {})
        processing.update(optimizations.get('processing', {}))
        
        # Update premiere settings if enabled
        if config.get('premiere', {}).get('enabled', False):
            premiere = config.setdefault('premiere', {})
            
            # Increase timeouts for Shadow PC
            if self.shadow_pc_detected:
                premiere['connection_timeout'] = 60
                premiere['export_timeout'] = 7200  # 2 hours
                premiere['processing_timeout'] = 3600  # 1 hour
        
        # Update topaz settings if enabled
        if config.get('topaz', {}).get('enabled', False):
            topaz = config.setdefault('topaz', {})
            
            # Increase timeout for network environments
            if self.shadow_pc_detected:
                topaz['timeout'] = 14400  # 4 hours
        
        # Add optimization metadata
        config['optimizations'] = {
            'applied_at': time.time(),
            'environment': optimizations['detected_environment'],
            'gpu_info': self.gpu_info,
            'network_info': self.network_info
        }
        
        self.logger.info("Applied environment-specific optimizations to configuration")
        return config

    def get_recommended_ffmpeg_args(self, input_file: str, output_file: str, 
                                   tape_type: str = None) -> List[str]:
        """Get recommended FFmpeg arguments based on detected hardware"""
        args = ['ffmpeg', '-i', input_file]
        
        # Hardware acceleration
        if self.gpu_info.get('nvidia'):
            args.extend(['-hwaccel', 'nvdec'])
        elif self.gpu_info.get('amd'):
            args.extend(['-hwaccel', 'dxva2'])
        elif self.gpu_info.get('intel'):
            args.extend(['-hwaccel', 'qsv'])
        
        # Video encoding
        if self.gpu_info.get('nvidia'):
            args.extend(['-c:v', 'h264_nvenc', '-preset', 'medium'])
        elif self.gpu_info.get('amd'):
            args.extend(['-c:v', 'h264_amf'])
        elif self.gpu_info.get('intel'):
            args.extend(['-c:v', 'h264_qsv'])
        else:
            args.extend(['-c:v', 'libx264', '-preset', 'medium'])
        
        # Quality settings
        args.extend(['-crf', '18'])
        
        # Audio encoding
        args.extend(['-c:a', 'aac', '-b:a', '192k'])
        
        # Tape-specific filters
        if tape_type:
            filters = []
            
            if tape_type.upper() in ['VHS', 'BETAMAX', 'HI8']:
                filters.append('yadif=0:0:0')  # Deinterlace
            
            if tape_type.upper() in ['VHS']:
                filters.append('denoise=hqdn3d=4:3:6:4.5')  # Noise reduction
            
            if filters:
                args.extend(['-vf', ','.join(filters)])
        
        # Shadow PC optimizations
        if self.shadow_pc_detected:
            args.extend(['-threads', '4'])  # Limit threads to avoid overwhelming the system
            
        # Output
        args.extend(['-y', output_file])
        
        return args

    def is_shadow_pc(self) -> bool:
        """Check if running on Shadow PC"""
        return self.shadow_pc_detected

    def has_gpu_acceleration(self) -> bool:
        """Check if GPU acceleration is available"""
        return bool(self.gpu_info)

    def get_gpu_info(self) -> Dict:
        """Get detected GPU information"""
        return self.gpu_info.copy()

    def get_network_info(self) -> Dict:
        """Get network analysis information"""
        return self.network_info.copy()