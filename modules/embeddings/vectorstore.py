# modules/embeddings/vectorestore.py
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def embed_and_store(documents, persist_dir, embed_model="mxbai-embed-large", collection_name='json_context'):
    embeddings = OllamaEmbeddings(model=embed_model)
    db = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_dir
    )
    db.add_documents(documents) # This will auto-persist
    # db.persist() # Remove: Because Chroma now auto-persists data as soon as .add_documents() is called.
    return db

def filter_relevant_contexts(
    query: str,
    doc_texts: list,
    embedding_func,
    min_keep: int = 1,
    debug: bool = False
) -> list:
    """
    Dynamically filters document texts based on cosine similarity to the query embedding.

    Args:
        query (str): User's input question.
        doc_texts (list): List of document strings retrieved from the vectorstore.
        embedding_func: LangChain embedding function.
        min_keep (int): Minimum number of documents to retain, even if scores are low.
        debug (bool): Whether to print similarity scores.

    Returns:
        list: Filtered document texts based on dynamic similarity threshold.
    """
    if not doc_texts:
        return []

    # Step 1: Compute embeddings
    query_vec = embedding_func.embed_query(query)
    doc_vecs = embedding_func.embed_documents(doc_texts)

    # Step 2: Compute cosine similarities
    sim_scores = cosine_similarity([query_vec], doc_vecs)[0]

    # Step 3: Dynamic threshold based on mean + weighted std deviation
    avg = np.mean(sim_scores)
    std = np.std(sim_scores)
    threshold = avg + (std * 0.25) # small boost above average

    # Step 4: Filter based on threshold
    scored_docs = list(zip(doc_texts, sim_scores))
    filtered = [(text, score) for text, score in scored_docs if score >= threshold]

    # Step 5: Sort by similarity
    filtered = sorted(filtered, key=lambda x: x[1], reverse=True)

    # Step 6: Ensure at least `min_keep` items are kept (by top scores)
    if len(filtered) < min_keep:
        sorted_docs = sorted(scored_docs, key=lambda x: x[1], reverse=True)
        filtered = sorted_docs[:min_keep]

    # Debugging: Print scores for insight
    if debug:
        valid_text = []
        print("\n-------- [DEBUG: Start] Similarity Scores --------")
        for i, (text, score) in enumerate(scored_docs):
            keep = "✔" if any(text == f[0] for f in filtered) else "✘"
            if any(text == f[0] for f in filtered): valid_text.append(text)
            print(f"Doc {i+1}: Score = {score:.4f} {keep}")
        print("\n💡 Matched Entries:")
        for i, text in enumerate(valid_text, start=1):
            print(f"[{i}] {text}")
        print("------------------- [DEBUG: End] -------------------")

    return [text for text, _ in filtered]
