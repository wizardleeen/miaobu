import oss2
import mimetypes
import gzip
from pathlib import Path
from typing import Optional, List, Dict
import os

from ..config import get_settings

settings = get_settings()


class OSSService:
    """
    Service for interacting with Alibaba Cloud OSS.

    Handles file uploads, directory uploads, and public URL generation.
    """

    def __init__(self, bucket_name: Optional[str] = None, endpoint: Optional[str] = None):
        """Initialize OSS client with credentials from settings.

        Args:
            bucket_name: Override bucket name (default: settings.aliyun_oss_bucket)
            endpoint: Override endpoint (default: settings.aliyun_oss_endpoint)
        """
        self.auth = oss2.Auth(
            settings.aliyun_access_key_id,
            settings.aliyun_access_key_secret
        )

        self._bucket_name = bucket_name or settings.aliyun_oss_bucket
        self._endpoint = endpoint or settings.aliyun_oss_endpoint

        self.bucket = oss2.Bucket(
            self.auth,
            self._endpoint,
            self._bucket_name,
        )

        # Text file extensions that should be gzipped
        self.gzip_extensions = {
            '.html', '.css', '.js', '.json', '.xml', '.svg',
            '.txt', '.md', '.csv', '.map'
        }

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """
        Check if bucket exists, create it if it doesn't.
        Sets bucket to public-read access for static hosting.
        """
        try:
            # Try to get bucket info to check if it exists
            self.bucket.get_bucket_info()
            print(f"[OSS] Bucket '{settings.aliyun_oss_bucket}' already exists")
        except oss2.exceptions.NoSuchBucket:
            # Bucket doesn't exist, create it
            print(f"[OSS] Creating bucket '{settings.aliyun_oss_bucket}'...")

            # Create bucket with public-read ACL for static hosting
            from oss2.models import BUCKET_ACL_PUBLIC_READ, BucketCreateConfig

            # Use service endpoint for bucket creation
            service = oss2.Service(self.auth, settings.aliyun_oss_endpoint)

            # Create bucket
            config = BucketCreateConfig(oss2.BUCKET_STORAGE_CLASS_STANDARD)
            self.bucket.create_bucket(BUCKET_ACL_PUBLIC_READ, config)

            print(f"[OSS] ✓ Bucket '{settings.aliyun_oss_bucket}' created successfully")
            print(f"[OSS] ✓ Bucket set to public-read access")
        except oss2.exceptions.OssError as e:
            print(f"[OSS] Error checking/creating bucket: {e}")
            # Don't fail initialization, just log the error
            # The error will surface when trying to upload files

    def get_content_type(self, file_path: Path) -> str:
        """
        Determine Content-Type for a file.

        Args:
            file_path: Path to the file

        Returns:
            MIME type string
        """
        content_type, _ = mimetypes.guess_type(str(file_path))

        if not content_type:
            # Default content types for common extensions
            ext = file_path.suffix.lower()
            defaults = {
                '.html': 'text/html',
                '.css': 'text/css',
                '.js': 'application/javascript',
                '.json': 'application/json',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.svg': 'image/svg+xml',
                '.ico': 'image/x-icon',
                '.woff': 'font/woff',
                '.woff2': 'font/woff2',
                '.ttf': 'font/ttf',
                '.eot': 'application/vnd.ms-fontobject',
            }
            content_type = defaults.get(ext, 'application/octet-stream')

        return content_type

    def should_gzip(self, file_path: Path) -> bool:
        """
        Determine if a file should be gzipped.

        Args:
            file_path: Path to the file

        Returns:
            True if file should be gzipped
        """
        return file_path.suffix.lower() in self.gzip_extensions

    def upload_file(
        self,
        local_path: Path,
        oss_path: str,
        headers: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload a single file to OSS.

        Args:
            local_path: Local file path
            oss_path: Destination path in OSS (without leading slash)
            headers: Optional HTTP headers

        Returns:
            Public URL of uploaded file
        """
        # Determine content type
        content_type = self.get_content_type(local_path)

        # Prepare headers
        upload_headers = {
            'Content-Type': content_type,
            'Cache-Control': 'public, max-age=31536000',  # 1 year cache
        }

        if headers:
            upload_headers.update(headers)

        # Read file content
        with open(local_path, 'rb') as f:
            content = f.read()

        # Gzip if appropriate
        if self.should_gzip(local_path) and len(content) > 1024:  # Only gzip files > 1KB
            content = gzip.compress(content)
            upload_headers['Content-Encoding'] = 'gzip'

        # Upload to OSS
        self.bucket.put_object(
            oss_path,
            content,
            headers=upload_headers
        )

        # Return public URL
        return self.get_public_url(oss_path)

    def upload_directory(
        self,
        local_dir: Path,
        oss_prefix: str,
        log_callback: Optional[callable] = None
    ) -> Dict[str, any]:
        """
        Upload an entire directory to OSS.

        Args:
            local_dir: Local directory path
            oss_prefix: OSS path prefix (e.g., "user_id/project_id/commit_sha/")
            log_callback: Optional callback for logging progress

        Returns:
            Dictionary with upload statistics and URLs
        """
        if not local_dir.exists() or not local_dir.is_dir():
            raise ValueError(f"Directory not found: {local_dir}")

        def log(message: str):
            if log_callback:
                log_callback(message)

        # Ensure prefix ends with /
        if not oss_prefix.endswith('/'):
            oss_prefix += '/'

        uploaded_files = []
        total_size = 0
        total_compressed = 0

        # Get all files to upload
        files = list(local_dir.rglob('*'))
        file_count = len([f for f in files if f.is_file()])

        log(f"Uploading {file_count} files to OSS...")
        log(f"OSS path: {oss_prefix}")

        # Upload each file
        for i, file_path in enumerate(files, 1):
            if not file_path.is_file():
                continue

            # Calculate relative path
            rel_path = file_path.relative_to(local_dir)
            oss_path = oss_prefix + str(rel_path).replace('\\', '/')

            # Get file size
            file_size = file_path.stat().st_size
            total_size += file_size

            # Upload file
            log(f"[{i}/{file_count}] Uploading {rel_path} ({file_size:,} bytes)")

            url = self.upload_file(file_path, oss_path)
            uploaded_files.append({
                'path': str(rel_path),
                'oss_path': oss_path,
                'url': url,
                'size': file_size
            })

        # Get total compressed size (approximate)
        total_compressed = total_size  # OSS doesn't report actual stored size

        log(f"✓ Upload complete!")
        log(f"  Files uploaded: {file_count}")
        log(f"  Total size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")

        # Find index.html for main URL
        index_file = next(
            (f for f in uploaded_files if f['path'] in ['index.html', 'index.htm']),
            uploaded_files[0] if uploaded_files else None
        )

        return {
            'files_uploaded': file_count,
            'total_size': total_size,
            'oss_prefix': oss_prefix,
            'index_url': index_file['url'] if index_file else None,
            'files': uploaded_files
        }

    def get_public_url(self, oss_path: str) -> str:
        """
        Get public URL for an OSS object.

        Args:
            oss_path: Object path in OSS

        Returns:
            Public HTTPS URL
        """
        # Generate URL based on OSS endpoint
        # Format: https://{bucket}.{endpoint}/{path}
        endpoint = settings.aliyun_oss_endpoint
        bucket = settings.aliyun_oss_bucket

        # Remove protocol if present
        if '://' in endpoint:
            endpoint = endpoint.split('://', 1)[1]

        return f"https://{bucket}.{endpoint}/{oss_path}"

    def delete_directory(self, oss_prefix: str) -> int:
        """
        Delete all objects under a prefix.

        Args:
            oss_prefix: OSS path prefix to delete

        Returns:
            Number of objects deleted
        """
        # Ensure prefix ends with /
        if not oss_prefix.endswith('/'):
            oss_prefix += '/'

        # List all objects with prefix
        deleted_count = 0
        for obj in oss2.ObjectIterator(self.bucket, prefix=oss_prefix):
            self.bucket.delete_object(obj.key)
            deleted_count += 1

        return deleted_count

    def download_object(self, key: str) -> bytes:
        """
        Download an object's content from OSS.

        Args:
            key: Object key in OSS

        Returns:
            Raw bytes of the object
        """
        return self.bucket.get_object(key).read()

    def object_exists(self, oss_path: str) -> bool:
        """
        Check if an object exists in OSS.

        Args:
            oss_path: Object path in OSS

        Returns:
            True if object exists
        """
        return self.bucket.object_exists(oss_path)

    def set_bucket_policy_public_read(self):
        """
        Set bucket policy to allow public read access.

        WARNING: This makes ALL objects in the bucket publicly readable.
        Should only be called during initial setup.
        """
        from oss2.models import BUCKET_ACL_PUBLIC_READ
        self.bucket.put_bucket_acl(BUCKET_ACL_PUBLIC_READ)

    def get_bucket_info(self) -> Dict[str, any]:
        """
        Get bucket information.

        Returns:
            Dictionary with bucket details
        """
        info = self.bucket.get_bucket_info()
        return {
            'name': info.name,
            'location': info.location,
            'creation_date': info.creation_date,
            'storage_class': info.storage_class,
        }
