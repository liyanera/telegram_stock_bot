"""
Semantic memory using ChromaDB + sentence-transformers.
Add documents via add_knowledge(); query via search().
"""
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "chroma_db"
_COLLECTION = "stock_knowledge"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(_DB_PATH))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _collection = _client.get_or_create_collection(
            name=_COLLECTION,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_knowledge(doc_id: str, text: str, metadata=None):
    """Add or update a knowledge document."""
    col = _get_collection()
    col.upsert(
        ids=[doc_id],
        documents=[text],
        metadatas=[metadata or {}],
    )


def add_knowledge_bulk(docs: list[dict]):
    """docs: list of {id, text, metadata}"""
    col = _get_collection()
    col.upsert(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[d.get("metadata", {}) for d in docs],
    )


def search(query: str, n_results: int = 4) -> list[dict]:
    """Return top-k relevant knowledge chunks."""
    col = _get_collection()
    if col.count() == 0:
        return []
    results = col.query(query_texts=[query], n_results=min(n_results, col.count()))
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    return [{"text": d, "metadata": m} for d, m in zip(docs, metas)]


def delete_knowledge(doc_id: str):
    _get_collection().delete(ids=[doc_id])


def list_knowledge(limit: int = 100) -> list[dict]:
    col = _get_collection()
    result = col.get(limit=limit)
    return [
        {"id": i, "text": d[:200], "metadata": m}
        for i, d, m in zip(result["ids"], result["documents"], result["metadatas"])
    ]
