# Pre-tax rules (R1–R10)

The rules decide, for each deduction, whether it was taken out **before tax**. Only pre-tax deductions lower AGI.

They are checked in order, top to bottom. **The first rule that matches decides**, and the rest are skipped. Settings and word lists are in the `rules` section of [config/default.yaml](../config/default.yaml).

| Rule | Short description | Example | Result |
|---|---|---|---|
| **R1** | The **employer** paid it (marked "ER", "Employer"…, or in an employer section). | "Medical ER" | `excluded` |
| **R2** | It's a **tax** (federal, state, Social Security, Medicare…). | "Fed Withholding" | `excluded` |
| **R3** | The stub **says post-tax** ("Post", "After Tax", "Roth", or a Pre-Tax column showing "N"). | "Roth 401k" | `not_pretax` |
| **R4** | The stub **says pre-tax** ("Pre-Tax", "Before Tax"…, a "Pre-Tax" heading, or a Pre-Tax column showing "Y"). | "401k Pre-Tax" | `pretax` |
| **R5** | It's a type of deduction that is **always post-tax** (garnishment, union dues, charity, child support). | "Child Support" | `not_pretax` |
| **R6** | It has a **star (\*)** and the matching **footnote says pre-tax**. | "Dental\*" + "\*Pre-tax" | `pretax` |
| **R7** | It has the code **"EE"**. | "Dental EE" | setting `ee_means` (now `not_pretax`) |
| **R8** | It has the code **"EMP"**. | "401k EMP" | setting `emp_means` (now `employee`: later rules decide) |
| **R9** | It's a **known benefit** (401k, medical, dental, HSA…) with nothing else on the stub to go on. | "Dental" | setting `bare_benefit_names` (now `not_pretax`) |
| **R10** | **Nothing matched.** | "Gym" | setting `unclear_default` (now `not_pretax`) |

## Results

| Result | Meaning |
|---|---|
| `pretax` | Taken before tax, so it lowers AGI |
| `not_pretax` | Taken after tax, so AGI doesn't change |
| `needs_review` | Unclear; a person should check |
| `excluded` | Not an employee deduction (a tax or employer-paid), so it's ignored |

## Good to know

- **Post-tax wins over pre-tax.** R3 is checked before R4, so "Pre-Tax Roth" counts as post-tax. When in doubt, AGI isn't lowered.
- **Current business rule:** if the stub doesn't clearly say pre-tax, the deduction is treated as post-tax.
- **Matching** is whole-word and ignores capital letters: "pre" matches "PRE" but not "premium".
- **Every decision is explained:** it shows the rule number and the exact words that triggered it.
- **The AI never decides.** It only copies what's printed on the stub; these rules make the decision.
