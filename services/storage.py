"""Pluggable file storage.

Local disk for development; Supabase Storage for cloud deploys (where the
container filesystem is ephemeral). Selected via STORAGE_BACKEND. Paths are the
same per-user relative form everywhere: "<user_id>/<filename>".
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from functools import lru_cache

from config import settings


class Storage:
    def put(self, relpath: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        raise NotImplementedError

    def get(self, relpath: str) -> bytes | None:
        raise NotImplementedError

    def delete(self, relpath: str) -> None:
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self) -> None:
        self.root = settings.storage_path  # ensures the uploads/ dir exists

    def _abs(self, relpath: str):
        return self.root / relpath

    def put(self, relpath, data, content_type="application/octet-stream"):
        p = self._abs(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, relpath):
        p = self._abs(relpath)
        return p.read_bytes() if p.exists() else None

    def delete(self, relpath):
        try:
            self._abs(relpath).unlink(missing_ok=True)
        except Exception:
            pass


class SupabaseStorage(Storage):
    """Talks to Supabase Storage's REST API with the service-role key."""

    def __init__(self) -> None:
        self.base = settings.supabase_url.rstrip("/") + "/storage/v1"
        self.bucket = settings.storage_bucket
        self.key = settings.supabase_service_role_key
        self._ensure_bucket()

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.key}", "apikey": self.key}
        if extra:
            h.update(extra)
        return h

    def _ensure_bucket(self) -> None:
        body = json.dumps(
            {"id": self.bucket, "name": self.bucket, "public": False}
        ).encode()
        req = urllib.request.Request(
            f"{self.base}/bucket", data=body, method="POST",
            headers=self._headers({"Content-Type": "application/json"}),
        )
        try:
            urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as e:
            # 400/409 == bucket already exists; anything else we ignore (best effort)
            if e.code not in (400, 409):
                pass
        except Exception:
            pass

    def put(self, relpath, data, content_type="application/octet-stream"):
        url = f"{self.base}/object/{self.bucket}/{relpath}"
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers=self._headers({"Content-Type": content_type, "x-upsert": "true"}),
        )
        urllib.request.urlopen(req, timeout=45)

    def get(self, relpath):
        url = f"{self.base}/object/{self.bucket}/{relpath}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            # Supabase returns 400 ("Object not found") rather than 404 for a
            # missing object on this endpoint; treat both as "not found".
            if e.code in (400, 404):
                return None
            raise

    def delete(self, relpath):
        url = f"{self.base}/object/{self.bucket}/{relpath}"
        req = urllib.request.Request(url, method="DELETE", headers=self._headers())
        try:
            urllib.request.urlopen(req, timeout=20)
        except Exception:
            pass


@lru_cache
def get_storage() -> Storage:
    if (
        settings.storage_backend == "supabase"
        and settings.supabase_url
        and settings.supabase_service_role_key
    ):
        return SupabaseStorage()
    return LocalStorage()
