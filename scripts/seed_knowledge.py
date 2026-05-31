"""
Seed the ChromaDB vector store with knowledge documents.
Run: python scripts/seed_knowledge.py
Add your own .md or .txt files to the knowledge/ directory and re-run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.vector_memory import add_knowledge_bulk

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def seed():
    docs = []
    for filepath in KNOWLEDGE_DIR.glob("**/*.md"):
        text = filepath.read_text()
        chunks = chunk_text(text)
        for idx, chunk in enumerate(chunks):
            docs.append({
                "id": f"{filepath.stem}_{idx}",
                "text": chunk,
                "metadata": {"source": filepath.name, "chunk": idx},
            })

    for filepath in KNOWLEDGE_DIR.glob("**/*.txt"):
        text = filepath.read_text()
        chunks = chunk_text(text)
        for idx, chunk in enumerate(chunks):
            docs.append({
                "id": f"{filepath.stem}_{idx}",
                "text": chunk,
                "metadata": {"source": filepath.name, "chunk": idx},
            })

    if not docs:
        print("No documents found in knowledge/")
        return

    add_knowledge_bulk(docs)
    print(f"Seeded {len(docs)} chunks from {KNOWLEDGE_DIR}")


if __name__ == "__main__":
    seed()
