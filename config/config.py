"""
NeMo Guardrails Custom Configuration Hook.
Registers a zero-dependency in-memory embedding index to bypass FastEmbed/ONNX.
"""

from nemoguardrails.embeddings.index import EmbeddingsIndex, IndexItem


class NoopEmbeddingsIndex(EmbeddingsIndex):
    """
    Lightweight, pure-Python in-memory index.
    Eliminates heavy HuggingFace downloads and ONNX CPU incompatibility in cloud VMs.
    """
    def __init__(self, **kwargs):
        self._items = []

    @property
    def embedding_size(self):
        return 0

    @property
    def cache_config(self):
        return None

    async def _get_embeddings(self, texts):
        return []

    async def add_item(self, item: IndexItem):
        self._items.append(item)

    async def add_items(self, items):
        self._items.extend(items)

    async def build(self):
        pass

    async def search(self, text: str, max_results: int = 1):
        return []


def init(rails):
    """Called automatically by NeMo Guardrails during initialization."""
    rails.embedding_search_providers["noop"] = lambda **kwargs: NoopEmbeddingsIndex(**kwargs)