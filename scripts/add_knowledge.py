"""
CLI tool to add a single knowledge entry to ChromaDB.
Run: python scripts/add_knowledge.py "doc-id" "Your knowledge text here"
Or:  python scripts/add_knowledge.py "doc-id" --file path/to/file.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.vector_memory import add_knowledge, list_knowledge, delete_knowledge


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        print("\nOther commands:")
        print("  python scripts/add_knowledge.py --list")
        print("  python scripts/add_knowledge.py --delete <doc-id>")
        return

    if args[0] == "--list":
        docs = list_knowledge()
        for d in docs:
            print(f"[{d['id']}] {d['text'][:100]}...")
        print(f"\nTotal: {len(docs)} chunks")
        return

    if args[0] == "--delete" and len(args) >= 2:
        delete_knowledge(args[1])
        print(f"Deleted: {args[1]}")
        return

    if len(args) < 2:
        print("Usage: python scripts/add_knowledge.py <id> <text>")
        print("       python scripts/add_knowledge.py <id> --file <path>")
        return

    doc_id = args[0]
    if len(args) >= 3 and args[1] == "--file":
        text = Path(args[2]).read_text()
    else:
        text = args[1]

    add_knowledge(doc_id, text)
    print(f"Added knowledge: [{doc_id}] ({len(text)} chars)")


if __name__ == "__main__":
    main()
