import argparse
import os
import shutil
from .utils import get_file_hash
from .embedder import json_to_documents
from .vectorstore import embed_and_store

# Global constant for hash file path
HASH_FILE = None  # This will be set by set_hash_file()

def set_hash_file(filepath):
    """Sets the hash file path and ensures it exists."""
    global HASH_FILE
    HASH_FILE = filepath

    # Ensure the directory exists for the hash file
    hash_dir = os.path.dirname(HASH_FILE)
    os.makedirs(hash_dir, exist_ok=True)

    if not os.path.exists(HASH_FILE):
        print(f"📂  Hash file not found. Setting up at: {HASH_FILE}")
        with open(HASH_FILE, "w") as f:
            f.write("")  # Start with an empty hash file

    return HASH_FILE

def run_embedding(json_path, chroma_dir, embed_model, collection_name, exclude_keys: set = None):

    if exclude_keys is None:
        exclude_keys = set()

    def has_changed(json_path):
        current = get_file_hash(json_path)
        if os.path.exists(HASH_FILE):
            with open(HASH_FILE) as f:
                stored = f.read().strip()
            return current != stored
        return True

    def update_hash(json_path):
        current = get_file_hash(json_path)
        with open(HASH_FILE, "w") as f:
            f.write(current)

    def clean_chroma_dir(filepath):
        if os.path.exists(filepath):
            shutil.rmtree(filepath)

    if not has_changed(json_path):
        print("✅   Embeddings up to date - JSON unchanged.")
        return

    print("🔍   Reading and flattening JSON...")
    docs = json_to_documents(json_path, exclude_keys)

    print("🏗️   Cleaning previous embeddings...")
    clean_chroma_dir(chroma_dir)

    print("📦   Embedding and storing in Chroma...")
    embed_and_store(docs, chroma_dir, embed_model, collection_name)

    update_hash(json_path)
    print(f"✅  Embedded {len(docs)} chunks.")

def search(chroma_dir, query, k=3, embed_model="mxbai-embed-large"):
    from langchain_ollama import OllamaEmbeddings
    from langchain_chroma import Chroma

    db = Chroma(
        collection_name="jobpilot_user_context",
        embedding_function=OllamaEmbeddings(model=embed_model),
        persist_directory=chroma_dir
    )
    results = db.similarity_search(query, k=k)
    print("\n🔎 Top Matches:")
    for i, doc in enumerate(results):
        print(f"\n[{i+1}] {doc.page_content}\n→ Metadata: {doc.metadata}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JSON Embedding Tool")
    parser.add_argument("--json", type=str, help="Path to JSON file") # Optionally, we can use `default=` parameter
    parser.add_argument("--chroma", type=str, help="Chroma storage dir") # Optionally, we can use `default=` parameter
    parser.add_argument("--embed_model", type=str, default="mxbai-embed-large", help="Embedding model name")
    parser.add_argument("--collection_name", type=str, default="json_context", help="Embedding collection name")
    parser.add_argument("--search", type=str, help="Query string to search the vector DB")
    parser.add_argument("--k", type=int, default=3, help="Top K search results")

    args = parser.parse_args()

    if args.search:
        search(args.chroma, args.search, args.k, args.embed_model)
    else:
        run_embedding(args.json, args.chroma, args.embed_model, args.collection_name)