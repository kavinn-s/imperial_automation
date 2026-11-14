# Batch Zip → Multi-Sheet Invoice — Build Spec

## 1. Goal
Add a **new, separate feature** alongside the existing single-file upload flow
(`POST /upload` in `backend/server.py`, which already handles inbound/outbound/
caregap one file at a time). This feature lets the user upload **one ZIP file**
containing multiple raw call exports at once, and get back **one Excel workbook**
with **one sheet per agent/direction**, each cleaned using the correct existing
logic.

**Do not modify the existing single-file `/upload` endpoint, the existing
frontend single-file flow, or `process_inbound.py` / `process_outbound.py` /
`process_caregap.py`'s core calculation logic.** This is purely additive: a new
endpoint, a new router/dispatch layer on top of the three existing processors,
and a new frontend entry point (e.g. a second upload mode, tab, or page) that
calls it.

## 2. Input
A ZIP file containing multiple raw export files (`.csv`, `.xlsx`). Each file
inside the ZIP is named using a fixed convention the user will follow exactly:

```
<AgentName>_<Direction>.xlsx
```

Examples the user will actually produce:
```
Claims_Inbound.xlsx
Authorization_Inbound.xlsx
ExchangeEligibility_Inbound.xlsx
MedicareEligibility_Inbound.xlsx
TRCPF_Inbound.xlsx
TRCPF_Outbound.xlsx
OEC_Inbound.xlsx
OEC_Outbound.xlsx
OEV_Inbound.xlsx
OEV_Outbound.xlsx
SmartAgent_<AnyName>.xlsx      (e.g. SmartAgent_Diabetes.xlsx, SmartAgent_Wellness.xlsx)
```

The outer ZIP/folder name itself (e.g. "Imperial") carries no meaning and can
be ignored — only the individual filenames inside matter.

Detection should be done with simple, case-insensitive keyword matching on the
filename (same style as the existing transcript-keyword matching in
`process_outbound.py` / `process_caregap.py`) — not by inspecting file
contents, and NOT using any AI/model call.

## 3. The fixed routing table

| Filename contains | Direction | Processor to call | Output columns | Sheet name |
|---|---|---|---|---|
| `claims` | inbound | `process_inbound.process()` unchanged | Original inbound columns (see 4a) | `Claims` |
| `authorization` | inbound | `process_inbound.process()` unchanged | Original inbound columns (see 4a) | `Authorization` |
| `exchangeeligibility` / `exchange eligibility` | inbound | `process_inbound.process()` unchanged | Original inbound columns (see 4a) | `Exchange Eligibility` |
| `medicareeligibility` / `medicare eligibility` | inbound | `process_inbound.process()` unchanged | Original inbound columns (see 4a) | `Medicare Eligibility` |
| `trcpf` / `trc-pf` / `trc_pf` | inbound | `process_inbound.process()` unchanged math, **remapped output columns** (see 4b) | Outbound-shaped columns (see 4b) | `TRC-PF Inbound` |
| `trcpf` / `trc-pf` / `trc_pf` | outbound | `process_outbound.process()` unchanged | Outbound columns as-is | `TRC-PF Outbound` |
| `oec` | inbound | `process_inbound.process()` unchanged math, **remapped output columns** (see 4b) | Outbound-shaped columns (see 4b) | `OEC Inbound` |
| `oec` | outbound | `process_outbound.process()` unchanged | Outbound columns as-is | `OEC Outbound` |
| `oev` | inbound | `process_inbound.process()` unchanged math, **remapped output columns** (see 4b) | Outbound-shaped columns (see 4b) | `OEV Inbound` |
| `oev` | outbound | `process_outbound.process()` unchanged | Outbound columns as-is | `OEV Outbound` |
| `smartagent` | n/a (caregap) | `process_caregap.process()` unchanged | Caregap columns as-is | The `<AnyName>` part of `SmartAgent_<AnyName>`, extracted from the filename |

**Direction detection**: look for `inbound` or `outbound` anywhere in the
filename (case-insensitive). A file matching an agent keyword with neither
direction word present, or a filename matching NONE of the agent keywords
above, must be **flagged and skipped with a clear error message** listing the
exact filename — never guessed or silently dropped.

## 4. Output column shapes

**4a. Original inbound columns** (used for Claims / Authorization / Exchange
Eligibility / Medicare Eligibility — no changes from what `process_inbound.py`
already outputs today):
```
Caller Name | Caller Phone Number | Call status | Human duration(mins) |
AI duration(mins) | Human Billable unitts | AI Billable units | Total billable units
```

**4b. Outbound-shaped columns for TRC-PF/OEC/OEV inbound files** (NEW mapping —
the underlying calculation is 100% identical to `process_inbound.py`'s existing
Human/AI-duration-split formula; only the final column selection/renaming
changes):
```
Member First Name   <- from the same source column process_inbound.py already
                        reads for caller name (split/rename as needed)
Member Last Name    <- same source, last-name portion if available, else blank
Phone Number        <- same source process_inbound.py already reads for phone
Member ID           <- pull from the raw file's member-id column (same field
                        process_outbound.py / process_caregap.py already map
                        as "member_id" in their COLUMN_MAP, e.g.
                        prospectDetails.pCustomFields.MemberId)
Call Status          <- same as "Call status" already computed (always
                        HUMAN_ANSWERED for inbound, unchanged)
callduration(mins)   <- this is exactly what process_inbound.py currently
                        calls "AI duration(mins)" -- same number, renamed
billableunits        <- this is exactly what process_inbound.py currently
                        calls "Total billable units" (Human Billable +
                        AI Billable already summed) -- same number, renamed
```
**Do NOT include** Human duration(mins), Human Billable unitts, or AI
Billable units as separate columns in this output shape — they still get
computed internally (needed to produce the Total), just not shown as their
own columns here.

**4c. Outbound columns** (TRC-PF/OEC/OEV outbound files) — identical to what
`process_outbound.py` already outputs today, no changes.

**4d. Caregap columns** — identical to what `process_caregap.py` already
outputs today, no changes.

## 5. Processing flow, step by step

1. User uploads one ZIP file through a new endpoint, e.g. `POST /upload-batch`.
2. Backend extracts the ZIP into a temp directory (reuse the existing `TEMP_DIR`
   pattern from `server.py`; use a fresh `uuid`-named subfolder per request,
   same as the existing single-file flow does for its temp files).
3. For each extracted file (ignore non-csv/xlsx files, hidden files, directory
   entries):
   a. Run filename keyword matching to determine **agent** and **direction**
      per the table in Section 3.
   b. If no match, or an agent keyword matches but direction is ambiguous/
      missing (and the agent is one that requires a direction, i.e. not a
      SmartAgent file) -> record this filename in a `skipped` list with a
      reason string; do not attempt to process it.
   c. If matched, call the correct existing processor function on that file,
      exactly as it's already called in `server.py`'s existing `/upload`
      handler (same formula_config pattern already in that file) -- except for
      TRC-PF/OEC/OEV inbound files, where after getting `process_inbound.py`'s
      normal output DataFrame, apply a small remapping step that selects/
      renames the columns per Section 4b before writing the sheet (this
      remapping function is new code, separate from `process_inbound.py`
      itself -- do not change that file).
   d. Write the resulting DataFrame to its own sheet in one shared `xlsx`
      workbook (use `pandas.ExcelWriter` with `openpyxl` engine, one `to_excel`
      call per DataFrame with `sheet_name=` set per Section 3's "Sheet name"
      column). Note Excel's 31-character sheet-name limit and invalid
      characters (`: \ / ? * [ ]`) -- sanitize/truncate sheet names as needed,
      especially for arbitrary SmartAgent names.
4. Return one combined `.xlsx` for download (reuse the existing `/download`
   endpoint pattern), plus a JSON summary: which sheets were created, how many
   rows each has, and the full `skipped` list with reasons -- surfaced in the
   frontend so the user can see at a glance if any file in their ZIP wasn't
   recognized.

## 6. Frontend
Add a new upload mode (separate from the existing single-file flow -- e.g. a
toggle, tab, or separate page: "Upload one file" vs "Upload a batch (ZIP)").
On success, show:
- A list of sheets created (agent/direction + row count each)
- Any skipped files with their reason
- A single download button for the combined workbook

Keep styling consistent with the existing Imperial Ledger visual theme already
built for this app (same fonts/palette/components) -- don't introduce a
different look for this one feature.

## 7. Privacy / safety requirements (same as the rest of this app)
- Everything runs server-side within this same backend, entirely locally --
  no new external/network calls, no AI/model calls anywhere in the routing or
  classification logic (filename matching and the existing transcript keyword
  rules are both plain string operations).
- Clean up extracted ZIP contents and temp files after the response is sent,
  same as the existing single-file flow already does (or should -- check
  current temp-file cleanup behavior in `server.py` and match it).

## 8. What must NOT change
- `process_inbound.py`, `process_outbound.py`, `process_caregap.py` -- their
  calculation logic stays exactly as validated today. Any new column-remapping
  needed for Section 4b lives in new code (e.g. a `batch_router.py` /
  `batch_processor.py` module), never inside these three files.
- The existing `/upload` endpoint and its current single-file frontend flow --
  must keep working exactly as it does today, unaffected by this change.