#!/usr/bin/env python3
import argparse
import sys

from aliyundrive_client import AliyunDriveClient, AliyunDriveError


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a file to Aliyun Drive.")
    parser.add_argument("--input", required=True, help="Local file to upload")
    parser.add_argument("--refresh-token", required=True, help="Aliyun Drive refresh token")
    args = parser.parse_args()

    client = AliyunDriveClient(args.refresh_token)
    try:
        info = client.upload_file(args.input)
        print("---ALIYUNDRIVE_UPLOAD_RESULT---")
        print(f"ALIYUNDRIVE_FILE_ID: {info['file_id']}")
        print(f"ALIYUNDRIVE_FILE_NAME: {info['file_name']}")
        print(f"ALIYUNDRIVE_DRIVE_ID: {info['drive_id']}")
        return 0
    except AliyunDriveError as exc:
        print(f"上传失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
