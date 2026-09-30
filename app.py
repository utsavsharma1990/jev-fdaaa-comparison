"""Jev vs LLM FDAAA Comparison — standalone Streamlit app.

Imports study lookup + LLM-based FDAAA from the existing clinical-trials-agent
project (sibling directory), then adds a Jev parallel determination.

Run with:
    cd jev-fdaaa-comparison
    streamlit run app.py
"""

from __future__ import annotations

import json
import os
import sys

# ── Import from sibling clinical-trials-agent project ────────────────────────
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "clinical-trials-agent")
sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
# Also load from sibling project .env for shared keys
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from tools.clinical_trials_api import compute_fdaaa_status, get_study_by_nct_id  # noqa: E402
from jev_fdaaa import determine_fdaaa_with_jev  # noqa: E402

import streamlit as st  # noqa: E402

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Jev vs LLM FDAAA Comparison · Utsav Sharma",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.hero {
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #1a4a5c 100%);
    border-radius: 12px; padding: 24px 28px 18px; margin-bottom: 20px;
    border: 1px solid #2c5364;
}
.hero h1 { color: #fff; font-size: 1.7em; font-weight: 700; margin: 0 0 6px; }
.hero p  { color: #a8d8ea; font-size: 0.9em; margin: 0; line-height: 1.6; }

.col-header {
    text-align: center; padding: 10px; border-radius: 8px;
    font-weight: 700; font-size: 1em; margin-bottom: 12px;
}
.col-llm  { background: #1a3350; color: #aed6f1; border: 1px solid #2c5364; }
.col-jev  { background: #1a3a1a; color: #a9dfbf; border: 1px solid #2c8a3c; }

.verdict-card {
    border-radius: 10px; padding: 14px 16px; margin-bottom: 8px;
    border-left: 4px solid #ccc;
}
.verdict-compliant    { border-left-color: #27ae60; background: #0d2818; }
.verdict-overdue      { border-left-color: #e74c3c; background: #2c0d0d; }
.verdict-not-yet      { border-left-color: #f39c12; background: #2c1e06; }
.verdict-not-app      { border-left-color: #7f8c8d; background: #1a1e22; }

.verdict-label { font-size: 0.75em; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.verdict-value { font-size: 1.3em; font-weight: 700; }
.verdict-value.compliant { color: #27ae60; }
.verdict-value.overdue   { color: #e74c3c; }
.verdict-value.not-yet   { color: #f39c12; }
.verdict-value.not-app   { color: #95a5a6; }

.conf-bar-wrap { margin-top: 6px; }
.conf-label { font-size: 0.72em; color: #888; margin-bottom: 3px; }
.conf-bar-bg { background: #2a2a3e; border-radius: 4px; height: 6px; }

.bool-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 7px 10px; border-radius: 6px; margin-bottom: 4px;
    background: #12192a; font-size: 0.85em;
}
.bool-label { color: #a8a8b3; flex: 1; }
.bool-val   { font-weight: 700; margin: 0 8px; }
.bool-true  { color: #27ae60; }
.bool-false { color: #e74c3c; }
.conf-chip  {
    font-size: 0.72em; padding: 2px 7px; border-radius: 10px; font-weight: 600;
}
.conf-high { background: #1e5631; color: #a9dfbf; }
.conf-mid  { background: #7d6608; color: #fdebd0; }
.conf-low  { background: #641e16; color: #fadbd8; }

.latency-badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 0.75em; font-weight: 600; background: #1a3a4a; color: #85c1e9;
    margin-top: 8px;
}
.raw-json { font-size: 0.72em; color: #888; font-family: monospace; }
.divider { border-top: 1px solid #2c3e50; margin: 14px 0; }

.trial-meta { background: #12192a; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }
.trial-meta-label { font-size: 0.7em; color: #555; text-transform: uppercase; letter-spacing: 0.4px; }
.trial-meta-value { font-size: 0.85em; color: #ccc; font-weight: 500; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verdict_css(status: str) -> str:
    s = (status or "").lower()
    if "compliant" in s:
        return "compliant"
    if "overdue" in s:
        return "overdue"
    if "not yet" in s:
        return "not-yet"
    return "not-app"


def _conf_chip(conf: float | None) -> str:
    if conf is None:
        return ""
    pct = int(conf * 100)
    cls = "conf-high" if conf >= 0.85 else ("conf-mid" if conf >= 0.70 else "conf-low")
    return f'<span class="conf-chip {cls}">{pct}%</span>'


def _conf_bar(conf: float | None, color: str) -> str:
    if conf is None:
        return ""
    pct = int(conf * 100)
    return f"""
<div class="conf-bar-wrap">
  <div class="conf-label">Confidence: {pct}%</div>
  <div class="conf-bar-bg">
    <div style="background:{color};border-radius:4px;height:6px;width:{pct}%;"></div>
  </div>
</div>"""


def _verdict_card(label: str, status: str | None, conf: float | None, side: str) -> str:
    if status is None:
        return f'<div class="verdict-card verdict-not-app"><div class="verdict-label">{label}</div><span style="color:#666">—</span></div>'
    css = _verdict_css(status)
    conf_color = "#27ae60" if css == "compliant" else ("#e74c3c" if css == "overdue" else ("#f39c12" if css == "not-yet" else "#7f8c8d"))
    conf_html = _conf_bar(conf, conf_color) if side == "jev" else ""
    return f"""
<div class="verdict-card verdict-{css}">
  <div class="verdict-label">{label}</div>
  <div class="verdict-value {css}">{status}</div>
  {conf_html}
</div>"""


def _bool_row(label: str, answer: bool | None, conf: float | None) -> str:
    if answer is None:
        val_html = '<span style="color:#666">—</span>'
    else:
        sym = "✓" if answer else "✗"
        cls = "bool-true" if answer else "bool-false"
        val_html = f'<span class="bool-val {cls}">{sym}</span>'
    chip = _conf_chip(conf) if conf is not None else ""
    return f'<div class="bool-row"><span class="bool-label">{label}</span>{val_html}{chip}</div>'


# ── Main UI ───────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero">
  <h1>⚡ Jev vs LLM FDAAA Comparison</h1>
  <p>
    Same ClinicalTrials.gov data. Two architectures.<br>
    <strong>LEFT</strong>: Deterministic rule-based LLM pipeline (existing clinical-trials-agent)
    &nbsp;·&nbsp;
    <strong>RIGHT</strong>: Jev typed decisions with confidence scores (TypeSafe AI)
  </p>
</div>
""", unsafe_allow_html=True)

nct_input = st.text_input(
    "Enter NCT ID",
    placeholder="e.g. NCT01866319",
    help="Any valid ClinicalTrials.gov identifier",
)

col_run, col_info = st.columns([1, 4])
with col_run:
    run_btn = st.button("▶ Run Comparison", type="primary", use_container_width=True)

if not run_btn or not nct_input.strip():
    st.markdown(
        "<div style='color:#555;font-size:0.85em;margin-top:8px;'>"
        "Enter an NCT ID above and click Run Comparison.</div>",
        unsafe_allow_html=True,
    )
    st.stop()

nct_id = nct_input.strip().upper()

# ── Fetch study ───────────────────────────────────────────────────────────────
with st.spinner(f"Fetching {nct_id} from ClinicalTrials.gov…"):
    study = get_study_by_nct_id(nct_id)

if study.get("error"):
    st.error(f"Could not fetch study: {study['error']}")
    st.stop()

# ── Study summary card ────────────────────────────────────────────────────────
phase = study.get("phase", "N/A")
study_type = study.get("study_type", "N/A")
sponsor = (study.get("sponsor_name") or "N/A")[:50]
pcd = (study.get("primary_completion_date") or "N/A")[:7]
is_drug = study.get("is_fda_regulated_drug", False)
is_device = study.get("is_fda_regulated_device", False)
fda_str = ", ".join(filter(None, [
    "FDA Drug" if is_drug else "",
    "FDA Device" if is_device else "",
])) or "Not FDA-regulated"
has_results = study.get("has_results", False)
title = (study.get("brief_title") or study.get("official_title", ""))[:90]

st.markdown(f"""
<div class="trial-meta">
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px 16px;">
    <div><div class="trial-meta-label">NCT ID</div><div class="trial-meta-value" style="color:#a8d8ea;font-family:monospace;font-weight:700;">{nct_id}</div></div>
    <div><div class="trial-meta-label">Phase</div><div class="trial-meta-value">{phase}</div></div>
    <div><div class="trial-meta-label">Type</div><div class="trial-meta-value">{study_type}</div></div>
    <div><div class="trial-meta-label">FDA Regulation</div><div class="trial-meta-value">{fda_str}</div></div>
    <div style="grid-column:span 2"><div class="trial-meta-label">Sponsor</div><div class="trial-meta-value">{sponsor}</div></div>
    <div><div class="trial-meta-label">Primary Completion</div><div class="trial-meta-value">{pcd}</div></div>
    <div><div class="trial-meta-label">Has Results</div><div class="trial-meta-value" style="color:{'#27ae60' if has_results else '#e74c3c'};">{'✓ Yes' if has_results else '✗ No'}</div></div>
  </div>
  <div style="margin-top:8px;font-size:0.82em;color:#a8a8b3;">{title}</div>
</div>
""", unsafe_allow_html=True)

# ── Run both determinations ───────────────────────────────────────────────────
with st.spinner("Running LLM determination…"):
    llm_result = compute_fdaaa_status(study)

with st.spinner("Running Jev determination…"):
    jev_result = determine_fdaaa_with_jev(study)

# ── Two-column comparison ─────────────────────────────────────────────────────
col_llm, col_jev = st.columns(2)

llm_status = llm_result.get("fdaaa_status", "Unknown")
llm_applicable = "Applicable" if llm_result.get("is_applicable_trial") else "Not Applicable"
llm_reason = llm_result.get("reason", "")

jev_error = jev_result.get("error")
jev_status = None if jev_error else (jev_result.get("compliance_status") or {}).get("answer")
jev_applicable = None if jev_error else (jev_result.get("fdaaa_applicable") or {}).get("answer")
jev_status_conf = None if jev_error else (jev_result.get("compliance_status") or {}).get("confidence")
jev_app_conf = None if jev_error else (jev_result.get("fdaaa_applicable") or {}).get("confidence")
jev_latency = jev_result.get("latency_ms", 0)

with col_llm:
    st.markdown('<div class="col-header col-llm">🤖 LLM-Based (Current)</div>', unsafe_allow_html=True)

    st.markdown(_verdict_card("FDAAA Applicable", llm_applicable, None, "llm"), unsafe_allow_html=True)
    st.markdown(_verdict_card("Compliance Status", llm_status, None, "llm"), unsafe_allow_html=True)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    if llm_result.get("results_due_date"):
        st.markdown(
            f'<div style="font-size:0.8em;color:#888;">Results due: '
            f'<span style="color:#a8d8ea;">{llm_result["results_due_date"]}</span></div>',
            unsafe_allow_html=True,
        )
    if llm_result.get("days_overdue"):
        st.markdown(
            f'<div style="font-size:0.8em;color:#e74c3c;margin-top:4px;">'
            f'{llm_result["days_overdue"]} days overdue</div>',
            unsafe_allow_html=True,
        )
    if llm_reason:
        st.markdown(
            f'<div style="font-size:0.78em;color:#666;margin-top:6px;font-style:italic;">'
            f'{llm_reason}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.75em;color:#555;">Rule-based deterministic computation '
        '— no confidence scores</div>',
        unsafe_allow_html=True,
    )

with col_jev:
    st.markdown('<div class="col-header col-jev">⚡ Jev-Based (New)</div>', unsafe_allow_html=True)

    if jev_error:
        st.warning(f"⚠️ Jev unavailable: {jev_error}")
    else:
        st.markdown(_verdict_card("FDAAA Applicable", jev_applicable, jev_app_conf, "jev"), unsafe_allow_html=True)
        st.markdown(_verdict_card("Compliance Status", jev_status, jev_status_conf, "jev"), unsafe_allow_html=True)

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        bool_questions = [
            ("Interventional study?", "is_interventional"),
            ("FDA regulated?",        "is_fda_regulated"),
            ("Phase 2 or later?",     "is_phase_2_or_later"),
            ("Deadline passed?",      "results_deadline_passed"),
            ("Results on time?",      "results_submitted_on_time"),
        ]
        bool_html = ""
        for label, key in bool_questions:
            item = (jev_result.get(key) or {})
            bool_html += _bool_row(label, item.get("answer"), item.get("confidence"))
        st.markdown(bool_html, unsafe_allow_html=True)

        st.markdown(
            f'<div class="latency-badge">⚡ Jev decision time: {jev_latency}ms</div>',
            unsafe_allow_html=True,
        )

# ── Jev raw response expander ─────────────────────────────────────────────────
if not jev_error and jev_result.get("jev_raw_response"):
    with st.expander("🔍 Jev Raw Response JSON", expanded=False):
        st.json(jev_result["jev_raw_response"])

# ── Agreement indicator ───────────────────────────────────────────────────────
if not jev_error and jev_status and llm_status:
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    llm_norm = llm_status.lower().replace("compliant (late)", "compliant")
    jev_norm = jev_status.lower()
    match = llm_norm == jev_norm
    icon = "✅" if match else "⚠️"
    color = "#27ae60" if match else "#f39c12"
    label = "Systems agree" if match else "Systems differ — review recommended"
    st.markdown(
        f'<div style="text-align:center;padding:10px;border-radius:8px;'
        f'background:#12192a;border:1px solid {color};">'
        f'<span style="font-size:1.2em;">{icon}</span> '
        f'<span style="color:{color};font-weight:600;">{label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
