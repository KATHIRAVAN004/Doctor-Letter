import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
S3_BUCKET = os.environ.get("S3_BUCKET", "doctor-letters-prod")

_s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4"),
)


def upload_html(mobile, letter_id, html):
    key = f"letters/{mobile}/{letter_id}.html"
    _s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )
    return key


def download_html(key):
    try:
        obj = _s3.get_object(Bucket=S3_BUCKET, Key=key)
        return obj["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise