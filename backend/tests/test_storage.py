import pytest

from app.services.storage import InMemoryStorage

pytestmark = pytest.mark.asyncio


async def test_put_get_roundtrip():
    store = InMemoryStorage()
    await store.put_object("a/b/inv.pdf", b"hello", "application/pdf")
    assert await store.get_object("a/b/inv.pdf") == b"hello"


async def test_get_missing_raises():
    store = InMemoryStorage()
    with pytest.raises(KeyError):
        await store.get_object("nope")
