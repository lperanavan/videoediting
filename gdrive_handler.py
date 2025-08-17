"""
Google Drive Handler for Video Processing Automation
Handles file downloads and uploads to Google Drive
"""

import os
import io
import logging
import time
import mimetypes
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import json

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

class GDriveHandler:
    """Handles Google Drive operations for video processing"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.service = None
        
        if not GOOGLE_AVAILABLE:
            raise ImportError("Google Drive dependencies not installed. Please install google-api-python-client and google-auth-httplib2")
        
        self._initialize_service()
        self.enabled = self.config.get("enabled", False) and GOOGLE_AVAILABLE
        
        if self.enabled:
            self._initialize_service()
        else:
            self.logger.warning("Google Drive integration disabled or dependencies missing")
        # Cache for folders we've already validated as writable
        self._validated_folders = set()
        self.service_account_email = None
        try:
            # Extract service account email (for user guidance) from credentials file if available
            credentials_path = self.config.get("credentials_file", "config/gdrive_credentials.json")
            if os.path.exists(credentials_path):
                with open(credentials_path, 'r', encoding='utf-8') as cf:
                    data = json.load(cf)
                    self.service_account_email = data.get('client_email')
        except Exception:
            pass
    
    def _initialize_service(self):
        """Initialize Google Drive service"""
        try:
            credentials_path = self.config.get("credentials_file", "config/gdrive_credentials.json")
            
            if not os.path.exists(credentials_path):
                self.logger.error(f"Google Drive credentials file not found: {credentials_path}")
                self.enabled = False
                return
            
            # Load service account credentials
            scopes = ['https://www.googleapis.com/auth/drive']
            credentials = Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )
            
            self.service = build('drive', 'v3', credentials=credentials)
            
            # Test connection
            self.service.about().get(fields='user').execute()
            self.logger.info("Google Drive service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Drive service: {e}")
            self.enabled = False
            self.service = None
    
    def download_files(self, file_identifiers: List[str], download_dir: str, 
                      job_id: str = None) -> List[str]:
        """Download files from Google Drive"""
        if not self.enabled:
            return self._mock_download_files(file_identifiers, download_dir, job_id)
        
        downloaded_files = []
        os.makedirs(download_dir, exist_ok=True)
        
        for identifier in file_identifiers:
            try:
                if identifier.startswith('http'):
                    # Extract file ID from Google Drive URL
                    file_id = self._extract_file_id_from_url(identifier)
                else:
                    # Assume it's already a file ID or search by name
                    file_id = identifier if self._is_valid_file_id(identifier) else self._search_file_by_name(identifier)
                
                if not file_id:
                    self.logger.error(f"Could not resolve file identifier: {identifier}")
                    continue
                
                local_path = self._download_single_file(file_id, download_dir, job_id)
                if local_path:
                    downloaded_files.append(local_path)
                    
            except Exception as e:
                self.logger.error(f"Error downloading file {identifier}: {e}")
                continue
        
        self.logger.info(f"Downloaded {len(downloaded_files)} files to {download_dir}")
        return downloaded_files
    
    def _download_single_file(self, file_id: str, download_dir: str, 
                             job_id: str = None) -> Optional[str]:
        """Download a single file from Google Drive"""
        try:
            # Get file metadata
            file_metadata = self.service.files().get(fileId=file_id, fields='name,size,mimeType,parents').execute()
            filename = file_metadata['name']
            file_size = int(file_metadata.get('size', 0))
            parents = file_metadata.get('parents', [])
            
            # Sanitize filename
            safe_filename = self._sanitize_filename(filename)
            if job_id:
                name, ext = os.path.splitext(safe_filename)
                safe_filename = f"{job_id}_{name}{ext}"
            
            local_path = os.path.join(download_dir, safe_filename)
            
            # Download file
            request = self.service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as file_handle:
                downloader = MediaIoBaseDownload(file_handle, request)
                done = False
                
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        self.logger.debug(f"Download progress {filename}: {progress}%")
            
            # Verify download
            if os.path.exists(local_path):
                actual_size = os.path.getsize(local_path)
                if file_size > 0 and abs(actual_size - file_size) > 1024:  # Allow 1KB difference
                    self.logger.warning(f"File size mismatch for {filename}: expected {file_size}, got {actual_size}")
                
                self.logger.info(f"Downloaded: {filename} ({actual_size} bytes)")
                return local_path
            else:
                self.logger.error(f"Downloaded file not found: {local_path}")
                return None
                
        except HttpError as e:
            self.logger.error(f"HTTP error downloading file {file_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error downloading file {file_id}: {e}")
            return None
    
    def get_file_parent(self, file_id: str) -> Optional[str]:
        """Return the first parent folder ID for a file (if any)."""
        if not self.enabled:
            return None
        try:
            meta = self.service.files().get(fileId=file_id, fields='parents').execute()
            parents = meta.get('parents', [])
            return parents[0] if parents else None
        except Exception as e:
            self.logger.error(f"Failed to get parent for file {file_id}: {e}")
            return None
    def upload_files(self, file_paths: List[str], folder_id: str = None, 
                    job_id: str = None) -> List[str]:
        """Upload files to Google Drive"""
        if not self.enabled:
            return self._mock_upload_files(file_paths, folder_id, job_id)
        
        uploaded_urls = []
        # Resolve folder ID preference order:
        # 1. Explicit parameter
        # 2. config.default_output_folder_id
        # 3. config.output_folder_id (legacy)
        # 4. None (will upload to root – not recommended for service accounts)
        if not folder_id:
            folder_id = (
                self.config.get('default_output_folder_id')
                or self.config.get('output_folder_id')
            )

        # Allow passing a full URL instead of raw ID
        if folder_id and folder_id.startswith('http'):
            extracted = self._extract_file_id_from_url(folder_id)
            if extracted:
                folder_id = extracted

        # If still not a valid ID treat as folder name to create / fetch
        if folder_id and not self._is_valid_file_id(folder_id):
            resolved_name = folder_id
            folder_id = self._get_or_create_folder(resolved_name)
            if not folder_id:
                self.logger.error(f"Failed to resolve or create folder: {resolved_name}")
        
        self.logger.info(
            f"Preparing to upload {len(file_paths)} file(s) to folder: {folder_id or 'ROOT (not recommended)'}"
        )

        # Log folder metadata (diagnostics) to help user understand why quota errors occur
        if folder_id:
            try:
                meta = self.service.files().get(
                    fileId=folder_id,
                    fields='id,name,mimeType,owners(emailAddress,displayName),driveId,parents',
                    supportsAllDrives=True
                ).execute()
                drive_id = meta.get('driveId')
                owner_info = meta.get('owners', [])
                owner_str = ', '.join([o.get('emailAddress','?') for o in owner_info]) or 'unknown'
                if drive_id:
                    self.logger.info(
                        f"Target folder metadata: name={meta.get('name')} id={folder_id} driveId={drive_id} owners={owner_str} (Shared Drive detected)"
                    )
                else:
                    self.logger.info(
                        f"Target folder metadata: name={meta.get('name')} id={folder_id} owners={owner_str} driveId=None (User 'My Drive' folder)"
                    )
                    if owner_info and any(self.service_account_email and self.service_account_email in (o.get('emailAddress') or '') for o in owner_info):
                        self.logger.warning(
                            "Folder appears to be OWNED by the service account (no personal quota). Move it into a human user's My Drive or a Shared Drive and share back to the service account."
                        )
                    else:
                        self.logger.info(
                            "If you continue to see storageQuotaExceeded, verify the folder is not inside the service account's own My Drive by moving it to a Shared Drive."
                        )
            except Exception as e:
                self.logger.debug(f"Could not fetch folder metadata for diagnostics: {e}")

        # Verify folder write access once per folder_id (if provided)
        if folder_id and folder_id not in self._validated_folders:
            if not self._verify_folder_writable(folder_id):
                self.logger.error(
                    "Aborting upload: Service account cannot write to folder %s. Share the folder with %s as Editor/Content Manager (or place it in a Shared Drive and share that).",
                    folder_id, self.service_account_email or 'the service account'
                )
                return []
            self._validated_folders.add(folder_id)
        
        for file_path in file_paths:
            try:
                if not os.path.exists(file_path):
                    self.logger.error(f"File not found for upload: {file_path}")
                    continue
                
                url = self._upload_single_file(file_path, folder_id, job_id)
                if url:
                    uploaded_urls.append(url)
                    
            except Exception as e:
                self.logger.error(f"Error uploading file {file_path}: {e}")
                continue
        
        self.logger.info(f"Uploaded {len(uploaded_urls)} files to Google Drive")
        return uploaded_urls
    
    def _upload_single_file(self, file_path: str, folder_id: str = None, 
                           job_id: str = None) -> Optional[str]:
        """Upload a single file to Google Drive"""
        try:
            filename = os.path.basename(file_path)
            if job_id:
                name, ext = os.path.splitext(filename)
                filename = f"{job_id}_{name}_processed{ext}"
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Prepare file metadata
            file_metadata = {
                'name': filename,
                'description': f'Processed by Video Automation Tool - Job: {job_id or "unknown"}'
            }
            
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            # Upload file
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
            
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink,webContentLink',
                supportsAllDrives=True
            )
            
            file_result = None
            while file_result is None:
                status, file_result = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    self.logger.debug(f"Upload progress {filename}: {progress}%")
            
            # Make file shareable
            self.service.permissions().create(
                fileId=file_result['id'],
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
            
            file_url = file_result.get('webViewLink')
            self.logger.info(f"Uploaded: {filename} -> {file_url}")
            
            return file_url
            
        except HttpError as e:
            # Provide clearer guidance for common 403 quota issue with service accounts
            try:
                reason = getattr(e, 'reason', '') or ''
                if 'storageQuotaExceeded' in str(e):
                    self.logger.error(
                        "HTTP error uploading file (quota). Service accounts have no personal My Drive quota. "
                        "Share a user-owned (or shared drive) folder with the service account and supply its folder ID in config.gdrive.default_output_folder_id or output_folder_id. "
                        "Alternatively use a Shared Drive and enable 'supportsAllDrives'. Original error: %s", e
                    )
                else:
                    self.logger.error(f"HTTP error uploading file {file_path}: {e}")
            except Exception:
                self.logger.error(f"HTTP error uploading file {file_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error uploading file {file_path}: {e}")
            return None
    
    def _extract_file_id_from_url(self, url: str) -> Optional[str]:
        """Extract file ID from Google Drive URL"""
        import re
        
        patterns = [
            r'/file/d/([a-zA-Z0-9-_]+)',
            r'id=([a-zA-Z0-9-_]+)',
            r'/open\?id=([a-zA-Z0-9-_]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def _is_valid_file_id(self, file_id: str) -> bool:
        """Check if string looks like a valid Google Drive file ID"""
        import re
        return bool(re.match(r'^[a-zA-Z0-9-_]{25,}$', file_id))
    
    def _search_file_by_name(self, filename: str) -> Optional[str]:
        """Search for file by name and return file ID"""
        try:
            query = f"name='{filename}' and trashed=false"
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                pageSize=10,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']  # Return first match
            
        except Exception as e:
            self.logger.error(f"Error searching for file {filename}: {e}")
        
        return None
    
    def _get_or_create_folder(self, folder_name: str) -> Optional[str]:
        """Get existing folder or create new one"""
        try:
            # Search for existing folder
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                pageSize=10,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            
            # Create new folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            
            self.logger.info(f"Created folder: {folder_name} ({folder_id})")
            return folder_id
            
        except Exception as e:
            self.logger.error(f"Error creating folder {folder_name}: {e}")
            return None

    def _verify_folder_writable(self, folder_id: str) -> bool:
        """Attempt to verify that the service account can write to the specified folder.
        Creates and deletes a tiny temp file. Returns True if successful."""
        try:
            # Get folder metadata to confirm it exists and is a folder
            meta = self.service.files().get(
                fileId=folder_id,
                fields='id,name,mimeType,driveId',
                supportsAllDrives=True
            ).execute()
            if meta.get('mimeType') != 'application/vnd.google-apps.folder':
                self.logger.error(f"Target ID {folder_id} is not a folder (mimeType={meta.get('mimeType')})")
                return False

            # Try creating a small temp file
            test_name = f".write_test_{int(time.time())}.tmp"
            file_metadata = {
                'name': test_name,
                'parents': [folder_id]
            }
            media = MediaFileUpload(__file__, mimetype='text/plain', resumable=False)
            # We upload the current source file (tiny) just as a writable test, then delete
            test_file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            ).execute()
            test_id = test_file.get('id')
            # Delete test file
            self.service.files().delete(fileId=test_id, supportsAllDrives=True).execute()
            self.logger.info(
                f"Verified write access to folder {folder_id} as service account {self.service_account_email or ''}".strip()
            )
            return True
        except HttpError as e:
            if 'storageQuotaExceeded' in str(e):
                self.logger.error(
                    "Write test failed due to storageQuotaExceeded. This indicates the folder is in the service account's 'My Drive'. Move it to a user-owned drive shared with the service account, or a Shared Drive."
                )
            else:
                self.logger.error(
                    f"Cannot write to folder {folder_id}. Share it with {self.service_account_email or 'service account'} and grant Editor permission. Error: {e}"
                )
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error verifying folder {folder_id}: {e}")
            return False
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for local filesystem"""
        import re
        # Remove or replace invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        sanitized = sanitized.strip('. ')
        return sanitized[:255]  # Limit length
    
    def _mock_download_files(self, file_identifiers: List[str], download_dir: str, 
                            job_id: str = None) -> List[str]:
        """Mock file download for testing without Google Drive"""
        self.logger.info(f"MOCK: Downloading {len(file_identifiers)} files to {download_dir}")
        
        os.makedirs(download_dir, exist_ok=True)
        downloaded_files = []
        
        for i, identifier in enumerate(file_identifiers):
            # Create mock files
            if job_id:
                filename = f"{job_id}_source_video_{i+1}.mp4"
            else:
                filename = f"mock_video_{i+1}.mp4"
            
            file_path = os.path.join(download_dir, filename)
            
            # Create a small mock video file (just a text file for testing)
            with open(file_path, 'w') as f:
                f.write(f"Mock video file for identifier: {identifier}\n")
                f.write(f"Created at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Job ID: {job_id}\n")
            
            downloaded_files.append(file_path)
            self.logger.info(f"MOCK: Downloaded {filename}")
        
        return downloaded_files
    
    def _mock_upload_files(self, file_paths: List[str], folder_id: str = None, 
                          job_id: str = None) -> List[str]:
        """Mock file upload for testing without Google Drive"""
        self.logger.info(f"MOCK: Uploading {len(file_paths)} files to Google Drive")
        
        uploaded_urls = []
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                self.logger.warning(f"MOCK: File not found: {file_path}")
                continue
            
            filename = os.path.basename(file_path)
            mock_url = f"https://drive.google.com/file/d/mock_{hash(filename)}/view"
            uploaded_urls.append(mock_url)
            
            self.logger.info(f"MOCK: Uploaded {filename} -> {mock_url}")
        
        return uploaded_urls
    
    def close(self):
        """Close Google Drive service connection"""
        if self.service:
            self.service = None
            self.logger.info("Google Drive service connection closed")