# -*- coding: utf-8 -*-
"""
ima 上传第二步：把本地文件传到 COS（enterprise-analyst Step 3.8）

前置：先调 mcp__ima-mcp__create_media 拿到 media_id + cos_credential，
把 cos_credential 那段 JSON 原样存成 cred.json（外层可有 {"cos_credential":{...}} 也可直接是内层对象）。

用法：
    python scripts/ima_upload_cos.py --cred cred.json --file 报告.html [--result out.txt]

结果写入 --result 指定的 UTF-8 文件（本机 PowerShell 不回显 stdout，必须落盘再 Read）。
成功写 "OK ETag=..."；失败写 "ERROR <异常类型>: <信息>"。

content_type：不传时按扩展名自动映射（html→text/html、md→text/markdown、pdf→application/pdf …），
映射不到则报错退出 —— ima 禁止用 application/octet-stream 兜底。

依赖：cos-python-sdk-v5（只装在隔离 venv）
    C:\\Users\\zx\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\python.exe
"""
import argparse
import json
import os
import sys

EXT_MAP = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
    "htm": "text/html",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "epub": "application/epub+zip",
    "xmind": "application/x-xmind",
}


def load_cred(path):
    obj = json.load(open(path, encoding="utf-8"))
    if "cos_credential" in obj:
        obj = obj["cos_credential"]
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", required=True, help="create_media 返回的凭证 JSON 文件")
    ap.add_argument("--file", required=True, help="待上传的本地文件绝对路径")
    ap.add_argument("--result", default=None, help="结果输出文件（UTF-8）")
    ap.add_argument("--content-type", default=None)
    args = ap.parse_args()

    out_path = args.result or os.path.join(os.path.dirname(os.path.abspath(args.file)), "_cos_result.txt")
    try:
        local = os.path.abspath(args.file)
        if not os.path.exists(local):
            raise FileNotFoundError(local)

        ext = os.path.splitext(local)[1].lstrip(".").lower()
        ctype = args.content_type or EXT_MAP.get(ext)
        if not ctype:
            raise ValueError("无法根据扩展名 .%s 推断 content_type，请显式传 --content-type" % ext)

        cred = load_cred(args.cred)
        from qcloud_cos import CosConfig, CosS3Client

        cfg = CosConfig(
            Region=cred["region"],
            SecretId=cred["secret_id"],
            SecretKey=cred["secret_key"],
            Token=cred["token"],
            Scheme="https",
        )
        client = CosS3Client(cfg)
        resp = client.put_object_from_local_file(
            Bucket=cred["bucket_name"],
            LocalFilePath=local,
            Key=cred["cos_key"],
            ContentType=ctype,
        )
        msg = "OK ETag=%s size=%d" % (resp.get("ETag", ""), os.path.getsize(local))
    except Exception as e:
        msg = "ERROR %s: %s" % (type(e).__name__, e)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(msg + "\n")
    print(msg)
    return 0 if msg.startswith("OK") else 1


if __name__ == "__main__":
    sys.exit(main())
