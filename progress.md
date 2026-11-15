# Progress

> Status and history of the build. Update at the end of every work session and every feature.
> Design: [docs/architecture.md](docs/architecture.md). Working rules: [AGENTS.md](AGENTS.md).

**Last updated:** 2026-11-15
**Current phase:** 1. Core logic
**Next action:** F10 (analyzer wiring).

---

## 1. Feature plan

Status: ⬜ not started · 🟨 in progress · 🔍 in critic review · ✅ done · ⛔ blocked

Order: pure, offline logic first; then the library wrappers; then wiring; then evaluation; then hardening.

| ID | Feature | Module(s) | Depends on | Status | Blocked by |
|---|---|---|---|---|---|
| F0 | Project scaffold: git, `pyproject.toml` (uv, GitHub sources), ruff/mypy/pytest config, `.gitignore`, empty package, environment tests | repo root | — | ✅ | |
| F1 | ~~Money parsing module~~ dropped: amounts are always USD; `Decimal` conversion happens in the models (F2) | — | — | — | |
| F2 | Data models: evidence, decisions, results (Pydantic) | `models.py` | F0 | ✅ | |
| F3 | Config: `AnalyzerConfig`, YAML loading, defaults, validation; `config/default.yaml` | `config.py`, `errors.py` | F2 | ✅ | |
| F4 | AGI calculation + answer-key replay test (eval 7a) | `agi.py`, `matching.py`, `evaluation/answer_keys.py` | F2, F3 | ✅ | |
| F5 | Rule engine R1–R10 | `rules.py` | F2, F3 | ✅ | |
| F6 | Checks: grounding, net reconciliation, Social Security/Medicare gap, federal taxable wages | `checks.py` | F2, F3 | ✅ | |
| F7 | OCR reading wrapper (words + tables, optional page images) | `reading.py` | F0 | ✅ | |
| F8 | Evidence extraction: schema, prompt, `idp-genai` call | `extraction.py` | F2, F7 | ✅ | |
| F9 | Evidence store (interface + file store) | `store.py` | F2 | ✅ | |
| F10 | `PaystubAnalyzer` wiring + public API; stub status `needs_review` when any flag has `send_to_review` (incl. stub-level, DL-037); OCR read from the store when saved, model called on every run (DL-039) | `analyzer.py`, `__init__.py` | F3–F9 | ⬜ | |
| F11 | Evaluation harness: download, run, baseline adapter, scoring 7a–7d, report; Textract `mode: sync \| async` setting (DL-035) | `evaluation/` | F10 | ⬜ | |
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

### F2: Data models ✅ (`tests/unit/test_models.py`, 46 tests)
- **Amounts** (`Money`):
  - accepted: int, float (converted through `str()`), `Decimal`, plain numeric strings;
  - rejected: booleans, NaN/infinity, `"$85"`, `"1,234.56"`, `"(85.00)"`, `"N/A"`, empty strings and containers;
  - negatives are kept.
- **Evidence models:** `AmountLine`, `CodeValue`, `Footnote`, `DeductionLine` (no pre-tax field; `in_employer_section` required), `PaystubEvidence` (ISO dates only).
- **Decision models:** `Decision`, `RuleId` (R1–R10), `DeductionDecision` (evidence text required).
- **AGI result models (added in F4):** `PayFrequency`, `AgiMethod`, `FrequencySource`, `AgiResult`.
- All models frozen and `extra="forbid"`; the pydantic mypy plugin is enabled.

### F3: Config ✅ (`tests/unit/test_config.py`, 43 tests)
- **Settings:**
  - `RulesConfig`: the 5 disputed-rule settings + `RuleKeywords`, 11 keyword lists for R1–R9;
  - `AgiConfig`: one-time earning keywords, periods per year (all 7 frequencies required, positive), `default_frequency`.
- **Loading:** `AnalyzerConfig.from_yaml` / `from_mapping`. Every failure raises `ConfigError`: missing file, invalid YAML, Python tags (safe_load), a non-mapping file, unknown keys or bad values.
- `config/default.yaml` documents every default; a test asserts it equals the built-in defaults.

### F4: AGI ✅ (`tests/unit/test_agi.py` 54 tests, `tests/unit/test_matching.py` 18 tests, `tests/acceptance/test_agi_replay.py` 83 tests)
- `compute_agi(evidence, decisions, AgiConfig)` ports the reference `agi.py` (see the facts below). It adds `agi_if_review_pretax` and `review_total` for `needs_review` rows.
- `matching.py`: whole-word, case-insensitive phrase matching, shared by AGI and (next) the rules.
- **7a replay:** `evaluation/answer_keys.py` loads the keys and ports the reference `_is_pretax` exactly. **82/82 keys reproduce `calculated` to the cent**: agi, frequency, source, periods, method, one-time total, pre-tax total and warnings. The keys exercise 21 stubs with pre-tax amounts, 37 with one-time pay and 5 different frequencies.

### F5: Rule engine ✅ (`tests/unit/test_rules.py` 60 tests, `tests/acceptance/test_worked_examples.py` 4 tests)
- **Design:** each rule is a class with `rule_id` and `apply(line, context) -> Verdict | None`. `classify(evidence, RulesConfig, rules=DEFAULT_RULES)` returns one `DeductionDecision` per row, in printed order. The first rule that answers wins. A custom rule list is supported (open/closed); a list that leaves a row undecided raises `ClassificationError`.
- **Where each rule looks:**

  | Rule | Looks at |
  |---|---|
  | R1 | employer section flag; employer markers in label, code values or heading |
  | R2 | tax names in the label |
  | R3 | post-tax markers in label, codes or heading; or a pre-tax column saying "N" |
  | R4 | pre-tax markers in label, codes or heading; or a pre-tax column saying "Y" |
  | R5 | always-post-tax categories in the label |
  | R6 | a row marker whose footnote text has a pre-tax phrase (`asterisk_scope`) |
  | R7 | EE in the label or codes |
  | R8 | EMP in the label or codes |
  | R9 | a benefit name in the label |
  | R10 | catch-all, `unclear_default` |

- **Pre-tax yes/no column** (confirmed by the business in round 1): two new keyword lists, `column_yes_values` and `column_no_values`.
- **Tests:** every rule has "fires", "doesn't fire" and "loses to earlier rules" tests, and every setting value is tested. The worked examples stub_0006 and stub_0002 pass end to end with the expected AGIs.

### F6: Checks ✅ (`tests/unit/test_checks.py` 46 tests; config and model tests extended)
- **API:**
  - `run_checks(evidence, decisions, ChecksConfig, document_text=None, checks=DEFAULT_CHECKS)` returns a `CheckReport`: flags, plus the checks that couldn't run (`not_run`).
  - `apply_review(decisions, report)` moves flagged rows to `needs_review` and records `escalated_from` and `escalated_by`.
- **Checks:**

  | Check | Runs when | Flags |
  |---|---|---|
  | Grounding | OCR text is given | Amounts not found among the document's numbers. Text (labels, headings, codes, footnotes) whose words aren't all in the document. Flags only (DL-019). |
  | Net | gross, net and every amount are present | Stub only. Employer rows are skipped; taxes listed among deductions (R2) are counted. |
  | Federal taxable wages | printed wages and gross are present | Stub, plus R9/R10 rows not already in review → review. |
  | Payroll-tax gap | gross and a single Social Security and/or Medicare line | Every available tax must imply wages below gross. Stub, plus R9/R10 `not_pretax` cafeteria-plan rows → review. |

- **Robustness:** decisions that don't match the evidence rows, and flags pointing at rows that don't exist, raise `InputMismatchError` instead of giving silently wrong results.
- **Settings:** a new `checks` section in `ChecksConfig` and `config/default.yaml` (DL-018, DL-020).

### F7: Reading ✅ (`tests/unit/test_reading.py` 38 tests; `tests/acceptance/test_reading_local_pdfs.py` 3; `tests/integration/test_reading_textract.py` opt-in)
- **API:**
  - `IdpOcrStubReader(ReadingConfig, readers={name: Reader}, downloader=None, renderer=render_pages).read(source, images=bool) -> ReadStub`;
  - `ReadStub` holds the document, text, reader name and images;
  - `StubReader` is the protocol the analyzer will depend on.
- **`document_text`:** page by page; Textract lines, or digital words grouped into lines by height; then each table as `| cell | cell |` rows.
- **Strategy (DL-034):** an ordered list of reader names, tried in order (default `[pdfplumber, textract]`). `pdfplumber` is built in; other names are supplied by the caller. A listed name that isn't supplied raises `ConfigError` at start-up.
- **Sources (DL-031):** a local path, or `s3://bucket/key` downloaded through the caller's downloader into a temp file. That file is used for OCR and images, then deleted.
- **Errors:** every library failure becomes `ReadingError` (with the library's reason code where there is one).
- **Real check (free, local):** stub_0006 and stub_0010 both read with pdfplumber, tables found (2 and 6), and all checked amounts present in the text.

### F8: Evidence extraction ✅ (DL-036; `tests/unit/test_extraction.py` 36 tests; config +7, models +1)
- **API:** `EvidenceExtractor(genai, model=..., config=ExtractionConfig).extract(ReadStub) -> PaystubEvidence`.
  - `wants_images` tells the analyzer (F10) whether to render page images.
  - `genai` is anything shaped like `idp_genai.GenAIService` (the `GenAI` protocol; mypy confirms the real service fits).
- **Prompt (`TASK`):** copy only, never decide pre-tax or calculate; this period only; year-to-date-only counts as not printed; parentheses after a federal tax description = taxable wages (Q20); a lone bracketed amount is copied without brackets and marked `in_brackets` (DL-037); plain numbers; ISO dates; null when not printed.
- **Brackets (DL-037):** new required `in_brackets` field on earnings, tax and deduction lines, and a new `BracketsCheck` that marks the whole stub for review (ignores `checks.send_to_review`; decisions unchanged). Tests: models +3, checks +7, extraction +2.
- **Schema:** generated from `PaystubEvidence`; amounts are "number or null"; no pre-tax field (tested on field names).
- **Failures** raise `ExtractionError(code)`: `refused`, `truncated`, `invalid_json`, `provider_error`, `schema_invalid`, `rejected_input`. Schema errors name field locations only, and the original error isn't chained, so document values can't reach logs.
- **Behaviours:** all done (config: defaults, each `send_images` value, unknown value, null/negative temperature, zero/negative tokens; models: Money JSON schema; extraction: every item in the plan). Verified red before green.
- **Integration (opt-in, not run):** `tests/integration/test_extraction_bedrock.py` reads stub_0006 with the free reader, then calls Bedrock Converse. Needs `PAYSTUB_TEST_AWS_REGION` and `PAYSTUB_TEST_MODEL_ID`.

**Notes:**
- **ASSUMPTION (Q25), superseded by DL-037:** I had read a lone bracketed amount as money taken out without asking. Now the model records `in_brackets` and the stub goes to review until the business answers.

**Checks:** ruff ✅ format ✅ mypy ✅ tests ✅ (527 passed, 2 integration deselected) coverage ✅ (100% line + branch; `extraction.py` 100%)

### F9: Evidence store ✅ (DL-038, DL-039; `tests/unit/test_store.py` 22 tests)
- **API (`store.py`):**
  - `EvidenceStore` protocol (`get`/`put` of text by key); `FileEvidenceStore(folder)` writes `<key>.json` (temp file, then swap).
  - `StoredRead` (OCR text + reader name) with `save_read` / `load_read`; `read_key(file_bytes, ReadingConfig)`: contents + reader strategy + saved format.
  - **Only the OCR read is saved (DL-039):** the model is called on every run; its answers are never reused.
- **Errors:** `StoreError` for an unsafe key, an unreadable or unwritable file, or a damaged item (message names the key, never document values; nothing chained).
- **Behaviours:** all done (file store, read round trip in memory and on disk, every key input, safe file names). Verified red before green; the answer-cache tests were removed with DL-039.

**Checks:** ruff ✅ format ✅ mypy ✅ tests ✅ (551 passed, 2 integration deselected) coverage ✅ (100% line + branch; `store.py` 100%)

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
| Q12 | I left the `tax_math_as_evidence` setting out of the config for now. Its "decide" option needs a design: which deductions explain a Social Security gap? (stub_0010 needed a 4-row combination.) `disputed_stubs` belongs in the evaluation config, not the component. OK to update architecture section 7 to match? | Architecture changes need approval | Yes; the gap stays a review flag (F6) |
| Q13 | One-time pay matches earning labels by whole word ("Overtime 1.5x", "Holiday Bonus" count). Abbreviations like "OT" don't. Add `ot` to the default list? | AGI on stubs that print "OT" | Don't add yet; check the stubs first |
| Q14 | More default keywords suggested by a public paystub-codes guide (not official; see decisions log 2026-11-11). See the list under the table. | Several of these stop a wrong pre-tax decision | Add group A now; groups B and C after review |

**Q14 proposals:**
- **A. Stops a wrong "pre-tax":**
  - R5 `posttax_categories`: `garn` ("GARN" isn't matched by "garnish"), `levy`, `loan` ("401K LOAN" currently reaches R9 as a benefit name), `bankruptcy`, `imputed` (imputed-income offset rows, e.g. stub_0010);
  - R1 `employer_markers`: `match` ("401K Match" with no ER).
- **B. Pre-tax markers:** R4 `pretax_markers`: `s125`, `section 125`, `sec 125`. R9 `benefit_names`: `deferred comp`, `dcfsa`, `dcap`, `tsa`.
- **C. Tax abbreviations for R2 `tax_labels`:** `fwt`, `fed wh`, `ss`, `soc sec`, `swt`, `lit`, `casdi`, `tdi`.
  - Not `med`: it means Medicare tax on some stubs and medical insurance on others.
- **Matching limitation:** joined proprietary codes such as "PX401 EEPRE" aren't matched (`eepre` is one word). This goes to the break-it phase.

| ID | Question | Why it matters | Proposed answer |
|---|---|---|---|
| Q15 | Grounding failures are currently **flagged only** (DL-019). Should a deduction whose label, heading, code or amount can't be found in the OCR text go to `needs_review`? | Defends against the model inventing a "Pre-Tax" heading or code | Yes, send it to review |
| Q16 | **AGI from printed federal taxable wages: settled.** (a) Bonus/overtime is a setting, not a question (DL-027). (b) Frequency found as before (DL-029). (c) This period only; wages above gross treated as a mix-up (DL-030, waiting for the user's OK). (d) Corrected keys including printed taxable wages: nice to have. | — | — |
| Q17 | DL-022: does "no need to flag it for manual review" also mean the checks shouldn't move rows to review? I've switched that off by default (`send_to_review: false`). | Review workload vs catching contradictions | Confirm |
| Q18 | ~~Access to the source-of-truth PDF~~ Resolved 2026-11-13: the user attached it (KnowledgeShare 113287; summary in DL-023/DL-025). | — | — |
| Q19 | $0.00 = invalid proof of income | — | **Answered: yes.** Implemented (DL-026). |
| Q20 | Parentheses = taxable wages | — | **Answered: yes.** Goes into the F8 extraction prompt. |
| Q21 | Handwritten pre-tax notes | — | **Answered: agreed, low priority.** F8 field + a new rule. |
| Q22 | Commission next to other pay | — | **Answered: configurable, counted once by default.** Implemented (DL-026). |
| Q23 | Printed annual amount | — | **Answered: yes.** Implemented (DL-026). |
| Q24 | Several stubs from one employer | — | **Answered: out of scope** (DL-028). |
| Q25 | What does a **lone** bracketed amount mean, e.g. `Medical (85.00)`: money taken out, or taxable wages (source document)? The two-amount tax line `Federal Income Tax (965.70) 120.00` is taxable wages. | Brackets also commonly mean "deducted"; nobody on the project knows | **Open with the business.** Until then such stubs go to review (DL-037). |

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

### Business rules: answered 2026-11-13 (DL-021 to DL-024)
| ID | Question | Answer |
|---|---|---|
| B1 | Source of truth | KnowledgeShare 113287 "Income Types List", section "Pay stubs (US)" (DL-023). Read 2026-11-13; new rules in DL-025. |
| B2 | Benefit name only | Post-tax |
| B3 | `EMP` | The employee's contribution, not the employer's |
| B4 | `EE` | Post-tax |
| B5 | Asterisk | An asterisk plus a footnote saying it's excluded from taxable wages makes any deduction pre-tax |
| B6 | Printed federal taxable wages | Use them for AGI (DL-024; details Q16) |
| B7 | No indicator | Post-tax; no manual review |
| B8 | Corrected answer keys | The business is correcting them to match these rules; expected next week |

Still open with the business: B9 (downstream use of AGI), B10 (`agi.py`'s never-pre-tax list), B11 (short markers `pre`/`pt`; check the PDF), B12 (heading vs row conflict).

### Business rules (original list, kept for history)
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
| B11 | Are "PRE"/"PT" on their own reliable pre-tax markers? E.g. "Pre-Paid Legal" or "PT" meaning part-time. | `pretax_markers` |
| B12 | Conflicting markers: the heading says "After-Tax" but the row says "Pre-Tax". Today post-tax wins (R3 runs before R4), which keeps AGI higher. Should it be `needs_review` instead? | rule order (architecture change) |

### Technical questions to verify while building
| ID | Question | When |
|---|---|---|
| T1 | Exact `idp-ocr` call for words + tables, and how Textract `TABLES` are requested through the automatic reader | F7 |
| T2 | How the `idp-genai` service is built for Converse vs Mantle, and how `extract()` returns parsed data and errors | F8 |
| T3 | ~~Confirm `uv` 0.13.0 installs the three GitHub libraries cleanly~~ Resolved: it does (F0). | F0 |

---

## 4. Decisions log

Moved to [decisionlog.md](decisionlog.md) (2026-11-11). The table below is kept for history only; new decisions go there.

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
| 2026-11-11 | Default keywords: `child support` added to R5; `transit`, `parking`, `commuter` added to R9 (still review by default). Source: the epaystubs.net guides. **Not official**, but they cite IRS Publications 15 and 15-B. Background only; the business team stays the authority on rules. | user |

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

### F2 review (2026-11-11)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | A non-finite `Decimal` check in `models.py` was dead code, because Pydantic already rejects NaN/infinity. | Low | Removed. A test pins the rejection. | Fixed |
| 2 | Amount strings with `$`, commas or brackets are rejected, so one bad amount fails the whole stub's evidence. That's deliberate (a clear error, never a wrong number); the prompt (F8) must ask for plain numbers. | Medium | Covered in F8 and the break-it phase. | Accepted |
| 3 | Labels have no maximum length. | Low | Break-it phase. | Open |
| 4 | Lines have no page number, so multi-page stubs rely on order only. | Low | Revisit if hand-verification needs it. | Accepted |
| 5 | The architecture draft had hours and rate on earnings; dropped because nothing uses them (YAGNI). | Low | — | Accepted |
| 6 | The JSON schema Pydantic generates for `Money` is "number or string". The extraction schema should say "number". | Medium | F8. | Open |

### F3 review (2026-11-11)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | Some default keywords are short and could match unrelated words: `pre` ("Pre-Paid Legal" would read as pre-tax), `pt` (could mean part-time), `er`, `post`. They're whole-word matches and editable in config. | Medium | Break-it tests; business question B11. | Open |
| 2 | `periods_per_year` is a `dict` inside a frozen model, so a caller could mutate it in place. Pydantic copies the default per instance, so instances don't share it. | Low | — | Accepted |
| 3 | `tax_math_as_evidence` and `disputed_stubs` from architecture section 7 aren't in the component config. | Medium | Q12. | Open |
| 4 | Every setting value has an "accepts" test and each setting has a "rejects unknown" test. The YAML security test (a `!!python/object` tag) passes. | — | — | OK |

### F4 review (2026-11-11)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | **Process:** `test_agi.py` was written before `agi.py`, but I didn't run it red before writing the code. Every other red step was run. | Low | Run red every time. | Noted |
| 2 | An empty keyword matched every text in `contains_any`. | High (silent wrong match) | Failing test first, then a guard. Config also rejects empty keywords. | Fixed |
| 3 | The printed frequency is normalised by removing all punctuation, while the reference only removes spaces, hyphens and underscores. Ours also accepts e.g. "Bi-Weekly.". The replay isn't affected, because the keys have no printed frequency. | Low | Documented. | Accepted |
| 4 | One-time detection uses whole-word keyword matching on verbatim labels, while the reference compares a normalised type exactly. Ours is broader ("Overtime 1.5x" counts). | Medium | Q13. | Open |
| 5 | The "exceeds regular pay" warning is only checked for `agi`, not for `agi_if_review_pretax`. | Low | Revisit in F10 if the review range is shown to users. | Open |
| 6 | Warnings never contain amounts or names, as in the reference. | — | — | OK |
| 7 | Would the replay catch a broken formula? Yes: 21 keys have pre-tax amounts and 37 have one-time pay, and every key compares agi, method, frequency and warnings exactly. | — | — | OK |

### F5 review (2026-11-11)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | R1's evidence for employer-section rows was just "employer section", without quoting the heading (breaks golden rule 7). | Medium | Failing test first; the evidence now quotes the heading. | Fixed |
| 2 | The "row has no heading" branch was untested. | Low | Test added; 100% branch coverage. | Fixed |
| 3 | R1 also checks the heading, so a heading like "Employee/Employer Deductions" would exclude **every** row under it. | Medium | Break-it test; consider checking headings only through the model's `in_employer_section` flag. | Open |
| 4 | A heading-level post-tax marker beats a row-level pre-tax marker. | Low | B12. | Open |
| 5 | R6 only looks for pre-tax footnotes. A footnote saying "\* after-tax" is ignored, so the row falls through to later rules. | Low | Break-it phase. | Open |
| 6 | Text in a label is only matched as words; it can't change rule order. Prompt-injection risk lies in the model **inventing** label text, which F6's grounding check (label words must appear in the OCR) will catch. | — | F6. | Noted |
| 7 | **Design:** no I/O, config passed in, rules swappable without editing the engine, and the stand-in rule in the tests satisfies the protocol. | — | — | OK |
| 8 | Evidence strings contain document text. They're part of the result, but must never be logged (AGENTS section 8). | — | Check again in F10. | Noted |

### F6 review (2026-11-11)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | `run_checks` assumed decisions lined up one-to-one with the evidence rows; a shorter or reordered list gave silently wrong net and federal-wages results. | High (silent wrong result) | Failing tests first; now raises `InputMismatchError`. | Fixed |
| 2 | `apply_review` silently ignored a flag pointing at a row that doesn't exist (a buggy custom check would go unnoticed). | Medium | Failing test first; now raises `InputMismatchError`. | Fixed |
| 3 | Test arithmetic: the fixture's net pay was wrong (1,374.56 instead of 1,299.56). Caught while checking the tests by hand, before the first green run. | Low | Fixed in the test. | Fixed |
| 4 | Grounding matches numbers anywhere in the document, so an invented amount that happens to equal another printed number (e.g. a year-to-date figure) passes. It's a weak defence on its own. | Medium | Break-it phase; F7 tables may let us check per row. | Open |
| 5 | Grounding for text needs all of its words somewhere in the document, not next to each other, so a heading stitched together from words elsewhere on the stub would pass. | Low | Break-it phase. | Open |
| 6 | The payroll-tax gap uses the Social Security and Medicare rates from config. The Additional Medicare tax (0.9% above $200k) makes implied wages **higher**, which can't cause a false gap. | — | — | OK |
| 7 | Flag messages include amounts. That's fine for results, but they must never be logged (AGENTS section 8). | — | Check again in F10. | Noted |
| 8 | **Design:** each check is a class behind a protocol; the stand-in check in the tests proves the list can be swapped. Checks have no I/O and only `apply_review` changes decisions, while extracted values are never touched (tested). | — | — | OK |

### F7 review (2026-11-13)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | **Path traversal:** the temp file was named after the S3 key's last part, so a key like `stubs/..` could make the download write outside the temp folder. | High (security) | Failing tests first; the file is now always `paystub` + the extension. | Fixed |
| 2 | Library errors raised by the S3 downloader weren't wrapped in `ReadingError`. | Medium | Failing test first; wrapped. | Fixed |
| 3 | Non-library exceptions from a caller's downloader propagate unchanged. That's deliberate (they aren't swallowed), but callers should know. | Low | — | Accepted |
| 4 | The "no tables found" fallback means a digital stub without a header band goes to paid Textract. The 82-stub run will show how often. | Medium (cost) | Evaluation phase. | Open |
| 5 | The digital reader can't recognise garbled text layers. F6 grounding and the net check are the safety net. | Medium | Break-it phase. | Open |
| 6 | `ReadStub.text` and `images` are `repr=False`, and nothing in `reading.py` logs. | — | — | OK |
| 7 | **Design:** no AWS client or bucket name in `src/`. Readers, downloader and renderer are passed in; stand-ins satisfy the library's protocols. | — | — | OK |
| 8 | **Not run:** the Textract integration test (costs money). Needs `PAYSTUB_TEST_AWS_REGION` (and optionally `PAYSTUB_TEST_STAGING_BUCKET`). | — | Waiting for the user's OK. | Open |

### F8 review (2026-11-13)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | A schema error from Pydantic carries the model's values (document text) in its message and input. Chaining it would put them in tracebacks and logs. | High (data in logs) | Failing test first; the error now lists field locations and error types only, and is raised outside the handler, so nothing is chained. | Fixed |
| 2 | The first "no pre-tax field" test searched the whole schema text and matched a docstring ("deliberately has no pre-tax field"), not a field. | Low (test checked the wrong thing) | Test now walks field names only. | Fixed |
| 3 | Model docstrings become `description`s in the schema the model sees, so editing a docstring changes the prompt. | Low | Accepted; the descriptions are accurate. Keep in mind when editing `models.py`. | Accepted |
| 4 | The schema uses `$defs`/`$ref` (Pydantic's default). Some providers' tool schemas may not accept references. | Medium | Unknown until a real call; the opt-in integration test will show it. Inline the references only if needed. | Open |
| 5 | One bad value (e.g. a date as `07/01/2026`, or an extra field) fails the whole stub with `schema_invalid`. That's deliberate (a clear error, never a wrong number); the prompt asks for ISO dates and the schema forbids extra fields. | Medium | Measure in the evaluation (F11). | Accepted |
| 6 | Temperature `0` is rejected by some newer models; they'll fail with `provider_error`. | Low | Setting `temperature: null` (DL-036). | Accepted |
| 7 | Brackets: the prompt says a bracketed amount means minus, except the federal tax line with two amounts (Q25). Amounts are later used as absolute values by the checks and AGI, so a minus sign on a deduction or tax can't change the result. A negative earnings row stays negative, as printed. | — | — | OK |
| 8 | **Design:** no boto3, model ID or region in `src/`; the service, model ID and settings come from the caller. A real `GenAIService` with a fake `ModelClient` proves the protocol fits and that the OCR text is fenced as untrusted. | — | — | OK |
| 9 | **Not run:** the Bedrock integration test (costs money). Needs `PAYSTUB_TEST_AWS_REGION` and `PAYSTUB_TEST_MODEL_ID`. | — | Waiting for the user's OK. | Open |
| 10 | **Process:** the prompt treated a lone bracketed amount as a deduction (minus). That was my own assumption, made without asking (AGENTS rule 1). | Medium | User chose option 3 (DL-037): record `in_brackets`, send the stub to review. Tests first. | Fixed |
| 11 | Adding a required field could let old "rejected" tests pass for the wrong reason (missing field instead of a bad amount). | Medium (tests) | Money tests now go through a helper that sets `in_brackets`, so they fail only on the amount. | Fixed |

### F9 review (2026-11-15)
| # | Finding | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | A damaged saved item would raise a Pydantic error carrying the saved document values. | High (data in logs) | Test first; `StoreError` names the key only and is raised outside the handler, so nothing is chained. | Fixed |
| 2 | Key parts joined without separators could collide (`"ab"+"c"` = `"a"+"bc"`). | Medium | Test first; every part is length-prefixed, and the two key kinds carry different tags. | Fixed |
| 3 | **Path safety:** only 64-character lower-case hex keys become file names, so a key can't escape the folder (tested with `../`, upper case, wrong lengths). | — | — | OK |
| 4 | If a write fails after the temporary file is written, a `.tmp` file can be left behind. It's never read (only `.json` is). | Low | — | Accepted |
| 5 | Two processes saving the same key at once would share one `.tmp` name. The POC runs one process. | Low | Revisit if F11 runs stubs in parallel. | Open |
| 6 | The model ID is in the fingerprint but the provider isn't (the `idp-genai` service doesn't expose it). The same model ID through Converse and Mantle would share saved answers. | Medium | Moot: answers are no longer saved (DL-039). | Closed |
| 7 | `read_key` needs the file's bytes. For `s3://` sources the analyzer must get the bytes before reading; the reader downloads internally today. | Medium (design) | F10. | Open |
| 8 | `StoredRead` keeps the text, not the OCR library's full document, so a stub loaded from the store has no `Document`. Nothing after reading uses it today. | Low (design) | F10 works from the text. | Open |
| 9 | Page-image rendering is repeatable (checked on stub_0006). | — | No longer needed for keys (DL-039). | Closed |
| 10 | **Design:** the protocol has only `get`/`put`; the in-memory test store is a real implementation; no folder or bucket name is in `src/`. | — | — | OK |
| 11 | **Design change (user, DL-039):** reusing a saved model answer hides run-to-run variation. Removed the answer cache and the extraction fingerprint; the store keeps only the OCR read. | — | — | Done |
| 12 | `docs/architecture.md` section 8.4 still describes saving the model's answer (and "fair comparisons" by reusing it). | Low (docs) | User approved; updated 8.4, the flow diagram, the corrected-keys row, the API comment, "Where things live" and the glossary entry. | Fixed |

<!-- Template:
### F<n> review (date)
| # | Finding | Severity | Fix (test first) | Status |
-->

---

## 6. Break-it log

_Phase not started. Items queued from reviews:_
- Taxable wages slightly above gross because of imputed income (DL-030 fallback would trigger).
- Labels hundreds of characters long (F2 #3).
- Short markers `pre`/`pt`/`er`/`post` matching unrelated words (F3 #1, B11).
- A heading like "Employee/Employer Deductions" excluding every row (F5 #3).
- A footnote saying "\* after-tax" (F5 #5).
- An invented amount equal to another printed number, e.g. a year-to-date figure (F6 #4).
- Joined codes such as "PX401 EEPRE" (Q14).

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
- **2026-11-11:**
  - Downloaded the 82 answer keys into `data/answer_keys/`.
  - Completed F2, F3 and F4; the 82/82 replay passes.
  - Q9–Q11 are still unanswered. I proceeded without them: dependency holds not copied, `summary.md` not committed, and the architecture doc not yet changed (the code follows `agi.py`).
  - Created `decisionlog.md` (DL-001 to DL-020) at the user's request. Keyword additions (DL-017) done. Completed F6 using the approved review policy (DL-018).
- **2026-11-13:**
  - Business answers received (B1–B8).
  - Defaults changed, tests first: benefit names, EE and unclear rows are now post-tax; new `emp_means: employee`; `checks.send_to_review: false`. All 392 tests pass, including the 82-key replay and the updated worked examples.
  - Federal-wages AGI (DL-024) waits on Q16. The source PDF waits on access (Q18).
  - The user attached the source document. Read it and recorded its paystub rules (DL-023, DL-025) and new questions Q19–Q24. No code changes yet.
  - User answered Q19–Q23. Implemented, tests first: $0.00 invalid, commission counted once (configurable), printed annual amount as last resort (DL-026). 411 tests pass, 100% coverage, replay still 82/82.
  - Q24 out of scope. Implemented AGI from printed federal taxable wages with a bonus/overtime setting (DL-027). 422 tests pass, 100% coverage, replay 82/82.
  - Textract sync/async will be a harness setting, built with F11 (DL-035). No code changes.
  - Completed F8 (DL-036), tests first: extraction settings, the prompt, the schema with amounts as numbers, and `ExtractionError` with no document values. 515 tests pass, 100% coverage. Bedrock integration test written, not run.
  - Q25: a lone bracketed amount has no known meaning. Implemented option 3 (DL-037), tests first: `in_brackets` on every line, and a brackets check that sends the stub to review. 527 tests pass, 100% coverage, replay 82/82.
- **2026-11-15:**
  - Completed F9 (DL-038), tests first: file store, typed load/save, content-fingerprint keys and the extraction fingerprint. 556 tests pass, 100% coverage. Open points for F10 (S3 bytes for the key, no `Document` from the store) and F11 (provider in the key).
  - User: the model must be called on every run (answers vary). Removed the answer cache and fingerprint; the store keeps only the OCR read (DL-039). 551 tests pass, 100% coverage.
