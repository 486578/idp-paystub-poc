Updated todo list

# Paystub `employee_pretax` / AGI use case: summary to date (as of 2026-11-04)

## 1. People and context
| Person | Role |
|---|---|
| **Swaroop** (you) | IDP libraries team (`idp-core`, `idp-ocr`, `idp-genai`, `idp-processor`). Investigating the paystub pre-tax/AGI problem. |
| **Kishan Joshi** | Developer who ran the paystub model comparison and owns `maximus-ai-accelerator/idp-paystub-model-comparison`. Main contact for the rules. |
| **Sierra Watkins** | Built the synthetic paystubs and answer keys. Owns a production pre-tax classifier that Kishan calls "empirical/trained": 30% better in her tests, no production improvement yet. |
| **Patrick Ameh** | Wants ideas split into **library-level** changes (`idp-ocr`/`idp-genai`) and **income domain pack-level** changes. |
| **Yashasvi Srivastava** | On the original call; Kishan will point him to stubs to focus on. |

**Business context:** the production IDP pipeline (`maximus-ai-accelerator/fsa-idp-non-sensitive`) processes income documents for federal student-loan **income-driven repayment** applications. Its document types include `income_driven_repayment_application`, and it holds a sample "Pay As You Earn (PAYE) Plan Request". AGI from paystubs feeds income verification. My general understanding is that AGI determines discretionary income and so the monthly loan payment; the exact downstream formula hasn't been confirmed.

## 2. Kishan's exercise (call on 2026-10-27)
- **Data:** 82 synthetic paystubs that Sierra modelled on real cases where extraction failed:
  - `advs_paystubs`: 10
  - `generated_complicated`: 22
  - `generated_scanned`: 50
- **Pipeline:** Textract OCR, then GenAI extraction, mirroring production. It uses `idp-ocr` and `idp-genai`.
- **Models:** NVIDIA, OpenAI gpt-oss-120B, Claude Sonnet 5.5 (text and vision), Llama 3 (production) and Gemma (about 26B, via Bedrock Mantle). Run date: 2026-10-14.
- **Results:**
  - Extraction in the 90s; Sonnet vision best (100% on dates).
  - `employee_pretax` about 75%.
  - **AGI low**: one wrong label makes that stub's AGI wrong.
  - Total deductions also low; Kishan says only pre-tax deductions matter.
- **Kishan's view:** pre-tax is a **classification** problem, not extraction. Stubs show it in many ways (employee/employer tables, EE/ER, `*`, or nothing). The project's rules in the prompt are about two lines, and he suggests solving it "outside just the Bedrock models".

**S3 bucket `idp-paystub-model-comparison`** (`us-east-1`, ATX Global Dev; the `default` profile works):
| What | Path |
|---|---|
| Paystub PDFs | `datasets/pay_stubs/paystubs/<folder>/<stub>.pdf` |
| Answer keys | `datasets/answer_keys/<folder>/<stub>.json` |
| Model outputs | `runs/2026-10-14/<model>/<folder>/<stub>.json` (e.g. `us.anthropic.claude-sonnet-5-5-text`) |

The bucket also holds Textract artifacts written by `idp-ocr`; their format hasn't been checked yet.

**Answer key JSON:**
- Fields: `schema_version`, `stub_id`, `category`, `amounts` (gross, net, total_deductions, taxes, bonus, overtime), `deductions[]` (type, amount, `employee_pretax`), `period`.
- `calculated` block: agi, annual_gross, pay_frequency, periods_per_year, frequency_source, method (`gross_less_pretax`), one_time_total, pretax_deductions, warnings. It's computed from the key's own labels, so it can't confirm them.
- **No field for federal taxable wages**, and no evidence for why a label is `false`.

**Model output JSON:** `results[0]` holds payer, payee, period, pay_frequency, `amounts` (gross, `federal_taxable_gross`, net), `earnings[]`, `deductions[]` (type, amount, description, `employee_pretax`), checks, `amounts_check_passed` and `amounts_check_delta`.

## 3. The failures CSV (`employee_pretax_failures.csv`)
**Columns:** model, dataset_folder, paystub, paystub_pdf_url, answer_key_url, model_output_url, key_category, deduction_amount, key_deduction_type, model_deduction_type, expected_employee_pretax, model_employee_pretax, model_description.

**Mismatches:** 345 in total (Sonnet text 108, Sonnet vision 111, Llama text 126).
- **Every** mismatch is key `false`, model `true`.
- There are 128 distinct failing deductions across 52 stubs.
- **107** of them fail for all 3 models.

**Those 107 shared failures:**
| By type | Count | By dataset | Count |
|---|---|---|---|
| 401k | 34 | generated_scanned | 50 |
| health insurance | 31 | generated_complicated | 48 |
| dental | 20 | advs_paystubs | 9 |
| vision | 12 | | |
| HSA | 6 | | |
| FSA | 2 | | |
| pension | 1 | | |
| retirement | 1 | | |

**Limit:** this is a failures-only report, so it can't give overall accuracy.

**Lesson:** models agreeing doesn't prove the key is wrong, because a shared prompt causes shared errors.

## 4. Concepts (agreed understanding)
| Term | Meaning |
|---|---|
| **Gross pay** | Everything the employee earned in **one pay period** (salary, overtime, bonus, commission) before their taxes and deductions. **Not CTC**: employer contributions aren't part of gross. |
| **Net pay** | Take-home pay: gross − taxes − deductions. **Not used for AGI.** |
| **Deductions** | Money taken from the employee's pay for benefits and similar items (401k, health, union dues…). Taxes are withheld separately. |
| **Pre-tax** | A **label** on a deduction: taken out *before* tax is calculated, so it lowers taxable wages. **For AGI: subtract it.** |
| **Post-tax** | Taken out after tax; doesn't change taxable income. **For AGI: ignore it.** It only lowers net. |
| **Federal taxable wages** | Gross − deductions excluded from federal income tax: the amount federal income tax is charged on. Labels include "Federal Taxable Wages", "FIT Wages", "Fed Taxable Gross". Year-end total = W-2 Box 1. |
| **Social Security wages** | What the 6.2% Social Security tax is charged on. **Not the same as federal taxable wages:** a traditional 401k lowers federal but **not** Social Security wages, and Social Security stops at a yearly cap (around $176k in 2025). W-2 Box 3. **Medicare wages** (1.45%, +0.9% above $200k) are usually the same as Social Security wages but without a cap; W-2 Box 5. |
| **AGI** | Adjusted Gross Income: **yearly**, an IRS measure. In tax terms, taxable income = AGI − standard/itemized deduction, so taxable income is usually lower than AGI. **In this project** AGI is a yearly income estimate from one paystub, and **no tax is calculated**. |
| **EE / ER / EMP** | EE = employee and ER/ERR = employer: **who pays**, not tax treatment. EE can also be a coverage tier ("DENTAL EE/SPOUSE"). **EMP is ambiguous**: employer in some payroll systems, employee in others. |
| **PRE / PT / PRTX** | Pre-tax markers. |
| **Pre-tax (traditional) 401k** | Retirement savings taken before federal income tax and taxed on withdrawal. Lowers federal taxable wages, not Social Security/Medicare wages. Roth 401k is post-tax. Employer match is employer money, not a deduction. |
| **Cafeteria-plan (Section 125) benefits** | Health, dental, vision, HSA and FSA through the employer's plan. Lower **both** federal and Social Security/Medicare wages. |
| **Uniform reimbursement** | Employer repays a required work-uniform expense. Usually non-taxable; may appear in earnings or deductions, often with `*`. If it's included in gross it must be removed before AGI (the README lists it as an item to subtract). Similar: military BAH/BAS. |
| **Imputed income** | Non-cash taxable benefit (e.g. employer-paid life insurance over $50k). Added to taxable wages; may appear in earnings **and** again as a deduction to cancel out the cash. |
| **Employer contributions** | 401k match, "Pension ER", "Payroll Benefits", employer HSA and similar. **Ignored for AGI** (not in gross, not subtracted). Imputed income is the exception above. |

**Taxes on paystubs** (all withheld amounts, all **ignored for AGI**; used only as checks):
- federal income tax (FIT/FED);
- Social Security (SS/OASDI/FICA SS, 6.2%);
- Medicare (MED/FICA MED, 1.45%);
- state income tax (SIT, e.g. "PA SIT", "KS");
- local/city/county taxes (EIT, LST, school district);
- state disability and family leave (SDI, PFL/FLI);
- the employee share of state unemployment (SUTA/SUI, in a few states).

**AGI formulas:**
- If federal taxable wages are printed: **AGI ≈ federal taxable wages × periods**. Strictly, with the one-time rule, **(federal taxable wages − bonus/overtime) × periods + bonus/overtime**.
- Otherwise: **AGI = (gross − bonus/overtime − pre-tax deductions) × periods + bonus/overtime**.
- Periods: weekly 52, biweekly 26, semimonthly 24, monthly 12.
- A wrong label shifts AGI by amount × periods: $100 biweekly is $2,600 a year.

**Simple example:** gross $1,000; 401k $50 (pre-tax); health $100 (pre-tax); Roth 401k $40 and union dues $20 (post-tax); biweekly.
- Federal taxable wages: $850.
- Social Security wages: $900, because the 401k isn't subtracted.
- AGI: $850 × 26 = **$22,100**.

**"Number gap" evidence:**
- If federal taxable wages (or the wages implied by Social Security tax ÷ 6.2%) are **below** gross, the gap is the pre-tax total, even without labels.
- The Social Security math can only reveal Section 125 items, never a 401k or pension.
- Most stubs print **neither** federal taxable wages nor Social Security wages. Of the 5 checked, only stub_0002 printed federal taxable wages. The model returned `federal_taxable_gross: null` on the others.

## 5. Evidence examined (PDFs, answer keys, Sonnet text outputs)
**`advs_paystubs/stub_0006`** (Borough of East Greenville; employee Harold J. Winters; biweekly)
- **Pay:** gross $1,760 (80 hours × $22).
- **Taxes ($367.90):**
  - federal income tax $158.40 (exactly 9%);
  - Social Security $109.12;
  - Medicare $25.52;
  - PA state tax $54.03 (3.07%);
  - local earned-income tax $17.60 (1%);
  - local services tax $2.00;
  - state unemployment $1.23.
- **Deductions ($167.40):** Medical 85, Dental 12, 401k 70.40, under a plain **"Deductions"** heading with no markers.
- **Other:** Benefits column Pension ER $88; net $1,224.70.
- All taxes are calculated on the full gross. Under the README, items under plain "Deductions" aren't pre-tax, so the key's `false` is consistent.
- **AGI:** key AGI $45,760; the model marked medical, dental and 401k `true`, giving $41,407.60, a $4,352.40 difference.
- **Other model errors:** it extracted Pension ER as an employee deduction (amounts check off by −$88) and used different type names (medical vs health_insurance, local_tax vs local_services_tax, other vs state_unemployment).
- Saved as `idp-genai/examples/paystub.png`.

**`advs_paystubs/stub_0002`** (Riverbend Auto Group)
- Health −87.00 is marked `*`, with the footnote "Excluded from federal taxable wages".
- The stub says "Your federal taxable wages this period are $965.70", which is $1,052.70 − $87.
- **Answer key: `true`.**

**`generated_complicated/stub07`**
- Medical labelled "Pre-Tax"; 401k, HSA and FSA coded **PRE**; dental and vision coded **EE** only; Roth separate.
- **Answer key:** dental and vision `false`. All 3 models said `true`.
- **Kishan:** the key is wrong, because "EE and PRE labels indicate pre-tax".

**`advs_paystubs/stub_0010`** (Fredonia Regional Hospital, KS; employee Sandra K. Whitfield; 07/01–07/14/2026, paid 07/17; biweekly; PDF reconfirmed)
- **Earnings:** gross $1,836.22, including imputed income of $4.18.
- **Taxes:** federal income tax $156.56, Social Security $106.95, Medicare $25.02, Kansas $62.43.
- **"Payroll Deductions"** (no pre-tax markers):
  - VISION INSURANCE $11.91, DENTAL EE/SPOUSE $34.65, HLTH EE OPT 2 $55.53;
  - GUARDIAN ACCIDENT $9.00, HOSPITAL INDEMNITY $6.76, MASA EMERGENCY TRANSPORT $7.00;
  - SUN VOLUNTARY LIFE $8.35, MEALS $63.75;
  - PENSION $55.09, VOLUNTARY ROTH $55.09;
  - IMPUTED INCOME $4.18;
  - UNIFORM $0.00 ($49.50 year to date), MISCELLANEOUS $0.00.
- **"Payroll Benefits"** (employer share, ignored): Sun Life/LTD/DLI $20.98, Advanced Life $6.50, HLTH EE OPT 2 $222.12, Pension $73.45. Net $1,173.95.
- **Social Security math:** $106.95 ÷ 6.2% ≈ $1,725, so about **$111** was taken out before tax. If nothing were pre-tax, Social Security would be $1,836.22 × 6.2% = $113.85.
- **Best match across all combinations:** **Health $55.53 + Dental $34.65 + Vision $11.91 + Guardian Accident $9.00 = $111.09**. That gives taxes of $106.96 and $25.01, within 1 cent of the printed $106.95 and $25.02. Health + dental + vision alone ($102.09) doesn't close the gap.
- **Pension:** the Social Security math can't tell whether it's pre-tax for federal income tax.
- **Answer key:** all `false`, AGI $47,741.72.
- **Kishan:** dental and vision should be pre-tax; he's double-checking. He didn't mention health or accident.
- **Model:** marked vision, dental, health and pension `true`, and extracted the Payroll Benefits rows as deductions.

**`generated_complicated/stub08`**
- No markers; Social Security and Medicare match the full gross ($3,381.55).
- Employer contributions are in a separate table, but the model extracted them anyway.
- **Answer key:** all `false`.

**`generated_scanned/stub01`**
- No markers, with one "Taxes and Deductions" table; Social Security and Medicare match the full gross.
- **Answer key:** all `false`.

**`generated_scanned/stub43`**
- Answer key all `false`; model marked medical, dental and 401k `true`.
- Only the JSON was compared; the PDF wasn't viewed.

**Scan of all 82 keys:** 39 deductions are `true`, in 21 stubs.

**Kishan confirms the keys are inconsistent:** both `employee_pretax` and `total_deductions` don't always match the stubs. He's looking at fixes.

## 6. Kishan's extraction prompt (YAML) and its problems
The prompt says pre-tax (`true`) covers 401k, 403b, 457, TSP, health insurance, HSA, FSA, medical, dental, vision, BCBS, dental buy-up, "FICA alternatives" and retirement plans. Post-tax covers Roth, garnishments, union dues and charitable contributions. Employer-paid items (`cs:`, `ER:`, `ERR`, `EMP`, "employer"/"company paid", employer sections) are excluded, and taxes are `false`. When uncertain, it falls back to keyword rules.

**Problems:**
- A category rule isn't always true: Roth variants exist, and health is pre-tax only through a cafeteria plan.
- It never says explicit marks on the stub take priority.
- It leaves out `PRE`, asterisk footnotes, "Sec 125" and pre-tax section headings.
- It mixes up EE (who pays) with tax treatment.

It's the **same category rule** as production's extractor schema (`models.py` in `fsa-idp-non-sensitive`). This is the root cause of the one-sided errors.

## 7. Governing rules: `maximus-ai-accelerator/fsa-idp-non-sensitive` (`main` branch; deployed version not verified)
**`apps/lambda/containerized/idp-paystub-data-extractor/README.md` → "Pre-Tax Deduction Rules"**
- **Decision:** no pre-tax term → use gross; a pre-tax term → subtract. *"Deductions are only removed if they are indicated as 'PRE-TAX.'"*
- **Pre-tax indicators:**
  - "Pre-tax" / `PT` / `PRTX`;
  - "Pre"/"PT" before or after Medical, Dental, Vision, 401K, Life Insurance, Health/HP/HDHP, HSA, or FSA/Dependent care;
  - "Before Tax", "Tax Deferred", "Tax Sheltered", "Tax Exempt", "Non-Taxed"/"No-Tax";
  - "deductions from gross"; "reduces current period taxable" (BAH/BAS);
  - uniform reimbursements; items defined as pre-tax with `*`. If the definition is cut off, check another stub from the same employer.
- **Not pre-tax:**
  - "BT"; plain "Deductions" with no other label; POST EE;
  - Roth; garnishments; union dues; taxes;
  - employer-paid items (`cs:`, `ER:`/`ERR:`, `EMP`).
- *"A benefit name alone (e.g., 'Medical', '401k') is not sufficient evidence."*

**`idp-income-calculator`** (production AGI)
- `utils/constants.py` → `is_indicated_pretax`: a strict allow-list (**"Option A"**). Benefit names only count with a Pre/PT/PRTX qualifier.
- `utils/income_calculators.py`: skips explicitly post-tax items and subtracts only when `is_indicated_pretax` matches. **It ignores the extractor's flag on its own**, and prefers federal taxable wages when present.
- `PAYSTUB_REFACTOR.md`: Options A (strict), **B (benefit name + qualifier, recommended)** and C (strict + manual review).

The extractor also has deterministic federal-taxable-wages extraction from OCR (`extract_federal_taxable_wages_from_ocr`).

## 8. Kishan's repo: `idp-paystub-model-comparison/paystub-extractor` (`main` branch)
**`src/agi.py`**
- Formula: `AGI = (gross − one_time − pretax) × periods + one_time`. Bonus and overtime are one-time; commission is regular pay.
- **Ignores `federal_taxable_gross` on purpose**, to match how the keys were calculated.
- `_is_pretax`: an explicit post-tax/pre-tax marker in the type decides first. Otherwise, a type matching `POSTTAX_EXCLUSIONS` (roth, life insurance, supplemental, ltd/std, accident, garnish, union dues, pension, fica/medicare/ss, aflac, stock…) is not pre-tax. Otherwise it **trusts the model's flag**.
- This is looser than production today.

**Scripts**
- `scripts/populate_agi.py`: writes the keys' `calculated` block from their own labels.
- `scripts/score_accuracy.py`:
  - pairs deduction rows **by amount**;
  - matches type and flag exactly;
  - requires AGI to match to the cent;
  - writes `summary.json/csv`, `summary_counts.csv` and `mismatches.csv`.
- `scripts/run_model_comparison.py`; `scripts/run_mantle_comparison.py` uses `idp_genai.prompts.build_messages` and `aws-bedrock-token-generator`.

**Extraction schema:** type, amount, description (mostly null) and the flag. **No fields for section heading, code columns or footnotes.**

## 9. Q&A with Kishan
**Round 1** (answers 2026-11-02)
1. **What does `false` mean?** "A combination": the label is usually the biggest indicator (401k likely pre-tax, Roth post-tax). See the README.
2. **Which markers count?** PRE, EMP or `*` in the title; a pre-tax true/false column; or a table whose header marks everything under it as pre-tax.
3. **stub07 and stub_0010?** Both keys are wrong; flagged to Sierra. Treat the ground truth with caution.
4. **Production classifier?** Empirical and trained, not fixed rules; Sierra has the details.
5. **No indicator?** `false`, if the label also doesn't meet the "generally pre-tax" criteria.
- **Placement:** keep the feature separate from the IDP extraction libraries, as downstream logic.

**Round 2** (answers 2026-11-03)
- **POC approved:** pre-tax classification is a bottleneck, and he supports testing it as a separate component.
- **"That comment applies to Uniform Reimbursements, but not generally, so I've removed the second comment."** Ambiguous. Probably the asterisk rule or the "check another stub" note applies only to uniform reimbursements. He didn't answer the README-authority, bare "401k" or `EMP` questions.
- **stub07:** "EE and PRE labels indicate pre-tax", so the key is wrong. This conflicts with the README, which doesn't list EE.
- **stub_0010:** dental and vision should be pre-tax; he's double-checking.
- **"Evidence" question:** he noted federal taxable wages and Social Security wages can equal gross when nothing is pre-tax. We meant the opposite case (below gross with no labels), which needs re-asking.
- **Answer keys:** `total_deductions` and `employee_pretax` are inconsistent; he's working on it.

**Conflicts still open:**
| Topic | Kishan | README / production code |
|---|---|---|
| Bare "401k" | Likely pre-tax | Not enough on its own |
| `EMP` | Pre-tax indicator | Employer-paid prefix |
| `EE` | Pre-tax (stub07) | Not listed; POST EE = not pre-tax |
| Asterisk | Uniform reimbursements only? | Used on stub_0002 health, key `true` |
| Production classifier | Trained | Code shows the rule-based `is_indicated_pretax` |

## 10. Final question list (simplified with examples, ready to post)
**A. Which rules to follow**
1. **Source of truth:** is the README's "Pre-Tax Deduction Rules" authoritative? If not, which document or code?
2. **Benefit name only:** is "401k $70.40" or "Medical $85.00" with no PRE/PT/Pre-Tax marker pre-tax? The README says no.
3. **`EMP`:** employer or employee? *Example:* "EMP 401k $50".
4. **`EE`:** always pre-tax, or only in layouts like stub07 (Medical PRE, Dental/Vision EE)? On stub_0010, "DENTAL **EE/SPOUSE**" and "HLTH **EE** OPT 2" look like coverage tiers.
5. **Asterisk:** only uniform reimbursements, or any deduction whose footnote says it's pre-tax? *Example (stub_0002):* "Health −87.00\*" with "\* Excluded from federal taxable wages"; the key says pre-tax.

**B. Using numbers on the stub**

6. **Taxable wages printed:** calculate AGI from that number and skip the labels? *Example (stub_0002):* $965.70 × 26.
7. **No labels, but a gap below gross:** should the matching deductions count as pre-tax, be flagged for review, or be ignored?
   - *Simple example:* gross $1,000, federal taxable wages $850, so $150 was pre-tax.
   - *Real example (stub_0010):* Social Security should be $113.85 if nothing were pre-tax, but the stub shows $106.95 (≈ $1,725 of wages). That's a ≈ $111 gap, matching Health + Dental + Vision + Guardian Accident = $111.09.
   - *Caveat:* the Social Security check doesn't cover a 401k or pension.

**C. Unclear cases**

8. **No clear indicator:** default to not pre-tax, or "needs review"? *Example:* "Hospital Indemnity $6.76".
9. **Target AGI calculation:** production's income calculator (federal taxable wages first, explicit markers only) or `agi.py` (always gross, trusts the model's flag)? *Example:* a "Medical $85" with no marker and a model `true` is subtracted by `agi.py` but not by production.

**Can follow later**

10. **stub07:** dental and vision both pre-tax?
11. **stub_0010:** health, and Guardian Accident, pre-tax as well?
12. **Employer contributions:** confirm they're ignored completely.
13. **Imputed income:** add it when federal taxable wages aren't printed?
14. **Answer keys:** timeline for corrected keys? Is it okay if we hand-verify about 20 stubs and share mismatches?
15. **Sierra's classifier:** separate from `is_indicated_pretax`? Can we get its outputs or indicators to compare?

## 11. Solution design (POC, approved by Kishan)
**Principle:** the **LLM extracts evidence only; deterministic code decides.** A better prompt alone won't fix it, because the root cause is models applying a prompt's category rule.

| Part | Done by |
|---|---|
| Read the stub and copy evidence verbatim: each deduction's label, amount, section heading, code/column (PRE/EE/ER), markers (`*`) and footnote text, plus gross, taxes and federal taxable wages if printed | LLM via **idp-ocr** (layout and tables) + **idp-genai** (schema-based call, Converse or Mantle) |
| Fixed single-value fields (gross, net, dates, federal taxable wages) | Optionally **idp-processor** (label rules first, model only for gaps) |
| Deduction rows (variable-length list) | **idp-genai** directly (idp-processor's table support not verified) |
| Pre-tax decision with the agreed rules; output `pretax` / `not_pretax` / `needs_review`, the rule that matched and the quoted evidence | **Our code** (downstream; later the income domain pack, **not** inside the IDP libraries) |
| AGI: federal taxable wages first, else gross − pre-tax, with the one-time handling | Our code |
| Checks: gross − taxes − deductions = net; Social Security wage gap as a review flag | Our code |

**Disputed points become settings:** `bare_benefit_names`, `emp_means`, `ee_means`, `asterisk_scope`, `tax_math_as_evidence`, the default for unclear cases, and a list of disputed stubs.

**How it differs from Kishan's repo:**
| | Kishan's repo | POC |
|---|---|---|
| Goal | Compare models end to end | Fix the pre-tax decision and AGI |
| Who decides pre-tax | Mostly the model's flag | Code with explicit rules |
| Model's task | Extract and classify | Extract evidence only |
| Federal taxable wages | Ignored | Used first, as production does |
| Unclear cases | Forced `true`/`false` | Sent to review |
| Explanations | None | Rule + quoted evidence per decision |
| Evaluation | Against keys with known errors | Hand-verified set; both error directions; per rule; side by side with `agi.py`, production's `is_indicated_pretax` and the raw model flag |
| Changing a rule | Edit the prompt and re-run every model | Edit the code and re-run on existing extractions |

**Reused:** the same S3 data, the IDP libraries, and possibly his scorer and AGI structure. **Option:** build it as a module inside his repo.

**Steps:**
1. Classifier and evaluation on existing S3 data (keys, model outputs, Textract artifacts). No new model calls; the IDP libraries aren't needed yet, though idp-core may be useful if the artifacts are in its document format.
2. Hand-verify about 20 stubs from the PDFs.
3. Prototype the evidence-only extraction with idp-ocr and idp-genai on one model.
4. Move it into the domain pack.
5. Report to Patrick, split into library-level and domain-pack items.

**Library-level asks** (general capabilities, no tax rules):
- keep table structure and headings from OCR;
- send text and image together;
- support "unknown" answers and source evidence in structured output.

## 12. Tools, environment and files
- **Fetch script:** `idp-genai/examples/fetch_s3_evidence.py` downloaded keys, outputs, PDFs, page PNGs and text (with pypdfium2 and pillow). It's **deleted from the working copy** of branch `feature/bedrock-mantle` (still in git history), and the `evidence/` folder is gone.
- **Downloading a stub with the AWS CLI:** `aws s3 cp s3://idp-paystub-model-comparison/<path> <dest> --profile default --region us-east-1`.
- **Rendering PDFs:** the idp-processor venv has pypdfium2 and pillow, e.g. `python.exe`. Scanned PDFs have no text layer.
- **Local files:**
  - `idp-genai/stub_0010.pdf` (repo root, not git-ignored; **don't commit**);
  - `idp-genai/examples/paystub.png` (= stub_0006);
  - rendered stub_0010 page in `%TEMP%\stub_0010_check`.
- **Network:** S3 works with the `default` profile. **Bedrock Mantle is blocked while on VPN** and reachable with VPN off; Artifactory needs VPN.

## 13. Bedrock Mantle model notes (for the extraction prototype)
- **GPT‑5.x need `base_url=https://bedrock-mantle.us-east-1.api.aws/openai/v1`**; on `/v1` they return 400 or time out. Nemotron and gpt-oss use the default `/v1`.

| Model | Valid JSON (prompt schema, 3 runs) | Images | Notes |
|---|---|---|---|
| **openai.gpt-5.4** | **3/3** | **Yes** | **Best fit**; now the default in `try_mantle.py` |
| openai.gpt-5.5 | 3/3 | Cut off | Image answer hit the 1,024-token limit |
| openai.gpt-oss-120b | 3/3 | No | Text-only; on the Responses API it sometimes returns reasoning only |
| nvidia.nemotron-nano-12b-v2 | 2/3 | Yes | No Responses API; sometimes ignores the tool call with images |
| google.gemma-3-27b-it | 0/3 | Yes | Wraps JSON in code fences |
| Anthropic models | — | — | Support neither OpenAI API on Mantle |
| google.gemma-4-31b | — | — | "Not supported on this route" |
| qwen3-vl, mistral-large-3, ministral-3, kimi-k2.5 | — | — | 403 for this account |

**GPT‑5.4 on `paystub.png` (stub_0006):** read everything correctly, including all taxes, totals (gross $1,760, taxes $367.90, deductions $167.40, net $1,224.70) and Pension ER. One phone digit was wrong.

**Nemotron on the same image:** missed lines and gave wrong totals.

**idp-genai deliberately rejects fenced JSON** (user decision: keep strict parsing).

## 14. Open items / next actions
1. Post the question list (section 10) to Kishan and get answers, especially 1–9.
2. Get corrected keys or agree to hand-verify about 20 stubs.
3. Build POC step 1 on the S3 data. First check the format of the Textract artifacts in the bucket.
4. Count how many of the 82 stubs print federal taxable wages: non-null `federal_taxable_gross` in the outputs and "taxable wages" in the OCR text. That's a free read-only check.
5. Confirm with Kishan/Patrick how AGI is used downstream.
6. Confirm the repo code examined (`main` branches) matches the 2026-10-14 run and what's deployed.