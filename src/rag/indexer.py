"""
Knowledge Base Indexer for SmartDesk AI.
Performs chunking, dense vector indexing with OpenAI text-embedding-3-small via ChromaDB,
and sparse keyword indexing via BM25.
"""

import hashlib
import json
import logging
import os
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

load_dotenv()
logger = logging.getLogger(__name__)


def stem_word(w: str) -> str:
    """Lightweight suffix stemmer for common English plurals and inflections."""
    w = w.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 3:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    if w.endswith("ing") and len(w) > 4:
        return w[:-3]
    return w


def simple_tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words including stemmed variants."""
    words = re.findall(r"\b\w+\b", text.lower())
    tokens = []
    for w in words:
        tokens.append(w)
        s = stem_word(w)
        if s != w:
            tokens.append(s)
    return tokens


def generate_fallback_embedding(text: str, dim: int = 1536) -> List[float]:
    """
    Generate a deterministic pseudo-embedding vector based on MD5 hashing.
    Used when OPENAI_API_KEY is not available (e.g., offline test environments).
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = []
    for i in range(dim):
        b = h[i % len(h)]
        val = (b / 128.0) - 1.0 + ((i % 17) * 0.01)
        vec.append(val)
    # L2 normalize
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


class KnowledgeBaseIndexer:
    """
    Handles chunking, dense embedding creation, ChromaDB storage,
    and BM25 sparse index serialization.
    """

    def __init__(
        self,
        kb_path: Optional[str] = None,
        chroma_dir: Optional[str] = None,
        collection_name: str = "smartdesk_kb",
        embedding_model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
    ):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.kb_path = Path(kb_path) if kb_path else base_dir / "data" / "knowledge_base" / "kb_entries.json"
        self.chroma_dir = Path(chroma_dir) if chroma_dir else base_dir / "data" / "chroma_db"
        self.bm25_path = self.chroma_dir / "bm25_index.pkl"
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "SmartDesk AI Enterprise Knowledge Base"}
        )

        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            if self.api_key:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.api_key)
        return self._openai_client

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings from OpenAI or fallback to local deterministic vector."""
        client = self._get_openai_client()
        if client and self.api_key and not self.api_key.startswith("mock_"):
            try:
                response = client.embeddings.create(
                    model=self.embedding_model,
                    input=texts
                )
                return [item.embedding for item in response.data]
            except Exception as e:
                logger.warning(f"OpenAI embedding call failed ({e}). Falling back to local embedding.")

        return [generate_fallback_embedding(t) for t in texts]

    def load_documents(self) -> List[Dict[str, Any]]:
        """Load structured entries from the JSON master file."""
        if not self.kb_path.exists():
            raise FileNotFoundError(f"Knowledge base file not found at {self.kb_path}")

        with open(self.kb_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def chunk_document(self, entry: Dict[str, Any], max_chunk_chars: int = 800, overlap_chars: int = 150) -> List[Dict[str, Any]]:
        """
        Chunking Strategy:
        Each policy document is segmented semantically. If content exceeds max_chunk_chars,
        it splits into overlapping character windows preserving sentence boundaries.
        Also includes a synthetic summary chunk containing the title, category, keywords,
        and sample questions to maximize retrieval hit rate for varied user queries.
        """
        chunks = []
        doc_id = entry["id"]
        title = entry["title"]
        domain = entry["domain"]
        category = entry["category"]
        keywords = ", ".join(entry.get("keywords", []))
        content = entry["content"]
        sample_questions = "\n".join(f"- {q}" for q in entry.get("sample_questions", []))

        # Chunk 1: Primary policy text (split if long)
        if len(content) <= max_chunk_chars:
            chunk_text = f"Title: {title}\nDomain: {domain} | Category: {category}\nPolicy Content: {content}"
            chunks.append({
                "chunk_id": f"{doc_id}_c1",
                "doc_id": doc_id,
                "domain": domain,
                "category": category,
                "title": title,
                "text": chunk_text,
                "type": "policy_body"
            })
        else:
            # Sliding window chunking
            start = 0
            idx = 1
            while start < len(content):
                end = min(start + max_chunk_chars, len(content))
                # Try to break at a period or space
                if end < len(content):
                    space_pos = content.rfind(". ", start, end)
                    if space_pos != -1 and space_pos > start + 200:
                        end = space_pos + 1

                sub_slice = content[start:end].strip()
                chunk_text = f"Title: {title} (Part {idx})\nDomain: {domain} | Category: {category}\nPolicy Content: {sub_slice}"
                chunks.append({
                    "chunk_id": f"{doc_id}_c{idx}",
                    "doc_id": doc_id,
                    "domain": domain,
                    "category": category,
                    "title": title,
                    "text": chunk_text,
                    "type": "policy_body"
                })
                idx += 1
                start = end - overlap_chars if end < len(content) else end

        # Chunk 2: FAQ & Keyword Index Chunk (enhances sparse & dense question-intent match)
        faq_text = (
            f"Title: {title} — Frequently Asked Questions & Keywords\n"
            f"Domain: {domain} | Category: {category}\n"
            f"Keywords: {keywords}\n"
            f"Relevant Questions Answered:\n{sample_questions}\n"
            f"Summary: {content[:300]}..."
        )
        chunks.append({
            "chunk_id": f"{doc_id}_faq",
            "doc_id": doc_id,
            "domain": domain,
            "category": category,
            "title": title,
            "text": faq_text,
            "type": "faq_keywords"
        })

        return chunks

    def build_indexes(self) -> Tuple[int, int]:
        """
        Chunks all documents, indexes them into ChromaDB (dense),
        and builds the BM25 model (sparse).
        Returns: (total_documents, total_chunks)
        """
        documents = self.load_documents()
        all_chunks = []
        for doc in documents:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)

        logger.info(f"Loaded {len(documents)} documents, created {len(all_chunks)} chunks.")

        # 1. Index into ChromaDB
        ids = [c["chunk_id"] for c in all_chunks]
        texts = [c["text"] for c in all_chunks]
        metadatas = [
            {
                "doc_id": c["doc_id"],
                "domain": c["domain"],
                "category": c["category"],
                "title": c["title"],
                "type": c["type"]
            }
            for c in all_chunks
        ]

        # Generate embeddings in batches of 50
        batch_size = 50
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_embeddings = self.get_embeddings(batch_texts)
            embeddings.extend(batch_embeddings)

        # Upsert into ChromaDB
        self.collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas
        )
        logger.info(f"Indexed {len(ids)} chunks into ChromaDB collection '{self.collection_name}'.")

        # 2. Build BM25 Sparse Index
        tokenized_corpus = [simple_tokenize(c["text"]) for c in all_chunks]
        bm25_model = BM25Okapi(tokenized_corpus)

        # Save BM25 artifact
        bm25_data = {
            "bm25_model": bm25_model,
            "chunks": all_chunks
        }
        with open(self.bm25_path, "wb") as f:
            pickle.dump(bm25_data, f)
        logger.info(f"Serialized BM25 index to {self.bm25_path}")

        return len(documents), len(all_chunks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    indexer = KnowledgeBaseIndexer()
    doc_count, chunk_count = indexer.build_indexes()
    print(f"Indexing complete! Documents: {doc_count}, Chunks indexed: {chunk_count}")
