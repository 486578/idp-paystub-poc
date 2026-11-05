# Progress

> Status and history of the build. Update at the end of every work session and every feature.
> Design: [docs/architecture.md](docs/architecture.md). Working rules: [AGENTS.md](AGENTS.md).

**Last updated:** 2026-11-05
**Current phase:** 1. Core logic
**Next action:** start F2 (data models). F0 is done; F1 was dropped (money handling lives in the models).

---

## 1. Feature plan

Status: ⬜ not started · 🟨 in progress · 🔍 in critic review · ✅ done · ⛔ blocked

Order: pure, offline logic first; then the library wrappers; then wiring; then evaluation; then hardening.

| ID | Feature | Module(s) | Depends on | Status | Blocked by |
|---|---|---|---|---|---|
| F0 | Project scaffold: git, `pyproject.toml` (uv, GitHub sources), ruff/mypy/pytest config, `.gitignore`, empty package, environment tests | repo root | — | ✅ | |
| F1 | ~~Money parsing module~~ dropped: amounts are always USD; `Decimal` conversion happens in the models (F2) | — | — | — | |
| F2 | Data models: evidence, decisions, results (Pydantic) | `models.py` | F0 | ⬜ | |
| F3 | Config: `AnalyzerConfig`, YAML loading, defaults, validation; `config/default.yaml` | `config.py` | F2 | ⬜ | |
| F4 | AGI calculation + answer-key replay test (eval 7a) | `agi.py` | F2, F3 | ⬜ | |
| F5 | Rule engine R1–R10 | `rules.py` | F2, F3 | ⬜ | |
| F6 | Checks: grounding, net reconciliation, Social Security/Medicare gap, federal taxable wages | `checks.py` | F2, F3 | ⬜ | |
| F7 | OCR reading wrapper (words + tables, optional page images) | `reading.py` | F0 | ⬜ | |
| F8 | Evidence extraction: schema, prompt, `idp-genai` call | `extraction.py` | F2, F7 | ⬜ | |
| F9 | Evidence store (interface + file store) | `store.py` | F2 | ⬜ | |
| F10 | `PaystubAnalyzer` wiring + public API | `analyzer.py`, `__init__.py` | F3–F9 | ⬜ | |
| F11 | Evaluation harness: download, run, baseline adapter, scoring 7a–7d, report | `evaluation/` | F10 | ⬜ | |
| F12 | "Break it" phase | all | F1–F11 | ⬜ | |
| F13 | Hand-verification support (~20 stubs: record evidence, then labels) | `evaluation/` | F11 | ⬜ | business answers |

Each feature follows AGENTS.md section 6: plan behaviours → TDD → checks green → critic review → fixes → update this file.

---

## 2. Current feature detail

### F0: Project scaffold ✅
**Behaviours (tests in `tests/unit/test_environment.py`):**
- [x] `test_environment_component_package_imports` (red first: `ModuleNotFoundError`, then green)
- [x] `test_environment_idp_core_has_table_models`
- [x] `test_environment_idp_ocr_is_the_tables_branch` (guards against installing the wrong `idp-ocr` branch)
- [x] `test_environment_idp_genai_service_exposes_capabilities`

**Done:**
- `git init` (local only, branch `main`).
- `.gitignore`: secrets, data, PDFs and the reference clone.
- `employee_pretax_failures.csv` moved to `data/`.
- Reference repo cloned (read-only) to `idp-paystub-model-comparison/` (branch `main`, git-ignored).
- `pyproject.toml` with the IDP libraries from GitHub; `uv.lock` pins:
  - `idp-core` `main` @ `b1b8dfa`;
  - `idp-ocr` `feature/tables` @ `b55ebf8`;
  - `idp-genai` `feature/bedrock-mantle` @ `d6a8162`.

**Checks:** ruff ✅ format ✅ mypy ✅ tests ✅ (4 passed) coverage ✅ (empty package)

### F4 preparation: what `agi.py` actually does (read 2026-11-05)
Source: `idp-paystub-model-comparison/paystub-extractor/src/agi.py`. These are **facts from the reference**, to be ported exactly:
- **Formula:** `AGI = (gross − one_time − pretax) × periods + one_time`, in `Decimal`, rounded **once at the end** to cents with `ROUND_HALF_UP`.
- **Periods:** weekly 52, biweekly 26, semimonthly 24, monthly 12, **quarterly 4, annual 1, one_time 1** (the architecture doc listed only the first four).
- **Pay frequency, in order:**
  1. the printed frequency;
  2. otherwise inferred from the period dates (`infer_pay_frequency`: 5–8 days weekly; 13–16 days semimonthly if the period runs 1st/16th to 15th/month-end, else biweekly up to 15 days; 27–32 monthly; 88–95 quarterly; 360–370 annual);
  3. otherwise a caller default;
  4. otherwise AGI is `None` with the warning "Pay frequency could not be determined".
- **One-time:** bonus + overtime. A value in `amounts.bonus`/`amounts.overtime` wins over earnings rows; a key present as `null` counts as 0.
- **No regular pay** (gross < $0.01) but one-time pay: method `one_time_only`, AGI = the one-time total.
- **Deduction amounts** are taken as absolute values.
- **Never raises on bad data:** returns `agi=None` plus a warning instead.
- **Its own pre-tax check** (`_is_pretax`), applied in order:
  1. an explicit post-tax marker in the type;
  2. an explicit pre-tax marker in the type;
  3. a type matching `POSTTAX_EXCLUSIONS` (roth, life insurance, supplemental, ltd/std, accident, critical, cancer, loan, garnish, child support, union dues, charity, pension, simple IRA, stock, aflac, fica/medicare/social security, ...) is **never** pre-tax;
  4. otherwise the `employee_pretax` flag.

  The 7a replay must apply this same check to the key labels to reproduce the keys' AGI.

<!-- Template for each feature:
### F<n>: <name>
**Behaviours (test names):**
- [ ] test_...
**Notes / decisions:**
**Checks:** ruff ⬜ format ⬜ mypy ⬜ tests ⬜ coverage ⬜
-->

---

## 3. Open questions

### Before we start coding: answered 2026-11-05
| ID | Question | Answer |
|---|---|---|
| Q1 | Git? | Local only. Done (`git init`). |
| Q2 | `agi.py` source? | Cloned into `idp-paystub-model-comparison/` (read-only, git-ignored). |
| Q3 | Answer keys in git? | No. Download into git-ignored `data/`; the replay test is skipped when they're absent. |
| Q4 | Package name? | `paystub_agi` |
| Q5 | Dev dependencies incl. `hypothesis`? | Yes. Also added `types-pyyaml` (type stubs needed for mypy strict). |
| Q6 | Coverage targets? | As proposed. |
| Q7 | `money.py`? | Not needed: amounts are always US dollars. `Decimal` conversion lives in the models. |
| Q8 | Failures CSV? | Moved to `data/`. |

### New questions for the user
| ID | Question | Why it matters | Proposed answer |
|---|---|---|---|
| Q9 | `idp-genai` holds `rpds-py` at `2026.6.3` for licence compliance, but that hold isn't inherited, so our lock has `2026.9.1`. Copy the libraries' version holds into our `pyproject.toml`? | Licence-compliance parity with the libraries | Yes, copy them |
| Q10 | `summary.md` holds people's names and synthetic employee names. Commit it, or keep it local (git-ignored)? | Data handling | Keep it local |
| Q11 | `agi.py` also supports quarterly/annual/one-time frequencies and infers frequency from period dates. OK to update architecture sections 5 and 8.2 to match? | Architecture changes need approval | Yes; `agi.py` is the reference |

### Before we start coding (original list, kept for history)
| ID | Question | Why it matters | Proposed answer |
|---|---|---|---|
| Q1 | This folder isn't a git repository. Should I run `git init` here? Is there a remote (GitHub org/repo name) it should push to later? | Commits at green points; `.gitignore` protection for data/secrets | `git init` locally; no remote until you say |
| Q2 | Can we get the source of `agi.py` (repo `idp-paystub-model-comparison/paystub-extractor`)? It isn't cloned locally. | F4 must reproduce it **to the cent**: rounding, pay-frequency fallback, which earnings count as one-time, and how imputed income is handled. Porting it from memory would be guessing. | Clone it read-only next to this repo |
| Q3 | May synthetic **answer keys** (JSON) be committed as test fixtures, or must they stay out of git and be downloaded from S3 when tests run? | The 7a replay test needs all 82 keys | Keep out of git; download into a git-ignored folder; the replay test is skipped if they're absent |
| Q4 | Package name `paystub_agi` OK? | Fixed once published | `paystub_agi` |
| Q5 | Dev dependencies: `pytest`, `pytest-cov`, `ruff`, `mypy`, plus **`hypothesis`** (property-based tests for the break-it phase). OK? Same versions as the IDP libraries where they overlap? | AGENTS.md says ask before adding dependencies | Yes; match the libraries' versions |
| Q6 | Coverage targets in AGENTS.md 5.4: 100% for core logic, ≥90% for wrappers. OK? | Definition of Done | As proposed |
| Q7 | `money.py` is a new module that isn't in architecture section 8.5. It puts money parsing in one place. OK to add it, and update the architecture doc? | Architecture changes need your approval | Yes |
| Q8 | `employee_pretax_failures.csv` sits in the repo root. Keep it, git-ignore it, or move it to a git-ignored `data/` folder? | Data stays out of git | Move to `data/` (git-ignored) |

### Business rules (outside answers pending)
These don't block building; they're **settings** (architecture section 7). The POC default is `needs_review` unless noted.

| ID | Question | Setting |
|---|---|---|
| B1 | Which document/rule set is authoritative for pre-tax? | all |
| B2 | Is a benefit name alone ("401k", "Medical") pre-tax? | `bare_benefit_names` |
| B3 | `EMP`: employer or employee? | `emp_means` |
| B4 | `EE`: pre-tax, or "who pays" / a coverage tier? | `ee_means` |
| B5 | Does the asterisk rule apply only to uniform reimbursements? | `asterisk_scope` (default `any`) |
| B6 | Can a Social Security wage gap alone make a deduction pre-tax? | `tax_math_as_evidence` (default `flag_only`) |
| B7 | No indicator at all: not pre-tax or review? | `unclear_default` |
| B8 | When will corrected answer keys be available? | evaluation |
| B9 | How is AGI used downstream? | reporting only |
| B10 | `agi.py` treats pension, accident, life, supplemental, LTD/STD, critical illness, cancer and Aflac as **never** pre-tax. But on stub_0010 the Social Security math suggests Guardian Accident **was** taken out before Social Security tax. Should our rules include `agi.py`'s never-pre-tax list? | R5 keyword list (`posttax_categories`) |

### Technical questions to verify while building
| ID | Question | When |
|---|---|---|
| T1 | Exact `idp-ocr` call for words + tables, and how Textract `TABLES` are requested through the automatic reader | F7 |
| T2 | How the `idp-genai` service is built for Converse vs Mantle, and how `extract()` returns parsed data and errors | F8 |
| T3 | ~~Confirm `uv` 0.13.0 installs the three GitHub libraries cleanly~~ Resolved: it does (F0). | F0 |

---

## 4. Decisions log

| Date | Decision | Source |
|---|---|---|
| 2026-11-04 | Use `idp-ocr` + `idp-genai` directly, not `idp-processor` (no tables / repeating rows in processor) | architecture D1 |
| 2026-11-04 | `agi.py` is the AGI reference | user |
| 2026-11-05 | Tables come from `idp-ocr` branch `feature/tables` | user + verified in repo |
| 2026-11-05 | Install IDP libraries from GitHub branches (core `main`, ocr `feature/tables`, genai `feature/bedrock-mantle`) | user |
| 2026-11-05 | The caller chooses provider and model; images are sent only if the model supports them | user |
| 2026-11-05 | In memory by default; optional evidence store | user |
| 2026-11-05 | Answer keys are the main automated check, with mismatch triage (7a–7d) | user |
| 2026-11-05 | TDD, a critic review per feature, a final break-it phase, no secrets in the repo | user |
| 2026-11-05 | SOLID principles; nothing environment-specific hard-coded (credentials, model, region, bucket, paths); Pydantic for all model classes | user |
| 2026-11-05 | All amounts are US dollars; no `money.py` | user |
| 2026-11-05 | Git local only; reference repo cloned in-repo and git-ignored; answer keys stay out of git | user |

---

## 5. Review log (critic reviews per feature)

### F0 review (2026-11-05)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | `idp-genai`'s licence version hold (`rpds-py==2026.6.3`) isn't inherited; our lock has `2026.9.1`. | Medium (compliance) | Ask the user (Q9). | Open |
| 2 | `ruff format` also reformatted Python blocks inside markdown (architecture examples). | Low | Excluded `*.md` from ruff. | Fixed |
| 3 | Per-module coverage targets can't be expressed in a single `fail_under`. | Low | Check per module in each critic review, from the `term-missing` report. | Accepted |
| 4 | `test_environment_idp_ocr_is_the_tables_branch` depends on an internal module path of `idp-ocr`. | Low | Intentional branch guard. If `idp-ocr` reorganises, update the test, not the branch. | Accepted |
| 5 | Secret scan: no tokens or credentials in `pyproject.toml` or `uv.lock`. Lock URLs are plain `https://github.com/...#<commit>`. `data/`, PDFs and the reference clone are confirmed git-ignored. | — | — | OK |
| 6 | `summary.md` holds people's and synthetic employee names. | Low (data handling) | Not committed; ask the user (Q10). | Open |
| 7 | A `-m "not integration"` default in `addopts` could hide integration tests. A command-line `-m integration` overrides it (the later option wins). | — | — | OK |

<!-- Template:
### F<n> review (date)
| # | Finding | Severity | Fix (test first) | Status |
-->

---

## 6. Break-it log

_None yet._

---

## 7. Library asks (for the IDP libraries team)

1. `idp-ocr`: merge and release `feature/tables`; add Textract layout (section titles, footers).
2. `idp-genai`: built-in "unknown" answers and source evidence per extracted value.
3. `idp-processor`: support for repeating rows / tables.

---

## 8. Session notes

- **2026-11-05:**
  - Wrote the architecture doc, AGENTS.md and this file.
  - Environment checked: Python 3.14.8 and uv 0.13.0 are installed; the folder isn't a git repo yet.
  - Received answers Q1–Q8. Completed F0. Read the reference `agi.py` (notes in section 2).
