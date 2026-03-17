"""
Analysis Orchestrator: coordinates L1, L2, and L3 analysis layers.

Each analysis run is assigned a unique run_id (UUID). Every analysis case
(L1, L2-1 through L2-8, L3) writes its result as a separate row in the
openclaw_analysis_results table, linked by run_id. Reports can be generated
by querying all rows for a given run_id.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

from scripts.config import AppConfig
from scripts.db import execute_batch_insert, execute_query
from scripts.llm_client import LlmClient
from scripts.types import TimeRange, last_n_days_range
from scripts.analysis.operational_insight import (
    analyze_token_efficiency,
    analyze_session_depth,
    analyze_tool_chains,
    analyze_high_cost_sessions,
    analyze_anomalies,
)
from scripts.analysis.behavior_insight import (
    classify_intents,
    assess_task_complexity,
    estimate_task_success_rate,
    score_prompt_quality,
    cluster_topics,
    detect_retry_behavior,
    analyze_thinking_depth,
    track_user_maturity,
)
from scripts.analysis.organizational_insight import run_l3_analysis, generate_narrative_report

RESULTS_TABLE = "openclaw_analysis_results"

CREATE_RESULTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS `{RESULTS_TABLE}` (
    row_id BIGINT NOT NULL AUTO_INCREMENT,
    run_id VARCHAR(36) NOT NULL COMMENT 'Unique ID for each analysis run (UUID)',
    case_name VARCHAR(100) NOT NULL COMMENT 'Analysis case name, e.g. L1, L2-1, L2-2, ..., L3',
    analysis_type VARCHAR(50) NOT NULL COMMENT 'L1_OPERATIONAL / L2_BEHAVIOR / L3_ORGANIZATIONAL',
    status VARCHAR(20) NOT NULL DEFAULT 'success' COMMENT 'success / failure / skipped',
    elapsed_seconds DOUBLE DEFAULT NULL COMMENT 'Execution time in seconds',
    time_range_start VARCHAR(30) DEFAULT NULL COMMENT 'Analysis window start timestamp',
    time_range_end VARCHAR(30) DEFAULT NULL COMMENT 'Analysis window end timestamp',
    summary TEXT DEFAULT NULL COMMENT 'Human-readable summary of the result',
    details LONGTEXT NOT NULL COMMENT 'Full analysis result JSON',
    error_message TEXT DEFAULT NULL COMMENT 'Error message if status is failure',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (row_id),
    INDEX idx_run_id (run_id),
    INDEX idx_case_name (case_name),
    INDEX idx_analysis_type (analysis_type)
)
"""

# ─── Summarizers for each case ───

def _summarize_l1_1(result: dict) -> str:
    overall = result.get("overall", {})
    total_sessions = overall.get("totalSessions", 0)
    total_input = overall.get("totalInput", 0)
    total_output = overall.get("totalOutput", 0)
    ratio = overall.get("outputInputRatio", 0)
    cache = overall.get("cacheHitRatePct", 0)
    by_user = result.get("byUser", [])
    return (f"共 {total_sessions} 个 session, input={total_input:,} output={total_output:,} "
            f"o/i={ratio:.2f} cache={cache:.1f}% {len(by_user)} 个用户")


def _summarize_l1_2(result: dict) -> str:
    total_chains = result.get("totalChains", 0)
    buckets = result.get("bucketDistribution", [])
    parts = [f"{b['depthBucket']}={b['chainCount']}" for b in buckets]
    return f"共 {total_chains} 个 task chain. 分布: {', '.join(parts)}"


def _summarize_l1_3(result: dict) -> str:
    bigrams = result.get("topBigrams", [])
    tools = result.get("toolSuccessRates", [])
    return f"共 {len(tools)} 个工具, {len(bigrams)} 个工具调用模式"


def _summarize_l1_4(result: dict) -> str:
    chains = result.get("taskChains", [])
    if chains:
        top_tokens = chains[0].get("totalTokens", 0)
        return f"Top {len(chains)} 高 token task chain, 最高 {top_tokens:,} tokens"
    return "无高 token task chain"


def _summarize_l1_5(result: dict) -> str:
    anomalies = result.get("anomalies", [])
    critical = sum(1 for a in anomalies if a.get("severity") == "critical")
    high = sum(1 for a in anomalies if a.get("severity") == "high")
    return f"共 {len(anomalies)} 个异常 (critical={critical}, high={high})"


def _summarize_l2_1(result: dict) -> str:
    dist = result.get("distribution", {})
    total = sum(dist.values())
    top = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:5]
    top_str = ", ".join(f"{k}({v})" for k, v in top)
    return f"共 {total} 条消息, {len(dist)} 种意图. Top: {top_str}"


def _summarize_l2_2(result: dict) -> str:
    dist = result.get("distribution", {})
    total = sum(dist.values())
    parts = [f"{k}={v}" for k, v in dist.items()]
    return f"共 {total} 个 task chain. 分布: {', '.join(parts)}"


def _summarize_l2_3(result: dict) -> str:
    overall = result.get("overall", {})
    total = sum(overall.values())
    failures = result.get("failures", [])
    rate = (overall.get("success", 0) / total * 100) if total > 0 else 0
    return f"共 {total} 个 task chain, 成功率 {rate:.0f}%, {len(failures)} 条失败明细"


def _summarize_l2_4(result: dict) -> str:
    team_avg = result.get("teamAverage", {})
    overall = team_avg.get("overall", 0)
    user_count = len(result.get("byUser", []))
    top_users = result.get("topUsers", [])
    bottom_users = result.get("bottomUsers", [])
    top_info = f", Best3: {', '.join(u['senderId'][:12] for u in top_users)}" if top_users else ""
    bottom_info = f", Worst3: {', '.join(u['senderId'][:12] for u in bottom_users)}" if bottom_users else ""
    return f"共 {user_count} 个用户, 团队平均 Prompt 质量分 {overall:.2f}{top_info}{bottom_info}"

def _summarize_l2_5(result: dict) -> str:
    cat_dist = result.get("categoryDistribution", {})
    total = sum(cat_dist.values())
    top_tags = result.get("topTags", [])
    cat_parts = [f"{k}={v}" for k, v in sorted(cat_dist.items(), key=lambda x: x[1], reverse=True)[:5]]
    return f"共 {total} 条消息, {len(cat_dist)} 个分类, {len(top_tags)} 个标签. Top分类: {', '.join(cat_parts)}"

def _summarize_l2_6(result: dict) -> str:
    total = result.get("totalSessions", 0)
    retry_count = result.get("retrySessionCount", 0)
    rate = result.get("retryRate", 0)
    return f"共 {total} 个 session, {retry_count} 个有重试行为, 重试率 {rate:.1f}%"

def _summarize_l2_7(result: dict) -> str:
    dist = result.get("distribution", {})
    total = sum(dist.values())
    parts = [f"{k}={v}" for k, v in dist.items()]
    return f"共 {total} 个 task chain. 思考深度分布: {', '.join(parts)}"

def _summarize_l2_8(result: dict) -> str:
    users = result.get("users", [])
    return f"共 {len(users)} 个用户的成熟度趋势"


def _summarize_l3(result: dict) -> str:
    insights = result.get("insights", [])
    return f"共 {len(insights)} 条组织级洞察"


_SUMMARIZERS = {
    "L1-1": _summarize_l1_1,
    "L1-2": _summarize_l1_2,
    "L1-3": _summarize_l1_3,
    "L1-4": _summarize_l1_4,
    "L1-5": _summarize_l1_5,
    "L2-1": _summarize_l2_1,
    "L2-2": _summarize_l2_2,
    "L2-3": _summarize_l2_3,
    "L2-4": _summarize_l2_4,
    "L2-5": _summarize_l2_5,
    "L2-6": _summarize_l2_6,
    "L2-7": _summarize_l2_7,
    "L2-8": _summarize_l2_8,
    "L3": _summarize_l3,
}


class AnalysisOrchestrator:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._table_name = config.adb.session_table
        self._results_table_ensured = False

    async def run_full_analysis(self, range_: TimeRange | None = None) -> str:
        """Run all enabled analysis layers and return the run_id."""
        run_id = str(uuid.uuid4())

        print("\n" + "=" * 60)
        print("🔍 Starting Full Analysis")
        print("=" * 60)

        analysis_config = self._config.analysis
        if not analysis_config:
            print("[Orchestrator] Analysis config not found, skipping analysis")
            return run_id

        analysis_range = range_ or last_n_days_range(analysis_config.analysis_window_days)

        print(f"[Orchestrator] Run ID: {run_id}")
        print(f"[Orchestrator] Time range: {analysis_range.start_date} to {analysis_range.end_date}")
        print(f"[Orchestrator] L1 enabled: {analysis_config.enable_l1}")
        print(f"[Orchestrator] L2 enabled: {analysis_config.enable_l2}")
        print(f"[Orchestrator] L3 enabled: {analysis_config.enable_l3}")

        self._ensure_results_table()

        llm_client = LlmClient(self._config.llm) if self._config.llm else None

        l1_results: dict | None = None
        l2_results: dict | None = None

        try:
            # ── L1 (each sub-case independently) ──
            if analysis_config.enable_l1:
                adb = self._config.adb
                table = self._table_name

                l1_case_results = {}
                l1_case_results["tokenEfficiency"] = await self._run_and_save_case(
                    run_id, "L1-1", "L1_OPERATIONAL", analysis_range,
                    analyze_token_efficiency, (adb, table, analysis_range),
                )
                l1_case_results["sessionDepth"] = await self._run_and_save_case(
                    run_id, "L1-2", "L1_OPERATIONAL", analysis_range,
                    analyze_session_depth, (adb, table, analysis_range),
                )
                l1_case_results["toolChains"] = await self._run_and_save_case(
                    run_id, "L1-3", "L1_OPERATIONAL", analysis_range,
                    analyze_tool_chains, (adb, table, analysis_range),
                )
                l1_case_results["highCostSessions"] = await self._run_and_save_case(
                    run_id, "L1-4", "L1_OPERATIONAL", analysis_range,
                    analyze_high_cost_sessions, (adb, table, analysis_range),
                )
                l1_case_results["anomalies"] = await self._run_and_save_case(
                    run_id, "L1-5", "L1_OPERATIONAL", analysis_range,
                    analyze_anomalies, (adb, table, analysis_range),
                )
                l1_results = {k: v for k, v in l1_case_results.items() if v is not None}

            # ── L2 (each sub-case in order L2-1 through L2-8) ──
            if analysis_config.enable_l2:
                max_items = analysis_config.max_sessions_for_llm
                adb = self._config.adb
                table = self._table_name

                l2_case_results = {}

                # L2-1: Intent Classification (LLM)
                if llm_client:
                    l2_case_results["intents"] = await self._run_and_save_case(
                        run_id, "L2-1", "L2_BEHAVIOR", analysis_range,
                        classify_intents, (adb, table, analysis_range, llm_client, max_items),
                    )
                else:
                    print("[Orchestrator] ⚠️ L2-1 skipped: requires LLM config")

                # L2-2: Task Complexity (SQL)
                l2_case_results["complexity"] = await self._run_and_save_case(
                    run_id, "L2-2", "L2_BEHAVIOR", analysis_range,
                    assess_task_complexity, (adb, table, analysis_range),
                )

                # L2-3: Task Success Rate (SQL)
                l2_case_results["successRate"] = await self._run_and_save_case(
                    run_id, "L2-3", "L2_BEHAVIOR", analysis_range,
                    estimate_task_success_rate, (adb, table, analysis_range),
                )

                # L2-4: Prompt Quality (LLM)
                if llm_client:
                    l2_case_results["promptQuality"] = await self._run_and_save_case(
                        run_id, "L2-4", "L2_BEHAVIOR", analysis_range,
                        score_prompt_quality, (adb, table, analysis_range, llm_client),
                    )
                else:
                    print("[Orchestrator] ⚠️ L2-4 skipped: requires LLM config")

                # L2-5: Topic Clustering (LLM)
                if llm_client:
                    l2_case_results["topics"] = await self._run_and_save_case(
                        run_id, "L2-5", "L2_BEHAVIOR", analysis_range,
                        cluster_topics, (adb, table, analysis_range, llm_client),
                    )
                else:
                    print("[Orchestrator] ⚠️ L2-5 skipped: requires LLM config")

                # L2-6: Retry Behavior (SQL)
                l2_case_results["retryBehavior"] = await self._run_and_save_case(
                    run_id, "L2-6", "L2_BEHAVIOR", analysis_range,
                    detect_retry_behavior, (adb, table, analysis_range),
                )

                # L2-7: Thinking Depth (SQL)
                l2_case_results["thinkingDepth"] = await self._run_and_save_case(
                    run_id, "L2-7", "L2_BEHAVIOR", analysis_range,
                    analyze_thinking_depth, (adb, table, analysis_range),
                )

                # L2-8: User Maturity (LLM)
                if llm_client:
                    l2_case_results["userMaturity"] = await self._run_and_save_case(
                        run_id, "L2-8", "L2_BEHAVIOR", analysis_range,
                        track_user_maturity, (adb, table, analysis_range, llm_client),
                    )
                else:
                    print("[Orchestrator] ⚠️ L2-8 skipped: requires LLM config")

                # Assemble combined L2 results for L3 consumption
                l2_results = {k: v for k, v in l2_case_results.items() if v is not None}

            # ── L3 ──
            l3_results: dict | None = None
            if analysis_config.enable_l3 and llm_client and l1_results and l2_results:
                l3_results = await self._run_and_save_case(
                    run_id, "L3", "L3_ORGANIZATIONAL", analysis_range,
                    run_l3_analysis, (
                        self._config.adb, self._table_name, analysis_range,
                        llm_client, l1_results, l2_results,
                    ),
                )
            elif analysis_config.enable_l3:
                print("[Orchestrator] ⚠️ L3 Analysis skipped: requires LLM config and L1/L2 results")

            # ── Final Report (L3-5) ──
            if llm_client and l1_results and l2_results:
                await self._generate_final_report(
                    run_id, analysis_range, llm_client,
                    l1_results, l2_results, l3_results or {},
                )

        except Exception as error:
            print(f"[Orchestrator] ❌ Analysis failed: {error}")
            raise

        print("\n" + "=" * 60)
        print("🎉 Full Analysis Completed")
        print(f"   Run ID: {run_id}")
        print("=" * 60)

        # Auto-generate report
        self.generate_report(run_id)

        return run_id

    async def _run_and_save_case(
        self,
        run_id: str,
        case_name: str,
        analysis_type: str,
        range_: TimeRange,
        analysis_fn,
        args: tuple,
    ) -> Optional[dict]:
        """Run a single analysis case, save result to DB, and return the result dict."""
        print(f"\n{'─'*50}")
        print(f"▶ Running {case_name}...")

        start = time.time()
        try:
            raw_result = analysis_fn(*args)
            # Support both sync and async analysis functions
            if asyncio.iscoroutine(raw_result):
                result = await raw_result
            else:
                result = raw_result
            elapsed = time.time() - start
            print(f"[{case_name}] Analysis function returned in {elapsed:.1f}s")

            summarizer = _SUMMARIZERS.get(case_name, lambda r: "完成")
            summary = summarizer(result)
            print(f"[{case_name}] Summary: {summary}")

            print(f"[{case_name}] Saving result to DB...")
            self._save_case_result(
                run_id, case_name, analysis_type, range_,
                status="success", elapsed=elapsed, summary=summary,
                details=result,
            )
            print(f"✅ {case_name} completed in {elapsed:.1f}s — {summary}")
            return result

        except Exception as exc:
            elapsed = time.time() - start
            error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            print(f"❌ {case_name} failed in {elapsed:.1f}s: {exc}")

            self._save_case_result(
                run_id, case_name, analysis_type, range_,
                status="failure", elapsed=elapsed, summary=f"执行失败: {exc}",
                details={}, error_message=error_msg,
            )
            return None

    def _save_case_result(
        self,
        run_id: str,
        case_name: str,
        analysis_type: str,
        range_: TimeRange,
        status: str,
        elapsed: float,
        summary: str,
        details: dict,
        error_message: Optional[str] = None,
    ) -> None:
        """Save a single case result to both local file and DB (synchronous)."""
        details_json = json.dumps(details, ensure_ascii=False, default=str)
        json_size_kb = len(details_json.encode("utf-8")) / 1024
        print(f"[{case_name}] details JSON size: {json_size_kb:.1f} KB")

        # Truncate details if too large for DB (max ~16MB for LONGTEXT, but keep reasonable)
        max_json_bytes = 4 * 1024 * 1024  # 4 MB
        if len(details_json.encode("utf-8")) > max_json_bytes:
            print(f"[{case_name}] ⚠️ details JSON too large ({json_size_kb:.0f} KB), truncating")
            details_json = json.dumps(
                {"_truncated": True, "_original_size_kb": round(json_size_kb)},
                ensure_ascii=False,
            )

        # Save to local file
        self._save_to_local_file(run_id, case_name, details_json)

        # Save to DB
        try:
            print(f"[{case_name}] Writing to DB...")
            columns = [
                "run_id", "case_name", "analysis_type", "status",
                "elapsed_seconds", "time_range_start", "time_range_end",
                "summary", "details", "error_message",
            ]
            rows = [[
                run_id, case_name, analysis_type, status,
                round(elapsed, 2), range_.start_date, range_.end_date,
                summary, details_json, error_message,
            ]]
            execute_batch_insert(self._config.adb, RESULTS_TABLE, columns, rows)
            print(f"[{case_name}] DB write completed")
        except Exception as error:
            print(f"[Orchestrator] ⚠️ Failed to save {case_name} to DB: {error}")

    def _save_to_local_file(self, run_id: str, case_name: str, details_json: str) -> None:
        try:
            output_dir = Path("output") / run_id
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = output_dir / f"{case_name}.json"
            filename.write_text(details_json, encoding="utf-8")
        except Exception as error:
            print(f"[Orchestrator] ⚠️ Failed to save {case_name} to local file: {error}")

    def _ensure_results_table(self) -> None:
        if self._results_table_ensured:
            return
        try:
            execute_query(self._config.adb, CREATE_RESULTS_TABLE_SQL)
            self._results_table_ensured = True
        except Exception as error:
            print(f"[Orchestrator] ⚠️ Failed to ensure results table: {error}")

    async def _generate_final_report(
        self,
        run_id: str,
        range_: TimeRange,
        llm_client: LlmClient,
        l1_results: dict,
        l2_results: dict,
        l3_results: dict,
    ) -> None:
        """Generate the final narrative report (L3-5), write to DB and final_report.md."""
        print(f"\n{'─'*50}")
        print("▶ Generating Final Report (L3-5)...")

        start = time.time()
        try:
            all_results = {
                "l1": l1_results,
                "l2": l2_results,
                "l3": l3_results,
            }
            result = await generate_narrative_report(all_results, range_, llm_client)
            elapsed = time.time() - start

            report_text = result.get("report", "")
            summary = f"最终报告已生成，共 {len(report_text)} 字符"

            # Save to DB (details stores the full report text as JSON)
            self._save_case_result(
                run_id, "L3-5", "FINAL_REPORT", range_,
                status="success", elapsed=elapsed, summary=summary,
                details={"report": report_text},
            )

            # Write to fixed local file
            report_path = Path("output") / "final_report.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report_text, encoding="utf-8")

            print(f"✅ Final Report generated in {elapsed:.1f}s → {report_path}")

        except Exception as exc:
            elapsed = time.time() - start
            error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            print(f"❌ Final Report generation failed in {elapsed:.1f}s: {exc}")
            self._save_case_result(
                run_id, "L3-5", "FINAL_REPORT", range_,
                status="failure", elapsed=elapsed, summary=f"执行失败: {exc}",
                details={}, error_message=error_msg,
            )

    def get_final_report(self) -> str:
        """Query the latest final narrative report from DB and return it."""
        sql = f"""
            SELECT details
            FROM `{RESULTS_TABLE}`
            WHERE case_name = 'L3-5' AND status = 'success'
            ORDER BY created_at DESC
            LIMIT 1
        """
        rows = execute_query(self._config.adb, sql)

        if not rows:
            return "❌ No final report found in database. Please run analysis first."

        details_raw = rows[0].get("details", "{}")
        details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
        return details.get("report", "")

    def generate_report(self, run_id: str) -> None:
        """Query all case results for a run_id and print a formatted report."""
        sql = f"""
            SELECT case_name, status, elapsed_seconds, time_range_start, time_range_end,
                   summary, details, error_message, created_at
            FROM `{RESULTS_TABLE}`
            WHERE run_id = %s
            ORDER BY case_name
        """
        rows = execute_query(self._config.adb, sql, (run_id,))

        if not rows:
            print(f"❌ No results found for run_id: {run_id}")
            return

        first_row = rows[0]
        time_start = first_row.get("time_range_start", "?")
        time_end = first_row.get("time_range_end", "?")
        total_elapsed = sum(float(r.get("elapsed_seconds") or 0) for r in rows)
        success_count = sum(1 for r in rows if r.get("status") == "success")
        failure_count = sum(1 for r in rows if r.get("status") == "failure")

        print("\n" + "=" * 70)
        print("📊 OpenClaw Insight Analysis Report")
        print("=" * 70)
        print(f"  Run ID:      {run_id}")
        print(f"  Time Range:  {time_start} → {time_end}")
        print(f"  Cases:       {len(rows)} total, {success_count} success, {failure_count} failure")
        print(f"  Total Time:  {total_elapsed:.1f}s")
        print("=" * 70)

        for row in rows:
            case_name = row.get("case_name", "?")
            status = row.get("status", "?")
            elapsed = float(row.get("elapsed_seconds") or 0)
            summary = row.get("summary", "")
            icon = "✅" if status == "success" else "❌"

            print(f"\n{icon} {case_name} ({elapsed:.1f}s) — {status}")
            print(f"   {summary}")

            if status == "failure":
                error_msg = row.get("error_message", "")
                if error_msg:
                    first_line = error_msg.strip().split("\n")[0]
                    print(f"   Error: {first_line}")

            if status == "success":
                details_raw = row.get("details", "{}")
                details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
                self._print_case_details(case_name, details)

        print(f"\n{'='*70}")
        print(f"📋 Report complete. Run ID: {run_id}")
        print(f"{'='*70}")

    def _print_case_details(self, case_name: str, details: dict) -> None:
        """Print case-specific details in a readable format."""
        if case_name == "L2-1":
            dist = details.get("distribution", {})
            total = sum(dist.values())
            for intent, count in sorted(dist.items(), key=lambda x: x[1], reverse=True):
                pct = (count / total * 100) if total > 0 else 0
                bar = "█" * int(pct / 5)
                print(f"     {intent}: {count} ({pct:.0f}%) {bar}")

        elif case_name == "L2-2":
            top_complex = details.get("topComplex", [])
            if top_complex:
                print(f"   Top 5 复杂 task chain:")
                for item in top_complex[:5]:
                    print(f"     session={item['sessionId'][:20]}... chain#{item.get('taskChainId','?')} "
                          f"score={item['complexityScore']} turns={item['userTurns']} tools={item['toolCallCount']}")

        elif case_name == "L2-3":
            by_user = details.get("byUser", {})
            if by_user:
                sorted_users = sorted(by_user.items(), key=lambda x: x[1].get('success', 0), reverse=True)
                for uid, counts in sorted_users[:10]:
                    total_u = sum(counts.values())
                    rate = (counts.get('success', 0) / total_u * 100) if total_u > 0 else 0
                    print(f"     {uid}: s={counts.get('success',0)} p={counts.get('partial',0)} f={counts.get('failure',0)} ({rate:.0f}%)")
            failures = details.get("failures", [])
            if failures:
                print(f"   失败明细 ({len(failures)} 条):")
                for item in failures:
                    print(f"     session={item['sessionId']} sender={item['senderId']} "
                          f"start={item.get('startRowId','?')} end={item.get('endRowId','?')}")

        elif case_name == "L2-6":
            top_retry = details.get("topRetrySessions", [])
            if top_retry:
                for item in top_retry[:5]:
                    print(f"     session={item.get('sessionId','?')[:20]}... retries={item.get('retryCount',0)}")
