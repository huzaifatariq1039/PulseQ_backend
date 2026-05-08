import os
import logging
from typing import Optional

import boto3
from botocore.client import Config

from app.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, R2_ENDPOINT_URL, R2_BUCKET_NAME, R2_REGION

logger = logging.getLogger(__name__)


def _get_s3_client():
    """Create and return a boto3 S3 client configured for a custom endpoint (Cloudflare R2).

    Relies on env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, R2_ENDPOINT_URL, R2_REGION
    """
    if not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and R2_ENDPOINT_URL):
        raise RuntimeError("S3/R2 credentials or endpoint not configured (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, R2_ENDPOINT_URL)")

    # Use signature_version='s3v4' for compatibility
    boto_config = Config(signature_version='s3v4', s3={'addressing_style': 'virtual'})

    client = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=R2_REGION or None,
        config=boto_config,
    )
    return client


def upload_bytes(key: str, body: bytes, content_type: Optional[str] = None, bucket: Optional[str] = None, acl: str = "public-read") -> str:
    """Upload raw bytes to the configured bucket and return the public URL.

    - `key` is the object key/path inside the bucket (e.g. 'avatars/userid.png')
    - `body` is the file bytes
    - `content_type` optional MIME type
    - `bucket` overrides the configured R2_BUCKET_NAME
    Returns the constructed public URL using the R2_ENDPOINT_URL and bucket.
    """
    bkt = bucket or R2_BUCKET_NAME
    if not bkt:
        raise RuntimeError("R2 bucket name not configured (R2_BUCKET_NAME)")

    client = _get_s3_client()

    extra_args = {}
    if content_type:
        extra_args['ContentType'] = content_type
    # Cloudflare R2 does not support ACLs for anonymous buckets in the same way as S3; still include for compatibility
    try:
        client.put_object(Bucket=bkt, Key=key, Body=body, ACL=acl, **extra_args)
    except Exception as e:
        logger.error(f"Failed to upload object to R2: {e}")
        raise

    # Construct a public URL. For Cloudflare R2 the endpoint typically supports direct object fetch:
    # {endpoint}/{bucket}/{key}
    public_url = f"{R2_ENDPOINT_URL.rstrip('/')}/{bkt}/{key}"
    return public_url
