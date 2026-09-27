"""
Outbound call billing automation.

Usage:
    python process_outbound.py input.csv output.csv

Runs entirely locally. No network calls, no external services, no AI/model calls --
the transcript classification below is plain keyword matching, not language understanding.
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
    "first_name": "prospectDetails.pFirstName",
    "last_name": "prospectDetails.pLastName",
    "phone": "prospectPhoneNo",
    "member_id": "prospectDetails.pCustomFields.MemberId",
}

OUTPUT_COLUMNS = [
    "Member First Name",
    "Member Last Name",
    "Phone Number",
    "Member ID",
    "Call Status",
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
# ---------------------------------------------------------------------------
def classify_transcript(transcript_text: str, record_duration_seconds: float) -> tuple[str, bool, dict]:
    """Returns (status, was_confidently_matched, audit_info)."""
    if transcript_text is None:
        transcript_text = ""
    t = str(transcript_text).strip().lower()

    if TRANSCRIPT_NOT_FOUND_PHRASE in t:
        duration_mins = record_duration_seconds / 60
        if duration_mins <= 0.25:
            return "HUMAN_NOT_ANSWERED", True, {"rule": "transcript_not_found_short", "reason": f"Transcript said 'transcript not found', duration was {duration_mins:.2f} min (<=0.25) -> classified as HUMAN_NOT_ANSWERED."}
        return "HUMAN_ANSWERED", True, {"rule": "transcript_not_found_long", "reason": f"Transcript said 'transcript not found', duration was {duration_mins:.2f} min (>0.25) -> classified as HUMAN_ANSWERED."}

    if VOICEMAIL_DROPPED_PHRASE in t:
        return "VOICEMAIL_DROPPED", True, {"rule": "matched_voicemail_dropped_phrase", "reason": f"Transcript contained '{VOICEMAIL_DROPPED_PHRASE}' -> classified as VOICEMAIL_DROPPED."}

    for k in VOICEMAIL_NOT_DROPPED_KEYWORDS:
        if k in t:
            return "VOICEMAIL_NOT_DROPPED", True, {"rule": "matched_voicemail_not_dropped_keyword", "reason": f"Transcript contained '{k}' -> classified as VOICEMAIL_NOT_DROPPED.", "keyword": k}

    if t == "":
        # No transcript text and no explicit "transcript not found" marker --
        # treat cautiously rather than assuming a real conversation happened.
        return "HUMAN_NOT_ANSWERED", False, {"rule": "flagged_unrecognized_empty", "reason": "No transcript and no explicit 'transcript not found' marker -> treated cautiously as HUMAN_NOT_ANSWERED."}

    # Default bucket: looks like a real conversation, no voicemail markers found.
    return "HUMAN_ANSWERED", True, {"rule": "default_human_answered", "reason": "Transcript indicates a real conversation -> classified as HUMAN_ANSWERED."}


# ---------------------------------------------------------------------------
# 3. BILLABLE UNIT FORMULA
# ---------------------------------------------------------------------------
def ceiling_to_multiple(x: float, sig: float) -> float:
    """Excel CEILING(x, sig): round x up to the nearest multiple of sig."""
    return math.ceil(round(x / sig, 10)) * sig


def human_answered_billable(mins: float, config: dict) -> float:
    if mins <= config["free_threshold"]:
        return 0.0
    if mins <= config["first_increment_limit"]:
        return config["first_increment_cost"]
    return math.ceil(mins / config["subsequent_increment_size"]) * config["subsequent_increment_cost"]


def billable_unit_for(status: str, mins: float, config: dict = None) -> float:
    if config is None:
        config = {
            "human_answered": {
                "free_threshold": 0.25,
                "first_increment_limit": 3.0,
                "first_increment_cost": 0.75,
                "subsequent_increment_size": 3.0,
                "subsequent_increment_cost": 0.75
            },
            "voicemail_dropped_cost": 0.25
        }
        
    s = str(status).strip().upper()
    if s == "HUMAN_ANSWERED":
        return human_answered_billable(mins, config.get("human_answered", {}))
    if s == "VOICEMAIL_DROPPED":
        return config.get("voicemail_dropped_cost", 0.25)
    if s in ("VOICEMAIL_NOT_DROPPED", "HUMAN_NOT_ANSWERED"):
        return 0.0
    return None  # unrecognized status -- flagged for manual review, not guessed


def clean_phone(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if "E+" in s.upper():
        try:
            return str(int(float(s)))
        except ValueError:
            return s
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


# ---------------------------------------------------------------------------
# 4. MAIN TRANSFORM
# ---------------------------------------------------------------------------
def process(input_path: str, formula_config: dict = None) -> tuple[pd.DataFrame, dict]:
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
        "total_billable_units": 0.0,
        "audit_rules_fired": {}
    }

    out_rows = []
    audit_trail = []

    for idx, row in df.iterrows():
        row_audit = {}
        row_modified = False
        
        # --- Step 1: fill empty recordDuration from duration ---
        record_duration_raw = row.get(COLUMN_MAP["record_duration"])
        if pd.isna(record_duration_raw) or str(record_duration_raw).strip() == "":
            record_duration_raw = row.get(COLUMN_MAP["duration"])
            stats["duration_copied_from_raw_duration"] += 1
            row_audit["recordDuration_source"] = "copied_from_duration"
            row_audit["recordDuration_reason"] = f"recordDuration was empty, copied value '{record_duration_raw}' from duration column."
            row_modified = True
        else:
            row_audit["recordDuration_source"] = "original"

        try:
            record_duration_seconds = float(record_duration_raw)
        except (ValueError, TypeError):
            record_duration_seconds = 0.0

        # --- Step 2: fill empty callBillingType from transcript, else keep as-is ---
        existing_status = row.get(COLUMN_MAP["call_status"])
        existing_status_empty = pd.isna(existing_status) or str(existing_status).strip() == ""

        if existing_status_empty:
            transcript_text = row.get(COLUMN_MAP["transcript"])
            status, matched, audit_info = classify_transcript(transcript_text, record_duration_seconds)
            stats["status_filled_from_transcript"] += 1
            rule = audit_info["rule"]
            stats["audit_rules_fired"][rule] = stats["audit_rules_fired"].get(rule, 0) + 1
            row_audit["callBillingType_source"] = rule
            row_audit["callBillingType_reason"] = audit_info["reason"]
            row_audit["transcript"] = str(transcript_text) if transcript_text else ""
            row_modified = True
            
            if not matched:
                stats["unrecognized_status_flagged"] += 1
        else:
            status = str(existing_status).strip()
            stats["status_kept_as_is"] += 1
            row_audit["callBillingType_source"] = "original"

        if row_modified:
            row_audit["phone"] = clean_phone(row.get(COLUMN_MAP["phone"]))
            row_audit["member_id"] = str(row.get(COLUMN_MAP["member_id"], ""))
            row_audit["row_index"] = idx + 1
            audit_trail.append(row_audit)

        # --- Step 3: compute callduration(mins) and billableunits ---
        call_duration_mins = round(record_duration_seconds / 60, 2)
        billable = billable_unit_for(status, call_duration_mins, formula_config)
        if billable is None:
            stats["unrecognized_status_flagged"] += 1
            billable = 0.0  # default to 0 but this row is flagged above for manual review
        billable = round(billable, 2)
        stats["total_billable_units"] += billable

        out_rows.append({
            "Member First Name": row.get(COLUMN_MAP["first_name"], ""),
            "Member Last Name": row.get(COLUMN_MAP["last_name"], ""),
            "Phone Number": clean_phone(row.get(COLUMN_MAP["phone"])),
            "Member ID": row.get(COLUMN_MAP["member_id"], ""),
            "Call Status": status,
            "callduration(mins)": call_duration_mins,
            "billableunits": billable,
        })

    out_df = pd.DataFrame(out_rows, columns=OUTPUT_COLUMNS)
    stats["output_rows"] = len(out_df)
    stats["total_billable_units"] = round(stats["total_billable_units"], 2)
    stats["audit_trail"] = audit_trail
    return out_df, stats


def main():
    if len(sys.argv) != 3:
        print("Usage: python process_outbound.py input.csv output.csv")
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
    print(f"  Rows flagged for manual review:            {stats['unrecognized_status_flagged']}")
    print(f"  Output rows written:                       {stats['output_rows']}")
    print(f"  TOTAL billable units (sum):                {stats['total_billable_units']}")
    print(f"  Output file:                                {output_path}")


if __name__ == "__main__":
    main()