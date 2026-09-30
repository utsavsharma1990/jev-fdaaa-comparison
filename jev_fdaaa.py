"""Jev-powered FDAAA 801 determination using TypeSafe AI structured decisions."""

from __future__ import annotations

import os
import time
from datetime import date, datetime

try:
    from typesafe_sdk import Choice, Noul, TypeSafeClient
    _JEV_AVAILABLE = True
except ImportError:
    _JEV_AVAILABLE = False

_JEV_API_KEY = os.getenv("JEV_API_KEY")


def _make_error_result(error_msg: str) -> dict:
    return {
        "jev_raw_response": None,
        "is_interventional": {"answer": None, "confidence": None},
        "is_fda_regulated": {"answer": None, "confidence": None},
        "is_phase_2_or_later": {"answer": None, "confidence": None},
        "results_deadline_passed": {"answer": None, "confidence": None},
        "results_submitted_on_time": {"answer": None, "confidence": None},
        "fdaaa_applicable": {"answer": None, "confidence": None},
        "compliance_status": {"answer": None, "confidence": None},
        "latency_ms": 0,
        "error": error_msg,
    }


def _noul_to_bool(noul_val: float) -> tuple[bool, float]:
    """Convert Noul probability to (answer, confidence)."""
    answer = noul_val >= 0.5
    confidence = noul_val if answer else (1.0 - noul_val)
    return answer, round(confidence, 4)


def _build_state(study_dict: dict) -> dict:
    """Extract relevant fields into a clean state dict for Jev."""
    phase = study_dict.get("phase", "N/A") or "N/A"
    primary_completion = study_dict.get("primary_completion_date")
    results_submit = study_dict.get("results_first_submit_date")

    deadline_detail = "primary_completion_date not set"
    results_detail = "no results submitted"

    if primary_completion:
        try:
            pcd = datetime.strptime(primary_completion[:7], "%Y-%m").date()
            due_date = date(pcd.year + 1, pcd.month, 1)
            today = date.today()
            passed = due_date <= today
            deadline_detail = (
                f"due_date={due_date.isoformat()}, today={today.isoformat()}, passed={passed}"
            )
            if results_submit:
                try:
                    submit_date = datetime.strptime(results_submit[:10], "%Y-%m-%d").date()
                    on_time = submit_date <= due_date
                    results_detail = (
                        f"submitted={results_submit[:10]}, due={due_date.isoformat()}, on_time={on_time}"
                    )
                except ValueError:
                    results_detail = f"could not parse results_submit_date: {results_submit}"
        except ValueError:
            deadline_detail = f"could not parse primary_completion_date: {primary_completion}"

    return {
        "nct_id": study_dict.get("nct_id", ""),
        "study_type": study_dict.get("study_type", ""),
        "phase": phase,
        "is_fda_regulated_drug": study_dict.get("is_fda_regulated_drug", False),
        "is_fda_regulated_device": study_dict.get("is_fda_regulated_device", False),
        "primary_completion_date": primary_completion or "not set",
        "has_results": study_dict.get("has_results", False),
        "results_first_submit_date": results_submit or "not submitted",
        "completion_date": study_dict.get("completion_date") or "not set",
        "start_date": study_dict.get("start_date") or "not set",
        "overall_status": study_dict.get("overall_status", ""),
        "_computed_deadline_passed": deadline_detail,
        "_computed_results_on_time": results_detail,
    }


def determine_fdaaa_with_jev(study_dict: dict) -> dict:
    """Determine FDAAA 801 compliance using Jev typed decisions.

    Args:
        study_dict: Clean study dict from ClinicalTrials.gov (same format as
                    get_study_by_nct_id() in clinical-trials-agent).

    Returns:
        Dict with Jev answers, confidence scores, latency, and raw response.
    """
    if not _JEV_AVAILABLE:
        return _make_error_result("typesafe-sdk not installed — run: pip install typesafe-sdk")

    if not _JEV_API_KEY:
        return _make_error_result("JEV_API_KEY environment variable not set")

    if study_dict.get("error"):
        return _make_error_result(f"Study data unavailable: {study_dict['error']}")

    state = _build_state(study_dict)

    questions = {
        "is_interventional": Noul(
            instructions=(
                "Is this an interventional clinical study "
                "(as opposed to observational)? "
                "Check the `study_type` field."
            )
        ),
        "is_fda_regulated": Noul(
            instructions=(
                "Is this study subject to FDA regulation "
                "(involves an FDA-regulated drug or device)? "
                "Check `is_fda_regulated_drug` and `is_fda_regulated_device`."
            )
        ),
        "is_phase_2_or_later": Noul(
            instructions=(
                "Is this study Phase 2, Phase 3, or Phase 4? "
                "Early Phase 1 and Phase 1 alone do not qualify for FDAAA. "
                "Check the `phase` field."
            )
        ),
        "results_deadline_passed": Noul(
            instructions=(
                "Has the results reporting deadline passed? "
                "The deadline is primary_completion_date plus 12 months. "
                "Use `_computed_deadline_passed` which shows due_date, today, and passed status."
            )
        ),
        "results_submitted_on_time": Noul(
            instructions=(
                "Were results submitted on time? "
                "Deadline = primary_completion_date + 12 months. "
                "Use `_computed_results_on_time` and `has_results`."
            )
        ),
        "fdaaa_applicable": Choice(
            instructions=(
                "Is this an applicable clinical trial under FDAAA Section 801? "
                "Requires ALL of: (1) interventional study type, "
                "(2) FDA-regulated drug or device, "
                "(3) Phase 2 or later (not Early Phase 1 only)."
            ),
            criteria={
                "Applicable": (
                    "Interventional, FDA-regulated, and Phase 2 or later — "
                    "all FDAAA applicability criteria met."
                ),
                "Not Applicable": (
                    "Fails at least one criterion: not interventional, "
                    "not FDA-regulated, or Early Phase 1 / N/A phase."
                ),
            },
        ),
        "compliance_status": Choice(
            instructions=(
                "What is the FDAAA 801 compliance status of this trial? "
                "STEP 1 — Check applicability first. "
                "If `is_fda_regulated_drug` is False AND `is_fda_regulated_device` is False, "
                "the trial is NOT FDAAA-applicable → answer MUST be 'Not Applicable'. "
                "If `study_type` does not contain 'interventional' (case-insensitive), "
                "the trial is NOT FDAAA-applicable → answer MUST be 'Not Applicable'. "
                "If `phase` is 'NA', 'N/A', or 'EARLY_PHASE1' (and not also Phase 2+), "
                "the trial is NOT FDAAA-applicable → answer MUST be 'Not Applicable'. "
                "STEP 2 — Only for applicable trials: check `_computed_deadline_passed` "
                "and `_computed_results_on_time` to determine Compliant / Overdue / Not Yet Due."
            ),
            criteria={
                "Compliant": (
                    "Applicable trial (interventional + FDA-regulated + Phase 2+) AND "
                    "results submitted on or before primary_completion_date + 12 months."
                ),
                "Overdue": (
                    "Applicable trial, results deadline has passed, no results submitted."
                ),
                "Not Yet Due": (
                    "Applicable trial but results deadline (primary_completion_date + 12 months) "
                    "has not yet passed."
                ),
                "Not Applicable": (
                    "Trial fails ANY applicability criterion: "
                    "(1) not FDA-regulated drug or device, "
                    "(2) study type is not interventional, or "
                    "(3) phase is N/A or Early Phase 1 only."
                ),
            },
        ),
    }

    start_ts = time.time()
    try:
        client = TypeSafeClient(api_key=_JEV_API_KEY)
        response = client.system_one(state=state, questions=questions)
        latency_ms = int((time.time() - start_ts) * 1000)
    except Exception as exc:
        latency_ms = int((time.time() - start_ts) * 1000)
        err_str = str(exc).lower()
        if "auth" in err_str or "401" in str(exc) or "403" in str(exc):
            return _make_error_result(
                f"Jev authentication failed: check JEV_API_KEY ({type(exc).__name__})"
            )
        if "timeout" in err_str or "timed out" in err_str:
            return _make_error_result("Jev API timed out after 10s")
        return _make_error_result(f"Jev API error ({type(exc).__name__}): {exc}")

    try:
        answers = response.answers

        def _get_noul(key: str) -> dict:
            ans = answers.get(key)
            if ans is None:
                return {"answer": None, "confidence": None}
            answer, conf = _noul_to_bool(ans.noul)
            return {"answer": answer, "confidence": conf}

        def _get_choice(key: str) -> dict:
            ans = answers.get(key)
            if ans is None:
                return {"answer": None, "confidence": None}
            return {"answer": ans.choice, "confidence": round(float(ans.confidence), 4)}

        raw_response: dict = {}
        try:
            raw_response = {
                k: {
                    "noul": getattr(v, "noul", None),
                    "choice": getattr(v, "choice", None),
                    "confidence": getattr(v, "confidence", None),
                    "probabilities": getattr(v, "probabilities", None),
                }
                for k, v in answers.items()
            }
        except Exception:
            pass

        return {
            "jev_raw_response": raw_response,
            "is_interventional": _get_noul("is_interventional"),
            "is_fda_regulated": _get_noul("is_fda_regulated"),
            "is_phase_2_or_later": _get_noul("is_phase_2_or_later"),
            "results_deadline_passed": _get_noul("results_deadline_passed"),
            "results_submitted_on_time": _get_noul("results_submitted_on_time"),
            "fdaaa_applicable": _get_choice("fdaaa_applicable"),
            "compliance_status": _get_choice("compliance_status"),
            "latency_ms": latency_ms,
            "error": None,
        }

    except Exception as exc:
        return _make_error_result(
            f"Unexpected Jev response format ({type(exc).__name__}): {exc}"
        )
