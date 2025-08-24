# modules/embeddings/embeddeder.py
import json
from langchain_core.documents import Document
from .flattener import flatten_json

def safe_metadata(meta: dict) -> dict:
    return {k: str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in meta.items()}

def json_to_documents(json_path, exclude_keys: set = None):

    if exclude_keys is None:
        exclude_keys = set()

    with open(json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    flattened = flatten_json(data=raw_data, exclude_keys=exclude_keys)

    documents = [
        Document(
            page_content=f"{key}: {value}",  # 🧠 Embedding full context
            metadata=safe_metadata({"field": key, "index": i, "source": json_path})
        )
        for i, (key, value) in enumerate(flattened) # (key, value) -> (question, answer) 
    ]
    return documents