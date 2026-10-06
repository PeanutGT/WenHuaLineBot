import io
import datetime
import pandas as pd
from urllib.parse import quote
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from models import Student

router = APIRouter()

def get_tw_now() -> datetime.datetime:
    return datetime.datetime.utcnow() + datetime.timedelta(hours=8)

@router.post("")
def create_grade(req: schemas.ExamScoreCreate, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == req.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    new_score = models.ExamScore(
        student_id=req.student_id,
        exam_name=req.exam_name,
        subject=req.subject,
        score=req.score
    )
    db.add(new_score)
    db.commit()
    return {"status": "success"}

@router.post("/bulk")
def create_grades_bulk(req: schemas.ExamScoreBulkCreate, db: Session = Depends(get_db)):
    for item in req.scores:
        if not item.score or str(item.score).strip() == "":
            continue
        new_score = models.ExamScore(
            student_id=item.student_id,
            exam_name=req.exam_name,
            subject=req.subject,
            score=str(item.score).strip()
        )
        db.add(new_score)
    db.commit()
    return {"status": "success"}

@router.get("/recent", response_model=List[schemas.ExamScoreResponse])
def get_recent_grades(db: Session = Depends(get_db)):
    records = db.query(models.ExamScore, Student.name)\
        .join(Student, models.ExamScore.student_id == Student.id)\
        .order_by(models.ExamScore.date.desc())\
        .limit(50).all()
        
    result = []
    for sc, s_name in records:
        tw_time = (sc.date + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
        result.append({
            "id": sc.id,
            "student_id": sc.student_id,
            "student_name": s_name,
            "exam_name": sc.exam_name,
            "subject": sc.subject,
            "score": sc.score,
            "date": tw_time
        })
    return result

@router.put("/{score_id}")
def update_grade(score_id: int, req: schemas.ExamScoreUpdate, db: Session = Depends(get_db)):
    score_record = db.query(models.ExamScore).filter(models.ExamScore.id == score_id).first()
    if not score_record:
        raise HTTPException(status_code=404, detail="Score not found")
        
    if req.exam_name is not None:
        score_record.exam_name = req.exam_name
    if req.subject is not None:
        score_record.subject = req.subject
    if req.score is not None:
        score_record.score = req.score
        
    db.commit()
    db.refresh(score_record)
    return {"status": "success", "id": score_record.id}

@router.delete("/{score_id}")
def delete_grade(score_id: int, db: Session = Depends(get_db)):
    score_record = db.query(models.ExamScore).filter(models.ExamScore.id == score_id).first()
    if not score_record:
        raise HTTPException(status_code=404, detail="Score not found")
        
    db.delete(score_record)
    db.commit()
    return {"status": "success"}

@router.get("/export")
def export_grades(exam_name: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.ExamScore, Student.name, Student.student_number).join(Student, models.ExamScore.student_id == Student.id)
    
    if exam_name:
        query = query.filter(models.ExamScore.exam_name == exam_name)
        
    records = query.order_by(models.ExamScore.date.asc()).all()
    
    data = []
    for sc, s_name, s_num in records:
        tw_time = (sc.date + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
        data.append({
            "學號": s_num,
            "姓名": s_name,
            "考試名稱": sc.exam_name,
            "科目": sc.subject or "",
            "成績": sc.score,
            "登錄時間": tw_time
        })
        
    df = pd.DataFrame(data)
    date_str = get_tw_now().strftime('%Y-%m-%d')
    file_name = f"{date_str}_成績紀錄.xlsx"
    if exam_name:
        file_name = f"{date_str}_{exam_name}_成績紀錄.xlsx"
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='學生成績')
        
        # Adjust column widths
        worksheet = writer.sheets['學生成績']
        widths = {'A': 15, 'B': 15, 'C': 25, 'D': 15, 'E': 10, 'F': 25}
        for col, width in widths.items():
            worksheet.column_dimensions[col].width = width
    
    output.seek(0)
    encoded_file_name = quote(file_name)
    headers = {
        'Content-Disposition': f"attachment; filename*=utf-8''{encoded_file_name}"
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
