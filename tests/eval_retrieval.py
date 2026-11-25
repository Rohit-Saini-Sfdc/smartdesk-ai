"""
Quantitative Retrieval Evaluation Suite for SmartDesk AI.
Benchmarks Hit Rate @ 1, Hit Rate @ 3, MRR, Escalation Recall, and Latency
across all 50 corporate policies and deliberate out-of-scope gaps.
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.rag.hybrid_retriever import HybridRetriever

logging.basicConfig(level=logging.WARNING)


def run_retrieval_eval():
    print("=" * 80)
    print("SMARTDESK AI — QUANTITATIVE RETRIEVAL EVALUATION SUITE")
    print("=" * 80)

    retriever = HybridRetriever()

    kb_file = ROOT_DIR / "data" / "knowledge_base" / "kb_entries.json"
    gaps_file = ROOT_DIR / "data" / "knowledge_base" / "deliberate_gaps.json"

    with open(kb_file, "r", encoding="utf-8") as f:
        kb_entries = json.load(f)

    with open(gaps_file, "r", encoding="utf-8") as f:
        deliberate_gaps = json.load(f)

    # 1. Benchmark In-KB Queries (Hit Rate & MRR)
    in_kb_tests: List[Dict[str, Any]] = []
    for entry in kb_entries:
        doc_id = entry["id"]
        # Test first 2 sample questions for each document
        for q in entry.get("sample_questions", [])[:2]:
            in_kb_tests.append({
                "query": q,
                "expected_doc_id": doc_id,
                "domain": entry["domain"],
                "category": entry["category"]
            })

    total_in_kb = len(in_kb_tests)
    hits_at_1 = 0
    hits_at_3 = 0
    reciprocal_ranks = []
    latencies = []
    false_escalations = 0

    print(f"\n[1/2] Evaluating {total_in_kb} In-Scope Queries across {len(kb_entries)} policies...")

    for i, test in enumerate(in_kb_tests, 1):
        q = test["query"]
        expected_id = test["expected_doc_id"]

        start_t = time.perf_counter()
        result = retriever.retrieve(q, top_n=3)
        latency = (time.perf_counter() - start_t) * 1000
        latencies.append(latency)

        retrieved_ids = [c.doc_id for c in result.chunks]

        # Hit @ 1
        is_hit_1 = len(retrieved_ids) > 0 and retrieved_ids[0] == expected_id
        if is_hit_1:
            hits_at_1 += 1

        # Hit @ 3
        is_hit_3 = expected_id in retrieved_ids
        if is_hit_3:
            hits_at_3 += 1

        # Reciprocal Rank
        if expected_id in retrieved_ids:
            rank = retrieved_ids.index(expected_id) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

        # False Escalation check
        if result.escalation_needed:
            false_escalations += 1

    # 2. Benchmark Deliberate Gaps (Escalation Accuracy & Recall)
    gap_tests: List[Dict[str, Any]] = []
    for gap in deliberate_gaps:
        gap_id = gap["gap_id"]
        for q in gap.get("trigger_queries", []):
            gap_tests.append({
                "query": q,
                "gap_id": gap_id,
                "expected_category": gap["expected_category"]
            })

    total_gaps = len(gap_tests)
    correct_escalations = 0

    print(f"\n[2/2] Evaluating {total_gaps} Deliberate Gap / Out-of-Scope Queries...")

    for test in gap_tests:
        q = test["query"]
        start_t = time.perf_counter()
        result = retriever.retrieve(q, top_n=3)
        latency = (time.perf_counter() - start_t) * 1000
        latencies.append(latency)

        if result.escalation_needed and result.suggested_action == "escalate_to_ticket":
            correct_escalations += 1

    # Aggregate Metrics
    hit_rate_1_pct = round((hits_at_1 / total_in_kb) * 100, 2)
    hit_rate_3_pct = round((hits_at_3 / total_in_kb) * 100, 2)
    mrr = round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4)
    false_escalation_pct = round((false_escalations / total_in_kb) * 100, 2)
    escalation_recall_pct = round((correct_escalations / total_gaps) * 100, 2)
    avg_latency_ms = round(sum(latencies) / len(latencies), 2)

    print("\n" + "=" * 80)
    print("EVALUATION RESULTS SUMMARY")
    print("=" * 80)
    print(f"Total In-Scope Queries Tested:     {total_in_kb}")
    print(f"Total Deliberate Gaps Tested:      {total_gaps}")
    print(f"Hit Rate @ 1 (Top-1 Accuracy):     {hit_rate_1_pct}% ({hits_at_1}/{total_in_kb})")
    print(f"Hit Rate @ 3 (Top-3 Accuracy):     {hit_rate_3_pct}% ({hits_at_3}/{total_in_kb})")
    print(f"Mean Reciprocal Rank (MRR):        {mrr}")
    print(f"In-Scope False Escalation Rate:    {false_escalation_pct}%")
    print(f"Escalation Recall (Gap Detection): {escalation_recall_pct}% ({correct_escalations}/{total_gaps})")
    print(f"Average Retrieval Latency:         {avg_latency_ms} ms")
    print("=" * 80)

    # Save JSON report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_dense": "OpenAI text-embedding-3-small",
        "model_sparse": "BM25Okapi with suffix stemmer",
        "fusion_algorithm": "Reciprocal Rank Fusion (k=60)",
        "metrics": {
            "total_queries_evaluated": total_in_kb + total_gaps,
            "hit_rate_at_1_pct": hit_rate_1_pct,
            "hit_rate_at_3_pct": hit_rate_3_pct,
            "mrr": mrr,
            "escalation_recall_pct": escalation_recall_pct,
            "false_escalation_rate_pct": false_escalation_pct,
            "avg_latency_ms": avg_latency_ms
        }
    }

    report_path = ROOT_DIR / "data" / "retrieval_eval_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n✅ Benchmark report saved to: {report_path}")
    return report


if __name__ == "__main__":
    run_retrieval_eval()
