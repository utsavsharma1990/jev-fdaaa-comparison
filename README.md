# ⚡ Jev vs LLM — FDAAA 801 Compliance Comparison

A side-by-side comparison of two architectures for determining FDAAA Section 801 compliance on any clinical trial from ClinicalTrials.gov.

**LEFT:** Deterministic rule-based pipeline (from [clinical-trials-agent](https://github.com/utsavsharma1990/clinical-trials-agent))  
**RIGHT:** Jev typed decisions with confidence scores ([TypeSafe AI](https://typesafe.ai))

Same NCT ID. Same source data. Two decision architectures. The comparison is the product.

---

## What is FDAAA 801?

The FDA Amendments Act (FDAAA) Section 801, enacted September 27 2007, requires **applicable clinical trials** to submit results to ClinicalTrials.gov within **12 months of primary completion date**.

A trial is *applicable* if it is:
1. **Interventional** (not observational)
2. **FDA-regulated** — involves an FDA-regulated drug or device
3. **Phase 2 or later** — Early Phase 1 trials are excluded

Non-compliance carries fines of up to $10,000/day and can affect FDA approval submissions.

---

## Why two architectures?

| | LLM-Based (existing) | Jev-Based (new) |
|---|---|---|
| **Approach** | Deterministic rule-based computation in Python | Typed structured decisions via TypeSafe AI |
| **Output** | Binary verdict + reason string | Answer + per-decision confidence score |
| **Explainability** | One reason sentence | 7 independent typed decisions, each with confidence |
| **Uncertainty** | None — always certain | Surfaces uncertainty via low confidence scores |
| **Speed** | < 5ms (pure Python) | 300–700ms (API call) |
| **Value** | Fast, auditable, no API cost | Shows *where* the AI is uncertain |

The confidence scores are the key differentiator. When Jev returns 59% confidence on a verdict, that's a signal to review the study manually — something a deterministic rule can never express.

---


## Project Structure

```
jev-fdaaa-comparison/
├── jev_fdaaa.py        # Jev-powered determination (7 typed questions)
├── app.py              # Streamlit comparison UI
├── test_queries.py     # CLI test runner for two reference NCT IDs
├── requirements.txt    # typesafe-sdk, streamlit, requests, dotenv
├── .env.example        # JEV_API_KEY template
└── README.md
```

This folder is **standalone** — it does not modify the existing `clinical-trials-agent` project. It imports `get_study_by_nct_id` and `compute_fdaaa_status` from the sibling project via `sys.path`.

---

## Setup

### Prerequisites

- Python 3.11+
- The sibling [clinical-trials-agent](https://github.com/utsavsharma1990/clinical-trials-agent) project cloned at `../clinical-trials-agent` (used for study lookup and LLM-based FDAAA)
- A [TypeSafe AI](https://typesafe.ai) API key

### Install

```bash
cd jev-fdaaa-comparison
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env and set your JEV_API_KEY
```

`.env` contents:
```
JEV_API_KEY=your_key_here
```

---

## Run

**Streamlit UI:**
```bash
python -m streamlit run app.py
```
Then open `http://localhost:8501`, enter any NCT ID, and click **Run Comparison**.

**CLI test (two reference trials):**
```bash
python test_queries.py
```

---

## How Jev Works

`jev_fdaaa.py` calls the TypeSafe AI `system_one` endpoint with:

**State** — a structured dict extracted from the ClinicalTrials.gov study record:
```python
{
    "nct_id": "NCT01866319",
    "study_type": "INTERVENTIONAL",
    "phase": "PHASE3",
    "is_fda_regulated_drug": True,
    "is_fda_regulated_device": False,
    "primary_completion_date": "2015-03-03",
    "has_results": True,
    "results_first_submit_date": "2015-12-09",
    "_computed_deadline_passed": "due_date=2016-03-01, today=2026-09-30, passed=True",
    "_computed_results_on_time": "submitted=2015-12-09, due=2016-03-01, on_time=True",
    ...
}
```

**7 typed questions** sent in a single API call:

| # | Question ID | Type | What it resolves |
|---|---|---|---|
| 1 | `is_interventional` | `Noul` (0–1 probability) | Is study_type interventional? |
| 2 | `is_fda_regulated` | `Noul` | Is drug or device FDA-regulated? |
| 3 | `is_phase_2_or_later` | `Noul` | Is phase Phase 2, 3, or 4? |
| 4 | `results_deadline_passed` | `Noul` | Has PCD + 12 months passed today? |
| 5 | `results_submitted_on_time` | `Noul` | Were results submitted before deadline? |
| 6 | `fdaaa_applicable` | `Choice` | Applicable / Not Applicable |
| 7 | `compliance_status` | `Choice` | Compliant / Overdue / Not Yet Due / Not Applicable |

`Noul` questions return a single float (0–1), converted to `(answer: bool, confidence: float)`.  
`Choice` questions return `(answer: str, confidence: float, probabilities: dict)`.

All 7 questions are evaluated **independently** — the model reasons from the raw state fields for each one, not from the other questions' outputs. This is why the `compliance_status` instructions explicitly encode the applicability check using the raw fields (`is_fda_regulated_drug`, `study_type`, `phase`), rather than depending on the `fdaaa_applicable` answer.

---

## Test Results

### NCT01866319 — Phase 3 compliant trial

```
Study: Phase 3 oncology trial, FDA-regulated drug, PCD 2015-03, results submitted 2015-12-09

LLM  → Compliant
Jev  → Compliant (99% confidence)
      ✅ SYSTEMS AGREE

Jev breakdown:
  is_interventional       : True   99%
  is_fda_regulated        : True   99%
  is_phase_2_or_later     : True   98%
  results_deadline_passed : True   98%
  results_submitted_on_time: True  97%
  fdaaa_applicable        : Applicable      100%
  compliance_status       : Compliant        99%
  Latency: 666ms
```

### NCT07780760 — Not applicable (not FDA-regulated)

```
Study: Interventional, Phase N/A, not FDA-regulated, PCD 2027-01

LLM  → Not Applicable (not FDA-regulated drug or device)
Jev  → Not Applicable (100% confidence)
      ✅ SYSTEMS AGREE

Jev breakdown:
  is_interventional       : True   99%
  is_fda_regulated        : False  97%
  is_phase_2_or_later     : False  97%
  results_deadline_passed : False  96%
  results_submitted_on_time: False 95%
  fdaaa_applicable        : Not Applicable  100%
  compliance_status       : Not Applicable  100%
  Latency: 339ms
```

---

## Confidence Score Interpretation

| Score | Color | Meaning |
|---|---|---|
| ≥ 85% | 🟢 Green | High confidence — verdict is reliable |
| 70–84% | 🟡 Amber | Moderate confidence — worth a manual check |
| < 70% | 🔴 Red | Low confidence — AI is uncertain, review recommended |

A low confidence score on `compliance_status` at 59% (as seen in edge cases) is itself a useful signal — the deterministic LLM pipeline returns a verdict with no uncertainty signal at all. Knowing *when* the AI is unsure is often as valuable as the verdict itself.

---

## Key Design Decisions

**Why pre-compute deadline fields in state?**  
Jev receives a snapshot of the state and reasons from text. Passing `_computed_deadline_passed = "due_date=2016-03-01, today=2026-09-30, passed=True"` is more reliable than asking the model to perform date arithmetic independently.

**Why explicit NOT APPLICABLE rules in `compliance_status` instructions?**  
Jev evaluates all 7 questions independently. Without explicit rules, `compliance_status` can see an interventional Phase 3 trial with a passed deadline and no results — and correctly answer "Overdue" — while `fdaaa_applicable` correctly returns "Not Applicable" because FDA regulation is False. Adding "if not FDA-regulated → MUST be Not Applicable" in the `compliance_status` question resolves the contradiction.

**Why not just use one question?**  
Decomposing into 7 atomic questions follows TypeSafe AI's speculative fan-out pattern. Each question is independently scored, confidence is meaningful at the question level, and the probability distribution shows *why* the model chose a given answer (e.g., 69% Not Yet Due vs 30% Not Applicable is very different from 99% Compliant vs 1% everything else).

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `typesafe-sdk` | ≥ 0.1.0 | TypeSafe AI / Jev client |
| `streamlit` | ≥ 1.35.0 | Comparison UI |
| `requests` | ≥ 2.31.0 | ClinicalTrials.gov API calls |
| `python-dotenv` | ≥ 1.0.0 | .env file loading |

Also inherits from `../clinical-trials-agent`: `tools/clinical_trials_api.py` (no separate install needed if sibling project is present).

---

## Related Project

This is a module extension of the [Clinical Trials Intelligence Agent](https://github.com/utsavsharma1990/clinical-trials-agent) — a 6-agent LangGraph system for querying ClinicalTrials.gov, checking FDAAA compliance, and synthesizing answers with quality scoring.

---

## Author

**Utsav Sharma** — Data Engineering Manager at Norstella Citeline  
[LinkedIn](https://www.linkedin.com/in/utsav001/) · [GitHub](https://github.com/utsavsharma1990)

Built to explore typed structured decisions (TypeSafe AI / Jev) as an alternative decision architecture alongside the deterministic rule-based FDAAA pipeline — comparing explainability, confidence calibration, and latency across real clinical trial data.
