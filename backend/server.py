import os
import shutil
import tempfile
import uuid
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import process_inbound
import process_outbound
import process_caregap

app = FastAPI()

# Enable CORS for the React frontend (running on a different port like 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev and github pages
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

@app.get("/")
def health_check():
    return {"status": "Imperial Automation API is running!"}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    format: str = Form("csv"),
    callType: str = Form("inbound"),
    humanIncrementSize: float = Form(3.0),
    humanIncrementCost: float = Form(0.15),
    aiFreeThreshold: float = Form(0.25),
    aiFirstLimit: float = Form(3.0),
    aiFirstCost: float = Form(0.75),
    aiSubsequentSize: float = Form(3.0),
    aiSubsequentCost: float = Form(0.75),
    outboundHumanFreeThreshold: float = Form(0.25),
    outboundHumanFirstLimit: float = Form(3.0),
    outboundHumanFirstCost: float = Form(0.75),
    outboundHumanSubsequentSize: float = Form(3.0),
    outboundHumanSubsequentCost: float = Form(0.75),
    outboundVoicemailDroppedCost: float = Form(0.25),
):
    # Validate file extension
    input_ext = os.path.splitext(file.filename)[1].lower()
    if input_ext not in [".csv", ".xlsx", ".xls"]:
        return JSONResponse(status_code=400, content={"error": "Only CSV and Excel files are supported."})
    
    # Save uploaded file temporarily with a UNIQUE secure ID
    unique_id = str(uuid.uuid4())
    input_path = os.path.join(TEMP_DIR, f"upload_{unique_id}{input_ext}")
    output_ext = f".{format.lower()}"
    if output_ext not in [".csv", ".xlsx", ".pdf"]:
        output_ext = ".csv"
        
    output_path = os.path.join(TEMP_DIR, f"output_{unique_id}{output_ext}")
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    if callType == "outbound":
        formula_config = {
            "human_answered": {
                "free_threshold": outboundHumanFreeThreshold,
                "first_increment_limit": outboundHumanFirstLimit,
                "first_increment_cost": outboundHumanFirstCost,
                "subsequent_increment_size": outboundHumanSubsequentSize,
                "subsequent_increment_cost": outboundHumanSubsequentCost,
            },
            "voicemail_dropped_cost": outboundVoicemailDroppedCost
        }
    else:
        formula_config = {
            "human": {
                "increment_size": humanIncrementSize,
                "increment_cost": humanIncrementCost,
            },
            "ai": {
                "free_threshold": aiFreeThreshold,
                "first_increment_limit": aiFirstLimit,
                "first_increment_cost": aiFirstCost,
                "subsequent_increment_size": aiSubsequentSize,
                "subsequent_increment_cost": aiSubsequentCost,
            }
        }
        
    try:
        # Call the appropriate processing logic based on callType
        if callType == "caregap":
            out_df, stats = process_caregap.process(input_path)
        elif callType == "outbound":
            out_df, stats = process_outbound.process(input_path, formula_config)
        else:
            out_df, stats = process_inbound.process(input_path, formula_config)
        
        # Save output file
        if output_path.endswith(".xlsx"):
            out_df.to_excel(output_path, index=False)
        elif output_path.endswith(".pdf"):
            process_inbound.export_to_pdf(out_df, output_path)
        else:
            out_df.to_csv(output_path, index=False)
            
        return {
            "stats": stats,
            "download_url": f"/download?filename=output_{unique_id}{output_ext}"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/download")
def download_file(filename: str):
    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        display_name = f"Cleaned_Invoices{os.path.splitext(filename)[1]}"
        return FileResponse(file_path, filename=display_name)
    return JSONResponse(status_code=404, content={"error": "File not found"})
