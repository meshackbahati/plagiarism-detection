import boto3
from botocore.client import Config
import os

class StorageService:
    def __init__(self, storage_type=None):
        self.storage_type = storage_type or os.getenv("STORAGE_TYPE", "local")
        if self.storage_type == "s3":
            self.s3 = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                config=Config(signature_version="s3v4"),
            )
            self.bucket_name = os.getenv("S3_BUCKET_NAME", "plagiarism-uploads")
        else:
            self.upload_dir = os.getenv("UPLOAD_DIR", "uploads")
            os.makedirs(self.upload_dir, exist_ok=True)

    def save(self, filename, content):
        if self.storage_type == "s3":
            self.s3.put_object(Bucket=self.bucket_name, Key=filename, Body=content)
            return f"s3://{self.bucket_name}/{filename}"
        else:
            path = os.path.realpath(os.path.join(self.upload_dir, filename))
            if not path.startswith(os.path.realpath(self.upload_dir) + os.sep):
                raise ValueError("Invalid storage path")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
            return path

    def delete(self, filename):
        if self.storage_type == "s3":
            self.s3.delete_object(Bucket=self.bucket_name, Key=filename)
        else:
            path = os.path.realpath(os.path.join(self.upload_dir, filename))
            if path.startswith(os.path.realpath(self.upload_dir) + os.sep) and os.path.exists(path):
                os.remove(path)

    def get_presigned_url(self, filename):
        if self.storage_type == "s3":
            return self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": filename},
                ExpiresIn=3600,
            )
        else:
            # For local storage, return a relative URL that the frontend can use
            # Assuming the backend serves the 'uploads' directory at /uploads
            return f"/api/v1/files/{filename}"
