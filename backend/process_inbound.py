"""
Inbound call billing automation.

Usage:
    python process_inbound.py input.csv output.csv
    python process_inbound.py input.csv output.xlsx

Runs entirely locally. No network calls, no external services.
"""

import math
import sys
import pandas as pd
from fpdf import FPDF


# ---------------------------------------------------------------------------
# 1. CONFIG — adjust these to match your real raw export's column names.
#    Left side = what THIS script calls the column internally.
#    Right side = what your raw file actually names it.
#    If your raw file uses different header text, only change this dict.
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    "duration": "duration",
    "after_transfer": "durationAfterTransfer",
    "before_transfer": "durationBeforeTransfer",
    "call_status": "callBillingType",
    "caller_name": "prospectDetails.pFirstName",
    "caller_phone": "prospectPhoneNo",
}

OUTPUT_COLUMNS = [
    "Caller Name",
    "Caller Phone Number",
    "Call status",
    "Human duration(mins)",
    "AI duration(mins)",
    "Human Billable unitts",
    "AI Billable units",
    "Total billable units",
]


# ---------------------------------------------------------------------------
# 2. FORMULAS
# ---------------------------------------------------------------------------
def human_billable_unit(human_mins: float, config: dict = None) -> float:
    if config is None:
        config = {"increment_size": 3, "increment_cost": 0.15}
    
    if human_mins == 0:
        return 0.0
    return math.ceil(human_mins / config["increment_size"]) * config["increment_cost"]


def ai_billable_unit(ai_mins: float, config: dict = None) -> float:
    if config is None:
        config = {
            "free_threshold": 0.25,
            "first_increment_limit": 3,
            "first_increment_cost": 0.75,
            "subsequent_increment_size": 3,
            "subsequent_increment_cost": 0.75
        }
        
    if ai_mins <= config["free_threshold"]:
        return 0.0
    if ai_mins <= config["first_increment_limit"]:
        return config["first_increment_cost"]
        
    # Subtract the first increment limit, then calculate subsequent increments
    remaining_mins = ai_mins - config["first_increment_limit"]
    subsequent_increments = math.ceil(remaining_mins / config["subsequent_increment_size"])
    return config["first_increment_cost"] + (subsequent_increments * config["subsequent_increment_cost"])


def clean_phone(value) -> str:
    """Fix Excel's scientific-notation mangling of long phone numbers (e.g. 9.11E+11),
    otherwise pass the value through unchanged (covers 'Restricted', '-', blanks, etc.)."""
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if "E+" in s.upper():
        try:
            return str(int(float(s)))
        except ValueError:
            return s
    # Strip a trailing ".0" pandas sometimes adds when a numeric column has NaNs
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


# ---------------------------------------------------------------------------
# 3. MAIN TRANSFORM
# ---------------------------------------------------------------------------
def process(input_path: str, formula_config: dict = None) -> tuple[pd.DataFrame, dict]:
    if formula_config is None:
        formula_config = {
            "human": {"increment_size": 3, "increment_cost": 0.15},
            "ai": {
                "free_threshold": 0.25,
                "first_increment_limit": 3,
                "first_increment_cost": 0.75,
                "subsequent_increment_size": 3,
                "subsequent_increment_cost": 0.75
            }
        }

    if input_path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(input_path, dtype=str)
    else:
        df = pd.read_csv(input_path, dtype=str)

    stats = {
        "total_rows": len(df),
        "empty_duration_rows": 0,
        "bad_transfer_value_rows": 0,
        "total_billable_sum": 0.0,
    }

    out_rows = []

    for _, row in df.iterrows():
        duration_raw = row.get(COLUMN_MAP["duration"])
        duration_empty = pd.isna(duration_raw) or str(duration_raw).strip() == ""

        if duration_empty:
            stats["empty_duration_rows"] += 1
            # Current default: skip the row rather than guess. Change this if the
            # stakeholder decides empty-duration rows should be kept/zeroed instead.
            continue

        # --- parse transfer times, defaulting to 0 and flagging bad values ---
        def to_seconds(value):
            if pd.isna(value) or str(value).strip() == "":
                return 0.0
            try:
                return float(value)
            except ValueError:
                stats["bad_transfer_value_rows"] += 1
                return 0.0

        after_sec = to_seconds(row.get(COLUMN_MAP["after_transfer"]))
        before_sec = to_seconds(row.get(COLUMN_MAP["before_transfer"]))

        human_mins = after_sec / 60
        ai_mins = before_sec / 60

        human_bill = human_billable_unit(human_mins, formula_config.get("human"))
        ai_bill = ai_billable_unit(ai_mins, formula_config.get("ai"))
        total_bill = human_bill + ai_bill
        stats["total_billable_sum"] += total_bill

        out_rows.append({
            "Caller Name": row.get(COLUMN_MAP["caller_name"], ""),
            "Caller Phone Number": clean_phone(row.get(COLUMN_MAP["caller_phone"])),
            "Call status": "HUMAN_ANSWERED",  # inbound: always normalized to this
            "Human duration(mins)": round(human_mins, 2),
            "AI duration(mins)": round(ai_mins, 2),
            "Human Billable unitts": round(human_bill, 2),
            "AI Billable units": round(ai_bill, 2),
            "Total billable units": round(total_bill, 2),
        })

    out_df = pd.DataFrame(out_rows, columns=OUTPUT_COLUMNS)
    stats["output_rows"] = len(out_df)
    stats["total_billable_sum"] = round(stats["total_billable_sum"], 2)
    return out_df, stats


# ---------------------------------------------------------------------------
# 4. EXPORT TO PDF
# ---------------------------------------------------------------------------
def export_to_pdf(df: pd.DataFrame, output_path: str):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    # Title
    pdf.set_font("helvetica", style="B", size=12)
    pdf.cell(0, 10, "Cleaned Inbound Calls Report", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Basic column width calculation (simplified)
    # A4 landscape is 297mm wide. Let's assume usable width ~277mm
    # Distribute 277mm among 8 columns evenly
    col_width = 277 / len(df.columns) if not df.empty else 277
    
    # Print Headers
    pdf.set_font("helvetica", style="B", size=8)
    for col in df.columns:
        # truncate header if too long
        header_text = str(col)[:20]
        pdf.cell(col_width, 8, header_text, border=1, align="C")
    pdf.ln()
    
    # Print Rows
    pdf.set_font("helvetica", size=8)
    for _, row in df.iterrows():
        for val in row:
            text = str(val)[:25] # Truncate to fit cell
            pdf.cell(col_width, 8, text, border=1, align="C")
        pdf.ln()
        
    pdf.output(output_path)


def main():
    if len(sys.argv) != 3:
        print("Usage: python process_inbound.py input.csv output.[csv|xlsx|pdf]")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]
    out_df, stats = process(input_path)

    if output_path.lower().endswith(".xlsx"):
        out_df.to_excel(output_path, index=False)
    elif output_path.lower().endswith(".pdf"):
        export_to_pdf(out_df, output_path)
    else:
        out_df.to_csv(output_path, index=False)

    print("Done.")
    print(f"  Input rows read:        {stats['total_rows']}")
    print(f"  Skipped (empty duration): {stats['empty_duration_rows']}")
    print(f"  Rows with bad transfer values (defaulted to 0): {stats['bad_transfer_value_rows']}")
    print(f"  Output rows written:    {stats['output_rows']}")
    print(f"  Output file:            {output_path}")


if __name__ == "__main__":
    main()