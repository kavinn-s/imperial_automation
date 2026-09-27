# Inbound Call Billing Automation — Build Spec

## 1. Goal
Build a script that takes a raw **inbound calls** export (CSV or XLSX) and produces a
cleaned, client-ready output file with calculated billing columns — replacing a manual
Excel workflow (formulas + cleanup) that is currently done by hand.

**This is NOT an ML/AI task.** It is a deterministic, rule-based data transformation.
Do not use a Hugging Face model, an LLM, or any external API call for the actual
transformation logic — use plain code (Python + pandas, or Node.js) so behavior is
100% predictable and auditable, and so no data ever needs to leave the local machine.

## 2. Privacy / data handling requirements
- The source data contains PHI-adjacent information (caller names, phone numbers tied
  to medical providers/patients). The script must run **entirely locally** — no network
  calls, no telemetry, no sending rows to any API.
- Development/testing should use synthetic/dummy data only. Real files are only ever
  fed to the finished, reviewed script — never pasted into a chat window or an AI tool.
- Output files should be written to a local folder the user controls; no cloud upload
  step should be added unless explicitly requested later.

## 3. Input file
A raw inbound-calls export (CSV or XLSX) with (at minimum) these columns present
somewhere in the sheet, in any order:

| Column (raw) | Meaning |
|---|---|
| `duration` (or similarly named) | Total call duration; may contain seconds or a formatted value. Used only as a **validation check** (see step 1 below) |
| `aftertransfer` | Seconds spent **after** transfer to a human agent |
| `beforetransfer` | Seconds spent **before** transfer (i.e. with the AI/bot) |
| `callbillingtype` (or similar) | Original call outcome/status label (e.g. "voicemail dropped", etc.) |
| Other columns | Caller name, phone number, timestamps, call IDs, etc. — some kept, most dropped (see step 5) |

> Note: exact raw column names should be confirmed against a real (dummy-data) sample
> file before finalizing the column-mapping code — some source systems label these
> slightly differently. Build the column-mapping step so header names are configurable
> in one place (e.g. a small `COLUMN_MAP` dict at the top of the script), not hardcoded
> throughout the logic.

## 4. Output file (target format)
Final columns, in this order:

| Column | Type |
|---|---|
| Caller Name | text |
| Caller Phone Number | text |
| Call status | text — always `HUMAN_ANSWERED` for inbound (see step 4) |
| Human duration(mins) | number, 2 decimals |
| AI duration(mins) | number, 2 decimals |
| Human Billable unitts | number, 2 decimals |
| AI Billable units | number, 2 decimals |
| Total billable units | number, 2 decimals |

All other original columns are dropped from the output.

## 5. Transformation logic (step by step)

**Step 1 — Validate `duration`**
For each row, check whether the raw `duration` field is empty/null.
- If **not empty**: proceed with the calculation below as normal.
- If **empty**: *(needs confirmation from stakeholder — see Open Questions #1)*.
  Default assumption until confirmed: skip/flag the row rather than silently
  calculating from possibly-missing transfer data.

**Step 2 — Compute duration columns**
```
Human duration (mins) = aftertransfer_seconds / 60
AI duration (mins)    = beforetransfer_seconds / 60
```
Round to 2 decimal places for display, but do the underlying math in full precision
before rounding (don't round intermediate values used in later formulas).

**Step 3 — Compute billable units**
```
Human Billable Unit = IF(HumanDurationMins == 0, 0, CEILING(HumanDurationMins / 3, 1) * 0.15)

AI Billable Unit = IF(AIDurationMins <= 0.25, 0,
                    IF(AIDurationMins <= 3, 0.75,
                      CEILING(AIDurationMins / 3, 1) * 0.75))

Total Billable Unit = Human Billable Unit + AI Billable Unit
```
`CEILING(x, 1)` = round up to the next whole integer (i.e. `math.ceil(x)` in Python;
there is no meaningful "nearest multiple of 1" distinction — it's just ceiling to an int).

**Step 4 — Normalize call status**
Every row's original `callbillingtype`/status value is overwritten to the literal
string `HUMAN_ANSWERED`, because this is the inbound flow and all inbound calls in
this dataset are treated as human-answered regardless of original label (e.g.
"voicemail dropped" also becomes `HUMAN_ANSWERED`). **Confirmed by stakeholder** — no
conditional logic needed here for inbound.

**Step 5 — Drop unneeded columns**
Keep only: Caller Name, Caller Phone Number, plus the 5 newly-computed/normalized
columns above. Drop everything else from the source file (raw duration, aftertransfer,
beforetransfer, callbillingtype, timestamps, call IDs, etc. are all dropped after
being used to compute the outputs above).

**Step 6 — Data-quality edge cases to handle defensively**
- Phone numbers that arrive as scientific notation from Excel (e.g. `9.11E+11`) —
  should be normalized back to a plain digit string, not left as float/exponential.
- Values like `Restricted`, blank, or `-` in place of a phone number — pass through
  as-is (don't attempt to fabricate a number).
- Caller Name blank or `-` — pass through as-is.
- Non-numeric or missing values in `aftertransfer`/`beforetransfer` — treat as 0
  rather than erroring the whole row, but log/flag such rows so they can be
  spot-checked (don't silently hide data-quality problems from the user).

## 6. Output format
- Accept CSV as primary input/output format (fastest, least error-prone for
  Excel-notation issues like scientific notation on phone numbers).
- Provide an option to also emit `.xlsx` for users who want to open it directly in Excel.
- Preserve the exact header names as in the target format table in Section 4.

## 7. Suggested implementation
- Python 3, using `pandas` for the bulk transform and `openpyxl` only if `.xlsx`
  output is needed.
- Single script, e.g. `process_inbound.py`, invoked as:
  ```
  python process_inbound.py input.csv output.csv
  ```
- Keep the column-name mapping, the two formulas, and the "drop columns" list as
  named constants near the top of the file so they're easy to adjust without
  touching the core logic — this file will likely need small tweaks once real
  (dummy) sample data is tested against it.
- Include a small `--dry-run` or summary mode that prints row counts, how many
  rows had empty/flagged duration, and how many rows had non-numeric
  transfer-time values, so data issues are visible before trusting the output.

## 8. Open questions (confirm before finalizing)
1. **Empty `duration` behavior** — what should happen to a row where the raw
   `duration` field is empty? Skip it? Include it with zeros? Flag it in a
   separate output file for manual review?
2. **Exact raw column header names** — need a real (dummy) sample of the *raw*
   inbound export (with `duration`, `aftertransfer`, `beforetransfer`,
   `callbillingtype` columns intact) to confirm exact header spelling/casing.
3. Confirm whether `.xlsx` output needs the formulas to be *live Excel formulas*
   (so the client can audit/recalculate them in Excel) versus pre-computed
   static values. This matters for how the script writes with openpyxl.

## 9. Out of scope for this phase
- **Outbound calls** — logic differs from inbound and will be defined in a
  follow-up spec once the outbound transcript/rules are reviewed. Do not build
  outbound handling yet; keep the script structured so an `process_outbound.py`
  (or a `--mode outbound` flag) can be added later without a rewrite.