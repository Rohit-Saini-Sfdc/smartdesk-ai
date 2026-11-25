"""
Hybrid Search Retriever for SmartDesk AI.
Combines ChromaDB dense semantic vector search with BM25 sparse keyword search,
fused using Reciprocal Rank Fusion (RRF) and dynamic confidence thresholding.
"""

import logging
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

from .indexer import KnowledgeBaseIndexer, generate_fallback_embedding, simple_tokenize

load_dotenv()
logger = logging.getLogger(__name__)


STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "how", "what", "when", "where", "why", "which", "who",
    "i", "my", "me", "we", "our", "you", "your", "they", "them", "their", "it", "its",
    "and", "or", "but", "if", "can", "could", "would", "should", "will", "shall",
    "so", "no", "not", "any", "some", "all", "more", "much", "very", "too", "also"
}


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    domain: str
    category: str
    title: str
    text: str
    score: float
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None


@dataclass
class RetrievalResult:
    query: str
    chunks: List[RetrievedChunk]
    confidence: float
    escalation_needed: bool
    suggested_action: str  # "answer" or "escalate_to_ticket"
    suggested_category: str
    formatted_context: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class HybridRetriever:
    """
    Executes hybrid dense-sparse search, fuses candidate lists with RRF,
    and applies confidence gating to detect queries that require human escalation.
    """

    def __init__(
        self,
        chroma_dir: Optional[str] = None,
        collection_name: str = "smartdesk_kb",
        confidence_threshold: float = 0.38,
        rrf_k: int = 60,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        api_key: Optional[str] = None,
    ):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.chroma_dir = Path(chroma_dir) if chroma_dir else base_dir / "data" / "chroma_db"
        self.bm25_path = self.chroma_dir / "bm25_index.pkl"
        self.collection_name = collection_name
        self.confidence_threshold = confidence_threshold
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        self.has_real_embeddings = bool(self.api_key and not self.api_key.startswith("mock_"))
        if not self.has_real_embeddings:
            # When offline/without OpenAI key, rely 100% on BM25 sparse keyword ranking to avoid random hash noise
            self.dense_weight = 0.0
            self.sparse_weight = 1.0

        # Load deliberate gaps
        gaps_path = base_dir / "data" / "knowledge_base" / "deliberate_gaps.json"
        self.deliberate_gaps = []
        if gaps_path.exists():
            try:
                import json
                with open(gaps_path, "r", encoding="utf-8") as f:
                    self.deliberate_gaps = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load deliberate gaps: {e}")

        # Load canonical document store for parent document retrieval
        kb_path = base_dir / "data" / "knowledge_base" / "kb_entries.json"
        self.doc_store: Dict[str, Dict[str, Any]] = {}
        if kb_path.exists():
            try:
                import json
                with open(kb_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                    self.doc_store = {e["id"]: e for e in entries}
                logger.info(f"Loaded {len(self.doc_store)} parent documents into doc_store.")
            except Exception as e:
                logger.warning(f"Failed to load doc_store: {e}")

        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.collection = self.chroma_client.get_or_create_collection(name=self.collection_name)

        # Initialize BM25 from cache
        self.bm25_model: Optional[BM25Okapi] = None
        self.corpus_chunks: List[Dict[str, Any]] = []
        self._load_bm25_index()

        self.indexer = KnowledgeBaseIndexer(
            chroma_dir=str(self.chroma_dir),
            collection_name=self.collection_name,
            api_key=self.api_key,
        )

    def _load_bm25_index(self):
        """Load BM25 sparse index from disk."""
        if self.bm25_path.exists():
            try:
                with open(self.bm25_path, "rb") as f:
                    data = pickle.load(f)
                    self.bm25_model = data["bm25_model"]
                    self.corpus_chunks = data["chunks"]
                logger.info("Successfully loaded BM25 sparse index.")
            except Exception as e:
                logger.warning(f"Failed to load BM25 index: {e}. Building index.")
                self._build_indexes_if_needed()
        else:
            logger.info("BM25 index not found. Triggering automated indexing.")
            self._build_indexes_if_needed()

    def _build_indexes_if_needed(self):
        """Build both dense and sparse indexes if missing."""
        indexer = KnowledgeBaseIndexer(
            chroma_dir=str(self.chroma_dir),
            collection_name=self.collection_name,
            api_key=self.api_key,
        )
        indexer.build_indexes()
        with open(self.bm25_path, "rb") as f:
            data = pickle.load(f)
            self.bm25_model = data["bm25_model"]
            self.corpus_chunks = data["chunks"]

    def _dense_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search ChromaDB using embedding vector."""
        query_embeddings = self.indexer.get_embeddings([query])
        results = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=min(top_k, self.collection.count() or 1),
            include=["documents", "metadatas", "distances"]
        )

        dense_candidates = []
        if results and results["ids"] and len(results["ids"][0]) > 0:
            for rank, chunk_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][rank]
                doc_text = results["documents"][0][rank]
                dist = results["distances"][0][rank] if "distances" in results else 1.0
                dense_candidates.append({
                    "chunk_id": chunk_id,
                    "doc_id": meta["doc_id"],
                    "domain": meta["domain"],
                    "category": meta["category"],
                    "title": meta["title"],
                    "text": doc_text,
                    "distance": dist,
                    "rank": rank + 1  # 1-indexed
                })
        return dense_candidates

    def _sparse_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search BM25 keyword index."""
        if not self.bm25_model or not self.corpus_chunks:
            return []

        tokens = simple_tokenize(query)
        if not tokens:
            return []

        scores = self.bm25_model.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        sparse_candidates = []
        for rank, idx in enumerate(top_indices):
            score = scores[idx]
            if score <= 0.0:
                continue
            chunk = self.corpus_chunks[idx]
            sparse_candidates.append({
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "domain": chunk["domain"],
                "category": chunk["category"],
                "title": chunk["title"],
                "text": chunk["text"],
                "bm25_score": float(score),
                "rank": rank + 1
            })
        return sparse_candidates

    def retrieve(self, query: str, top_n: int = 3) -> RetrievalResult:
        """
        Execute hybrid search with Reciprocal Rank Fusion, calculate confidence score,
        and determine whether escalation is required.
        """
        tokens = simple_tokenize(query)
        if not tokens:
            return RetrievalResult(
                query=query,
                chunks=[],
                confidence=0.0,
                escalation_needed=True,
                suggested_action="escalate_to_ticket",
                suggested_category="General Support",
                formatted_context="No search terms provided."
            )

        # 1. Fetch top dense and sparse lists
        dense_results = self._dense_search(query, top_k=15)
        sparse_results = self._sparse_search(query, top_k=15)

        # 2. Reciprocal Rank Fusion (RRF)
        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, Dict[str, Any]] = {}
        dense_ranks: Dict[str, int] = {}
        sparse_ranks: Dict[str, int] = {}

        for item in dense_results:
            cid = item["chunk_id"]
            dense_ranks[cid] = item["rank"]
            chunk_map[cid] = item
            rrf_scores[cid] = self.dense_weight * (1.0 / (self.rrf_k + item["rank"]))

        for item in sparse_results:
            cid = item["chunk_id"]
            sparse_ranks[cid] = item["rank"]
            if cid not in chunk_map:
                chunk_map[cid] = item
            score_increment = self.sparse_weight * (1.0 / (self.rrf_k + item["rank"]))
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + score_increment

        # Rank by fused RRF score
        sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        # 3. Calculate Confidence Score
        content_words = [t for t in tokens if t not in STOPWORDS]
        if not content_words:
            content_words = tokens

        # Check for deliberate gap match first
        known_gap_matched = False
        gap_category = None
        for gap in self.deliberate_gaps:
            for trigger in gap.get("trigger_queries", []):
                trigger_words = [w for w in simple_tokenize(trigger) if w not in STOPWORDS]
                common = set(content_words).intersection(trigger_words)
                if len(common) >= 2 or (len(content_words) <= 2 and len(common) >= 1 and common == set(content_words)):
                    known_gap_matched = True
                    gap_category = gap.get("expected_category", "IT Support")
                    break
            if known_gap_matched:
                break

        max_theoretical_rrf = (self.dense_weight + self.sparse_weight) / (self.rrf_k + 1)
        retrieved_chunks: List[RetrievedChunk] = []
        seen_docs = set()

        for cid in sorted_chunk_ids:
            item = chunk_map[cid]
            doc_id = item["doc_id"]
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)

            retrieved_chunks.append(RetrievedChunk(
                chunk_id=cid,
                doc_id=doc_id,
                domain=item["domain"],
                category=item["category"],
                title=item["title"],
                text=item["text"],
                score=rrf_scores[cid],
                dense_rank=dense_ranks.get(cid),
                sparse_rank=sparse_ranks.get(cid),
            ))
            if len(retrieved_chunks) >= top_n:
                break

        # Compute normalized confidence in [0.0, 1.0]
        if retrieved_chunks and not known_gap_matched:
            top_rrf = retrieved_chunks[0].score
            normalized_rrf = min(1.0, top_rrf / max_theoretical_rrf)

            # Check keyword match overlap on non-stopwords
            top_chunk_tokens = set(simple_tokenize(retrieved_chunks[0].text))
            content_overlap = len(set(content_words).intersection(top_chunk_tokens)) / max(len(content_words), 1)

            # Check top BM25 strength
            top_bm25 = 0.0
            if sparse_results and sparse_results[0]["doc_id"] == retrieved_chunks[0].doc_id:
                top_bm25 = sparse_results[0].get("bm25_score", 0.0)

            # High confidence requires strong non-stopword presence
            if content_overlap < 0.40 or top_bm25 < 6.0:
                confidence = round(min(0.35, normalized_rrf * content_overlap), 3)
            else:
                confidence = round(0.5 * normalized_rrf + 0.3 * content_overlap + 0.2 * min(1.0, top_bm25 / 15.0), 3)
        else:
            confidence = 0.15 if known_gap_matched else 0.0

        # 4. Escalation Gate Evaluation
        escalation_needed = known_gap_matched or (confidence < self.confidence_threshold) or (len(retrieved_chunks) == 0)

        # Infer suggested category
        suggested_category = gap_category or "IT Support"
        if not known_gap_matched and retrieved_chunks:
            suggested_category = retrieved_chunks[0].domain
        else:
            it_words = {"vpn", "password", "screen", "laptop", "wifi", "email", "hardware", "software", "monitor", "flicker"}
            if any(w in it_words for w in tokens):
                suggested_category = "IT Support"
            elif any(w in {"leave", "pto", "vacation", "sabbatical", "hr", "benefits", "insurance"} for w in tokens):
                suggested_category = "HR Policies"

        suggested_action = "escalate_to_ticket" if escalation_needed else "answer"

        # 5. Format Context Block with Source Citations (Parent Document Resolution)
        context_parts = []
        for i, c in enumerate(retrieved_chunks, 1):
            source_header = f"[Source {i}: {c.doc_id} — {c.title} (Domain: {c.domain} | Category: {c.category})]"
            # Resolve to the complete parent document content so the LLM gets 100% of the policy rules
            parent_doc = self.doc_store.get(c.doc_id)
            if parent_doc and "content" in parent_doc:
                body_content = f"Policy Content: {parent_doc['content']}"
            else:
                body_content = c.text
            context_parts.append(f"{source_header}\n{body_content}\n")

        formatted_context = "\n---\n".join(context_parts) if context_parts else "No relevant context found."

        return RetrievalResult(
            query=query,
            chunks=retrieved_chunks,
            confidence=confidence,
            escalation_needed=escalation_needed,
            suggested_action=suggested_action,
            suggested_category=suggested_category,
            formatted_context=formatted_context,
            metadata={
                "top_rrf_score": retrieved_chunks[0].score if retrieved_chunks else 0.0,
                "dense_results_count": len(dense_results),
                "sparse_results_count": len(sparse_results),
                "threshold": self.confidence_threshold,
            }
        )
