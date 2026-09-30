"""Run the two FDAAA test queries and print full output.

Usage:
    cd jev-fdaaa-comparison
    python test_queries.py
"""

from __future__ import annotations

import json
import os
import sys

# Import from sibling clinical-trials-agent project
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "clinical-trials-agent")
sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from tools.clinical_trials_api import compute_fdaaa_status, get_study_by_nct_id
from jev_fdaaa import determine_fdaaa_with_jev


def run_test(nct_id: str, description: str) -> None:
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"NCT ID: {nct_id}")
    print("=" * 70)

    print(f"\n[1/3] Fetching study from ClinicalTrials.gov…")
    study = get_study_by_nct_id(nct_id)
    if study.get("error"):
        print(f"ERROR fetching study: {study['error']}")
        return

    print(f"  Title  : {(study.get('brief_title') or '')[:80]}")
    print(f"  Type   : {study.get('study_type')}")
    print(f"  Phase  : {study.get('phase')}")
    print(f"  FDA Drug: {study.get('is_fda_regulated_drug')}  FDA Device: {study.get('is_fda_regulated_device')}")
    print(f"  PCD    : {study.get('primary_completion_date')}")
    print(f"  Results: {study.get('has_results')}  Submit date: {study.get('results_first_submit_date')}")

    print(f"\n[2/3] LLM-based FDAAA determination…")
    llm = compute_fdaaa_status(study)
    print(f"  FDAAA Status   : {llm.get('fdaaa_status')}")
    print(f"  Is Applicable  : {llm.get('is_applicable_trial')}")
    print(f"  Results Due    : {llm.get('results_due_date')}")
    print(f"  Days Overdue   : {llm.get('days_overdue')}")
    print(f"  Reason         : {llm.get('reason')}")

    print(f"\n[3/3] Jev-based FDAAA determination…")
    jev = determine_fdaaa_with_jev(study)

    if jev.get("error"):
        print(f"  ERROR: {jev['error']}")
    else:
        print(f"  Compliance Status : {jev['compliance_status']['answer']}  "
              f"(conf: {int((jev['compliance_status']['confidence'] or 0)*100)}%)")
        print(f"  FDAAA Applicable  : {jev['fdaaa_applicable']['answer']}  "
              f"(conf: {int((jev['fdaaa_applicable']['confidence'] or 0)*100)}%)")
        print(f"  is_interventional      : {jev['is_interventional']['answer']}  "
              f"conf={int((jev['is_interventional']['confidence'] or 0)*100)}%")
        print(f"  is_fda_regulated       : {jev['is_fda_regulated']['answer']}  "
              f"conf={int((jev['is_fda_regulated']['confidence'] or 0)*100)}%")
        print(f"  is_phase_2_or_later    : {jev['is_phase_2_or_later']['answer']}  "
              f"conf={int((jev['is_phase_2_or_later']['confidence'] or 0)*100)}%")
        print(f"  results_deadline_passed: {jev['results_deadline_passed']['answer']}  "
              f"conf={int((jev['results_deadline_passed']['confidence'] or 0)*100)}%")
        print(f"  results_submitted_on_time: {jev['results_submitted_on_time']['answer']}  "
              f"conf={int((jev['results_submitted_on_time']['confidence'] or 0)*100)}%")
        print(f"  Latency: {jev['latency_ms']}ms")

        llm_norm = (llm.get("fdaaa_status") or "").lower().replace("compliant (late)", "compliant")
        jev_norm = (jev["compliance_status"]["answer"] or "").lower()
        agree = llm_norm == jev_norm
        print(f"\n  {'✅ SYSTEMS AGREE' if agree else '⚠️  SYSTEMS DIFFER'}: "
              f"LLM={llm.get('fdaaa_status')}  Jev={jev['compliance_status']['answer']}")

        print(f"\n  --- Jev raw response ---")
        print(json.dumps(jev.get("jev_raw_response"), indent=2, default=str))


if __name__ == "__main__":
    run_test(
        "NCT01866319",
        "FDAAA applicable + compliant trial",
    )
    run_test(
        "NCT07780760",
        "Not applicable trial",
    )
    print("\n" + "=" * 70)
    print("All tests complete.")
