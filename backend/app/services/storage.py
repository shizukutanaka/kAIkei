"""S3互換オブジェクトストレージ抽象（証憑ファイル本体の保存）。

同期のboto3クライアントをrun_in_threadpoolでイベントループ外に逃がして非同期化する。
モジュール変数 `storage` を各所から参照し、テストではインメモリ実装に差し替え可能にする。
"""
import logging

from fastapi.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


class S3Storage:
    """MinIO / S3互換ストレージへの put/get ラッパー。"""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name="us-east-1",
                # MinIOはパススタイルアドレッシングが必要。
                config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
            )
        return self._client

    def _ensure_bucket_sync(self) -> None:
        from botocore.exceptions import ClientError

        client = self._get_client()
        try:
            client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        except ClientError:
            client.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    def _put_sync(self, key: str, data: bytes, content_type: str | None) -> None:
        self._ensure_bucket_sync()
        kwargs = {"Bucket": settings.S3_BUCKET_NAME, "Key": key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        self._get_client().put_object(**kwargs)

    def _get_sync(self, key: str) -> bytes:
        resp = self._get_client().get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return resp["Body"].read()

    async def put_object(self, key: str, data: bytes, content_type: str | None = None) -> None:
        await run_in_threadpool(self._put_sync, key, data, content_type)

    async def get_object(self, key: str) -> bytes:
        return await run_in_threadpool(self._get_sync, key)


class InMemoryStorage:
    """テスト用インメモリストレージ。"""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def put_object(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self._store[key] = bytes(data)

    async def get_object(self, key: str) -> bytes:
        if key not in self._store:
            raise KeyError(key)
        return self._store[key]


# 既定はS3/MinIO。テストではこのモジュール変数を差し替える。
storage = S3Storage()
