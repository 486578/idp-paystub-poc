# Decision log

> Every decision that shapes the component: what was decided, why, what else was considered, and who approved it.
> Newest last. Never delete an entry; if a decision changes, add a new entry and mark the old one **Superseded by DL-xxx**.
> Status values: **Active** · **Superseded** · **Provisional** (made to keep moving; waiting for a business answer).

| ID | Date | Area | Decision | Status |
|---|---|---|---|---|
| DL-001 | 2026-11-04 | Architecture | The LLM extracts evidence only; deterministic code decides pre-tax | Active |
| DL-002 | 2026-11-04 | Libraries | Use `idp-ocr` + `idp-genai` directly, not `idp-processor` | Active |
| DL-003 | 2026-11-04 | AGI | `agi.py` from the model-comparison repo is the AGI reference | Active |
| DL-004 | 2026-11-05 | Libraries | Tables come from the `idp-ocr` branch `feature/tables` | Active |
| DL-005 | 2026-11-05 | Libraries | Install the IDP libraries from GitHub branches, not Artifactory | Active |
| DL-006 | 2026-11-05 | Component | The caller chooses provider and model; page images only if the model accepts them | Active |
| DL-007 | 2026-11-05 | Component | In memory by default; saving evidence is optional (evidence store) | Active |
| DL-008 | 2026-11-05 | Evaluation | Answer keys are the main automated check; every mismatch is explained (7a–7d) | Active |
| DL-009 | 2026-11-05 | Process | TDD, a critic review per feature, a final break-it phase | Active |
| DL-010 | 2026-11-05 | Code | SOLID; nothing environment-specific in code; Pydantic for all model classes | Active |
| DL-011 | 2026-11-05 | Money | All amounts are US dollars as `Decimal`; no separate money module | Active |
| DL-012 | 2026-11-05 | Repo | Git local only; reference repo cloned in-repo and git-ignored; data stays out of git | Active |
| DL-013 | 2026-11-05 | Rules | Disputed rules are settings; POC defaults send unclear cases to `needs_review` | Superseded by DL-021 |
| DL-014 | 2026-11-11 | AGI | Port `agi.py` exactly, including quarterly/annual/one-time frequencies and date inference | Active |
| DL-015 | 2026-11-11 | Rules | Rule order R1–R10; explicit post-tax (R3) beats explicit pre-tax (R4) | Provisional |
| DL-016 | 2026-11-11 | Rules | A pre-tax yes/no column counts as an explicit marker | Active |
| DL-017 | 2026-11-11 | Rules | Keywords: `child support` always post-tax; `transit`, `parking`, `commuter` are benefit names | Active |
| DL-018 | 2026-11-11 | Checks | Failed checks never change extracted values; some move decisions to `needs_review` | Partly superseded by DL-022 |
| DL-019 | 2026-11-11 | Checks | Grounding failures are flagged only, for now | Provisional |
| DL-020 | 2026-11-11 | Checks | Default tolerances: net $0.02; wages $1.00 | Provisional |
| DL-021 | 2026-11-13 | Rules | Business answers: only an explicit pre-tax marker makes a deduction pre-tax; EE post-tax; EMP = employee; asterisk + footnote applies to any deduction | Active |
| DL-022 | 2026-11-13 | Checks | Checks flag only by default; moving rows to review is opt-in (`send_to_review`) | Active |
| DL-023 | 2026-11-13 | Rules | Source of truth: KnowledgeShare doc 113287 "Income Types List", section "Pay stubs (US)" | Active |
| DL-024 | 2026-11-13 | AGI | When federal taxable wages are printed, AGI comes from that number; otherwise from gross | Active (implemented, DL-027) |
| DL-025 | 2026-11-13 | Rules | Paystub rules from the source document that the design must add (see entry) | Active (items 1–6); item 7 pending |
| DL-026 | 2026-11-13 | AGI | Commission next to other pay is counted once (configurable); $0.00 pay is invalid; printed annual amount is the last resort | Active |
| DL-027 | 2026-11-13 | AGI | AGI from printed federal taxable wages; bonus/overtime handling is a setting (default: counted once) | Active |
| DL-028 | 2026-11-13 | Scope | Only one paystub per person; no averaging of several stubs | Active |
| DL-029 | 2026-11-13 | AGI | Pay frequency for the federal-wages AGI is found as before: printed, else from period dates | Active |
| DL-030 | 2026-11-13 | AGI | Only this period's taxable wages are used, never year-to-date; wages above gross are treated as a mix-up | Active |
| DL-031 | 2026-11-13 | Reading | Input is a local path or `s3://` URI; no bucket names in code | Active |
| DL-032 | 2026-11-13 | Reading | Reading strategy is a setting (`digital_then_ocr` / `ocr_only` / `digital_only`); the caller supplies the OCR engines in order | Superseded by DL-034 |
| DL-033 | 2026-11-13 | Reading | Page images: at most 3 pages, 144 dpi, greyscale | Active |
| DL-034 | 2026-11-13 | Reading | `reading.strategy` is an ordered list of reader names, tried in that order | Active |
| DL-035 | 2026-11-13 | Reading | Textract sync/async is a caller setting (`textract.mode`), built with F11 | Active (planned) |
| DL-036 | 2026-11-13 | Extraction | Extraction settings (images auto, temperature 0, 8192 tokens); no retries in the component; failures raise `ExtractionError` | Active |
| DL-037 | 2026-11-13 | Extraction / Checks | A lone bracketed amount is recorded (`in_brackets`) and sends the stub to review until its meaning is known | Active (temporary) |
| DL-038 | 2026-11-15 | Store | Evidence store: content fingerprints, OCR read and model answer saved separately, damaged files stop with an error | Partly superseded by DL-039 |
| DL-039 | 2026-11-15 | Store | Only the OCR read is saved; the model is called on every run, never reused | Active |
| DL-040 | 2026-11-15 | Analyzer | Stub status rules, errors raised, one analyzer per model, result contents, path/S3 input | Active |
| DL-041 | 2026-11-15 | Evaluation | Harness setup: 4 models, text only, PDFs downloaded once, pilot first, exact AGI match, Textract sync, no baseline yet | Active |
| DL-042 | 2026-11-15 | Evaluation | Temperature set per model in the harness (Opus 5/Sonnet 5 reject it); 2-page scans left failing under sync | Active |
| DL-043 | 2026-11-17 | Evaluation | `s3` settings optional; only `download` needs them, so own stub sets run without S3 | Active |
| DL-044 | 2026-11-17 | Evaluation | Component settings go in a `component` section of each harness config; `evaluation/component.yaml` removed | Active |
| DL-045 | 2026-11-17 | Rules / AGI / Prompt | `PRE` is a code-only marker; mixed pre-tax headings don't decide; "double time" is one-time pay; prompt skips total and net-pay distribution rows | Active |
| DL-046 | 2026-11-17 | Evaluation | `score` also writes `overview.csv` and "why" tables in `summary.md`: one plain-words cause per AGI mismatch | Active |
| DL-047 | 2026-11-17 | AGI | "award" is one-time pay (closes Q27) | Active |
| DL-048 | 2026-11-17 | Evaluation | Local answer keys may be corrected when the stub clearly contradicts them; each correction is logged (first: advs stub_0009) | Active |
| DL-049 | 2026-11-17 | Prompt | With no line called "gross", the model uses this period's total earnings; the "no total rows" rule only applies to the lists | Active |
| DL-050 | 2026-11-17 | Evaluation | When neither we nor the key have an AGI, it counts as an AGI match (result `both_empty`) | Active |
| DL-051 | 2026-11-19 | Evaluation | Textract `mode: auto`: sync first, staged async only for multi-page PDFs; staging bucket `idp-paystub-poc` | Active (partly supersedes DL-042) |
| DL-052 | 2026-11-19 | Component / Evaluation | `AutoTextractReader` moves into the component (public API); harness `textract.mode` defaults to `auto` with a staging bucket, `sync` without | Active |

---

## DL-001: The LLM extracts evidence only; code decides pre-tax
- **Decision:** the model copies what's printed (labels, amounts, headings, codes, markers, footnotes). It never decides pre-tax status or calculates anything. The extraction schema has no pre-tax field.
- **Why:** in the earlier model comparison, every mismatch went the same way (key "not pre-tax", model "pre-tax"), and 107 of 128 failing deductions failed in all three models. The shared prompt's category rule ("health, dental, 401k are pre-tax") is the root cause. In code, rules are explicit, testable and explainable.
- **Alternatives:** a better prompt (rejected: it's still the model applying a rule); a trained classifier (no access, can't explain its decisions).
- **Approved by:** business team (POC approved), user.

## DL-002: Use `idp-ocr` + `idp-genai` directly, not `idp-processor`
- **Decision:** call `idp-ocr` and `idp-genai` from our component.
- **Why:** `idp-processor` handles single-value fields only. Its README says "tables and nested/repeating fields are out of scope", and deductions are a variable-length list of rows.
- **Alternatives:** `idp-processor` for single values plus `idp-genai` for the rows (two paths for one stub; not worth it for the POC).
- **Approved by:** user.

## DL-003: `agi.py` is the AGI reference
- **Decision:** the AGI formula and its details follow `paystub-extractor/src/agi.py` in the model-comparison repo.
- **Why:** the answer keys' AGI was calculated with it. The "production" calculator mentioned earlier couldn't be located.
- **Approved by:** user.

## DL-004: Tables from `idp-ocr` `feature/tables`
- **Decision:** use that branch: Textract `TABLES` for scanned PDFs, pdfplumber table detection for digital PDFs.
- **Why:** `idp-ocr` `main` only asks Textract for key-value pairs.
- **Limits:** no Textract layout (section titles, footers), so headings and footnotes come from OCR lines or page images.
- **Approved by:** user; verified in the repo.

## DL-005: IDP libraries from GitHub branches
- **Decision:** `idp-core` `main`, `idp-ocr` `feature/tables`, `idp-genai` `feature/bedrock-mantle`, declared in `[tool.uv.sources]`. `uv.lock` pins exact commits.
- **Why:** the table support isn't released to Artifactory yet.
- **Later:** switch back to versioned Artifactory packages once tables are released.
- **Approved by:** user.

## DL-006: The caller chooses provider and model
- **Decision:** the component receives a ready-made `idp-genai` service. Page images are sent only if the service reports image support.
- **Why:** reusability; no model, region or credentials inside the component.
- **Approved by:** user.

## DL-007: In memory by default; optional evidence store
- **Decision:** `analyze()` runs in memory. A caller may plug in an `EvidenceStore` to save and reuse OCR and model output.
- **Why:** production callers usually don't want files. The evaluation needs reuse for cost, fair comparisons (model output varies run to run) and audit.
- **Approved by:** user.

## DL-008: Answer keys are the main automated check
- **Decision:** evaluate in four layers:
  - 7a, replay the keys' own labels through our AGI code;
  - 7b, extraction;
  - 7c, classification, with every disagreement sorted into a bucket;
  - 7d, end-to-end AGI.
- **Why:** they're the only labels for all 82 stubs, but some are known to be wrong, so disagreements must be explained, not just counted.
- **Approved by:** user.

## DL-009: TDD, critic review, break-it phase
- **Decision:** a failing test before code; a self-review against a checklist after each feature; a final phase of deliberately trying to break the component.
- **Approved by:** user.

## DL-010: Coding principles
- **Decision:** SOLID (rules, checks and stores are small swappable objects; dependencies are passed in). No credentials, model IDs, regions, buckets or paths in code. All data classes are frozen Pydantic models.
- **Approved by:** user.

## DL-011: Money
- **Decision:** amounts are US dollars as `Decimal`. Conversion happens once, in model validation; floats go through `str()`.
- **Alternatives:** a separate `money.py` (dropped as unnecessary).
- **Approved by:** user.

## DL-012: Repository and data
- **Decision:**
  - git is local only;
  - the reference repo is cloned into `idp-paystub-model-comparison/`, read-only and git-ignored;
  - answer keys, PDFs, the failures CSV and `summary.md` stay out of git;
  - answer keys are downloaded into `data/answer_keys/`.
- **Approved by:** user.

## DL-013: Disputed rules are settings (provisional defaults)
- **Decision:** `bare_benefit_names`, `ee_means`, `emp_means` and `unclear_default` default to `needs_review`; `asterisk_scope` defaults to `any`.
- **Why:** the business rules aren't agreed yet (questions B1–B12). `needs_review` shows how much depends on each open question.
- **Revisit when:** the business answers.
- **Approved by:** user (architecture review).

## DL-014: Port `agi.py` exactly
- **Decision:** every detail of the reference is ported:
  - all 7 frequencies;
  - frequency from print, then period dates, then a configured default;
  - one-time pay = bonus + overtime, added once;
  - "one time only" when gross < $0.01;
  - deduction amounts taken as absolute values;
  - rounding half up, once at the end;
  - warnings instead of exceptions.
- **Deliberate extensions:**
  - `agi_if_review_pretax`, the AGI range for `needs_review` rows;
  - one-time earnings matched by whole word on verbatim labels;
  - the printed frequency normalised by removing all punctuation.
- **Evidence:** 82/82 answer keys reproduced to the cent.
- **Approved by:** user ("agi.py is our reference").

## DL-015: Rule order (provisional)
- **Decision:** R1 employer → R2 tax → R3 explicit post-tax → R4 explicit pre-tax → R5 always-post-tax category → R6 footnote → R7 EE → R8 EMP → R9 benefit name → R10 catch-all. The first rule that matches wins.
- **Why:** agreed rules first; post-tax before pre-tax so "Roth 401k" or "POST EE" can never be marked pre-tax.
- **Known trade-off:** a heading saying "After-Tax" beats a row saying "Pre-Tax" (B12).
- **Approved by:** user (architecture review).

## DL-016: Pre-tax yes/no column
- **Decision:** a code under a column whose header is a pre-tax marker counts as explicit evidence: a yes value (Y/Yes/X/True) is pre-tax under R4, and a no value (N/No/False) is post-tax under R3.
- **Why:** the business named "a pre-tax true/false column" as a marker (round 1, Q2).
- **Approved by:** business answer.

## DL-017: Keyword additions from the public paystub guides
- **Decision:** `child support` is added to R5 (always post-tax). `transit`, `parking` and `commuter` are added to R9 benefit names, so they still go to review by default.
- **Why:** epaystubs.net guides. They're **not official**, but they cite IRS Publications 15 and 15-B. Used as background only; the business team stays the authority.
- **Pending:** more keywords proposed (progress.md, Q14).
- **Approved by:** user.

## DL-018: What failed checks do
- **Decision:** checks never change extracted values. They add flags, and some flags move specific decisions to `needs_review`:

  | Check | Flag | Moves to `needs_review` |
  |---|---|---|
  | Net reconciliation (gross − taxes − employee deductions ≈ net) | stub | nothing |
  | Federal taxable wages printed ≠ gross − pre-tax | stub | every R9/R10 row not already in review |
  | Social Security **and** Medicare implied wages both clearly below gross | stub | R9/R10 rows decided `not_pretax` whose label is a cafeteria-plan benefit (medical, health, dental, vision, HSA, FSA) |

- **Why:**
  - A federal-wages mismatch means some decision is wrong, and R9/R10 decisions are the ones based on weakest evidence.
  - A payroll-tax gap suggests cafeteria-plan items were taken out before tax, so a `not_pretax` decision on them deserves a human look.
  - Requiring **both** Social Security and Medicare avoids false alarms from the Social Security yearly wage cap.
  - The net check points at extraction problems, not at classification.
- **Interpretation of the proposal:** the original wording was "health, dental or vision". The default list adds medical (a synonym), HSA and FSA, which are also cafeteria-plan items, and it's configurable. Only `not_pretax` rows move for the gap check, because a gap supports pre-tax and so doesn't contradict a `pretax` decision.
- **Each moved decision records** the original decision and the check that moved it.
- **Approved by:** user (2026-11-11, "go ahead with your suggestion").

## DL-019: Grounding failures are flagged only (provisional)
- **Decision:** an amount, label, heading, code or footnote that can't be found in the OCR text gets a flag, but the decision isn't changed.
- **Why:** the proposal approved in DL-018 didn't cover grounding. Moving those rows to review is likely right, but needs the user's OK (progress.md Q15).
- **Approved by:** pending.

## DL-020: Default check tolerances (provisional)
- **Decision:**
  - `net_tolerance` $0.02: gross − taxes − deductions vs printed net.
  - `wage_tolerance` $1.00: printed federal taxable wages vs gross − pre-tax, and wages implied by Social Security/Medicare vs gross.
- **Why:**
  - Net is a sum of amounts rounded to the cent, so a couple of cents covers rounding.
  - Implied wages divide a tax rounded to the cent by a small rate, so rounding alone can move them by about $0.08 (Social Security) or $0.34 (Medicare).
  - $1.00 is above that noise and far below any real deduction.
- **Revisit when:** evaluation on the 82 stubs shows false flags or misses.
- **Approved by:** made while implementing the approved check proposal (DL-018); configurable in `checks`.

## DL-021: Business answers on the disputed rules (supersedes DL-013)
- **Decision (defaults in `config/default.yaml`):**

  | Question | Answer | Setting |
  |---|---|---|
  | Benefit name only ("401k $70.40", "Medical $85.00") | Post-tax | `bare_benefit_names: not_pretax` |
  | `EMP` | The **employee's** contribution, not the employer's. It's not a pre-tax marker, so the rules after R8 decide. | `emp_means: employee` (new option; R8 doesn't fire) |
  | `EE` | Post-tax. This corrects the earlier "EE = pre-tax" for stub07; the guidelines don't list EE as a pre-tax indicator. | `ee_means: not_pretax` |
  | Asterisk | An asterisk **and** a footnote saying it's excluded from taxable wages make **any** deduction pre-tax, not just uniform reimbursements. | `asterisk_scope: any` (unchanged) |
  | No clear indicator | Post-tax; no manual review needed | `unclear_default: not_pretax` |

- **Effect:** by default no deduction is sent to `needs_review`, and AGI is a single number (the review range collapses). stub_0006: $45,760, which matches its answer key. stub_0002: $25,108.20 (pre-tax by the footnote).
- **Still to check against the source document (DL-023):**
  - the exact explicit pre-tax markers (R4 keywords, including the short ones `pre`/`pt`, B11);
  - whether our footnote phrases (R6) are wider than "excluded from taxable wages".
- **The earlier settings remain available,** e.g. `needs_review`, for sensitivity runs.
- **Approved by:** business team (answers received 2026-11-13).

## DL-022: Checks flag only by default (partly supersedes DL-018)
- **Decision:** `checks.send_to_review` defaults to `false`.
  - The federal-wages and payroll-tax-gap checks still name the affected R9/R10 rows, but don't move them to `needs_review`.
  - Setting it to `true` restores the DL-018 behaviour.
- **Why:** the business answered "Anything without a pre-tax marker is post-tax, so there's no need to flag it for manual review."
- **Interpretation (needs confirmation):** I read this as also covering review triggered by the checks, not just the rule defaults.
- **Alternatives:** keep escalation on (rows the numbers contradict get a human look); remove escalation entirely (loses a useful option).
- **Approved by:** derived from the business answer; awaiting user confirmation.

## DL-023: Source of truth is the project document
- **Decision:** KnowledgeShare document 113287, "Income Types List" (41 pages, printed 2025-06-10), replaces the earlier README and our assumptions as the authority. Paystubs are covered by **"Pay stubs (US)"** (pages 25–27). Related sections: Pay stubs (Foreign), Commission, Allowances and Reimbursements, Stipends.
- **Handling:** the document is marked "Confidential and Proprietary Information of Maximus". It isn't stored in the repo; only short paraphrases appear here.
- **Which program applies:** the rules differ by program. **IDR/FRAT/DHAR** use federal taxable wages; **ISR** uses gross wages. This project is income-driven repayment (IDR), so the IDR rules apply.
- **Not covered by the document:** it doesn't list the pre-tax marker words (PRE, PT, ...), and it doesn't say how bonus/overtime combine with federal taxable wages. Those still rest on the business answers (DL-021) and Q16.
- **Approved by:** business team (Legal confirmed it can be shared).

## DL-024: AGI from printed federal taxable wages
- **Decision:** when a stub prints federal taxable wages, that number is the source of truth. AGI is calculated from it, without gross pay and without the deduction decisions. If the wages can't be determined, aren't listed or are illegible, gross is used (the current method).
- **Confirmed by the source document:** "Must use the federal taxable wages when available" (Pay stubs (US), IDR/FRAT/DHAR).
- **Departs from the reference:** `agi.py` deliberately ignores federal taxable wages (DL-003/DL-014). Stubs that print them will no longer match the current answer keys' AGI; the business is correcting the keys.
- **Not implemented yet:** the exact formula needs confirming (open questions in progress.md, Q16).
- **Approved by:** business team; source document.

## DL-025: Further paystub rules from the source document (proposed)
Each item still needs a design decision before coding (progress.md Q19–Q24).

| # | What the document says (paraphrased) | What it means for the component |
|---|---|---|
| 1 | An amount in parentheses after a description represents **taxable wages**. | Extraction (F8) must capture it as federal taxable wages. |
| 2 | $0.00 in the taxable-income or gross field = **invalid proof of income** (deny). | No AGI; the result says "invalid". This differs from `agi.py`, which calculates "one-time only" AGI when gross is 0 but there's a bonus. |
| 3 | Pre-tax can be shown **in writing**, by circling or annotating specific deductions on the stub. A blanket note ("$200 of this pay is pre-tax") doesn't count. | A new kind of explicit pre-tax evidence. Extraction needs a per-row handwritten-note field; vision models only. |
| 4 | The printed **annual amount** may be used if gross/federal taxable wages are unavailable or the frequency can't otherwise be determined. | A new last-resort AGI path, and an extraction field. |
| 5 | **Commission:** commission alone goes in the federal-taxable-wages column; commission alongside other pay goes in the **overtime/bonus** column. | Commission becomes one-time pay when there's other pay. `agi.py` treats it as regular pay. |
| 6 | **Allowances and reimbursements** (and stipends) on a stub are neither removed from nor added to gross/taxable wages. | Earnings stay as printed. Uniform reimbursements aren't subtracted as pre-tax deductions. |
| 7 | **Several valid stubs from one source** are averaged, then multiplied by the pay frequency. | Out of scope for the one-stub component; the caller could do it later. |

- **Contrast to note:** for **letters** (employer, explaining income, retirement, self-employment), the document says to remove any pre-tax deduction, "including items such as medical insurance with no pre-tax label". That rule is for letters, not paystubs; for paystubs the business answer is that unmarked items are post-tax (DL-021).
- **User decisions (2026-11-13):**
  - 1 parentheses = taxable wages: **yes** (extraction, F8);
  - 2 $0.00 = invalid: **yes**;
  - 3 handwritten notes: **agreed**, low priority (F8 and a new rule);
  - 4 annual amount: **yes**;
  - 5 commission: **configurable, counted once by default**;
  - 7 averaging: explanation requested.
- **Approved by:** user.

## DL-026: AGI changes from the source document (implemented)
- **$0.00 is invalid (item 2):**
  - if printed gross or federal taxable wages are $0.00 (anything under one cent), AGI is `None`, `invalid_proof_of_income` is true, and the warning says so;
  - this **replaces** the reference's "one-time only" method (gross 0 with a bonus), which no longer exists;
  - none of the 82 keys used it.
- **Commission (item 5):**
  - `agi.commission_with_other_pay: one_time` (default) counts commission once when any other earning line has a non-zero amount; commission alone stays regular pay;
  - `regular` restores the reference behaviour;
  - labels come from `agi.commission_earnings` (default `commission`).
- **Annual amount (item 4):**
  - a new evidence field `annual_amount` holds a printed yearly figure, never year-to-date;
  - it's used, as is, when the frequency can't be found from the stub or gross is missing;
  - it's checked **before** the caller's `default_frequency`, because a printed figure beats a configured guess.
- **Replay:** still 82/82. The answer-key adapter doesn't pass commission or an annual amount, so it keeps reproducing the reference.
- **Approved by:** user.

## DL-027: AGI from printed federal taxable wages (implements DL-024)
- **Order of methods:**
  1. $0.00 gross or taxable wages → invalid;
  2. printed annual amount, if the frequency is unknown or no pay figure is printed;
  3. configured default frequency;
  4. **printed federal taxable wages** (method `federal_taxable_wages`);
  5. gross − pre-tax (method `gross_less_pretax`).
- **Deduction decisions don't change this AGI.** The printed wages already reflect pre-tax deductions, so `agi_if_review_pretax` equals `agi`. The decisions are still reported for explanation, and the federal-wages check (F6) still compares them.
- **Bonus/overtime is a setting:** `agi.one_time_with_federal_wages`.
  - `once` (default) = `(wages − one_time) × periods + one_time`;
  - `annualise` = `wages × periods`.
  - Bonus/overtime **is taxable** and included in the printed wages either way; the setting only decides whether that one-off amount is multiplied by the number of pay periods.
  - The default matches the gross formula and the source document's separate overtime/bonus column. The user confirmed (2026-11-13) that this is a setting, not a business question.
- **stub_0002:** $965.70 × 26 = $25,108.20, whatever the asterisk setting.
- **Replay:** unaffected; the answer keys don't contain federal taxable wages.
- **Approved by:** user.

## DL-028: One paystub per person
- **Decision:** the component handles one paystub at a time. Averaging several stubs from the same employer (source document) is out of scope.
- **Approved by:** user.

## DL-029: Pay frequency for the federal-wages AGI
- **Decision:** the federal-wages AGI still needs the number of paychecks per year. It's found the same way as for gross: the frequency printed on the stub, otherwise worked out from the pay period dates. The printed annual amount is the fallback when neither works (DL-026).
- **Approved by:** user ("if taxable wages is printed we will obviously need the pay frequency").

## DL-030: This period only, never year-to-date (proposed)
- **Decision:**
  1. AGI uses only the **this-period** taxable wages; a year-to-date figure is never used.
  2. If only a year-to-date figure is printed, the taxable wages count as "not printed", so AGI falls back to gross − pre-tax.
  3. **Safety check:** this-period taxable wages greater than this-period gross are impossible. Most likely the year-to-date column was read by mistake. Flag it, ignore the taxable wages, and use gross − pre-tax.
  4. The extraction prompt (F8) tells the model to copy only the this-period column.
- **Why:** AGI multiplies one paycheck by the paychecks per year, so a year-to-date figure would count the same money many times (stub_0002: $351k instead of $25k).
- **Implemented:** item 3 in `compute_agi` (warning "Federal taxable wages are above gross pay (year-to-date figure?); used gross instead"). Items 1, 2 and 4 belong to the F8 extraction prompt.
- **Known edge case:** imputed income added to taxable wages but not to gross could legitimately push taxable wages slightly above gross. We'd fall back to gross with a warning. Revisit in the break-it phase if real stubs show it.
- **Approved by:** user (2026-11-13).

## DL-031: Input is a local path or an S3 URI
- **Decision:** `read()` accepts a local file path or `s3://bucket/key`.
  - An S3 file is downloaded to a temporary file through a downloader **supplied by the caller**, used for both OCR and page images, then deleted.
  - The Textract **staging bucket** (needed for multi-page scans) and the region are given by the caller when it builds the OCR reader.
  - No bucket name or region appears in the component's code or config.
- **Approved by:** user (the user will create the staging bucket).

## DL-032: Reading strategy is a setting
- **Decision:** `reading.strategy` chooses the order:

  | Strategy | What runs |
  |---|---|
  | `digital_then_ocr` (default) | pdfplumber, then OCR only when the digital read looks wrong |
  | `ocr_only` | OCR only |
  | `digital_only` | pdfplumber only; never calls a paid service |

  - The OCR engines are passed in by the caller as an **ordered list** of `idp-core` `Reader`s (e.g. Textract, then another engine). They're tried in order.
  - A strategy that needs OCR with no OCR reader supplied raises `ConfigError` at start-up.
- **When the digital read "looks wrong"** (library behaviour, verified in `idp-ocr` `feature/tables`):
  - no pages or no text;
  - images cover half or more of a page;
  - tables were requested but none found;
  - a page has zero words;
  - a timeout or temporary error (retried first).
- **Why:** different stub sets (digital vs scanned) and cost control; reusable with other OCR engines.
- **Approved by:** user.

## DL-033: Page image defaults
- **Decision:** at most 3 pages, 144 dpi, greyscale (the `idp-ocr` `render_pages` defaults). Configurable in `reading`.
- **Approved by:** user.

## DL-034: Reading strategy is an ordered list (supersedes DL-032)
- **Decision:** `reading.strategy` lists reader names in the order to try them, e.g. `[pdfplumber, textract]` (default) or `[pdfplumber, textract, other_ocr]`.
  - Each reader runs only if the one before it failed or gave an unusable read.
  - `pdfplumber` (free, local) is built in.
  - Every other name must be supplied by the caller as `readers={"textract": TextractReader(...), ...}`. A listed name that isn't supplied raises `ConfigError` at start-up.
  - Readers that are supplied but not listed never run.
  - Names are lower-case letters, digits and `_`, and each may appear **once** (a duplicate would just pay twice for the same failing read).
- **Examples:** free only = `[pdfplumber]`; OCR only = `[textract]`; three-step = `[pdfplumber, textract, other_ocr]`.
- **Why:** the user wants to be able to chain any number of readers.
- **Approved by:** user.

## DL-035: Textract sync/async is a caller setting
- **Decision:** the evaluation harness config gets a `textract` section: `mode` (`sync` | `async`), `region` and `staging_bucket`.
  - `sync`: the reader gets no staging bucket. 1-page local files only; more pages give a clear `ReadingError`.
  - `async`: the reader gets the staging bucket (upload, read, delete). Any page count.
  - `async` without a bucket fails at start-up with a clear error.
  - `s3://` files are always read asynchronously by `idp-ocr`, whatever the mode.
- **Where:** a harness helper `build_textract(mode, region, staging_bucket)`, built and tested with F11. The component (`src/`) is unchanged: it never builds readers (DL-010, DL-031).
- **Why:** `idp-ocr` has no mode switch; it decides only on whether it gets a staging bucket. Region and bucket are caller choices.
- **Alternatives:** a component setting (rejected, because the component doesn't build the reader); `auto` (sync for 1 page, async for more), which is left out unless the stubs turn out to be mixed, because it needs our own page count.
- **Approved by:** user (build with F11).

## DL-036: Extraction design (F8)
- **Decision:**
  - New `extraction` settings: `send_images: auto | never` (default `auto`: images only if the model takes them), `temperature` (default `0`, `null` = model default), `max_output_tokens` (default `8192`).
  - The **model ID is passed in by the caller** with the `idp-genai` service, never in config or code.
  - The schema sent to the model is generated from `PaystubEvidence` (one source of truth); amounts appear as "number or null".
  - **No retries in the component.** The caller configures retries (e.g. adaptive mode, attempt count) on the boto3 client/session it passes to `idp-genai`. A model failure (refused, cut off, invalid JSON, or JSON that doesn't fit the schema) raises `ExtractionError` with a `code`; never a guessed value.
  - Error messages never contain document values: schema errors list field locations only, and the original exception isn't chained.
  - **No extra text cleaning or size cap** before the call. The OCR text is still fenced as untrusted by `idp-genai`.
  - Handwritten pre-tax notes (Q21) come later, as their own small feature after F10.
- **Alternatives:** temperature `null`; 4096 tokens; retry once in the component; a 100,000-character cap with control-character cleaning.
- **Approved by:** user (2026-11-13).

## DL-037: A lone bracketed amount goes to review (temporary)
- **Problem:** the source document says "an amount in parentheses after a description represents taxable wages". Brackets are also a common way to print money taken out, e.g. `Medical (85.00)`. Nobody on the project knows which meaning applies to a lone bracketed amount, and our two local stubs have no example.
- **Decision (until the business answers Q25):**
  - **Two amounts on a tax line**, e.g. `Federal Income Tax (965.70) 120.00`: the bracketed amount is the federal taxable wages (Q20, unchanged).
  - **A lone bracketed amount**, e.g. `Medical (85.00)`: the model copies the number without brackets (`85.00`) and sets a new field `in_brackets: true` on that line (earnings, taxes and deductions). It no longer turns brackets into a minus sign.
  - A new check (`brackets`) flags every such line and marks the **stub** for review (`send_to_review`), whatever `checks.send_to_review` says, because the uncertainty is about what the number is, not about pre-tax status. Pre-tax decisions are not changed.
- **Why:** don't guess; a clear review flag instead of a possibly wrong number.
- **Supersedes:** my earlier F8 assumption that a lone bracketed amount is simply a deduction (made without asking).
- **Approved by:** user (2026-11-13, "option 3").

## DL-038: Evidence store design (F9)
- **Decision:**
  1. **Same stub** = same file **contents** (a SHA-256 fingerprint), not the file name.
  2. **Two saved items:** the OCR read (shared by every model, so Textract is paid once per stub) and the model's answer (one per model setup).
  3. **OCR read key:** file contents + `reading.strategy` + the saved format. **Answer key:** the OCR text + the images sent + an automatic fingerprint of the model ID, prompt, schema and extraction settings. Any change to the prompt or schema means a fresh call; there is no version number to remember.
  4. **Saved:** the OCR text and reader name, and the extracted evidence. **Not** page images (big, rebuilt from the PDF) or the OCR library's full document.
  5. A damaged or unreadable saved item raises `StoreError` (no silent re-run). The message never contains document values.
  6. File names are the fingerprint (64 hex characters) + `.json`; any other key is refused. Files are written to a temporary file first, then swapped in, so a crash can't leave a half-written file.
- **Where:** `store.py` (`EvidenceStore` protocol with `get`/`put`, `FileEvidenceStore`, key builders, typed load/save). The folder comes from the caller and must be git-ignored (e.g. under `data/`).
- **Approved by:** user (2026-11-15).

## DL-039: The model is called on every run (partly supersedes DL-038)
- **Decision:** the store saves **only the OCR read**. The model's answer is never saved for reuse: every run calls the model again, even for the same stub and model.
- **Why (user):** the same model can give different answers for the same stub, so reusing a saved answer hides that variation; reusing it "doesn't make sense at all".
- **Removed:** the answer key (`evidence_key`) and the model-setup fingerprint (`EvidenceExtractor.fingerprint`). DL-038 items 1, 5 and 6 (content fingerprint, damaged-file error, safe file names) still apply to the OCR read.
- **Consequences:** each evaluation run pays for one model call per stub per model; OCR is still paid once per stub. Run-to-run differences between answers become visible, which is wanted.
- **Approved by:** user (2026-11-15).

## DL-040: Analyzer behaviour (F10)
- **Decision:**
  1. **Stub status:** `invalid` when gross or taxable wages are $0.00 (DL-026); otherwise `needs_review` when any flag has `send_to_review` (e.g. brackets, DL-037), any deduction is `needs_review`, or AGI couldn't be calculated; otherwise `ok`. `invalid` wins, because there is no AGI to review.
  2. **Failures:** a reading or model failure raises `ReadingError` / `ExtractionError`; no result is returned. The evaluation harness records the stub as failed.
  3. **One analyzer per model.** Several analyzers can share one store, so OCR is still paid once per stub.
  4. **Result:** status, the AGI result, every deduction decision (rule + quoted evidence), all flags, the checks that couldn't run, the extracted evidence, the reader used and whether the read came from the store. **Not** the OCR text.
  5. **Input:** a local path or `s3://` URI (DL-031). An S3 file is downloaded once to a temporary file, used for the fingerprint, OCR and page images, then deleted.
- **Design:** `PaystubAnalyzer(config, reader=..., extractor=..., store=None)` only wires the steps (dependency injection); `PaystubAnalyzer.create(config, genai=..., model=..., readers=..., downloader=..., store=...)` builds the standard parts for callers. `ReadStub` now keeps the page numbers instead of the OCR library's document, so a read loaded from the store is complete and page images can be re-rendered.
- **Approved by:** user (2026-11-15).

## DL-041: Evaluation harness setup (F11)
- **Models (one per family, Bedrock, us-east-1):** `us.anthropic.claude-opus-5`, `us.anthropic.claude-sonnet-5`, `google.gemma-3-27b-it`, `openai.gpt-oss-120b-1:0`. Chosen by the user from the account's model list.
- **Provider:** Converse by default; Mantle only where a model requires it (a per-model setting).
- **Text only for now:** the harness's component settings use `extraction.send_images: never`.
- **Stub PDFs:** downloaded once from `s3://<bucket>/datasets/paystubs/<folder>/` into git-ignored `data/paystubs/<folder>/`; runs read the local copies. (Corrected 2026-11-15: the bucket's real layout; the reference script's `datasets/pay_stubs/paystubs/` doesn't exist.)
- **Pilot first:** 5 stubs × 1 model, results and call counts shown to the user before any full run.
- **Scoring:** 7b extraction, 7c classification (disagreement buckets), 7d AGI **exact to the cent** (the size of each difference is reported). Scored against the current keys; the keys folder is a setting, so corrected keys can be swapped in.
- **Textract:** `mode: sync` by default (DL-035).
- **Not now:** the baseline adapter (old model outputs through our rules).
- **Where settings live:** a harness YAML file (`evaluation/config.yaml`, git-ignored; `evaluation/config.example.yaml` committed with placeholders). Region, bucket, model IDs and retry settings live there; credentials come from the AWS profile only.
- **Approved by:** user (2026-11-15).

## DL-042: Per-model temperature; 2-page scans (pilot findings)
- **Finding:** the first pilot run failed every Opus call. A direct check showed Bedrock rejects any `temperature` for **Opus 5 and Sonnet 5** ("`temperature` is deprecated for this model"); **Gemma 3 27B and GPT-OSS 120B** accept `temperature: 0` and our forced-tool schema (checked with one tiny call each).
- **Decision:** each model in the harness settings may set `temperature`. When given (even as `null`), it replaces the component's `extraction.temperature` for that model only; otherwise the component value (0, DL-036) applies. Opus and Sonnet use `null`; Gemma and GPT use `0`.
- **Also decided:** the 2 two-page scanned stubs (`generated_scanned/stub06`, `stub17`) stay failing under Textract `sync` for now (no staging bucket).
- **Alternative:** `temperature: null` for every model (less repeatable for the models that support 0).
- **Approved by:** user (2026-11-15).

## DL-043: S3 settings are optional in the harness
- **Decision:** `s3` in the harness settings may be left out. Only the `download` command needs it, and it stops with a clear `ConfigError` when it's missing. `run` and `score` work on any local folders laid out as `<group>/<stub>.pdf` + `<group>/<stub>.json`.
- **Why:** the harness should run on the team's own stubs and answer keys, not just the 82 in S3; a placeholder bucket name was confusing.
- **Alternative:** keep `s3` required and use a placeholder (rejected: misleading).
- **Approved by:** user (2026-11-17).

## DL-044: Component settings inside the harness config (partly supersedes DL-041)
- **Decision:** each harness config has an optional `component` section with the component settings for that run (same keys as `config/default.yaml`; anything not listed keeps its default). The separate `evaluation/component.yaml` and the `component_config` path are removed. The demo uses the built-in defaults.
- **Why:** one file per run is simpler; a second file only for one setting was confusing.
- **Note:** the harness's model capabilities are text-only, so no images are sent even without `send_images: never`; the committed configs still state it.
- **Alternative:** keep a separate file per run (rejected by the user).
- **Approved by:** user (2026-11-17).

## DL-045: Fixes from the first subset run (Opus, 30 stubs)
- **Decisions:**
  1. **`PRE` only as a code.** It moved from `pretax_markers` to a new `pretax_codes` list that R4 checks in code columns only. Why: in a label, whole-word matching split "Pre-Pocketed Cash Tip Offset" into "pre" + "pocketed" and made it pre-tax (complicated/stub03, −$3,900). Cost: a label like "Medical PRE" (no code column) no longer counts. `pt` stays a marker for now.
  2. **Mixed headings don't decide.** R4 ignores a pre-tax heading that also contains a word from `mixed_heading_words` (other, taxes, withholding, withholdings), e.g. "Pre-Tax, Taxes, and Other Deductions". Rows under it need their own marker. Why: the heading covers pre-tax *and* other rows (scanned/stub05: "Benefits / Other" was made pre-tax). R3 (post-tax headings) is unchanged.
  3. **"Double time" is one-time pay** (added to `agi.one_time_earnings`). Why: it's overtime at twice the rate; the keys treat it as overtime (complicated/stub07, stub08).
  4. **Prompt:** don't list total/subtotal rows or net-pay distribution rows (direct deposit, checking). Why: 20 such extra rows in the run.
- **Effect (replay of the saved Opus evidence, no model calls):** exact AGI 18 → 21 of 30. scanned/stub05 still differs: with the heading ignored, its 401(k) and Medical rows have no marker and become post-tax under R9 (key: pre-tax).
- **Alternatives:** keep `pre` for labels but not before a hyphen (too clever); split the mixed heading into its parts (guessing).
- **Approved by:** user (2026-11-17).

## DL-046: A simple report with plain-words causes
- **Decision:** `score` also writes `overview.csv` (model, stub, result, our AGI, key AGI, difference, why) and adds "AGI mismatches" and "Failed" tables to `summary.md`. The "why" lists, in order: pre-tax disagreements (with rule), rows sent to review, missing pre-tax rows, extra rows counted pre-tax, field differences that change AGI (gross, one-time pay, period dates), and "ours starts from the printed federal taxable wages". Results: `match`, `mismatch`, `failed`, `both_empty`. The score now records our AGI method for this. `stubs.csv` and `rows.csv` are unchanged.
- **Why:** the detailed CSVs were hard to read in one go.
- **Note:** `both_empty` is still counted as not exact in the totals; changing that wasn't approved.
- **Approved by:** user (2026-11-17).

## DL-047: "Award" is one-time pay (closes Q27)
- **Decision:** "award" is added to `agi.one_time_earnings`, so a line such as "Award / Other" is counted once, not multiplied by the pay periods.
- **Why:** the keys treat "Award / Other" as a bonus (generated_scanned/stub01 +$2,500, stub03 +$3,125 before this).
- **Approved by:** user (2026-11-17).

## DL-048: Correcting local answer keys
- **Decision:** when a stub clearly contradicts its answer key, the local key copies (`data/answer_keys/` and `data/subset/answer_keys/`, git-ignored) are corrected to the printed figures. The S3 originals stay unchanged. Every correction is listed here with before/after values.
- **Corrections:**

  | Stub | Field | Was | Now | Evidence on the stub |
  |---|---|---|---|---|
  | advs_paystubs/stub_0009 | `amounts.gross` | 5744.49 | 5741.25 | "Gross Earnings 5,741.25" (current); every other earnings line is 0.00 this period |
  | | `amounts.total_deductions` | 1663.16 | 1659.92 | The key's own deduction rows add up to 1,659.92; 5,741.25 − 1,659.92 = printed net 4,081.33 |
  | | `calculated.annual_gross` | 137867.76 | 137790.00 | 5,741.25 × 24 |
  | | `calculated.agi` | 134497.68 | 134419.92 | (5,741.25 − 140.42) × 24 |

- **Why:** the key had $3.24 in gross and in total deductions that isn't printed in the current column, so it marked a correct reading as wrong.
- **Alternative:** list the stub in `disputed_stubs` only (rejected: that doesn't change the AGI comparison).
- **To do:** tell the key owners so the S3 originals can be fixed; a fresh copy of the keys from S3 would undo this.
- **Approved by:** user (2026-11-17).

## DL-049: Gross from a total when no line is called "gross" (prompt)
- **Decision:** the prompt now says: if no line is called "gross", use this period's total earnings (e.g. "Total Earnings" or "Check Totals"); and totals may still be used for gross and net (the DL-045 "no total rows" rule only applies to the earnings, taxes and deductions lists).
- **Why:** in `subset-opus-2`, advs stub_0003 (a payroll register whose only gross figure is "Check Totals 2,000.00") came back with no gross, so no AGI; in the run before DL-045 it was read correctly.
- **Alternative (not done, needs business approval):** in code, use the sum of the earnings lines when gross is missing, with a warning and a review flag.
- **Approved by:** user (2026-11-17).

## DL-050: No AGI on both sides counts as a match
- **Decision:** when our result and the answer key both have no AGI (e.g. no pay frequency printed), the scorer counts it as an AGI match. The overview still labels it `both_empty`, and it no longer appears in the "AGI mismatches" table. Our AGI missing while the key has one (or the reverse) is still a mismatch. Supersedes the DL-046 note.
- **Why:** both sides correctly refuse to produce a number from missing information (complicated/stub05).
- **Approved by:** user (2026-11-17).

## DL-051: Textract "auto" mode (partly supersedes DL-042)
- **Decision:** the harness setting `textract.mode` gains `auto`. The harness builds two idp-ocr readers: plain sync, and one with the staging bucket. `auto` tries sync first; only when sync refuses the file as unsupported input (multi-page PDF, refused before any AWS call) is it read again through the staging bucket (upload to `idp-ocr/<id>`, async job, file deleted afterwards). Other errors are not caught. `auto` and `async` need `staging_bucket`; `sync` refuses one. The real configs use `auto` with `idp-paystub-poc` (us-east-1).
- **Why:** multi-page stubs (e.g. advs stub_0007) failed under sync, which DL-042 had accepted for the time being. With `async`, every stub would go through S3 and polling; `auto` keeps one-page stubs on the faster sync path.
- **How it's built:** in `evaluation/clients.py`, so the component and the IDP libraries are unchanged. idp-ocr treats "unsupported input" as final (no fallback to the next reader), so listing two Textract readers in `reading.strategy` wouldn't work; a small wrapper reader does the switch.
- **Also:** `evaluation/subset.yaml` is now git-ignored like `config.yaml`, because it holds a real bucket name (DL-041 keeps real infrastructure names out of git).
- **Needs:** S3 put/get/delete on the bucket and Textract async permissions for the developer's AWS login.
- **Approved by:** user (2026-11-19).

## DL-052: Auto Textract as a component building block; harness mode default
- **Decisions:**
  1. The auto-switching reader moves from the harness into the component as `AutoTextractReader(sync, staged)` in `reading.py`, exported from `paystub_agi`. The caller still builds both Textract readers (with its own region and bucket) and passes the wrapper in `readers`. The component still creates no AWS clients and holds no bucket names.
  2. In the harness, `textract.mode` is optional: left out, it is `auto` when `staging_bucket` is set and `sync` when it isn't. An explicit mode still wins and is still checked against the bucket.
- **Why:** any team using the component gets the multi-page fallback without copying harness code; one less harness setting to get wrong.
- **Rejected:** putting the Textract mode in `config/default.yaml` (the component config holds business settings only; the mode needs a bucket, which is infrastructure, and would make the component build AWS clients).
- **Approved by:** user (2026-11-19).
