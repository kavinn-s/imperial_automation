"""
Batch ZIP -> Multi-Sheet Excel Router & Processor.

Processes a ZIP archive containing multiple raw call exports (.csv, .xlsx),
routes each file to the appropriate processor based on fixed filename conventions,
reshapes output columns when required (Section 4b), and writes all results into
a single multi-sheet Excel workbook.

Runs 100% locally with deterministic rule-based logic. No AI/external calls.
"""

import os
import re
import math
import shutil
import zipfile
import uuid
import tempfile
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional
import pandas as pd

import process_inbound
import process_outbound
import process_caregap

TEMP_DIR = tempfile.gettempdir()

OUTBOUND_SHAPED_COLUMNS = [
    "Member First Name",
    "Member Last Name",
    "Phone Number",
    "Member ID",
    "Call Status",
    "callduration(mins)",
    "billableunits",
]

MEMBER_ID_CANDIDATES = [
    "prospectDetails.pCustomFields.MemberId",
    "prospectDetails.pCustomFields.Member_Id",
    "prospectDetails.pCustomFields.memberId",
    "prospectDetails.pCustomFields.member_id",
    "prospectDetails.MemberId",
    "prospectDetails.Member_Id",
    "MemberId",
    "Member_Id",
    "member_id",
    "memberId",
    "memberid",
    "Member ID",
    "member id",
]

FIRST_NAME_CANDIDATES = [
    "prospectDetails.pFirstName",
    "prospectDetails.pfirstName",
    "pFirstName",
    "FirstName",
    "First Name",
    "first_name",
]

LAST_NAME_CANDIDATES = [
    "prospectDetails.pLastName",
    "prospectDetails.plastName",
    "pLastName",
    "LastName",
    "Last Name",
    "last_name",
]


def clean_str(val: Any) -> str:
    if pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Finds matching column by exact name, case-insensitive match, or fallback pattern."""
    col_map = {str(col).strip().lower(): col for col in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        cand_lower = cand.strip().lower()
        if cand_lower in col_map:
            return col_map[cand_lower]
            
    # Substring heuristic for Member ID if candidates didn't directly match
    if any("member" in c.lower() for c in candidates):
        for col in df.columns:
            cl = str(col).strip().lower()
            if "member" in cl and "id" in cl:
                return col

    return None


def sanitize_sheet_name(raw_name: str, existing_names: List[str]) -> str:
    """Sanitizes sheet name for Excel: max 31 chars, no invalid characters, unique."""
    # Replace invalid Excel characters: \ / ? * [ ] :
    clean = re.sub(r'[\\/*?\[\]:]', '_', raw_name).strip()
    # Remove leading/trailing apostrophes
    clean = clean.strip("'")
    if not clean:
        clean = "Sheet"
    
    # Excel limit is 31 characters
    base = clean[:31]
    candidate = base
    counter = 2
    while candidate.lower() in [n.lower() for n in existing_names]:
        suffix = f"_{counter}"
        max_base_len = 31 - len(suffix)
        candidate = f"{base[:max_base_len]}{suffix}"
        counter += 1

    return candidate


def classify_filename(filename: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Determines (agent_key, direction, sheet_name, error_reason) for a file.
    Follows Section 3 routing table.
    """
    stem = Path(filename).stem.strip()
    stem_lower = stem.lower()

    # 1. SmartAgent check (Caregap)
    if "smartagent" in stem_lower:
        # Extract <AnyName> from SmartAgent_<AnyName>
        # e.g. SmartAgent_Diabetes.xlsx -> Diabetes
        parts = re.split(r'smartagent[_\-\s]*', stem, flags=re.IGNORECASE)
        any_name = parts[-1].strip(" _-") if len(parts) > 1 and parts[-1].strip(" _-") else "SmartAgent"
        return ("smartagent", "caregap", any_name, None)

    # 2. Direction check for other agents
    has_inbound = "inbound" in stem_lower
    has_outbound = "outbound" in stem_lower

    if has_inbound and has_outbound:
        return (None, None, None, f"Ambiguous direction: both 'inbound' and 'outbound' found in filename '{stem}'")
    if not has_inbound and not has_outbound:
        return (None, None, None, f"Direction ('inbound' or 'outbound') not found in filename '{stem}'")

    direction = "inbound" if has_inbound else "outbound"

    # 3. Agent identification
    if "claims" in stem_lower:
        if direction != "inbound":
            return (None, None, None, f"Unexpected direction 'outbound' for Claims in '{stem}' (only inbound supported)")
        return ("claims", "inbound", "Claims", None)

    if "authorization" in stem_lower:
        if direction != "inbound":
            return (None, None, None, f"Unexpected direction 'outbound' for Authorization in '{stem}' (only inbound supported)")
        return ("authorization", "inbound", "Authorization", None)

    # Match exchange eligibility (with or without spaces/underscores/hyphens)
    if re.search(r'exchange[\s_\-]*eligibility', stem_lower):
        if direction != "inbound":
            return (None, None, None, f"Unexpected direction 'outbound' for Exchange Eligibility in '{stem}' (only inbound supported)")
        return ("exchange_eligibility", "inbound", "Exchange Eligibility", None)

    # Match medicare eligibility
    if re.search(r'medicare[\s_\-]*eligibility', stem_lower):
        if direction != "inbound":
            return (None, None, None, f"Unexpected direction 'outbound' for Medicare Eligibility in '{stem}' (only inbound supported)")
        return ("medicare_eligibility", "inbound", "Medicare Eligibility", None)

    # Match TRC-PF
    if re.search(r'trc[\s_\-]*pf', stem_lower) or "trcpf" in stem_lower:
        sheet = "TRC-PF Inbound" if direction == "inbound" else "TRC-PF Outbound"
        return ("trcpf", direction, sheet, None)

    # Match OEC
    # Use word boundary or underscore check so we don't accidentally match substrings of longer words
    if re.search(r'(^|[_\-\s])oec([_\-\s]|$)', stem_lower) or stem_lower.startswith("oec") or "oec_" in stem_lower or "oec-" in stem_lower:
        sheet = "OEC Inbound" if direction == "inbound" else "OEC Outbound"
        return ("oec", direction, sheet, None)

    # Match OEV
    if re.search(r'(^|[_\-\s])oev([_\-\s]|$)', stem_lower) or stem_lower.startswith("oev") or "oev_" in stem_lower or "oev-" in stem_lower:
        sheet = "OEV Inbound" if direction == "inbound" else "OEV Outbound"
        return ("oev", direction, sheet, None)

    return (None, None, None, f"Unrecognized agent in filename '{stem}'. Expected Claims, Authorization, Exchange Eligibility, Medicare Eligibility, TRC-PF, OEC, OEV, or SmartAgent.")


def remap_inbound_to_outbound_shape(raw_file_path: str, inbound_df: pd.DataFrame) -> pd.DataFrame:
    """
    Section 4b: Outbound-shaped columns for TRC-PF/OEC/OEV inbound files.
    Pulls Member ID and Member Last Name from raw file; maps AI duration -> callduration(mins)
    and Total billable units -> billableunits.
    """
    if raw_file_path.lower().endswith((".xlsx", ".xls")):
        raw_df = pd.read_excel(raw_file_path, dtype=str)
    else:
        raw_df = pd.read_csv(raw_file_path, dtype=str)

    # Filter raw_df with the same logic process_inbound uses for duration
    duration_col = process_inbound.COLUMN_MAP["duration"]
    if duration_col in raw_df.columns:
        valid_mask = raw_df[duration_col].apply(
            lambda v: not (pd.isna(v) or str(v).strip().lower() in ("", "nan", "none", "null"))
        )
        filtered_raw = raw_df[valid_mask].reset_index(drop=True)
    else:
        filtered_raw = raw_df.reset_index(drop=True)

    # Identify member id column
    member_id_col = find_column(filtered_raw, MEMBER_ID_CANDIDATES)
    first_name_col = find_column(filtered_raw, FIRST_NAME_CANDIDATES)
    last_name_col = find_column(filtered_raw, LAST_NAME_CANDIDATES)

    n_rows = len(inbound_df)
    member_first_names = []
    member_last_names = []
    member_ids = []

    for i in range(n_rows):
        # Fallbacks if raw row count matches filtered_raw
        if i < len(filtered_raw):
            raw_row = filtered_raw.iloc[i]
            mid = clean_str(raw_row.get(member_id_col)) if member_id_col else ""
            lname = clean_str(raw_row.get(last_name_col)) if last_name_col else ""
            fname = clean_str(raw_row.get(first_name_col)) if first_name_col else ""
        else:
            mid = ""
            lname = ""
            fname = ""

        # Fallback to Caller Name from inbound_df if fname is empty
        if not fname:
            caller_name = clean_str(inbound_df.iloc[i].get("Caller Name", ""))
            if caller_name:
                parts = caller_name.split()
                fname = parts[0]
                if not lname and len(parts) > 1:
                    lname = " ".join(parts[1:])
            else:
                fname = ""

        member_ids.append(mid)
        member_first_names.append(fname)
        member_last_names.append(lname)

    reshaped_df = pd.DataFrame({
        "Member First Name": member_first_names,
        "Member Last Name": member_last_names,
        "Phone Number": inbound_df["Caller Phone Number"].tolist(),
        "Member ID": member_ids,
        "Call Status": inbound_df["Call status"].tolist(),
        "callduration(mins)": inbound_df["AI duration(mins)"].tolist(),
        "billableunits": inbound_df["Total billable units"].tolist(),
    }, columns=OUTBOUND_SHAPED_COLUMNS)

    return reshaped_df


def process_batch_zip(zip_path: str, formula_config: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extracts ZIP, routes files, processes each, and creates a combined multi-sheet Excel file.
    Returns: (output_xlsx_path, sheets_summary, skipped_files)
    """
    batch_id = str(uuid.uuid4())
    extract_dir = os.path.join(TEMP_DIR, f"batch_extract_{batch_id}")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    except Exception as e:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise ValueError(f"Failed to extract ZIP archive: {str(e)}")

    processed_sheets: List[Dict[str, Any]] = []
    skipped_files: List[Dict[str, Any]] = []
    existing_sheet_names: List[str] = []

    # Gather all extracted files
    all_extracted_files: List[str] = []
    for root, _, files in os.walk(extract_dir):
        for file in files:
            all_extracted_files.append(os.path.join(root, file))

    # Sort files for deterministic processing
    all_extracted_files.sort()

    for file_path in all_extracted_files:
        base_name = os.path.basename(file_path)

        # Ignore macOS and temporary hidden files
        if (base_name.startswith(".") or 
            base_name.startswith("~") or 
            "__MACOSX" in file_path or 
            base_name.lower() in ("thumbs.db", ".ds_store")):
            continue

        ext = os.path.splitext(base_name)[1].lower()
        if ext not in [".csv", ".xlsx", ".xls"]:
            skipped_files.append({
                "filename": base_name,
                "reason": f"Unsupported file extension '{ext}'. Only CSV and Excel files are processed."
            })
            continue

        agent, direction, raw_sheet_name, error_reason = classify_filename(base_name)

        if error_reason:
            skipped_files.append({
                "filename": base_name,
                "reason": error_reason
            })
            continue

        sheet_name = sanitize_sheet_name(raw_sheet_name, existing_sheet_names)
        existing_sheet_names.append(sheet_name)

        try:
            # Route to the appropriate processor
            if agent == "smartagent":
                df, stats = process_caregap.process(file_path)
                billable_sum = stats.get("total_billable_units", 0.0)
            elif direction == "outbound":
                outbound_config = formula_config.get("outbound", {})
                df, stats = process_outbound.process(file_path, outbound_config)
                billable_sum = stats.get("total_billable_units", 0.0)
            else:
                # Inbound files
                inbound_config = formula_config.get("inbound", {})
                raw_df, stats = process_inbound.process(file_path, inbound_config)
                billable_sum = stats.get("total_billable_sum", 0.0)

                # Check if remapping to Outbound-shaped columns is needed (4b: TRC-PF, OEC, OEV)
                if agent in ("trcpf", "oec", "oev"):
                    df = remap_inbound_to_outbound_shape(file_path, raw_df)
                else:
                    # Original inbound shape (4a: Claims, Authorization, Exchange Eligibility, Medicare Eligibility)
                    df = raw_df

            processed_sheets.append({
                "sheet_name": sheet_name,
                "filename": base_name,
                "agent": agent.upper() if agent != "smartagent" else "SmartAgent",
                "direction": direction,
                "rows": len(df),
                "billable_sum": round(float(billable_sum), 2),
                "df": df,
            })

        except Exception as e:
            skipped_files.append({
                "filename": base_name,
                "reason": f"Processing error: {str(e)}"
            })

    # Clean up extracted temp directory
    shutil.rmtree(extract_dir, ignore_errors=True)

    if not processed_sheets:
        raise ValueError(
            "No files could be processed from the ZIP archive. "
            "Please check that filenames match the required naming convention (e.g. Claims_Inbound.xlsx)."
        )

    # Sort processed sheets following Section 3 table order
    TABLE_ORDER = [
        "claims_inbound",
        "authorization_inbound",
        "exchange_eligibility_inbound",
        "medicare_eligibility_inbound",
        "trcpf_inbound",
        "trcpf_outbound",
        "oec_inbound",
        "oec_outbound",
        "oev_inbound",
        "oev_outbound",
    ]

    def get_sort_key(sheet_data: Dict[str, Any]) -> Tuple[int, str]:
        key = f"{sheet_data['agent'].lower()}_{sheet_data['direction'].lower()}"
        if key in TABLE_ORDER:
            return (TABLE_ORDER.index(key), sheet_data["sheet_name"])
        return (100, sheet_data["sheet_name"])

    processed_sheets.sort(key=get_sort_key)

    # Write combined workbook
    output_filename = f"output_batch_{batch_id}.xlsx"
    output_path = os.path.join(TEMP_DIR, output_filename)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_data in processed_sheets:
            sheet_data["df"].to_excel(writer, sheet_name=sheet_data["sheet_name"], index=False)

    # Prepare summary excluding raw dataframe objects
    summary_sheets = [
        {
            "sheet_name": s["sheet_name"],
            "filename": s["filename"],
            "agent": s["agent"],
            "direction": s["direction"],
            "rows": s["rows"],
            "billable_sum": s["billable_sum"],
        }
        for s in processed_sheets
    ]

    return output_filename, summary_sheets, skipped_files
