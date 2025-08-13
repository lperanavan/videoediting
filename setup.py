"""
Setup script for Video Processing Automation Tool
Installation and environment setup
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

class SetupManager:
    """Manages installation and setup of the video processing tool"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.python_exe = sys.executable
        
    def run_setup(self):
        """Run complete setup process"""
        print("🎬 Video Processing Automation Tool Setup")
        print("=" * 50)
        
        try:
            self.check_python_version()
            self.create_directories()
            self.install_dependencies() 
            self.check_external_tools()
            self.create_sample_files()
            self.setup_logging()
            self.final_instructions()
            
            print("\n✅ Setup completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
            sys.exit(1)
    
    def check_python_version(self):
        """Check Python version compatibility"""
        print("Checking Python version...")
        
        if sys.version_info < (3, 9):
            raise Exception("Python 3.9 or higher is required")
        
        print(f"✅ Python {sys.version.split()[0]} is compatible")
    
    def create_directories(self):
        """Create necessary directories"""
        print("Creating directory structure...")
        
        directories = [
            "input_videos",
            "output_videos", 
            "temp",
            "temp/premiere_projects",
            "temp/topaz",
            "presets",
            "config",
            "logs",
            "templates",
            "static",
            "tests/mock_data"
        ]
        
        for directory in directories:
            dir_path = self.project_root / directory
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  📁 {directory}")
        
        print("✅ Directory structure created")
    
    def install_dependencies(self):
        """Install Python dependencies"""
        print("Installing Python dependencies...")
        
        requirements_file = self.project_root / "requirements.txt"
        
        if not requirements_file.exists():
            print("⚠️  requirements.txt not found, skipping dependency installation")
            return
        
        try:
            subprocess.run([
                self.python_exe, "-m", "pip", "install", "-r", str(requirements_file)
            ], check=True, capture_output=True, text=True)
            
            print("✅ Dependencies installed successfully")
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Some dependencies failed to install: {e}")
            print("You may need to install them manually")
    
    def check_external_tools(self):
        """Check for external tools with Windows-specific enhancements"""
        print("Checking external tools...")
        
        tools = {
            "ffmpeg": "FFmpeg (for video analysis and fallback processing)",
            "ffprobe": "FFprobe (for video metadata extraction)"
        }
        
        for tool, description in tools.items():
            if shutil.which(tool):
                print(f"  ✅ {tool} - {description}")
            else:
                print(f"  ⚠️  {tool} not found - {description}")
                if tool == "ffmpeg":
                    self._suggest_ffmpeg_installation()
        
        # Windows-specific checks
        if sys.platform == "win32":
            self._check_windows_dependencies()
        
        # Check optional tools
        self._check_optional_tools()

    def _suggest_ffmpeg_installation(self):
        """Suggest FFmpeg installation methods"""
        print("    💡 To install FFmpeg:")
        if sys.platform == "win32":
            print("    - Download from https://ffmpeg.org/download.html")
            print("    - Or use Chocolatey: choco install ffmpeg")
            print("    - Or use winget: winget install Gyan.FFmpeg")
        else:
            print("    - Ubuntu/Debian: apt-get install ffmpeg")
            print("    - macOS: brew install ffmpeg")

    def _check_windows_dependencies(self):
        """Check Windows-specific dependencies"""
        print("\nWindows-specific dependencies:")
        
        # Check COM automation
        try:
            import win32com.client
            import pythoncom
            print("  ✅ pywin32 - Windows COM automation support")
        except ImportError:
            print("  ❌ pywin32 not found - Required for Adobe Premiere Pro automation")
            print("    💡 Install with: pip install pywin32")
        
        # Check Windows Media Foundation
        try:
            import subprocess
            result = subprocess.run(['reg', 'query', 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Setup\\WindowsFeatures', '/v', 'WindowsMediaFormat-Runtime'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("  ✅ Windows Media Foundation - Media processing support")
            else:
                print("  ⚠️  Windows Media Foundation status unknown")
        except Exception:
            print("  ⚠️  Could not check Windows Media Foundation")
        
        # Check DirectShow filters
        try:
            result = subprocess.run(['reg', 'query', 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\Filter'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("  ✅ DirectShow filters available")
        except Exception:
            print("  ⚠️  Could not check DirectShow filters")

    def _check_optional_tools(self):
        """Check optional tools with enhanced detection"""
        print("\nOptional professional tools:")
        
        # Adobe Premiere Pro detection
        premiere_paths = [
            (r"C:\Program Files\Adobe\Adobe Premiere Pro 2025", "Adobe Premiere Pro 2025"),
            (r"C:\Program Files\Adobe\Adobe Premiere Pro 2024", "Adobe Premiere Pro 2024"), 
            (r"C:\Program Files\Adobe\Adobe Premiere Pro 2023", "Adobe Premiere Pro 2023"),
            (r"C:\Program Files\Adobe\Adobe Premiere Pro CC*", "Adobe Premiere Pro CC")
        ]
        
        premiere_found = False
        for path, name in premiere_paths:
            if "*" in path:
                # Check for any version
                parent = Path(path).parent
                if parent.exists() and any(parent.glob(Path(path).name)):
                    print(f"  ✅ {name} detected")
                    premiere_found = True
                    break
            else:
                if Path(path).exists():
                    print(f"  ✅ {name} found")
                    premiere_found = True
                    break
        
        if not premiere_found:
            print("  ⚠️  Adobe Premiere Pro not found")
            print("    💡 Download from Adobe Creative Cloud")
        
        # Topaz Video AI detection
        topaz_paths = [
            r"C:\Program Files\Topaz Labs LLC\Topaz Video AI\Topaz Video AI.exe",
            r"C:\Program Files (x86)\Topaz Labs LLC\Topaz Video AI\Topaz Video AI.exe"
        ]
        
        topaz_found = False
        for path in topaz_paths:
            if Path(path).exists():
                print(f"  ✅ Topaz Video AI found at {path}")
                topaz_found = True
                break
        
        if not topaz_found:
            print("  ⚠️  Topaz Video AI not found")
            print("    💡 Download from https://www.topazlabs.com/video-ai")
        
        # Shadow PC detection
        if sys.platform == "win32":
            self._detect_shadow_pc()

    def _detect_shadow_pc(self):
        """Detect Shadow PC environment"""
        try:
            from utils.shadow_pc_optimizer import ShadowPCOptimizer
            optimizer = ShadowPCOptimizer()
            
            if optimizer.is_shadow_pc():
                print("  🌩️  Shadow PC environment detected")
                gpu_info = optimizer.get_gpu_info()
                if gpu_info:
                    print(f"    GPU acceleration available: {list(gpu_info.keys())}")
                network_info = optimizer.get_network_info()
                if network_info.get('is_high_latency'):
                    print("    High latency network detected - optimizations will be applied")
            else:
                print("  💻 Standard Windows environment")
                
        except Exception as e:
            print(f"  ⚠️  Could not detect environment: {e}")
    
    def create_sample_files(self):
        """Create sample configuration and test files"""
        print("Creating sample files...")
        
        # Sample Google Drive credentials template
        gdrive_template = {
            "type": "service_account",
            "project_id": "your-project-id",
            "private_key_id": "your-private-key-id", 
            "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n",
            "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
            "client_id": "your-client-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
        }
        
        gdrive_creds_file = self.project_root / "config" / "gdrive_credentials_template.json"
        with open(gdrive_creds_file, 'w') as f:
            import json
            json.dump(gdrive_template, f, indent=2)
        
        print("  📄 config/gdrive_credentials_template.json")
        
        # Sample test data
        test_data_file = self.project_root / "tests" / "mock_data" / "sample_videos.json"
        test_data = {
            "sample_videos": [
                {
                    "filename": "sample_vhs_tape.mp4",
                    "tape_type": "VHS",
                    "description": "Sample VHS tape conversion"
                },
                {
                    "filename": "sample_minidv_tape.mp4", 
                    "tape_type": "MiniDV",
                    "description": "Sample MiniDV tape conversion"
                }
            ]
        }
        
        with open(test_data_file, 'w') as f:
            import json
            json.dump(test_data, f, indent=2)
        
        print("  📄 tests/mock_data/sample_videos.json")
        print("✅ Sample files created")
    
    def setup_logging(self):
        """Initialize logging"""
        print("Setting up logging...")
        
        # Initialize logging to test it works
        try:
            from utils.logger import setup_logging
            setup_logging()
            print("✅ Logging system initialized")
        except Exception as e:
            print(f"⚠️  Logging setup warning: {e}")
    
    def final_instructions(self):
        """Display final setup instructions"""
        print("\n" + "=" * 50)
        print("🎉 Setup Complete! Next Steps:")
        print("=" * 50)
        
        instructions = [
            "1. 📋 Configure Google Drive API:",
            "   - Copy config/gdrive_credentials_template.json to config/gdrive_credentials.json",
            "   - Add your actual Google Drive service account credentials",
            "   - Set 'gdrive.enabled': true in config/app_settings.json",
            "",
            "2. 🎬 Configure Adobe Premiere Pro (optional):",
            "   - Ensure Premiere Pro is installed",
            "   - Set 'premiere.enabled': true in config/app_settings.json",
            "   - Add your preset files to the presets/ directory",
            "",
            "3. 🔧 Configure Topaz Video AI (optional):",
            "   - Install Topaz Video AI",
            "   - Update the application path in config/app_settings.json",
            "   - Set 'topaz.enabled': true",
            "",
            "4. 🚀 Start the application:",
            "   Web UI:     python web_ui.py",
            "   CLI:        python main.py", 
            "   Interactive: python scripts/interactive.py",
            "",
            "5. 🌐 Access the Web Dashboard:",
            "   Open your browser to: http://localhost:5000",
            "",
            "6. 📚 Read the documentation:",
            "   Check README.md for detailed usage instructions"
        ]
        
        for instruction in instructions:
            print(instruction)

if __name__ == "__main__":
    setup = SetupManager()
    setup.run_setup()