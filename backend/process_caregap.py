"""
Caregap call billing automation.

Caregap combines both inbound-style and outbound-style calls in a single export,
distinguished by the `type` column. The fill-in logic (Steps 1-2) is identical to
outbound and runs for every row regardless of type. The billable-unit FORMULA then
branches based on `type`:

    type == inbound  -> always apply the AI-billable formula, unconditionally,
                        regardless of what callbillingtype says (every inbound
                        call is treated as answered, same as the original
                        inbound workflow).
    type == outbound -> same as process_outbound.py: branch on callbillingtype
                        (HUMAN_ANSWERED / VOICEMAIL_DROPPED / etc).

Usage:
    python process_caregap.py input.csv output.csv

Runs entirely locally. No network calls, no external services, no AI/model calls --
transcript classification is plain keyword matching, not language understanding.
"""

import math
import sys
import pandas as pd


# ---------------------------------------------------------------------------
# 1. CONFIG -- adjust these to match your real raw export's column names.
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    "duration": "duration",
    "record_duration": "recordDuration",
    "call_status": "callBillingType",
    "transcript": "transcript",
    "type": "type",
    "first_name": "prospectDetails.pFirstName",
    "last_name": "prospectDetails.pLastName",
    "phone": "prospectPhoneNo",
    "member_id": "prospectDetails.pCustomFields.MemberId",
}

MEMBER_ID_FALLBACKS = [
    "prospectDetails.pCustomFields.MemberId",
    "prospectDetails.pCustomFields.Member_Id",
    "prospectDetails.pCustomFields.memberId",
    "prospectDetails.pCustomFields.member_id",
    "prospectDetails.MemberId",
    "prospectDetails.Member_Id",
    "member_id",
    "memberId",
    "memberid",
    "MemberId",
    "Member_Id",
    "Member ID",
    "member id",
]

def get_member_id(row) -> str:
    # 1. Try each known column candidate in order
    for col in MEMBER_ID_FALLBACKS:
        if col in row:
            val = clean_str(row.get(col))
            if val:
                return val
    # 2. Case-insensitive / substring fallback across row index
    if hasattr(row, "index"):
        for key in row.index:
            k_lower = str(key).strip().lower()
            if "member" in k_lower and "id" in k_lower:
                val = clean_str(row.get(key))
                if val:
                    return val
    return ""

OUTPUT_COLUMNS = [
    "Member First Name",
    "Member Last Name",
    "Phone Number",
    "Member ID",
    "Call Status",
    "Type",
    "callduration(mins)",
    "billableunits",
]

VOICEMAIL_DROPPED_PHRASE = "calling with a message for"

VOICEMAIL_NOT_DROPPED_KEYWORDS = [
    "record your message",
    "at the tone",
    "forwarded to voicemail",
    "leave your name and number",
    "press one",
    "press two",
    "cannot process your entries",
    "voicemail of",
    "please leave your message",
]

TRANSCRIPT_NOT_FOUND_PHRASE = "transcript not found"


# ---------------------------------------------------------------------------
# 2. TRANSCRIPT CLASSIFICATION (keyword rules only -- no AI/model involved)
#    Identical to the outbound script. Runs for every row regardless of type,
#    whenever callbillingtype is empty.
# ---------------------------------------------------------------------------
def classify_transcript(transcript_text: str, record_duration_seconds: float) -> tuple[str, bool]:
    if transcript_text is None:
        transcript_text = ""
    t = str(transcript_text).strip().lower()

    if TRANSCRIPT_NOT_FOUND_PHRASE in t:
        duration_mins = record_duration_seconds / 60
        if duration_mins <= 0.25:
            return "HUMAN_NOT_ANSWERED", True
        return "HUMAN_ANSWERED", True

    if VOICEMAIL_DROPPED_PHRASE in t:
        return "VOICEMAIL_DROPPED", True

    if any(k in t for k in VOICEMAIL_NOT_DROPPED_KEYWORDS):
        return "VOICEMAIL_NOT_DROPPED", True

    if t == "":
        return "HUMAN_NOT_ANSWERED", False

    return "HUMAN_ANSWERED", True


# ---------------------------------------------------------------------------
# 3. BILLABLE UNIT FORMULA
#    Same shape used two ways: unconditionally for inbound-type rows, and
#    gated by callbillingtype for outbound-type rows.
# ---------------------------------------------------------------------------
def standard_billable(mins: float) -> float:
    """IF(A<=0.25,0,IF(A<=3,0.75,CEILING(A/3,1)*0.75)) -- confirmed-correct
    mechanic (round A/3 up to whole number, then multiply by 0.75)."""
    if mins is None or math.isnan(mins) or mins <= 0.25:
        return 0.0
    if mins <= 3:
        return 0.75
    return math.ceil(mins / 3) * 0.75


def outbound_style_billable(status: str, mins: float):
    if mins is None or math.isnan(mins):
        mins = 0.0
    s = str(status).strip().upper()
    if s == "HUMAN_ANSWERED":
        return standard_billable(mins)
    if s == "VOICEMAIL_DROPPED":
        return 0.25
    if s in ("VOICEMAIL_NOT_DROPPED", "HUMAN_NOT_ANSWERED"):
        return 0.0
    return None  # unrecognized -- flagged for manual review


def clean_phone(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.lower() in ("nan", "none", "null", ""):
        return ""
    if "E+" in s.upper():
        try:
            return str(int(float(s)))
        except (ValueError, OverflowError):
            return s
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def clean_str(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


# ---------------------------------------------------------------------------
# 4. MAIN TRANSFORM
# ---------------------------------------------------------------------------
def process(input_path: str) -> tuple[pd.DataFrame, dict]:
    if input_path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(input_path, dtype=str)
    else:
        df = pd.read_csv(input_path, dtype=str)

    stats = {
        "total_rows": len(df),
        "duration_copied_from_raw_duration": 0,
        "status_filled_from_transcript": 0,
        "status_kept_as_is": 0,
        "unrecognized_status_flagged": 0,
        "inbound_rows": 0,
        "outbound_rows": 0,
        "unrecognized_type_flagged": 0,
        "total_billable_units": 0.0,
    }

    out_rows = []

    for _, row in df.iterrows():
        # --- Step 1: fill empty recordDuration from duration (same as outbound) ---
        record_duration_raw = row.get(COLUMN_MAP["record_duration"])
        record_dur_empty = pd.isna(record_duration_raw) or str(record_duration_raw).strip().lower() in ("", "nan", "none", "null")

        if record_dur_empty:
            duration_raw = row.get(COLUMN_MAP["duration"])
            dur_empty = pd.isna(duration_raw) or str(duration_raw).strip().lower() in ("", "nan", "none", "null")
            if not dur_empty:
                record_duration_raw = duration_raw
                stats["duration_copied_from_raw_duration"] += 1
            else:
                record_duration_raw = 0.0

        try:
            val = float(record_duration_raw)
            record_duration_seconds = 0.0 if (math.isnan(val) or math.isinf(val)) else val
        except (ValueError, TypeError):
            record_duration_seconds = 0.0

        # --- Step 2: fill empty callBillingType from transcript, else keep as-is ---
        # Runs for EVERY row regardless of type (per spec).
        existing_status = row.get(COLUMN_MAP["call_status"])
        existing_status_empty = pd.isna(existing_status) or str(existing_status).strip().lower() in ("", "nan", "none", "null")

        if existing_status_empty:
            transcript_text = row.get(COLUMN_MAP["transcript"])
            status, matched = classify_transcript(transcript_text, record_duration_seconds)
            stats["status_filled_from_transcript"] += 1
            if not matched:
                stats["unrecognized_status_flagged"] += 1
        else:
            status = str(existing_status).strip()
            stats["status_kept_as_is"] += 1

        # --- Step 3: compute callduration(mins) ---
        call_duration_mins = round(record_duration_seconds / 60, 2)

        # --- Step 4: billable unit, branched on type ---
        call_type_raw = row.get(COLUMN_MAP["type"])
        call_type = clean_str(call_type_raw)
        call_type_upper = call_type.upper()

        if call_type_upper == "INBOUND":
            stats["inbound_rows"] += 1
            billable = standard_billable(call_duration_mins)  # unconditional, ignores status
        elif call_type_upper == "OUTBOUND":
            stats["outbound_rows"] += 1
            billable = outbound_style_billable(status, call_duration_mins)
            if billable is None:
                stats["unrecognized_status_flagged"] += 1
                billable = 0.0
        else:
            stats["unrecognized_type_flagged"] += 1
            billable = 0.0  # unrecognized type -- flagged, not guessed

        if billable is None or math.isnan(billable):
            billable = 0.0
        billable = round(billable, 2)
        stats["total_billable_units"] += billable

        out_rows.append({
            "Member First Name": clean_str(row.get(COLUMN_MAP["first_name"])),
            "Member Last Name": clean_str(row.get(COLUMN_MAP["last_name"])),
            "Phone Number": clean_phone(row.get(COLUMN_MAP["phone"])),
            "Member ID": get_member_id(row),
            "Call Status": status,
            "Type": call_type,
            "callduration(mins)": call_duration_mins,
            "billableunits": billable,
        })

    out_df = pd.DataFrame(out_rows, columns=OUTPUT_COLUMNS)
    stats["output_rows"] = len(out_df)
    stats["total_billable_units"] = round(stats["total_billable_units"], 2)
    return out_df, stats


def main():
    if len(sys.argv) != 3:
        print("Usage: python process_caregap.py input.csv output.csv")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]
    out_df, stats = process(input_path)

    if output_path.lower().endswith(".xlsx"):
        out_df.to_excel(output_path, index=False)
    else:
        out_df.to_csv(output_path, index=False)

    print("Done.")
    print(f"  Input rows read:                         {stats['total_rows']}")
    print(f"  recordDuration copied from duration:      {stats['duration_copied_from_raw_duration']}")
    print(f"  Call status filled from transcript:        {stats['status_filled_from_transcript']}")
    print(f"  Call status kept as-is (already filled):   {stats['status_kept_as_is']}")
    print(f"  Inbound-type rows:                         {stats['inbound_rows']}")
    print(f"  Outbound-type rows:                        {stats['outbound_rows']}")
    print(f"  Rows with unrecognized status (flagged):   {stats['unrecognized_status_flagged']}")
    print(f"  Rows with unrecognized type (flagged):     {stats['unrecognized_type_flagged']}")
    print(f"  Output rows written:                       {stats['output_rows']}")
    print(f"  TOTAL billable units (sum):                {stats['total_billable_units']}")
    print(f"  Output file:                                {output_path}")


if __name__ == "__main__":
    main()