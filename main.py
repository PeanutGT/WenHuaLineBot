import os
import sys
import logging
import io
import secrets
import re
from urllib.parse import quote
from typing import List
from fastapi import FastAPI, Request, HTTPException, Depends, Header, status, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3 import WebhookHandler

from database import engine, Base, get_db, SessionLocal
import models
from sqlalchemy import text
from sqlalchemy.orm import Session
from models import Parent, Student, Attendance
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest
import schemas
from fastapi.staticfiles import StaticFiles
import datetime
from linebot.v3.messaging import PushMessageRequest, TextMessage
from routers.line_webhook import router as webhook_router
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Determine execution context
if getattr(sys, 'frozen', False):
    # PyInstaller executable
    app_dir = os.path.dirname(sys.executable)
    static_dir = sys._MEIPASS
else:
    # Normal Python script
    app_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = app_dir

# Auto-migrate groups table to add is_active column if missing
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE groups ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
        conn.commit()
except Exception as e:
    pass # Column might already exist

# Phase 1: Create database tables if they don't exist
Base.metadata.create_all(bind=engine)

load_dotenv(os.path.join(app_dir, ".env"))

# Phase 2: LINE Bot Configuration
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

if channel_secret is None or channel_access_token is None:
    logger.error('Specify LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN as environment variables.')
    sys.exit(1)

configuration = Configuration(access_token=channel_access_token)

# Phase 1 Zero Trust: Token Definitions
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
CRON_TOKEN = os.getenv("CRON_TOKEN")
KIOSK_TOKEN = os.getenv("KIOSK_TOKEN")

security = HTTPBearer()

class TokenVerifier:
    def __init__(self, expected_token: str, token_name: str):
        self.expected_token = expected_token
        self.token_name = token_name

    def __call__(self, credentials: HTTPAuthorizationCredentials = Depends(security)):
        if not self.expected_token or not secrets.compare_digest(credentials.credentials, self.expected_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid {self.token_name} Token")
        return credentials.credentials

verify_kiosk_token = TokenVerifier(KIOSK_TOKEN, "Kiosk")
verify_admin_token = TokenVerifier(ADMIN_TOKEN, "Admin")
verify_cron_token = TokenVerifier(CRON_TOKEN, "Cron")

def get_tw_now() -> datetime.datetime:
    """Returns the current time in Taiwan (UTC+8) as a naive datetime object."""
    return datetime.datetime.utcnow() + datetime.timedelta(hours=8)

handler = WebhookHandler(channel_secret)

app = FastAPI(
    title="Smart Parent-Teacher Communication System",
    description="Backend API for LINE Messaging API integration.",
    version="1.0.0"
)

# Phase 4 & 5: Zero Trust CORS Middleware with whitelist
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/liff", StaticFiles(directory=os.path.join(static_dir, "liff")), name="liff")
app.mount("/static", StaticFiles(directory=os.path.join(static_dir, "static")), name="static")

# Include Routers
app.include_router(webhook_router)

def clean_phone(val):
    if pd.isna(val):
        return None
    try:
        if isinstance(val, (float, int)):
            s = str(int(val))
        else:
            s = str(val).strip()
            # 先去掉分機常見符號後面的內容
            s = re.split(r'[#\*ext分機]', s, flags=re.IGNORECASE)[0]
            s = ''.join(filter(str.isdigit, s))
            
        if not s:
            return None
        # 如果是 9 碼且以 9 開頭，自動補 0 (例如 912345678 -> 0912345678)
        if len(s) == 9 and s.startswith('9'):
            return '0' + s
            
        # 擷取台灣手機 10 碼 (09開頭) 或市話 (0開頭, 最多保留 10 碼)
        if len(s) > 10 and s.startswith('09'):
            return s[:10]
        elif len(s) > 10 and s.startswith('0'):
            return s[:10]
            
        return s
    except Exception:
        return None

def clean_card_number(val):
    if pd.isna(val) or not val:
        return None
    try:
        s = str(val).strip()
        if s.endswith('.0'):
            s = s[:-2]
        # 如果整串都是數字，自動補齊到 10 碼
        if s.isdigit():
            return s.zfill(10)
        return s
    except:
        return None

@app.get("/api/config")
def get_config():
    return {"liffId": os.getenv("LIFF_ID", "")}

@app.get("/api/ping")
def ping():
    return {"status": "ok", "message": "Pong! Server is awake."}

# Use UploadFile in the API endpoint instead of reading from disk
def sync_excel_to_db_from_file(file_content: bytes):
    logger.info("Starting stateless Excel sync...")
    try:
        db = SessionLocal()
        df = pd.read_excel(io.BytesIO(file_content), dtype=str)
        
        # Replace NaN with None
        df = df.where(pd.notnull(df), None)
        
        parents_updated = 0
        students_updated = 0
        skipped = []
        
        for index, row in df.iterrows():
            row_idx = index + 2 # Excel is 1-indexed, plus header
            
            student_number = str(row.get('學號')).strip() if row.get('學號') else None
            student_name = str(row.get('姓名')).strip() if row.get('姓名') else None
            card_number = clean_card_number(row.get('卡號'))
            
            phone = clean_phone(row.get('簡訊電話1'))
            if not phone:
                phone = clean_phone(row.get('媽媽手機'))
            if not phone:
                phone = clean_phone(row.get('爸爸手機'))
            if not phone:
                phone = clean_phone(row.get('家裡電話'))
            if not phone:
                phone = clean_phone(row.get('學生手機'))
                
            if not student_number or not student_name or not phone:
                reason = []
                if not student_number: reason.append("缺少學號")
                if not student_name: reason.append("缺少姓名")
                if not phone: reason.append("手機號碼無效或缺失")
                skipped.append({"row": row_idx, "name": student_name or "(未知)", "reason": "、".join(reason)})
                continue
                
            # 確保家長存在並更新名稱 (若有改變)
            parent = db.query(Parent).filter(Parent.phone_number == phone).first()
            parent_name = str(row.get('家長姓名')).strip() if '家長姓名' in row and row.get('家長姓名') else f"{student_name}的家長"
            
            if not parent:
                parent = Parent(name=parent_name, phone_number=phone)
                db.add(parent)
                db.commit()
                db.refresh(parent)
                parents_updated += 1
            else:
                if parent.name != parent_name:
                    parent.name = parent_name
                    db.commit()
                    
            # Class and Subject mapping
            class_name = str(row.get('班級')).strip() if '班級' in row and row.get('班級') and str(row.get('班級')) != 'nan' else None
            enrolled_subjects = str(row.get('科目')).strip() if '科目' in row and row.get('科目') and str(row.get('科目')) != 'nan' else None
                
            # 確保學生存在並更新資料
            student = db.query(Student).filter(Student.student_number == student_number).first()
            if not student:
                student = Student(
                    name=student_name, 
                    student_number=student_number, 
                    card_number=card_number, 
                    parent_id=parent.id, 
                    class_name=class_name,
                    enrolled_subjects=enrolled_subjects
                )
                db.add(student)
                students_updated += 1
            else:
                updated = False
                if student.name != student_name: student.name = student_name; updated = True
                if student.parent_id != parent.id: student.parent_id = parent.id; updated = True
                if student.card_number != card_number: student.card_number = card_number; updated = True
                if student.class_name != class_name: student.class_name = class_name; updated = True
                if student.enrolled_subjects != enrolled_subjects: student.enrolled_subjects = enrolled_subjects; updated = True
                
                if updated:
                    db.commit()
                    students_updated += 1
                    
        db.commit()
        db.close()
        logger.info(f"Excel sync completed! Parents created/updated: {parents_updated}, Students created/updated: {students_updated}. Skipped: {len(skipped)}")
        return parents_updated, students_updated, skipped
    except Exception as e:
        logger.error(f"Error during Excel sync: {e}")
        return 0, 0, []

@app.on_event("startup")
def startup_event():
    logger.info("Startup complete. Executing DB migration...")
    db = SessionLocal()
    from sqlalchemy import text
    try:
        db.execute(text("ALTER TABLE students ADD COLUMN class_name VARCHAR"))
        logger.info("Added class_name to students")
    except Exception as e:
        logger.info(f"Skipped class_name: {e}")
    try:
        db.execute(text("ALTER TABLE students ADD COLUMN enrolled_subjects VARCHAR"))
        logger.info("Added enrolled_subjects to students")
    except Exception as e:
        logger.info(f"Skipped enrolled_subjects: {e}")
    try:
        db.execute(text("ALTER TABLE exam_scores ADD COLUMN subject VARCHAR"))
        logger.info("Added subject to exam_scores")
    except Exception as e:
        logger.info(f"Skipped subject: {e}")
    db.commit()
    db.close()

@app.post("/api/cron/check_missing_departure")
def check_missing_departure(db: Session = Depends(get_db), token: str = Depends(verify_cron_token)):
    logger.info("Running external cron check_missing_departure...")
    try:
        now_utc = datetime.datetime.utcnow()
        now_tw = get_tw_now()
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        today_date_str = now_tw.strftime('%Y-%m-%d')
        day_of_week = now_tw.weekday()
        
        students = db.query(Student).all()
        for s in students:
            if not s.group:
                continue
                
            schedule = db.query(models.ClassSchedule).filter(
                models.ClassSchedule.group_id == s.group.id,
                models.ClassSchedule.day_of_week == day_of_week,
                models.ClassSchedule.is_active == True
            ).first()
            
            if not schedule:
                continue # No class today or schedule inactive
                
            # Check if current time is past departure time + 15 mins buffer
            dep_time = schedule.departure_time
            dep_datetime = now_tw.replace(hour=dep_time.hour, minute=dep_time.minute, second=0, microsecond=0)
            if now_tw < dep_datetime + datetime.timedelta(minutes=15):
                continue
            
            # Check Idempotency
            log_exists = db.query(models.NotificationLog).filter(
                models.NotificationLog.student_id == s.id,
                models.NotificationLog.notification_type == "missing_departure",
                models.NotificationLog.date == today_date_str
            ).first()
            
            if log_exists:
                continue
                
            last_att = db.query(Attendance).filter(
                Attendance.student_id == s.id,
                Attendance.timestamp >= today_start
            ).order_by(Attendance.timestamp.desc()).first()
            
            if last_att and last_att.status == "已進班":
                if s.parent and s.parent.is_bound and s.parent.line_user_id:
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        msg_text = f"【防走失警示】\n⚠️ 您的孩子 {s.name} 今天已進班，表定於 {dep_time.strftime('%H:%M')} 放學，但至今尚未有離班打卡紀錄。\n請留意孩子是否還在班上或忘記打卡。"
                        push_req = PushMessageRequest(
                            to=s.parent.line_user_id,
                            messages=[TextMessage(text=msg_text)]
                        )
                        line_bot_api.push_message(push_req)
                    
                    # Record log
                    new_log = models.NotificationLog(
                        student_id=s.id,
                        notification_type="missing_departure",
                        date=today_date_str
                    )
                    db.add(new_log)
                    db.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in check_missing_departure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cron/send_daily_summary")
def send_daily_summary(db: Session = Depends(get_db), token: str = Depends(verify_cron_token)):
    logger.info("Running external cron send_daily_summary...")
    try:
        now_utc = datetime.datetime.utcnow()
        now_tw = get_tw_now()
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        today_date_str = now_tw.strftime('%Y-%m-%d')
        
        parents = db.query(Parent).filter(Parent.is_bound == True, Parent.line_user_id != None).all()
        for p in parents:
            # Check Idempotency
            if not p.students:
                continue
                
            first_student_id = p.students[0].id
            log_exists = db.query(models.NotificationLog).filter(
                models.NotificationLog.student_id == first_student_id,
                models.NotificationLog.notification_type == "daily_summary",
                models.NotificationLog.date == today_date_str
            ).first()
            
            if log_exists:
                continue
                
            summary_lines = []
            for s in p.students:
                atts = db.query(Attendance).filter(
                    Attendance.student_id == s.id,
                    Attendance.timestamp >= today_start
                ).order_by(Attendance.timestamp.asc()).all()
                if atts:
                    time_records = []
                    for att in atts:
                        tw_time = (att.timestamp + datetime.timedelta(hours=8)).strftime('%H:%M')
                        time_records.append(f"{att.status}({tw_time})")
                    summary_lines.append(f"👨‍🎓 {s.name}：{' / '.join(time_records)}")
            
            if summary_lines:
                msg_text = "【今日出勤總結】\n" + "\n".join(summary_lines)
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    push_req = PushMessageRequest(
                        to=p.line_user_id,
                        messages=[TextMessage(text=msg_text)]
                    )
                    line_bot_api.push_message(push_req)
                
                # Record log using first student id
                new_log = models.NotificationLog(
                    student_id=first_student_id,
                    notification_type="daily_summary",
                    date=today_date_str
                )
                db.add(new_log)
                db.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in send_daily_summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/groups", response_model=List[schemas.GroupResponse])
def get_groups(db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    groups = db.query(models.Group).filter(models.Group.is_active == True).all()
    return groups

@app.post("/api/groups")
def create_group(req: schemas.GroupCreate, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    group = db.query(models.Group).filter(models.Group.name == req.name).first()
    if not group:
        group = models.Group(name=req.name)
        db.add(group)
        db.flush()
    else:
        group.is_active = True
        
    db.query(models.ClassSchedule).filter(models.ClassSchedule.group_id == group.id).delete()
    
    for sched in req.schedules:
        try:
            arr_time = datetime.datetime.strptime(sched.arrival_time, "%H:%M").time()
            dep_time = datetime.datetime.strptime(sched.departure_time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="時間格式錯誤，需為 HH:MM")
            
        new_sched = models.ClassSchedule(
            group_id=group.id,
            day_of_week=sched.day_of_week,
            arrival_time=arr_time,
            departure_time=dep_time
        )
        db.add(new_sched)
        
    db.commit()
    return {"status": "success"}

@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    group.is_active = False
    db.query(models.ClassSchedule).filter(models.ClassSchedule.group_id == group_id).delete()
    db.query(Student).filter(Student.group_id == group_id).update({"group_id": None})
    
    db.commit()
    return {"status": "success"}

@app.post("/api/bind")
def bind_account(req: schemas.BindRequest, db: Session = Depends(get_db)):
    phone = clean_phone(req.phone_number)
    if not phone:
        raise HTTPException(status_code=400, detail="無效的手機號碼格式")
        
    parent = db.query(Parent).filter(Parent.phone_number == phone).first()
    if not parent:
        raise HTTPException(status_code=404, detail="找不到對應之家長資料")
        
    student = db.query(Student).filter(Student.parent_id == parent.id, Student.name == req.student_name).first()
    if not student:
        raise HTTPException(status_code=404, detail=f"找不到名為「{req.student_name}」且關聯至該手機號碼的學生資料")
    
    # Phase 3: Update DB, overwriting logic included
    old_parent = db.query(Parent).filter(Parent.line_user_id == req.line_user_id).first()
    if old_parent and old_parent.id != parent.id:
        old_parent.is_bound = False
        old_parent.line_user_id = None
        old_parent.bound_at = None

    parent.line_user_id = req.line_user_id
    parent.is_bound = True
    parent.bound_at = datetime.datetime.utcnow()
    db.commit()
    
    return {"status": "success", "detail": "綁定成功"}

@app.post("/api/push/arrival")
def push_arrival(req: schemas.PushMessageReq, db: Session = Depends(get_db)):
    """Phase 4: Push arrival notification to bound parent"""
    parent = db.query(Parent).filter(Parent.line_user_id == req.line_user_id).first()
    if not parent or not parent.is_bound:
        raise HTTPException(status_code=400, detail="此家長尚未綁定 LINE 帳號")
        
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_req = PushMessageRequest(
                to=req.line_user_id,
                messages=[TextMessage(text=req.message)]
            )
            line_bot_api.push_message(push_req)
        return {"status": "success", "detail": "到校推播成功"}
    except Exception as e:
        logger.error(f"Push failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="推播失敗")

@app.post("/api/swipe")
def swipe_card(req: schemas.SwipeRequest, db: Session = Depends(get_db), token: str = Depends(verify_kiosk_token)):
    student = db.query(Student).filter(Student.card_number == req.card_number).first()
    if not student:
        raise HTTPException(status_code=404, detail="找不到該感應卡號")
        
    # Idempotency check
    if req.client_swipe_id:
        existing = db.query(Attendance).filter(Attendance.client_swipe_id == req.client_swipe_id).first()
        if existing:
            return {"status": "success", "student_name": student.name, "new_status": existing.status, "detail": "已處理過的打卡紀錄"}
        
    # Parse timestamp if offline mode
    now = datetime.datetime.utcnow()
    is_offline_retry = False
    
    if req.offline_timestamp:
        try:
            swipe_time = datetime.datetime.fromisoformat(req.offline_timestamp.replace("Z", "+00:00")).astimezone(datetime.timezone.utc).replace(tzinfo=None)
            
            # Timestamp validation
            if swipe_time > now + datetime.timedelta(minutes=5):
                raise HTTPException(status_code=400, detail="無效的時間戳：不能為未來時間")
            if swipe_time < now - datetime.timedelta(hours=24):
                raise HTTPException(status_code=400, detail="無效的時間戳：已超過 24 小時")
                
            if now - swipe_time > datetime.timedelta(minutes=2):
                is_offline_retry = True
                
        except ValueError:
            swipe_time = now
    else:
        swipe_time = now
    
    # Check latest attendance for today
    today_start = swipe_time.replace(hour=0, minute=0, second=0, microsecond=0)
    last_attendance = db.query(Attendance)\
        .filter(Attendance.student_id == student.id, Attendance.timestamp >= today_start)\
        .order_by(Attendance.timestamp.desc()).first()
    
    if last_attendance and last_attendance.status == "已進班":
        new_status = "已離班"
    else:
        new_status = "已進班"
        
    new_record = Attendance(student_id=student.id, status=new_status, timestamp=swipe_time, client_swipe_id=req.client_swipe_id)
    db.add(new_record)
    db.commit()
    
    # 依使用者要求，移除打卡即時推播，轉為純查詢制 (家長透過 LINE 查詢)
    
    return {"status": "success", "student_name": student.name, "new_status": new_status}

@app.get("/api/attendance/today")
def get_today_attendance(db: Session = Depends(get_db), token: str = Depends(verify_kiosk_token)):
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    records = db.query(Attendance, Student.name, Student.student_number)\
        .join(Student, Attendance.student_id == Student.id)\
        .filter(Attendance.timestamp >= today_start)\
        .order_by(Attendance.timestamp.desc())\
        .limit(50)\
        .all()
        
    result = []
    for att, name, s_num in records:
        time_str = (att.timestamp + datetime.timedelta(hours=8)).strftime('%H:%M:%S')
        result.append({
            "name": name,
            "student_number": s_num,
            "status": att.status,
            "time": time_str
        })
    # Reverse so the frontend can prepend them properly if needed, but since we prepend 
    # individually, actually sending them ascending is better for prepending in a loop.
    # We send ascending so `data.forEach(prepend)` ends up with the newest on top.
    result.reverse()
    return result

@app.get("/api/setup-menu")
def api_setup_menu():
    try:
        from scripts.setup_rich_menus import create_and_set_rich_menu
        create_and_set_rich_menu()
        return {"status": "Rich Menu successfully updated on LINE server!"}
    except Exception as e:
        logger.error(f"Error setting up rich menu: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}

@app.post("/api/sync-excel")
async def api_sync_excel(file: UploadFile = File(...), token: str = Depends(verify_admin_token)):
    content = await file.read()
    p_count, s_count, skipped = sync_excel_to_db_from_file(content)
    return {
        "status": "success", 
        "parents_updated": p_count, 
        "students_updated": s_count,
        "skipped": skipped
    }

@app.post("/api/attendance/export")
def api_export_attendance(db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    records = db.query(Attendance, Student.name, Student.student_number)\
        .join(Student, Attendance.student_id == Student.id)\
        .filter(Attendance.timestamp >= today_start)\
        .order_by(Attendance.timestamp.asc())\
        .all()
        
    data = []
    for att, name, s_num in records:
        tw_time = (att.timestamp + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
        data.append({
            "學號": s_num,
            "姓名": name,
            "狀態": att.status,
            "打卡時間": tw_time
        })
        
    df = pd.DataFrame(data)
    date_str = get_tw_now().strftime('%Y-%m-%d')
    file_name = f"{date_str}_出勤紀錄.xlsx"
    
    # Phase 4: Stateless Memory Stream (io.BytesIO)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='出勤紀錄')
    
    output.seek(0)
    encoded_file_name = quote(file_name)
    headers = {
        'Content-Disposition': f"attachment; filename*=utf-8''{encoded_file_name}"
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.get("/api/students")
def get_students(db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    students = db.query(Student, Parent).outerjoin(Parent, Student.parent_id == Parent.id).order_by(Student.student_number).all()
    return [{
        "id": s.id, 
        "name": s.name, 
        "student_number": s.student_number,
        "class_name": s.class_name,
        "enrolled_subjects": s.enrolled_subjects,
        "parent_name": p.name if p else "",
        "line_user_id": p.line_user_id if p else ""
    } for s, p in students]

@app.get("/api/students/export")
def api_export_students(db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
    students = db.query(Student, Parent).outerjoin(Parent, Student.parent_id == Parent.id).order_by(Student.student_number).all()
    
    data = []
    for s, p in students:
        data.append({
            "學號": s.student_number,
            "姓名": s.name,
            "卡號": s.card_number,
            "家長姓名": p.name if p else "",
            "聯絡電話": p.phone_number if p else "",
            "Line ID": p.line_user_id if p else "",
            "班級": s.class_name,
            "科目": s.enrolled_subjects
        })
        
    df = pd.DataFrame(data)
    date_str = get_tw_now().strftime('%Y-%m-%d')
    file_name = f"{date_str}_學生名單.xlsx"
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='學生名單')
    
    output.seek(0)
    encoded_file_name = quote(file_name)
    headers = {
        'Content-Disposition': f"attachment; filename*=utf-8''{encoded_file_name}"
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post("/api/grades")
def create_grade(req: schemas.ExamScoreCreate, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
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

@app.post("/api/grades/bulk")
def create_grades_bulk(req: schemas.ExamScoreBulkCreate, db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
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

@app.get("/api/grades/recent", response_model=List[schemas.ExamScoreResponse])
def get_recent_grades(db: Session = Depends(get_db), token: str = Depends(verify_admin_token)):
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

@app.post("/api/timetable/import")
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
                import re
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

@app.get("/api/timetable/export")
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
                # We need to construct a DataFrame.
                # First, find all unique time slots and sort them.
                # Usually we just sort them alphabetically, or assume HH:MM:SS format.
                # Generate default time slots from 12:00 to 22:00
                fixed_time_slots = [f"{str(h).zfill(2)}:00" for h in range(12, 23)]
                db_time_slots = [x.time_slot for x in gitems]
                
                # Merge and sort
                time_slots = sorted(list(set(fixed_time_slots + db_time_slots)))
                days = ["一", "二", "三", "四", "五", "六", "日"]
                
                rows = []
                for ts in time_slots:
                    row = {"時間": ts}
                    for d in days:
                        # Find subject
                        subj = next((x.subject for x in gitems if x.time_slot == ts and x.day_of_week == d), "")
                        row[d] = subj
                    rows.append(row)
                    
                df = pd.DataFrame(rows)
                # Ensure sheet_name is valid (max 31 chars, avoid invalid chars if possible)
                safe_gname = str(gname).replace('/', '-').replace('\\', '-')[:31]
                df.to_excel(writer, index=False, sheet_name=safe_gname)
                
    output.seek(0)
    encoded_file_name = quote("課表.xlsx")
    headers = {
        'Content-Disposition': f"attachment; filename*=utf-8''{encoded_file_name}"
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.get("/api/timetable")
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
