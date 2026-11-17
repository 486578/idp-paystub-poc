"""Ask the caller's model to copy evidence from a paystub (architecture step 3).

The model only copies what is printed; it never decides pre-tax status (the schema
has no such field) and never calculates. Retries belong to the caller's client.
"""

from typing import Protocol

from idp_core.exceptions import IdpError
from idp_core.models import ModelCapabilities
from idp_genai.responses import ParsedResponse
from idp_genai.service import Attachment
from pydantic import ValidationError

from paystub_agi.config import ExtractionConfig
from paystub_agi.errors import ConfigError, ExtractionError
from paystub_agi.models import PaystubEvidence
from paystub_agi.reading import ReadStub

TASK = """\
Copy the facts printed on this US paystub into the JSON schema. Only copy: do not \
decide whether any deduction is pre-tax or post-tax, and do not calculate anything.

General rules:
- Copy labels, headings, codes, markers and footnotes exactly as printed: same \
words, spelling and capitals.
- If something is not printed, use null (or an empty list). Never guess.
- Use only this period's amounts (the "Current" or "This Period" column). Never use \
a year-to-date (YTD) amount. A value printed only as a year-to-date figure counts \
as not printed.
- Write every amount as a plain number without "$" or commas, e.g. 1224.70. Keep \
a minus sign if one is printed.
- An amount printed on its own in brackets, e.g. "Medical (85.00)": write the \
number without the brackets (85.00) and set in_brackets to true for that line. \
Otherwise in_brackets is false.
- Write dates as YYYY-MM-DD.
- Don't list total or subtotal rows (e.g. "Total Deductions", "Total Earnings") \
or net-pay distribution rows (e.g. direct deposit to a checking or savings \
account) as earnings, taxes or deductions.

Fields:
- gross, net: this period's gross pay and net pay.
- pay_frequency: the pay frequency exactly as printed, e.g. "Biweekly"; null if \
not printed. Don't work it out from the dates.
- period_start, period_end, pay_date: the pay period dates and the pay date.
- federal_taxable_wages: this period's federal taxable wages, e.g. "Federal \
Taxable Wages" or "Fed Taxable Gross". When a federal income tax line shows an \
amount in parentheses after its description and then the tax, e.g. "Federal \
Income Tax (965.70) 120.00", the amount in parentheses is the federal taxable \
wages: copy it here as a positive number, use the other amount for the tax, and \
set in_brackets to false on that tax line.
- annual_amount: a printed yearly pay figure such as "Annual Salary"; never a \
year-to-date total.
- earnings: every earnings row with its label and this period's amount.
- taxes: every tax withheld (federal, state, local, Social Security, Medicare).
- deductions: every other row that takes money out of pay or shows a benefit \
amount, including rows in employer or benefits tables:
  - label: the row's description.
  - amount: this period's amount.
  - section_heading: the heading of the table or section the row is in, or null.
  - codes: values printed in the row's other columns, e.g. a "Type" column \
showing "PRE" or a "Pre-Tax" column showing "Y", each with its column header \
(null if the column has no header).
  - markers: symbols attached to the label or amount, such as "*" or "+".
  - in_employer_section: true only if the row is in a section for amounts the \
employer pays, e.g. "Employer Contributions" or "Company Paid Benefits".
- footnotes: every footnote with its marker and text.
"""


class GenAI(Protocol):
    """What the component needs from an `idp_genai.GenAIService`."""

    @property
    def capabilities(self) -> ModelCapabilities: ...

    def extract(
        self,
        *,
        model: str,
        task: str,
        document_text: str | None,
        attachments: tuple[Attachment, ...],
        schema: type,
        max_output_tokens: int,
        temperature: float | None,
    ) -> ParsedResponse: ...


class Extractor(Protocol):
    """What the analyzer needs from the extraction step."""

    @property
    def wants_images(self) -> bool: ...

    def extract(self, stub: ReadStub) -> PaystubEvidence: ...


def _schema_problems(error: ValidationError) -> str:
    """Field locations and error types only; never the model's (document) values."""
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or '<root>'} ({item['type']})"
        for item in error.errors(include_input=False, include_url=False)
    )


class EvidenceExtractor:
    def __init__(self, genai: GenAI, *, model: str, config: ExtractionConfig) -> None:
        if not model.strip():
            raise ConfigError("a model ID is required")
        self._genai = genai
        self._model = model
        self._config = config

    @property
    def wants_images(self) -> bool:
        """True when page images should be rendered and sent with the text."""
        return self._config.send_images == "auto" and bool(
            self._genai.capabilities.image_media_types
        )

    def extract(self, stub: ReadStub) -> PaystubEvidence:
        attachments = (
            tuple(Attachment(image.media_type, image.data) for image in stub.images)
            if self.wants_images
            else ()
        )
        try:
            response = self._genai.extract(
                model=self._model,
                task=TASK,
                document_text=stub.text,
                attachments=attachments,
                schema=PaystubEvidence,
                max_output_tokens=self._config.max_output_tokens,
                temperature=self._config.temperature,
            )
        except IdpError as exc:
            raise ExtractionError(
                f"the model call was rejected: {exc}", code="rejected_input"
            ) from exc
        if not response.ok:
            raise ExtractionError(
                f"the model gave no usable answer ({response.status})",
                code=response.status,
            )
        if not isinstance(response.data, dict):
            raise ExtractionError(
                "the model's answer is not a JSON object", code="invalid_json"
            )
        try:
            return PaystubEvidence.model_validate(response.data)
        except ValidationError as exc:
            problems = _schema_problems(exc)
        # Raised outside the handler so the document values in `exc` aren't chained.
        raise ExtractionError(
            f"the model's answer doesn't fit the evidence schema: {problems}",
            code="schema_invalid",
        )
