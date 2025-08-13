# Shadow PC Installation Guide for Video Processing Automation

This guide provides step-by-step instructions for setting up the Video Processing Automation Tool on Shadow PC.

## Prerequisites

- Shadow PC subscription with boost-level performance (recommended)
- Windows 10/11 on Shadow PC
- Administrative access to install software
- Stable internet connection (minimum 25 Mbps recommended)

## Step 1: Initial Setup

### 1.1 Connect to Shadow PC
1. Launch Shadow app and connect to your Shadow PC
2. Ensure you have a stable connection with good latency (<50ms recommended)

### 1.2 Install Python
1. Download Python 3.9+ from https://www.python.org/downloads/windows/
2. During installation, check "Add Python to PATH"
3. Verify installation: Open Command Prompt and run `python --version`

### 1.3 Install Git (Optional)
1. Download Git from https://git-scm.com/download/win
2. Use default installation settings

## Step 2: Download and Setup the Application

### 2.1 Download the Application
```cmd
# Option 1: Using Git
git clone https://github.com/lperanavan/videoediting.git
cd videoediting

# Option 2: Download ZIP from GitHub and extract
```

### 2.2 Run Initial Setup
```cmd
python setup.py
```

The setup will:
- Install Python dependencies
- Create necessary directories
- Check for external tools
- Detect Shadow PC environment
- Apply optimizations automatically

## Step 3: Install Required Tools

### 3.1 Install FFmpeg
Choose one of these methods:

#### Option A: Using Chocolatey (Recommended)
```cmd
# Install Chocolatey first (as Administrator)
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install FFmpeg
choco install ffmpeg
```

#### Option B: Using winget
```cmd
winget install Gyan.FFmpeg
```

#### Option C: Manual Installation
1. Download FFmpeg from https://www.gyan.dev/ffmpeg/builds/
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to Windows PATH

### 3.2 Install Adobe Premiere Pro (Optional)
1. Download Adobe Creative Cloud
2. Install Adobe Premiere Pro 2023 or newer
3. Ensure it runs at least once to complete initial setup

### 3.3 Install Topaz Video AI (Optional)
1. Download from https://www.topazlabs.com/video-ai
2. Install with default settings
3. Note the installation path for configuration

## Step 4: Configuration

### 4.1 Basic Configuration
The application will automatically detect Shadow PC and apply optimizations. Key optimizations include:
- Single concurrent job processing
- Increased timeouts for network operations
- Hardware acceleration detection
- Network-aware file handling

### 4.2 Google Drive Setup
1. Copy `config/gdrive_credentials_template.json` to `config/gdrive_credentials.json`
2. Add your Google Drive service account credentials
3. Set `"enabled": true` in the gdrive section of `config/app_settings.json`

### 4.3 Premiere Pro Setup (if installed)
1. In `config/app_settings.json`, set:
   ```json
   {
     "premiere": {
       "enabled": true,
       "connection_timeout": 60,
       "export_timeout": 7200
     }
   }
   ```

### 4.4 Topaz Video AI Setup (if installed)
1. In `config/app_settings.json`, set:
   ```json
   {
     "topaz": {
       "enabled": true,
       "application_path": "C:\\Program Files\\Topaz Labs LLC\\Topaz Video AI\\Topaz Video AI.exe",
       "timeout": 14400
     }
   }
   ```

## Step 5: Shadow PC Specific Optimizations

The application automatically detects Shadow PC and applies these optimizations:

### 5.1 Processing Optimizations
- **Single Job Processing**: Reduces network congestion
- **Increased Timeouts**: Accommodates network latency
- **Chunk Processing**: Better handling of large files
- **Memory Optimization**: Efficient use of Shadow PC resources

### 5.2 Network Optimizations
- **Adaptive Timeouts**: Based on detected latency
- **Progressive Upload**: Better handling of slow connections
- **Retry Logic**: Robust error recovery
- **Bandwidth Monitoring**: Adjusts behavior based on available bandwidth

### 5.3 GPU Acceleration
The tool automatically detects and utilizes:
- NVIDIA NVENC (if available)
- AMD VCE (if available)
- Intel Quick Sync (if available)

## Step 6: Running the Application

### 6.1 Web Interface (Recommended for Shadow PC)
```cmd
python web_ui.py
```
Then open your browser to: http://localhost:5000

### 6.2 Command Line Interface
```cmd
# Process queue once
python main.py --single-run

# Run continuously
python main.py
```

## Step 7: Optimization Tips for Shadow PC

### 7.1 Performance Tips
1. **Use Boost Tier**: Higher-tier Shadow PCs provide better performance
2. **Stable Connection**: Ensure consistent internet speed
3. **Close Unnecessary Apps**: Free up resources on Shadow PC
4. **Local Storage**: Use Shadow's storage for temporary files

### 7.2 Network Tips
1. **Ethernet Connection**: Use wired connection if possible
2. **QoS Settings**: Configure router for Shadow traffic priority
3. **Background Apps**: Minimize bandwidth usage by other applications
4. **Upload Scheduling**: Process during off-peak hours

### 7.3 Monitoring
- Monitor the web dashboard for real-time status
- Check logs in `logs/video_processor.log`
- Watch resource usage through Task Manager

## Troubleshooting

### Common Issues

#### Connection Timeouts
**Problem**: Processing fails with timeout errors
**Solution**: 
- Increase timeout values in configuration
- Check internet connection stability
- Try processing smaller files first

#### High Latency
**Problem**: Slow response times
**Solution**:
- The application automatically adjusts for high latency
- Consider using boost-tier Shadow PC
- Process during off-peak hours

#### GPU Acceleration Not Working
**Problem**: No hardware acceleration detected
**Solution**:
- Verify GPU drivers are installed
- Check Windows Device Manager for GPU
- Some Shadow PCs may not expose GPU for hardware encoding

#### Premiere Pro COM Errors
**Problem**: Cannot connect to Premiere Pro
**Solution**:
- Ensure Premiere Pro is installed and licensed
- Run Premiere Pro manually once to complete setup
- Check Windows UAC settings

### Log Files
Check these log files for detailed error information:
- `logs/video_processor.log` - Main application log
- `logs/structured.jsonl` - Structured logging data

### Configuration Reset
If configuration becomes corrupted:
```cmd
# Backup current config
copy config\app_settings.json config\app_settings.backup.json

# Reset to defaults
del config\app_settings.json
python setup.py
```

## Support

For additional support:
1. Check the main README.md file
2. Review log files for error details
3. Test with smaller files first
4. Ensure all prerequisites are properly installed

## Performance Expectations

On Shadow PC, expect:
- **Processing Speed**: 0.5-2x real-time depending on complexity
- **Upload Speed**: Depends on your internet connection
- **Resource Usage**: Optimized for Shadow PC hardware
- **Reliability**: Enhanced error recovery for network issues

The application is specifically optimized for Shadow PC's virtualized environment and will automatically adjust settings for the best performance and reliability.