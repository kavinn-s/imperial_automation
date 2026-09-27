# Outbound Call Billing Automation — Build Spec

## 1. Goal
Take a raw **outbound calls** export (CSV or XLSX) and produce a cleaned, client-ready
output file with a computed call duration and billable-unit column per row, plus a
grand total.

**This is NOT a machine-learning task.** The one part that sounds like it needs "AI"
(reading the transcript) turns out to be plain keyword/phrase matching, because the
outbound agent's own script is templated and produces consistent, repeatable phrases.
No model training, no LLM API calls, no external services — everything runs locally,
on plain text rules plus arithmetic.

## 2. Privacy / data handling requirements
- Same as inbound: run entirely locally, no network calls, no telemetry.
- Transcripts may contain real member names and conversation content — treat any real
  transcript data with the same care as the phone/name data in the inbound file.
  Development and testing should use synthetic transcripts, not real ones.

## 3. Input file — raw columns actually used
The raw export has ~150+ columns (mostly internal MongoDB fields you can ignore —
`_id.buffer.*`, `agentId.buffer.*`, `dispositionId.buffer.*`, etc.). Only these matter:

| Column (raw) | Used for |
|---|---|
| `duration` | Fallback source for `recordDuration` when it's empty |
| `recordDuration` | Primary source of call length in **seconds** |
| `callBillingType` | Existing call-outcome label; only filled in when empty, never overwritten |
| `transcript` | Read only when `callBillingType` is empty, to classify the call |
| `prospectDetails.pFirstName` | → Member First Name |
| `prospectDetails.pLastName` | → Member Last Name |
| `prospectPhoneNo` | → Phone Number |
| `prospectDetails.pCustomFields.MemberId` | → Member ID (confirmed: same value as the top-level `Member ID` column, so either works) |

Configure these as a `COLUMN_MAP` dict at the top of the script (same pattern as the
inbound script), not hardcoded inline, since header names can drift between exports.

## 4. Output file (target format)
Exactly these 7 columns, in this order:

| Column | Notes |
|---|---|
| Member First Name | |
| Member Last Name | |
| Phone Number | Clean scientific-notation artifacts the same way inbound does |
| Member ID | |
| Call Status | Renamed from `callBillingType`, same convention as inbound's "Call status" |
| callduration(mins) | New column, computed (see step 3) |
| billableunits | New column, computed (see step 4) |

All other original columns are dropped. A **grand total of `billableunits`** should be
printed in the run summary (not necessarily as an extra row in the CSV itself) so the
person running it can see the batch total at a glance.

## 5. Transformation logic (step by step)

**Step 1 — Fill empty `recordDuration` from `duration`**
For each row: if `recordDuration` is empty, copy the value from `duration` into it for
that row. This is a straight copy, no calculation. If `recordDuration` already has a
value, leave it untouched.

**Step 2 — Fill empty `callBillingType` by reading the transcript**
Only touch rows where `callBillingType` is empty. **Never overwrite an existing
value** — if it's already populated, leave it exactly as-is (still run Step 3/4 on
it, just don't touch the label itself).

For empty rows, read `transcript` and classify into one of four labels using plain
substring/keyword matching (all matching should be case-insensitive):

1. **Transcript literally contains "transcript not found"** →
   - Convert `recordDuration` (seconds) to minutes.
   - If minutes ≤ 0.25 → label = `HUMAN_NOT_ANSWERED`
   - If minutes > 0.25 → label = `HUMAN_ANSWERED` (confirmed choice — even though the
     transcript is missing, a call this long is treated as answered)

2. **Transcript contains the phrase "calling with a message for"** →
   `VOICEMAIL_DROPPED`. This is the agent's own fixed closing script when it
   successfully leaves a voicemail message (e.g. "...calling with a message for
   [NAME]... Please give Member Services a call back... Thank you, and have a great
   day!").

3. **Transcript contains any of these voicemail-system phrases, but NOT the
   "calling with a message for" phrase above** → `VOICEMAIL_NOT_DROPPED`:
   - "record your message"
   - "at the tone"
   - "forwarded to voicemail"
   - "leave your name and number"
   - "press one"
   - "press two"
   - "cannot process your entries"
   - "voicemail of"
   - "please leave your message"

4. **None of the above, and there is real transcript text** → `HUMAN_ANSWERED`
   (default/fallback bucket — a genuine back-and-forth conversation with no voicemail
   markers).

**Safety net:** if a transcript is empty/blank but does *not* literally say "transcript
not found," don't silently guess — default to `HUMAN_NOT_ANSWERED` / 0 billable, but
flag that row in a "needs manual review" count so nothing gets miscategorized quietly.
Same for any row whose final status string (existing or filled) doesn't match one of
the four known labels when it's time to compute the billable unit in Step 4 — flag it
rather than guessing.

**Step 3 — Compute `callduration(mins)`**
```
callduration(mins) = recordDuration (seconds, after Step 1's fill) / 60
```
Round to 2 decimal places for display.

**Step 4 — Compute `billableunits`**
Based on the row's final Call Status (whether it was already filled or just filled in
Step 2):

```
IF Call Status == HUMAN_ANSWERED:
    A = callduration(mins)
    billable = IF(A <= 0.25, 0,
                IF(A <= 3, 0.75,
                  CEILING(A / 3, 0.75)))   # Excel CEILING(x, 0.75): round x UP to the
                                            # nearest multiple of 0.75 -- NOT the same
                                            # mechanic as the inbound formula. Confirm
                                            # against a real Excel-calculated row before
                                            # trusting this at scale.

IF Call Status == VOICEMAIL_DROPPED:
    billable = 0.25   # flat, no formula

IF Call Status == VOICEMAIL_NOT_DROPPED or HUMAN_NOT_ANSWERED:
    billable = 0      # flat

ELSE (unrecognized status):
    billable = 0, and flag the row for manual review
```

## 6. Edge cases to handle defensively
- Same phone-number cleanup as inbound (scientific notation like `9.11E+11`,
  trailing `.0` from Excel exports).
- Non-numeric `recordDuration`/`duration` values → treat as 0 seconds, but count/flag
  so it's visible in the run summary.
- Keep a running count of: rows where duration was copied from `duration`, rows where
  status was filled from transcript vs. left as-is, and rows flagged for manual
  review — print all of these plus the grand total billable units at the end of the
  run, same style as the inbound script's summary.

## 7. Open items still worth confirming against a handful of real rows (not dummy data)
1. The `CEILING(A/3, 0.75)` formula behaves differently from the inbound formula's
   `CEILING(A/3,1)*0.75` for larger durations — worth sanity-checking one real
   long-duration `HUMAN_ANSWERED` row's billable unit by hand in Excel to make sure
   the script's math matches exactly.
2. The keyword list in Step 2.3 (`VOICEMAIL_NOT_DROPPED` triggers) was built from a
   handful of real examples — if real data surfaces a voicemail system with different
   wording that doesn't match any of these phrases, it will currently fall through to
   the `HUMAN_ANSWERED` default bucket instead of being correctly caught. Watch the
   "flagged for manual review" count and the overall `HUMAN_ANSWERED` rate for
   anything that looks abnormally high as a signal this needs a new keyword added.

## 8. Reference implementation
A working, tested Python version of this exact logic already exists
(`process_outbound.py`), built and verified against synthetic test data covering all
four classification buckets, the duration-copy fallback, and the "don't overwrite an
existing Call Status" rule. Use it as the starting point rather than rebuilding from
scratch — the main task left is validating it against a small real (or realistic
dummy) sample and adjusting the keyword list per item 7.2 above if needed.