# Glossary: paystub and AGI terms in plain words

> Simple meanings and examples for the terms used in this project.
> All examples use one made-up biweekly paystub (paid every two weeks):
> gross pay $1,052.70, one pre-tax health deduction of $87.00.

---

## The words on a paystub

### Gross pay
**All the money earned in this one paycheck, before anything is taken out.**
- Includes regular pay, overtime, bonus and commission.
- Also called: *Gross*, *Gross Earnings*, *Total Earnings*, *Total Gross*.
- Example: 40 hours × $26.32 = **$1,052.70 gross**.

### Taxes (withholding)
**Money the employer takes out of the paycheck and sends to the government.**
- Common lines: Federal Income Tax (FIT/FED), Social Security (OASDI), Medicare (MED), State tax (SIT), local/city tax.
- Taxes **never** change AGI in this project. They're only used for checks.

### Deductions
**Other money taken out of the paycheck**, for things like health insurance, a 401k or union dues.
- Each deduction is either **pre-tax** or **post-tax** (below).

### Pre-tax deduction
**Taken out *before* tax is worked out, so the person pays tax on less money.**
- **For AGI: subtract it.**
- In this project, a deduction counts as pre-tax **only if the stub clearly says so**, for example:
  - "Pre-Tax", "PRE", "PT", "Before Tax" next to the item or in its section heading;
  - a "Pre-Tax: Y" column;
  - an `*` with a footnote such as "Excluded from federal taxable wages";
  - a handwritten circle or note marking that specific deduction as pre-tax.
- A benefit name alone ("Medical $85") is **not** enough (business answer).

### Post-tax deduction
**Taken out *after* tax is worked out.** It doesn't change the taxable amount.
- **For AGI: ignore it.**
- In this project, anything **without** a clear pre-tax marker is post-tax.

### Net pay
**What actually lands in the bank:** gross − taxes − deductions.
- Also called: *Take-home pay*, *Net*, *Net Check*.
- **Not used for AGI.**

### Federal taxable wages
**The part of this paycheck that federal income tax is charged on**, i.e. gross minus the pre-tax deductions.
- Example: $1,052.70 − $87.00 pre-tax health = **$965.70**.
- Also called: *Federal Taxable Wages*, *Fed Taxable Gross*, *FIT Wages*, *FWT Wages*, *Taxable Wages*, *Taxable Income*.
- An amount **in parentheses after a description** also means taxable wages (source document), e.g. "Gross Pay 1,052.70 **(965.70)**".
- At the end of the year, all of them added up = **W-2 Box 1**.
- **Most important rule:** if this number is printed, AGI comes from it (business answer + source document).

### Social Security wages and Medicare wages
**The amounts the Social Security tax (6.2%) and Medicare tax (1.45%) are charged on.**
- Usually **not** the same as federal taxable wages: a 401k lowers federal taxable wages but **not** Social Security/Medicare wages, while health, dental and vision usually lower both.
- Also called: *OASDI wages*, *FICA wages*, *SS wages*, *MED wages*. Year-end totals: **W-2 Box 3** (Social Security) and **Box 5** (Medicare).
- **Not used for AGI.** We only use them as a **check** (see "Payroll-tax gap").

### Annual salary (annual amount)
**A yearly pay figure printed on the stub**, e.g. "Annual Salary: $27,370.20".
- Also called: *Annual Rate*, *Annual Pay*, *Yearly Salary*.
- **Not** the same as year-to-date (below).
- **Only a backup:** used as the AGI when we can't work out how often the person is paid.

### This Period vs Year-to-Date (YTD)
Most stubs print two columns:

```
                          This Period    Year-to-Date
Federal Taxable Wages        965.70        13,519.80
```

- **This Period** (also *Current*, *Current Period*, *This Pay*): this one paycheck only. **We use this.**
- **Year-to-Date** (*YTD*): everything since January 1 added up. **Never used for AGI.**

### Pay period, pay date
- **Pay period:** the dates the paycheck covers, e.g. 07/01/2026 – 07/14/2026.
- **Pay date:** the day the money is paid, e.g. 07/17/2026.

### Pay frequency and paychecks per year
**How often the person is paid.** We need it to turn one paycheck into a yearly figure.

| Pay frequency | Also written as | Paychecks per year |
|---|---|---|
| Weekly | Wkly | 52 |
| Biweekly | Bi-Weekly, Every two weeks | 26 |
| Semimonthly | Semi-Monthly, Twice a month | 24 |
| Monthly | Mthly | 12 |

- Found by: (1) reading it from the stub, otherwise (2) counting the days in the pay period (14 days = biweekly).

### One-time pay (bonus, overtime)
**Pay that probably won't come every paycheck.**
- It's still income and still taxable. It's just added **once** instead of being multiplied by the number of paychecks (setting `once`).
- **Commission:** if it's the only pay, it's regular pay; if it comes on top of other pay, it's one-time pay (source document; configurable).

### Employer contributions
**Money the employer pays, not the employee**, e.g. 401k match, "Pension ER", employer health share.
- It's not taken out of the employee's paycheck, so **ignore it for AGI**.

### EE / ER / EMP
- **ER** = employer → employer money, ignored.
- **EE** = employee → *who pays*, not tax treatment. Counts as **post-tax** (business answer).
- **EMP** = employee's own contribution (business answer); it's not a pre-tax marker.

### Other terms you may see
| Term | Meaning |
|---|---|
| **401k (traditional)** | Retirement savings. Usually pre-tax, but here it counts only if the stub marks it. |
| **Roth 401k** | Retirement savings taken **after** tax → post-tax. |
| **Section 125 / cafeteria plan** | The employer plan that lets health, dental, vision, HSA and FSA be taken pre-tax. |
| **Imputed income** | A taxable non-cash benefit (e.g. employer-paid life insurance). Often shows in earnings and again as a deduction to cancel it out. |
| **Allowances / reimbursements / stipends** | Left as printed: not removed from or added to gross or taxable wages (source document). |
| **Garnishment, union dues, charity, child support** | Always post-tax. |

---

## The result we calculate

### AGI (Adjusted Gross Income)
**In this project: an estimate of the person's yearly income from one paystub.** (It's not a full tax-return calculation.)

**Basic idea:** AGI = **one paycheck's taxable amount × paychecks per year**

**How we pick the numbers, in order:**

| Step | If... | Then AGI = | Example |
|---|---|---|---|
| 0 | Gross or taxable wages printed as **$0.00** | no AGI ("invalid proof of income") | — |
| 1 | **Federal taxable wages printed** (This Period) | taxable wages × paychecks per year | $965.70 × 26 = **$25,108.20** |
| 2 | Not printed | (gross − pre-tax deductions) × paychecks per year | ($1,052.70 − $87.00) × 26 = **$25,108.20** |
| 3 | We **can't find the pay frequency**, but an annual salary is printed | the annual salary | **$27,370.20** |
| 4 | Nothing usable | no AGI, with a reason | — |

**With a bonus** (steps 1 and 2): the bonus is added once, not × 26.
- Example: taxable wages $1,800 including a $500 bonus, biweekly → ($1,800 − $500) × 26 + $500 = **$34,300**.

---

## Checks (they never change the numbers, they only raise a flag)

| Check | Simple meaning |
|---|---|
| **Grounding** | Every number and word we use must actually be printed on the stub. |
| **Net check** | gross − taxes − deductions should equal net pay. If not, something was misread. |
| **Federal taxable wages check** | If taxable wages are printed, gross − our pre-tax deductions should equal them. If not, a pre-tax decision may be wrong. |
| **Payroll-tax gap** | Social Security tax ÷ 6.2% gives the Social Security wages. If they're clearly below gross, something (often health, dental or vision) was taken out before tax. |

---

## What the open proposal (DL-030) means

**Problem:** the model might copy the **Year-to-Date** taxable wages instead of **This Period** by mistake.

**Proposal:**
1. Always use **This Period** taxable wages. Never use Year-to-Date.
2. If only Year-to-Date taxable wages are printed, act as if taxable wages are **not printed**, and use step 2 (gross − pre-tax).
3. **Safety check:** this paycheck's taxable wages can never be bigger than this paycheck's gross pay. If they are, the model must have copied Year-to-Date. **Flag it and use step 2 instead.**
   - Example: gross $1,052.70, but taxable wages read as $13,519.80 → impossible → use ($1,052.70 − $87.00) × 26 = **$25,108.20**.

---

## Project words

| Term | Meaning |
|---|---|
| **Answer key** | The "correct answers" file for each test paystub, used to check our results. Some keys are known to be wrong and are being corrected. |
| **needs_review** | We can't decide; a person should look. Not used by default any more (business answer). |
| **excluded** | Not an employee deduction at all (employer money, or a tax listed among deductions). |
| **IDR** | Income-driven repayment, the student-loan program this AGI is for. It uses federal taxable wages when printed. |
| **Rule R1–R10** | The ten checks, in order, that decide pre-tax or post-tax for each deduction. |
