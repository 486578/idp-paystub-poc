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
| DL-023 | 2026-11-13 | Rules | Source of truth: the project PDF, page 25 onward (paystub extraction) | Active (document not yet read) |
| DL-024 | 2026-11-13 | AGI | When federal taxable wages are printed, AGI comes from that number | Approved, not implemented |

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

## DL-023: Source of truth is the project PDF
- **Decision:** the project document (SharePoint, TG-AIAccelerator; page 25 onward covers paystub extraction) replaces the earlier README and our assumptions as the authority on rules. Legal has confirmed it can be shared with the team.
- **Status:** the link needs a Microsoft sign-in, so the document hasn't been read yet. Every rule and keyword must be checked against it once it's available.
- **Approved by:** business team.

## DL-024: AGI from printed federal taxable wages
- **Decision:** when a stub prints federal taxable wages, that number is the source of truth. AGI is calculated from it, without gross pay and without the deduction decisions.
- **Departs from the reference:** `agi.py` deliberately ignores federal taxable wages (DL-003/DL-014). Stubs that print them will no longer match the current answer keys' AGI; the business is correcting the keys.
- **Not implemented yet:** the exact formula needs confirming (open questions in progress.md, Q16).
- **Approved by:** business team.
