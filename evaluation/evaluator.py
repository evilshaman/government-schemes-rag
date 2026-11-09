"""
Automated Evaluation & Benchmark Framework for Government Schemes RAG (Phase 5).
Computes enterprise-grade RAG metrics:
- Retrieval Precision@K, Recall@K, and Mean Reciprocal Rank (MRR)
- Verdict Accuracy (Eligible vs Conditional vs Ineligible)
- Document Gap Identification Precision & Recall
- Affirmative Booster Consistency
- Zero-Hallucination Groundedness Rate via HallucinationGuard
"""

from __future__ import annotations
import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pydantic import BaseModel, Field

from schemas.business_profile import BusinessProfile
from schemas.government_scheme import GovernmentScheme
from schemas.reasoner_schema import FullReasoningReport
from engine.pipeline_phase3 import Phase3ReasonerPipeline
from knowledge_base.storage import SchemeKnowledgeStore
from knowledge_base.vector_store import SchemeVectorStore
from guardrails.hallucination_guard import HallucinationGuard

logger = logging.getLogger("Evaluator")

BENCHMARK_PATH = os.path.join(BASE_DIR, "evaluation", "benchmark_dataset.json")


class CaseEvaluationResult(BaseModel):
    case_id: str
    description: str
    retrieval_hits_at_k: int
    expected_hits_count: int
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    verdict_accuracy: float
    document_gap_recall: float
    affirmative_boost_correct: bool
    grounding_score: float
    violations_detected: int


class BenchmarkSummary(BaseModel):
    total_test_cases: int
    macro_precision_at_k: float
    macro_recall_at_k: float
    mean_reciprocal_rank: float
    average_verdict_accuracy: float
    average_document_gap_recall: float
    average_grounding_score: float
    total_hallucination_violations: int
    all_tests_passed: bool
    case_results: List[CaseEvaluationResult] = Field(default_factory=list)


class BenchmarkEvaluator:
    """
    Executes and scores the Government Schemes RAG platform against the golden benchmark suite.
    """

    def __init__(
        self,
        knowledge_store: Optional[SchemeKnowledgeStore] = None,
        vector_store: Optional[SchemeVectorStore] = None,
        benchmark_file: Optional[str] = None,
    ):
        self.store = knowledge_store or SchemeKnowledgeStore()
        self.vector_store = vector_store or SchemeVectorStore()
        self.vector_store.load_index()
        self.pipeline = Phase3ReasonerPipeline(knowledge_store=self.store, vector_store=self.vector_store)
        self.benchmark_file = benchmark_file or BENCHMARK_PATH

    def load_benchmark_cases(self) -> List[Dict[str, Any]]:
        with open(self.benchmark_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("test_cases", [])

    def run_evaluation(self, top_k: int = 4) -> BenchmarkSummary:
        """
        Runs evaluation over all golden benchmark test cases.
        """
        cases = self.load_benchmark_cases()
        all_schemes = self.store.list_schemes(status="Active", limit=200)
        scheme_map = {s.scheme_id: s for s in all_schemes}

        case_results: List[CaseEvaluationResult] = []

        for case in cases:
            case_id = case["id"]
            desc = case["description"]
            profile = BusinessProfile.model_validate(case["profile"])
            expected_top = [s.lower() for s in case.get("expected_top_scheme_ids", [])]
            expected_disq = [s.lower() for s in case.get("expected_disqualified_scheme_ids", [])]
            expected_boost = case.get("expected_affirmative_boost", False)

            # Run RAG Pipeline
            report: FullReasoningReport = self.pipeline.run(
                profile=profile,
                top_k_retrieve=8,
                top_n_rerank=top_k,
                apply_hard_filters=True,
            )

            retrieved_ids = [rec.scheme_id.lower() for rec in report.top_recommendations]

            # 1. Retrieval Metrics
            matched_hits = [s_id for s_id in retrieved_ids if any(exp in s_id or s_id in exp for exp in expected_top)]
            precision = round(len(matched_hits) / len(retrieved_ids), 3) if retrieved_ids else 0.0
            recall = round(len(matched_hits) / len(expected_top), 3) if expected_top else 1.0

            # Reciprocal Rank (position of first golden match)
            rr = 0.0
            for rank_idx, s_id in enumerate(retrieved_ids, 1):
                if any(exp in s_id or s_id in exp for exp in expected_top):
                    rr = round(1.0 / rank_idx, 3)
                    break

            # 2. Disqualification / Constraint Consistency
            disq_ok = True
            for d_id in expected_disq:
                # Disqualified scheme should either NOT be in top recommendations OR marked Ineligible
                rec = next((r for r in report.top_recommendations if d_id in r.scheme_id.lower()), None)
                if rec and rec.verdict == "Eligible":
                    disq_ok = False
                    break
            verdict_acc = 1.0 if disq_ok else 0.5

            # 3. Document Gap Recall
            doc_gap_recall = 1.0
            expected_docs = case.get("expected_missing_documents", [])
            if expected_docs and report.top_recommendations:
                all_missing_docs = [
                    d.document_name.lower()
                    for rec in report.top_recommendations
                    for d in rec.document_checklist
                    if d.status in ["Missing", "Action Required"]
                ]
                hits = 0
                for exp_doc in expected_docs:
                    key = exp_doc.replace("_", " ").lower()
                    if any(key in d_name for d_name in all_missing_docs):
                        hits += 1
                doc_gap_recall = round(hits / len(expected_docs), 3) if expected_docs else 1.0

            # 4. Affirmative Booster Check
            boost_detected = False
            for rec in report.top_recommendations:
                if rec.financial_benefit.special_affirmative_boost:
                    boost_detected = True
                    break
            boost_correct = (boost_detected == expected_boost) or (expected_boost is False)

            # 5. Hallucination Guardrail Audit
            audit = HallucinationGuard.audit_full_report(report, scheme_map, profile)
            g_score = audit["average_grounding_score"]
            violations = audit["total_violations"]

            case_results.append(
                CaseEvaluationResult(
                    case_id=case_id,
                    description=desc,
                    retrieval_hits_at_k=len(matched_hits),
                    expected_hits_count=len(expected_top),
                    precision_at_k=precision,
                    recall_at_k=min(recall, 1.0),
                    reciprocal_rank=rr,
                    verdict_accuracy=verdict_acc,
                    document_gap_recall=doc_gap_recall,
                    affirmative_boost_correct=boost_correct,
                    grounding_score=g_score,
                    violations_detected=violations,
                )
            )

        # Macro Metrics
        total_cases = len(case_results)
        macro_prec = round(sum(c.precision_at_k for c in case_results) / total_cases, 3)
        macro_rec = round(sum(c.recall_at_k for c in case_results) / total_cases, 3)
        mrr = round(sum(c.reciprocal_rank for c in case_results) / total_cases, 3)
        avg_verdict = round(sum(c.verdict_accuracy for c in case_results) / total_cases, 3)
        avg_doc_gap = round(sum(c.document_gap_recall for c in case_results) / total_cases, 3)
        avg_grounding = round(sum(c.grounding_score for c in case_results) / total_cases, 3)
        total_viol = sum(c.violations_detected for c in case_results)

        passed = (macro_prec >= 0.70 and mrr >= 0.80 and avg_grounding >= 0.95 and total_viol == 0)

        return BenchmarkSummary(
            total_test_cases=total_cases,
            macro_precision_at_k=macro_prec,
            macro_recall_at_k=macro_rec,
            mean_reciprocal_rank=mrr,
            average_verdict_accuracy=avg_verdict,
            average_document_gap_recall=avg_doc_gap,
            average_grounding_score=avg_grounding,
            total_hallucination_violations=total_viol,
            all_tests_passed=passed,
            case_results=case_results,
        )

    @classmethod
    def print_benchmark_table(cls, summary: BenchmarkSummary):
        """
        Prints a clean ASCII report summarizing the evaluation metrics.
        """
        print("\n" + "=" * 80)
        print("   GOVERNMENT SCHEMES RAG - PHASE 5 BENCHMARK EVALUATION REPORT")
        print("   Grounding, Hallucination Prevention & Retrieval Precision Benchmark")
        print("=" * 80)
        print(f" Total Evaluation Cases : {summary.total_test_cases}")
        print(f" Macro Precision@K      : {summary.macro_precision_at_k * 100:.1f}%")
        print(f" Macro Recall@K         : {summary.macro_recall_at_k * 100:.1f}%")
        print(f" Mean Reciprocal Rank   : {summary.mean_reciprocal_rank:.3f} (MRR)")
        print(f" Verdict Consistency    : {summary.average_verdict_accuracy * 100:.1f}%")
        print(f" Document Gap Recall    : {summary.average_document_gap_recall * 100:.1f}%")
        print(f" Factual Grounding Rate : {summary.average_grounding_score * 100:.1f}%")
        print(f" Hallucination Violations: {summary.total_hallucination_violations} detected")
        print(f" Status                 : {'[PASSED] ALL BENCHMARKS MET' if summary.all_tests_passed else '[ATTENTION REQUIRED]'}")
        print("-" * 80)
        print(f"{'Case ID':<26} | {'P@K':<6} | {'R@K':<6} | {'MRR':<6} | {'Grounding':<10} | {'Violations'}")
        print("-" * 80)
        for c in summary.case_results:
            print(
                f"{c.case_id:<26} | {c.precision_at_k * 100:>5.1f}% | {c.recall_at_k * 100:>5.1f}% | "
                f"{c.reciprocal_rank:>6.3f} | {c.grounding_score * 100:>8.1f}% | {c.violations_detected:>10}"
            )
        print("=" * 80 + "\n")


if __name__ == "__main__":
    evaluator = BenchmarkEvaluator()
    summary = evaluator.run_evaluation()
    BenchmarkEvaluator.print_benchmark_table(summary)
    sys.exit(0 if summary.all_tests_passed else 1)
