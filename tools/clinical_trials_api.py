"""ClinicalTrials.gov v2 API wrappers — study lookup and FDAAA determination.

Bundled here so this project is self-contained for Streamlit Cloud deployment.
Source: github.com/utsavsharma1990/clinical-trials-agent
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

import requests

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
DEFAULT_TIMEOUT = 10

_STUDY_CACHE: dict[str, dict] = {}
_CACHE_TTL = 3600


def _cache_get(store: dict, key: str):
    entry = store.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(store: dict, key: str, data) -> None:
    store[key] = {"data": data, "ts": time.time()}


def _safe_get(d: dict, *keys: str, default: Any = None) -> Any:
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is None:
            return default
    return current


def _parse_date(date_struct: dict | None) -> str | None:
    if not date_struct:
        return None
    return date_struct.get("date")


def _extract_study_fields(raw: dict) -> dict:
    proto = raw.get("protocolSection", {})
    results_section = raw.get("resultsSection", {})

    id_mod       = proto.get("identificationModule", {})
    status_mod   = proto.get("statusModule", {})
    design_mod   = proto.get("designModule", {})
    sponsor_mod  = proto.get("sponsorCollaboratorsModule", {})
    cond_mod     = proto.get("conditionsModule", {})
    desc_mod     = proto.get("descriptionModule", {})
    oversight_mod = proto.get("oversightModule", {})
    contacts_mod = proto.get("contactsLocationsModule", {})

    phases: list[str] = design_mod.get("phases", [])
    phase_str = ", ".join(phases) if phases else "N/A"
    locations: list[dict] = contacts_mod.get("locations", [])

    results_first_submit: str | None = status_mod.get(
        "resultsFirstSubmitDate"
    ) or _safe_get(results_section, "moreInfoModule", "submittedQCDate")

    return {
        "nct_id":                  id_mod.get("nctId", ""),
        "official_title":          id_mod.get("officialTitle", ""),
        "brief_title":             id_mod.get("briefTitle", ""),
        "overall_status":          status_mod.get("overallStatus", ""),
        "start_date":              _parse_date(status_mod.get("startDateStruct")),
        "primary_completion_date": _parse_date(status_mod.get("primaryCompletionDateStruct")),
        "completion_date":         _parse_date(status_mod.get("completionDateStruct")),
        "phase":                   phase_str,
        "sponsor_name":            _safe_get(sponsor_mod, "leadSponsor", "name", default=""),
        "conditions":              cond_mod.get("conditions", []),
        "brief_summary":           desc_mod.get("briefSummary", ""),
        "is_fda_regulated_drug":   oversight_mod.get("isFdaRegulatedDrug", False),
        "is_fda_regulated_device": oversight_mod.get("isFdaRegulatedDevice", False),
        "results_first_submit_date": results_first_submit,
        "has_results":             bool(results_section) and bool(results_first_submit),
        "enrollment_count":        _safe_get(design_mod, "enrollmentInfo", "count", default=0),
        "study_type":              design_mod.get("studyType", ""),
        "locations_count":         len(locations),
    }


def get_study_by_nct_id(nct_id: str) -> dict:
    """Fetch a single study by NCT ID from ClinicalTrials.gov v2 API."""
    cache_key = nct_id.upper()
    cached = _cache_get(_STUDY_CACHE, cache_key)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/{nct_id}"
    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 404:
            return {"nct_id": nct_id, "error": "Study not found"}
        if resp.status_code == 429:
            time.sleep(2)
            resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        result = _extract_study_fields(resp.json())
        _cache_set(_STUDY_CACHE, cache_key, result)
        return result
    except requests.exceptions.Timeout:
        return {"nct_id": nct_id, "error": "Request timed out"}
    except requests.exceptions.RequestException as exc:
        return {"nct_id": nct_id, "error": f"API error: {exc}"}


def compute_fdaaa_status(study_dict: dict) -> dict:
    """Determine FDAAA 801 compliance status for a study.

    Returns dict with fdaaa_status, is_applicable_trial, results_due_date,
    has_results, days_overdue, and reason.
    """
    nct_id = study_dict.get("nct_id", "")

    if study_dict.get("error"):
        return {
            "nct_id": nct_id, "is_applicable_trial": False,
            "results_due_date": None, "has_results": False,
            "fdaaa_status": "Not Applicable", "days_overdue": None,
            "reason": "Study data unavailable",
        }

    is_fda_drug    = study_dict.get("is_fda_regulated_drug", False)
    is_fda_device  = study_dict.get("is_fda_regulated_device", False)
    study_type     = study_dict.get("study_type", "")
    phase          = study_dict.get("phase", "")
    has_results    = study_dict.get("has_results", False)
    primary_completion_str = study_dict.get("primary_completion_date")
    results_submit_str     = study_dict.get("results_first_submit_date")
    start_date_str         = study_dict.get("start_date")

    if start_date_str:
        try:
            start_dt = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
            if start_dt < date(2007, 9, 27):
                return {
                    "nct_id": nct_id, "is_applicable_trial": False,
                    "results_due_date": None, "has_results": has_results,
                    "fdaaa_status": "Not Applicable", "days_overdue": None,
                    "reason": "Study initiated before FDAAA enactment (2007-09-27)",
                }
        except ValueError:
            pass

    is_interventional = "interventional" in study_type.lower()
    phase_upper = phase.upper()
    is_excluded_phase = (
        "EARLY_PHASE1" in phase_upper or "EARLY PHASE 1" in phase_upper
    ) and "PHASE2" not in phase_upper and "PHASE 2" not in phase_upper
    is_applicable = (is_fda_drug or is_fda_device) and is_interventional and not is_excluded_phase

    if not is_applicable:
        reasons = []
        if not (is_fda_drug or is_fda_device):
            reasons.append("not FDA-regulated drug or device")
        if not is_interventional:
            reasons.append(f"study type is {study_type}")
        if is_excluded_phase:
            reasons.append(f"phase is {phase}")
        return {
            "nct_id": nct_id, "is_applicable_trial": False,
            "results_due_date": None, "has_results": has_results,
            "fdaaa_status": "Not Applicable", "days_overdue": None,
            "reason": "; ".join(reasons) if reasons else "Not an applicable clinical trial",
        }

    if not primary_completion_str:
        return {
            "nct_id": nct_id, "is_applicable_trial": True,
            "results_due_date": None, "has_results": has_results,
            "fdaaa_status": "Not Yet Due", "days_overdue": None,
            "reason": "Primary completion date not set",
        }

    try:
        pcd = datetime.strptime(primary_completion_str[:7], "%Y-%m").date()
        due_date = date(pcd.year + 1, pcd.month, 1)
    except ValueError:
        try:
            pcd = datetime.strptime(primary_completion_str[:10], "%Y-%m-%d").date()
            due_date = date(pcd.year + 1, pcd.month, 1)
        except ValueError:
            return {
                "nct_id": nct_id, "is_applicable_trial": True,
                "results_due_date": None, "has_results": has_results,
                "fdaaa_status": "Not Yet Due", "days_overdue": None,
                "reason": f"Could not parse primary completion date: {primary_completion_str}",
            }

    today = date.today()
    due_date_str = due_date.isoformat()

    if due_date > today:
        return {
            "nct_id": nct_id, "is_applicable_trial": True,
            "results_due_date": due_date_str, "has_results": has_results,
            "fdaaa_status": "Not Yet Due", "days_overdue": None,
            "reason": f"Results due {due_date_str}; today is {today.isoformat()}",
        }

    days_overdue = (today - due_date).days

    if has_results and results_submit_str:
        try:
            submit_date = datetime.strptime(results_submit_str[:10], "%Y-%m-%d").date()
            if submit_date <= due_date:
                return {
                    "nct_id": nct_id, "is_applicable_trial": True,
                    "results_due_date": due_date_str, "has_results": True,
                    "fdaaa_status": "Compliant", "days_overdue": None,
                    "reason": f"Results submitted {results_submit_str}, due {due_date_str}",
                }
            else:
                late_days = (submit_date - due_date).days
                return {
                    "nct_id": nct_id, "is_applicable_trial": True,
                    "results_due_date": due_date_str, "has_results": True,
                    "fdaaa_status": "Compliant (Late)", "days_overdue": None,
                    "reason": f"Results submitted {late_days} days late on {results_submit_str}",
                }
        except ValueError:
            pass

    if has_results:
        return {
            "nct_id": nct_id, "is_applicable_trial": True,
            "results_due_date": due_date_str, "has_results": True,
            "fdaaa_status": "Compliant", "days_overdue": None,
            "reason": "Results submitted (submission date unverified)",
        }

    return {
        "nct_id": nct_id, "is_applicable_trial": True,
        "results_due_date": due_date_str, "has_results": False,
        "fdaaa_status": "Overdue", "days_overdue": days_overdue,
        "reason": f"Results due {due_date_str}; no results submitted; {days_overdue} days overdue",
    }
