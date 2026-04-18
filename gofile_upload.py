#!/usr/bin/env python3
import argparse
import sys

from gofile_client import GofileClient, GofileError


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a file to Gofile.")
    parser.add_argument("--input", required=True, help="Local file to upload")
    args = parser.parse_args()

    client = GofileClient()
    try:
        info = client.upload_file(args.input)
        print("---GOFILE_UPLOAD_RESULT---")
        print(f"GOFILE_DOWNLOAD_PAGE: {info['downloadPage']}")
        print(f"GOFILE_CODE: {info['code']}")
        print(f"GOFILE_FILE_ID: {info['fileId']}")
        print(f"GOFILE_FILE_NAME: {info['fileName']}")
        return 0
    except GofileError as exc:
        print(f"上传失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())