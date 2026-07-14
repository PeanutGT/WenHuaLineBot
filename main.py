import os
import sys
import logging
import io
import secrets
from fastapi import FastAPI, Request, HTTPException, Depends, Header, status, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from database import engine, Base, get_db, SessionLocal
import models
from sqlalchemy.orm import Session
from models import Parent, Student, Attendance
from linebot.v3.messaging import ReplyMessageRequest
import schemas
from fastapi.staticfiles import StaticFiles
import datetime
from linebot.v3.messaging import PushMessageRequest, TextMessage
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

def clean_phone(val):
    if pd.isna(val):
        return None
    try:
        if isinstance(val, (float, int)):
            s = str(int(val))
        else:
            s = str(val).strip()
            s = ''.join(filter(str.isdigit, s))
            
        if not s:
            return None
        # 如果是 9 碼且以 9 開頭，自動補 0 (例如 912345678 -> 0912345678)
        if len(s) == 9 and s.startswith('9'):
            return '0' + s
        return s
    except Exception:
        return None

# Use UploadFile in the API endpoint instead of reading from disk
def sync_excel_to_db_from_file(file_content: bytes):
    logger.info("Starting stateless Excel sync...")
    try:
        db = SessionLocal()
        df = pd.read_excel(io.BytesIO(file_content))
        
        parents_updated = 0
        students_updated = 0
        skipped = []
        
        for index, row in df.iterrows():
            row_idx = index + 2 # Excel is 1-indexed, plus header
            
            # Handle student number (might be float in pandas)
            raw_sn = row.get('學號')
            if pd.notna(raw_sn):
                student_number = str(int(raw_sn)).strip() if isinstance(raw_sn, float) else str(raw_sn).strip()
            else:
                student_number = None
                
            student_name = str(row['姓名']).strip() if pd.notna(row['姓名']) else None
            
            # Handle card number (often read as float e.g. 123.0)
            raw_card = row.get('卡號')
            if pd.notna(raw_card):
                card_number = str(int(raw_card)).strip() if isinstance(raw_card, float) else str(raw_card).strip()
            else:
                card_number = None
            
            phone = clean_phone(row.get('簡訊電話1'))
            if not phone:
                phone = clean_phone(row.get('媽媽手機'))
            if not phone:
                phone = clean_phone(row.get('爸爸手機'))
                
            if not student_number or not student_name or not phone:
                reason = []
                if not student_number: reason.append("缺少學號")
                if not student_name: reason.append("缺少姓名")
                if not phone: reason.append("手機號碼無效或缺失")
                skipped.append({"row": row_idx, "name": student_name or "(未知)", "reason": "、".join(reason)})
                continue
                
            # 確保家長存在並更新名稱 (若有改變)
            parent = db.query(Parent).filter(Parent.phone_number == phone).first()
            parent_name = str(row.get('家長姓名')).strip() if '家長姓名' in row and pd.notna(row['家長姓名']) else f"{student_name}的家長"
            
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
                
            # 確保學生存在並更新資料
            student = db.query(Student).filter(Student.student_number == student_number).first()
            if not student:
                student = Student(name=student_name, student_number=student_number, card_number=card_number, parent_id=parent.id)
                db.add(student)
                students_updated += 1
            else:
                if student.name != student_name or student.parent_id != parent.id or student.card_number != card_number:
                    student.name = student_name
                    student.parent_id = parent.id
                    student.card_number = card_number
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
    logger.info("Startup complete. Cron scheduling is now externalized.")

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


@app.post("/webhook")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """
    Phase 2: LINE Webhook Endpoint.
    Validates X-Line-Signature to reject unverified requests.
    """
    if x_line_signature is None:
        logger.warning("Webhook called without X-Line-Signature header.")
        raise HTTPException(status_code=400, detail="X-Line-Signature header missing")

    # Get request body as text
    body = await request.body()
    body_str = body.decode('utf-8')
    logger.info(f"Received Webhook Event: {body_str}")

    # Handle webhook body and signature
    try:
        handler.handle(body_str, x_line_signature)
    except InvalidSignatureError:
        logger.error("Invalid signature. Check your channel secret.")
        raise HTTPException(status_code=400, detail="Invalid signature. Unauthentic request rejected.")
    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    return JSONResponse(content={"status": "OK"})

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        if text == "查詢孩子資料":
            db = SessionLocal()
            try:
                parent = db.query(Parent).filter(Parent.line_user_id == user_id).first()
                if not parent:
                    reply_text = (
                        "【智慧親師通 - 系統提示】\n"
                        "您目前尚未綁定家長身分。\n\n"
                        "為啟用即時出勤通知，請按左下角小鍵盤圖示，並輸入以下格式進行綁定：\n"
                        "「綁定 學生姓名 手機號碼」\n\n"
                        "範例：綁定 王小明 0912345678"
                    )
                else:
                    if not parent.students:
                        reply_text = "您目前名下沒有綁定的學生資料。"
                    else:
                        reply_messages = []
                        for s in parent.students:
                            last_attendance = db.query(Attendance)\
                                .filter(Attendance.student_id == s.id)\
                                .order_by(Attendance.timestamp.desc()).first()
                            
                            status = last_attendance.status if last_attendance else "尚無出勤紀錄"
                            time_str = (last_attendance.timestamp + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S') if last_attendance else ""
                            
                            reply_messages.append(f"👨‍🎓 學生：{s.name}\n🕒 狀態：{status} {time_str}")
                        
                        reply_text = "\n\n".join(reply_messages)
                
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
            except Exception as e:
                logger.error(f"Error querying data: {e}", exc_info=True)
            finally:
                db.close()
        elif text.startswith("綁定 "):
            parts = text.split()
            db = SessionLocal()
            try:
                reply_text = (
                    "【智慧親師通 - 系統升級公告】\n"
                    "🔒 為保障您的資料安全，我們已全面升級為「LIFF 網頁安全綁定」系統。\n\n"
                    "請勿在此直接輸入綁定資訊。請點擊下方的「選單」，選擇「綁定身分」進行簡訊驗證綁定手續。"
                )
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
            except Exception as e:
                logger.error(f"Error binding data: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.info(f"Received unknown message from {user_id}: {text}")

@app.post("/api/otp/request")
def request_otp(req: schemas.OTPRequest, db: Session = Depends(get_db)):
    parent = db.query(Parent).filter(Parent.phone_number == req.phone_number).first()
    if not parent:
        raise HTTPException(status_code=404, detail="找不到該手機號碼，請確認是否為註冊家長")
    
    import random
    mock_otp = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    
    otp_record = db.query(models.OtpRecord).filter(models.OtpRecord.phone_number == req.phone_number).first()
    if otp_record:
        otp_record.otp = mock_otp
        otp_record.expires_at = expires_at
        otp_record.attempts = 0
    else:
        otp_record = models.OtpRecord(phone_number=req.phone_number, otp=mock_otp, expires_at=expires_at)
        db.add(otp_record)
        
    db.commit()
    
    # [TODO] 實作真實簡訊閘道呼叫，例如三竹簡訊或 Twilio
    # def send_sms(phone, msg): ...
    logger.info(f"== [SMS MOCK] 向 {req.phone_number} 發送簡訊 OTP: {mock_otp} ==")
    
    return {"status": "success", "detail": "驗證碼已發送"}

@app.post("/api/bind")
def bind_account(req: schemas.BindRequest, db: Session = Depends(get_db)):
    otp_record = db.query(models.OtpRecord).filter(models.OtpRecord.phone_number == req.phone_number).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="無效的驗證碼或驗證碼已過期")
        
    if datetime.datetime.utcnow() > otp_record.expires_at:
        db.delete(otp_record)
        db.commit()
        raise HTTPException(status_code=400, detail="驗證碼已失效，請重新取得")
        
    otp_record.attempts += 1
    if otp_record.attempts > 5:
        db.delete(otp_record)
        db.commit()
        raise HTTPException(status_code=400, detail="錯誤次數過多，驗證碼已失效")
        
    if otp_record.otp != req.otp:
        db.commit()
        raise HTTPException(status_code=400, detail=f"驗證碼錯誤 (剩餘 {5 - otp_record.attempts} 次機會)")
    
    parent = db.query(Parent).filter(Parent.phone_number == req.phone_number).first()
    if not parent:
        raise HTTPException(status_code=404, detail="找不到對應之家長資料")
    
    # Phase 3: Update DB, overwriting logic included
    old_parent = db.query(Parent).filter(Parent.line_user_id == req.line_user_id).first()
    if old_parent and old_parent.id != parent.id:
        old_parent.is_bound = False
        old_parent.line_user_id = None
        old_parent.bound_at = None

    parent.line_user_id = req.line_user_id
    parent.is_bound = True
    parent.bound_at = datetime.datetime.utcnow()
    db.delete(otp_record)
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
    
    # Phase 3 & 5: Push immediate notification for Arrival (skip if offline historical retry)
    if not is_offline_retry and new_status == "已進班" and student.parent and student.parent.is_bound and student.parent.line_user_id:
        try:
            tw_time = get_tw_now().strftime('%H:%M')
            msg_text = f"【到班通知】\n✅ 您的孩子 {student.name} 已於 {tw_time} 抵達補習班。"
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                push_req = PushMessageRequest(
                    to=student.parent.line_user_id,
                    messages=[TextMessage(text=msg_text)]
                )
                line_bot_api.push_message(push_req)
        except Exception as e:
            logger.error(f"Error pushing arrival notification: {e}")
    
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
    headers = {
        'Content-Disposition': f'attachment; filename="{file_name}"'
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
