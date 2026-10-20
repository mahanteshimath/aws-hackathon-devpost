"""Blob/JSON storage: local folder for dev, S3 in the cloud. Story docs store keys; URLs are minted on read."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .config import settings


class Storage:
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes | None:  # pragma: no cover - interface
        raise NotImplementedError

    def url(self, key: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, key: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def put_json(self, key: str, obj: Any) -> None:
        self.put_bytes(key, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json")

    def get_json(self, key: str) -> Any | None:
        raw = self.get_bytes(key)
        return json.loads(raw) if raw is not None else None


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"invalid key: {key}")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            tmp.write_bytes(data)
            tmp.replace(path)  # atomic so pollers never read half a file

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.exists() else None

    def url(self, key: str) -> str:
        return f"/files/{key}"

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage(Storage):
    def __init__(self, bucket: str, region: str):
        import boto3

        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get_bytes(self, key: str) -> bytes | None:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def url(self, key: str) -> str:
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=6 * 3600
        )


_store: Storage | None = None
_store_lock = threading.Lock()


def store() -> Storage:
    global _store
    with _store_lock:
        if _store is None:
            cfg = settings()
            if cfg.storage == "s3":
                if not cfg.bucket:
                    raise RuntimeError("CRAYON_STORAGE=s3 requires CRAYON_BUCKET")
                _store = S3Storage(cfg.bucket, cfg.region)
            else:
                _store = LocalStorage(cfg.data_dir)
        return _store
