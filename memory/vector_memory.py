"""
Semantic memory using ChromaDB + sentence-transformers.
Supports credibility-weighted search — theses with higher credibility
scores rank higher for the same semantic relevance.
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
    col = _get_collection()
    col.upsert(ids=[doc_id], documents=[text], metadatas=[metadata or {}])


def add_knowledge_bulk(docs: list):
    col = _get_collection()
    col.upsert(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[d.get("metadata", {}) for d in docs],
    )


def update_credibility(doc_id: str, credibility: float):
    """Update credibility score in ChromaDB metadata."""
    col = _get_collection()
    existing = col.get(ids=[doc_id])
    if not existing["ids"]:
        return
    meta = existing["metadatas"][0]
    meta["credibility"] = round(credibility, 3)
    col.update(ids=[doc_id], metadatas=[meta])


def search(query: str, n_results: int = 4) -> list:
    """
    Return top-k relevant chunks, re-ranked by credibility.
    Score = semantic_similarity * (0.6 + 0.4 * credibility)
    Neutral credibility (0.5) gives no penalty/boost.
    """
    col = _get_collection()
    if col.count() == 0:
        return []

    # Fetch more candidates than needed, then re-rank
    fetch = min(n_results * 3, col.count())
    results = col.query(
        query_texts=[query],
        n_results=fetch,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]  # cosine distance: lower = more similar

    scored = []
    for doc, meta, dist in zip(docs, metas, distances):
        similarity = 1 - dist  # convert distance to similarity
        credibility = float(meta.get("credibility", 0.5))
        # Credibility boosts/penalizes: 0.5 = neutral, 1.0 = +40% boost, 0.0 = -40%
        adjusted = similarity * (0.6 + 0.4 * credibility)
        scored.append({"text": doc, "metadata": meta, "score": adjusted})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:n_results]


def delete_knowledge(doc_id: str):
    _get_collection().delete(ids=[doc_id])


def list_knowledge(limit: int = 100) -> list:
    col = _get_collection()
    result = col.get(limit=limit)
    return [
        {"id": i, "text": d[:200], "metadata": m}
        for i, d, m in zip(result["ids"], result["documents"], result["metadatas"])
    ]
