# %%
# Running Imports #
import os
import sys

import boto3
from botocore.client import Config
from dotenv import load_dotenv

# append grandparent
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_utils import data_dir, grandparent_dir  # noqa: F401
from utils.display_tools import (  # noqa: F401
    pprint_df,
    pprint_dict,
    pprint_ls,
    print_logger,
)

# %%
# Variables #


dotenv_path = os.path.join(grandparent_dir, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("S3_ENDPOINT"),
    aws_access_key_id=os.getenv("MINIO_ROOT_USER"),
    aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD"),
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


# %%
# Functions #


def ensure_bucket_exists(bucket_name):
    try:
        s3.head_bucket(Bucket=bucket_name)
    except s3.exceptions.ClientError:
        print(f"Bucket: '{bucket_name}' does not exist, creating it now.")
        s3.create_bucket(Bucket=bucket_name)


def list_bucket_contents(bucket_name):
    """List all objects in an S3 bucket."""
    try:
        response = s3.list_objects_v2(Bucket=bucket_name)
        if "Contents" in response:
            for obj in response["Contents"]:
                print(obj["Key"])
        else:
            print("No objects found in the bucket.")
    except Exception as e:
        print(f"Error listing bucket contents: {e}")


def upload_file_to_s3(local_file_path, bucket_name, s3_key):
    """Upload a file to an S3 bucket."""
    try:
        s3.upload_file(local_file_path, bucket_name, s3_key)
        print(f"File {local_file_path} uploaded to {bucket_name}/{s3_key}.")
        return True
    except Exception as e:
        print(f"Error uploading file: {e}")
        return False


def download_file_from_s3(bucket_name, s3_key, local_file_path):
    """Download a file from an S3 bucket."""
    try:
        s3.download_file(bucket_name, s3_key, local_file_path)
        print(f"File {bucket_name}/{s3_key} downloaded to {local_file_path}.")
    except Exception as e:
        print(f"Error downloading file: {e}")


# %%
