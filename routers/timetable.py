import io
import re
import logging
import pandas as pd
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models
from main import verify_admin_token

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/import")
async def import_timetable(file: UploadFile = File(...), db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    content = await file.read()
    try:
        # Read all sheets
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=str)
        db.query(models.TimetableItem).delete() # Clear old timetable completely
        
        for sheet_name, df in sheets.items():
            df = df.where(pd.notnull(df), None)
            time_col = df.columns[0]
            days_cols = df.columns[1:]
            
            for index, row in df.iterrows():
                time_slot = str(row[time_col]).strip() if row[time_col] else None
                if not time_slot or time_slot == "nan" or time_slot == "None":
                    continue
                
                # Remove seconds formatting (HH:MM:SS -> HH:MM)
                time_slot = re.sub(r'(\d{1,2}:\d{2}):00(?!\d)', r'\1', time_slot)
                    
                for day in days_cols:
                    subject = str(row[day]).strip() if row[day] else None
                    if subject and subject not in ["nan", "None", ""]:
                        item = models.TimetableItem(
                            group_name=sheet_name,
                            time_slot=time_slot,
                            day_of_week=str(day).strip(),
                            subject=subject
                        )
                        db.add(item)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error importing timetable: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
def export_timetable(db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    items = db.query(models.TimetableItem).all()
    
    # Group items by group_name
    groups = {}
    for item in items:
        groups.setdefault(item.group_name, []).append(item)
        
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not groups:
            # Empty timetable
            pd.DataFrame().to_excel(writer, sheet_name="無課表")
        else:
            for gname, gitems in groups.items():
                fixed_time_slots = [f"{str(h).zfill(2)}:00" for h in range(12, 23)]
                db_time_slots = [x.time_slot for x in gitems]
                
                # Merge and sort
                time_slots = sorted(list(set(fixed_time_slots + db_time_slots)))
                days = ["日", "一", "二", "三", "四", "五", "六"]
                
                rows = []
                for ts in time_slots:
                    row = {gname: ts}
                    for d in days:
                        subj = next((x.subject for x in gitems if x.time_slot == ts and x.day_of_week == d), "")
                        row[d] = subj
                    rows.append(row)
                    
                df = pd.DataFrame(rows)
                safe_gname = str(gname).replace('/', '-').replace('\\', '-')[:31]
                df.to_excel(writer, index=False, sheet_name=safe_gname)
                
    output.seek(0)
    encoded_file_name = quote("課表.xlsx")
    headers = {
        'Content-Disposition': f"attachment; filename*=utf-8''{encoded_file_name}"
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@router.get("")
def get_timetable(db: Session = Depends(get_db)):
    # Public endpoint for swipe.html
    items = db.query(models.TimetableItem).all()
    result = {}
    for item in items:
        if item.group_name not in result:
            result[item.group_name] = []
        result[item.group_name].append({
            "time_slot": item.time_slot,
            "day_of_week": item.day_of_week,
            "subject": item.subject
        })
    return result
