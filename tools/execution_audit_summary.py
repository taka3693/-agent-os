#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


LOG_DIR = Path("runtime_logs/execution")


def load_logs() -> list[dict]:
    if not LOG_DIR.exists():
        return []

    logs: list[dict] = []
    for path in sorted(LOG_DIR.glob("execution_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_path"] = str(path)
                logs.append(data)
        except Exception:
            continue
    return logs


def main() -> None:
    logs = load_logs()
    if not logs:
        print("no execution logs found")
        return

    total_runs = len(logs)
    converged_runs = 0
    total_iterations = 0
    total_fix_attempts = 0
    total_applied = 0
    total_skipped = 0
    total_verified = 0
    total_failed = 0
    missing_evidence_policy_runs = 0
    review_required_runs = 0
    high_confidence_runs = 0

    stopped_reasons = Counter()
    fixed_keys = Counter()
    skipped_keys = Counter()

    valid_logs = []
    skipped_legacy = 0

    for log in logs:
        stats = log.get("stats")
        if not isinstance(stats, dict):
            skipped_legacy += 1
            continue
        valid_logs.append(log)
        if stats.get("converged") is True:
            converged_runs += 1

    logs = valid_logs
    total_runs = len(logs)

    for log in logs:
        stats = log.get("stats", {}) or {}

        total_iterations += int(log.get("iteration_count", 0) or 0)
        total_fix_attempts += int(stats.get("total_fix_attempts", 0) or 0)
        total_applied += int(stats.get("applied_count", 0) or 0)
        total_skipped += int(stats.get("skipped_count", 0) or 0)
        total_verified += int(stats.get("verified_count", 0) or 0)
        total_failed += int(stats.get("failed_count", 0) or 0)

        evidence_policy = None

        chain_results = log.get("chain_results") or []
        if isinstance(chain_results, list):
            for cr in chain_results:
                out = cr.get("output") if isinstance(cr, dict) else None
                if not isinstance(out, dict):
                    continue
                ep = out.get("evidence_policy")
                if isinstance(ep, dict):
                    evidence_policy = ep
                    break

        if evidence_policy is None:
            missing_evidence_policy_runs += 1
        else:
            if evidence_policy.get("review_required"):
                review_required_runs += 1
            if evidence_policy.get("has_high_confidence_evidence"):
                high_confidence_runs += 1

        evidence_policy = {}

        chain_results = log.get("chain_results") or []
        if isinstance(chain_results, list):
            for cr in chain_results:
                out = cr.get("output") if isinstance(cr, dict) else None
                if not isinstance(out, dict):
                    continue
                ep = out.get("evidence_policy")
                if isinstance(ep, dict):
                    evidence_policy = ep
                    break

        if evidence_policy.get("review_required"):
            review_required_runs += 1
        if evidence_policy.get("has_high_confidence_evidence"):
            high_confidence_runs += 1


        evidence_policy = {}
        for cr in log.get("chain_results", []):
            out = cr.get("output", {}) or {}
            ep = out.get("evidence_policy")
            if ep:
                evidence_policy = ep
                break

        if evidence_policy.get("review_required"):
            review_required_runs += 1
        if evidence_policy.get("has_high_confidence_evidence"):
            high_confidence_runs += 1


        evidence_policy = log.get("evidence_policy", {}) or {}
        if evidence_policy.get("review_required") is True:
            review_required_runs += 1
        if evidence_policy.get("has_high_confidence_evidence") is True:
            high_confidence_runs += 1

        reason = stats.get("stopped_reason")
        if reason:
            stopped_reasons[str(reason)] += 1

        for k in log.get("fixed_keys", []) or []:
            if isinstance(k, str) and k:
                fixed_keys[k] += 1

        for k in log.get("skipped_keys", []) or []:
            if isinstance(k, str) and k:
                skipped_keys[k] += 1

    avg_iterations = total_iterations / total_runs if total_runs else 0.0
    convergence_rate = converged_runs / total_runs if total_runs else 0.0

    print("=== execution audit summary ===")
    print(f"runs: {total_runs}")
    print(f"legacy_logs_skipped: {skipped_legacy}")
    print(f"converged_runs: {converged_runs}")
    print(f"convergence_rate: {convergence_rate:.2%}")
    print(f"avg_iterations: {avg_iterations:.2f}")
    print(f"total_fix_attempts: {total_fix_attempts}")
    print(f"total_applied: {total_applied}")
    print(f"total_skipped: {total_skipped}")
    print(f"total_verified: {total_verified}")
    print(f"total_failed: {total_failed}")
    print(f"review_required_runs: {review_required_runs}")
    print(f"high_confidence_runs: {high_confidence_runs}")

    print("\n=== stopped reasons ===")
    if stopped_reasons:
        for key, count in stopped_reasons.most_common():
            print(f"{key}: {count}")
    else:
        print("none")

    print("\n=== top fixed keys ===")
    if fixed_keys:
        for key, count in fixed_keys.most_common(10):
            print(f"{count:>3}  {key}")
    else:
        print("none")

    print("\n=== top skipped keys ===")
    if skipped_keys:
        for key, count in skipped_keys.most_common(10):
            print(f"{count:>3}  {key}")
    else:
        print("none")

    latest = logs[-1]
    print("\n=== latest run ===")
    print(f"path: {latest.get('_path')}")
    print(f"run_id: {latest.get('run_id')}")
    print(f"iteration_count: {latest.get('iteration_count')}")
    print(f"final_findings_count: {latest.get('stats', {}).get('final_findings_count')}")
    print(f"converged: {latest.get('stats', {}).get('converged')}")


if __name__ == "__main__":
    main()
