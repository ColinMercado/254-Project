#!/usr/bin/env python3
"""
eval/eval.py — CSV Doctor Evaluation Script

Measures the data_quality_score across all labeled test cases.

Metric:
    data_quality_score = (correctly_identified_issues + runnable_cleaning_steps)
                         / (total_expected_issues + total_expected_steps)

Usage:
    # Start the Flask app first: python app.py
    python eval/eval.py
    python eval/eval.py --verbose
    python eval/eval.py --url http://localhost:5000
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:5000"
RESULTS_FILE = Path(__file__).parent / "results.json"
TEST_CASES_FILE = Path(__file__).parent / "test_cases.json"
PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def score_issue_detection(issues: list, expected_keywords: list) -> tuple[int, int]:
    """
    Check how many expected issue keywords appear in the AI-detected issues.

    Returns (detected_count, total_expected)
    """
    if not expected_keywords:
        return 0, 0

    # Flatten all issue text for keyword matching
    issues_text = " ".join(
        f"{i.get('column','')} {i.get('issue_type','')} {i.get('description','')} {i.get('suggested_fix','')}"
        for i in issues
    ).lower()

    detected = sum(1 for kw in expected_keywords if kw.lower() in issues_text)
    return detected, len(expected_keywords)


def score_code_runnability(cleaning_code: str, csv_path: str) -> tuple[int, int]:
    """
    Execute the generated cleaning code against the test CSV.
    Returns (runnable_count, total_steps) where total_steps is 1 (pass/fail).
    """
    if not cleaning_code or not cleaning_code.strip():
        return 0, 1

    # Read the CSV
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            csv_text = f.read()
    except FileNotFoundError:
        return 0, 1

    # Write temp files
    csv_tmp = None
    out_tmp = None
    script_tmp = None

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_text)
            csv_tmp = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            out_tmp = f.name

        wrapper = f"""
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv({repr(csv_tmp)})

{cleaning_code}

if 'df_cleaned' in dir():
    df_cleaned.to_csv({repr(out_tmp)}, index=False)
else:
    df.to_csv({repr(out_tmp)}, index=False)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(wrapper)
            script_tmp = f.name

        result = subprocess.run(
            [sys.executable, script_tmp],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            return 1, 1
        else:
            return 0, 1

    except subprocess.TimeoutExpired:
        return 0, 1
    except Exception:
        return 0, 1
    finally:
        for path in [csv_tmp, out_tmp, script_tmp]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------------

def run_eval(base_url: str, verbose: bool = False) -> dict:
    """Run all test cases and return results dict."""

    # Load test cases
    with open(TEST_CASES_FILE, "r") as f:
        test_cases = json.load(f)

    print(f"\n{'='*60}")
    print(f"  CSV Doctor Evaluation")
    print(f"  Server: {base_url}")
    print(f"  Test cases: {len(test_cases)}")
    print(f"{'='*60}\n")

    # Check server is running
    try:
        resp = requests.get(base_url, timeout=5)
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to {base_url}")
        print("Make sure the Flask app is running: python app.py")
        sys.exit(1)

    results = []
    total_detected = 0
    total_expected_issues = 0
    total_runnable = 0
    total_expected_steps = 0

    for tc in test_cases:
        tc_id = tc["id"]
        csv_path = PROJECT_ROOT / tc["csv_file"]
        expected_issues = tc.get("expected_issues", [])
        expected_steps = tc.get("expected_cleaning_steps", [])

        print(f"Running {tc_id}: {tc['description'][:60]}...")

        # Read CSV
        if not csv_path.exists():
            print(f"  ⚠ CSV file not found: {csv_path}")
            results.append({
                "id": tc_id,
                "error": f"CSV file not found: {csv_path}",
                "score": 0.0,
            })
            continue

        with open(csv_path, "r", encoding="utf-8") as f:
            csv_text = f.read()

        # Call /api/analyze
        start = time.time()
        try:
            resp = requests.post(
                f"{base_url}/api/analyze",
                json={"csv_text": csv_text},
                timeout=60,
            )
            elapsed = time.time() - start
            data = resp.json()
        except requests.Timeout:
            print(f"  ✗ Timeout after 60s")
            results.append({"id": tc_id, "error": "Timeout", "score": 0.0})
            continue
        except Exception as e:
            print(f"  ✗ Request error: {e}")
            results.append({"id": tc_id, "error": str(e), "score": 0.0})
            continue

        if not resp.ok:
            print(f"  ✗ API error: {data.get('error', 'Unknown')}")
            results.append({"id": tc_id, "error": data.get("error"), "score": 0.0})
            continue

        issues = data.get("issues", [])
        cleaning_code = data.get("cleaning_code", "")

        # Score issue detection
        detected, n_expected = score_issue_detection(issues, expected_issues)

        # Score code runnability
        runnable, n_steps = score_code_runnability(cleaning_code, str(csv_path))

        # Per-case score
        denom = n_expected + n_steps
        score = (detected + runnable) / denom if denom > 0 else 0.0

        total_detected += detected
        total_expected_issues += n_expected
        total_runnable += runnable
        total_expected_steps += n_steps

        status = "✓" if score >= 0.7 else "~" if score >= 0.4 else "✗"
        print(f"  {status} Score: {score:.2f} | Issues: {detected}/{n_expected} | Code: {runnable}/{n_steps} | {elapsed:.1f}s")

        if verbose:
            print(f"    Issues found ({len(issues)}):")
            for issue in issues:
                print(f"      [{issue.get('severity','?')}] {issue.get('column','?')}: {issue.get('issue_type','?')}")
            print(f"    Code preview: {cleaning_code[:200].strip()}...")
            print()

        results.append({
            "id": tc_id,
            "description": tc["description"],
            "issues_detected": detected,
            "issues_expected": n_expected,
            "code_runnable": runnable,
            "code_steps": n_steps,
            "score": round(score, 4),
            "elapsed_s": round(elapsed, 2),
            "issues_found": [
                {"column": i.get("column"), "type": i.get("issue_type"), "severity": i.get("severity")}
                for i in issues
            ],
        })

    # Overall score
    total_denom = total_expected_issues + total_expected_steps
    overall_score = (total_detected + total_runnable) / total_denom if total_denom > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"  OVERALL data_quality_score: {overall_score:.4f} ({overall_score*100:.1f}%)")
    print(f"  Issues detected: {total_detected}/{total_expected_issues}")
    print(f"  Code runnable:   {total_runnable}/{total_expected_steps}")
    print(f"{'='*60}\n")

    # Print per-case table
    print(f"{'ID':<8} {'Score':>6}  {'Issues':>8}  {'Code':>6}  Description")
    print("-" * 70)
    for r in results:
        if "error" in r and r.get("score", 0) == 0 and "issues_detected" not in r:
            print(f"{r['id']:<8} {'ERROR':>6}  {'—':>8}  {'—':>6}  {r.get('error','')[:40]}")
        else:
            issues_str = f"{r.get('issues_detected',0)}/{r.get('issues_expected',0)}"
            code_str = f"{r.get('code_runnable',0)}/{r.get('code_steps',0)}"
            desc = r.get("description", "")[:40]
            print(f"{r['id']:<8} {r.get('score',0):>6.2f}  {issues_str:>8}  {code_str:>6}  {desc}")

    # Save results
    output = {
        "overall_score": round(overall_score, 4),
        "total_issues_detected": total_detected,
        "total_issues_expected": total_expected_issues,
        "total_code_runnable": total_runnable,
        "total_code_steps": total_expected_steps,
        "test_cases": results,
    }

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {RESULTS_FILE}")
    return output


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CSV Doctor Evaluation Script")
    parser.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the running Flask app (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full AI responses for each test case",
    )
    args = parser.parse_args()

    run_eval(base_url=args.url, verbose=args.verbose)
