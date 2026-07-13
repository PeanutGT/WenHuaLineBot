import os
import sys
import logging
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse, FileResponse
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
from apscheduler.schedulers.background import BackgroundScheduler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Phase 1: Create database tables if they don't exist
Base.metadata.create_all(bind=engine)

load_dotenv()

# Phase 2: LINE Bot Configuration
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

if channel_secret is None or channel_access_token is None:
    logger.error('Specify LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN as environment variables.')
    sys.exit(1)

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

app = FastAPI(
    title="Smart Parent-Teacher Communication System",
    description="Backend API for LINE Messaging API integration.",
    version="1.0.0"
)

# Mount static files
app.mount("/liff", StaticFiles(directory="liff"), name="liff")
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    except:
        return None

def sync_excel_to_db():
    logger.info("Starting Excel sync...")
    try:
        db = SessionLocal()
        df = pd.read_excel('excels/學生資料.xlsx')
        
        parents_updated = 0
        students_updated = 0
        
        for index, row in df.iterrows():
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
        logger.info(f"Excel sync completed! Parents created/updated: {parents_updated}, Students created/updated: {students_updated}.")
        return parents_updated, students_updated
    except Exception as e:
        logger.error(f"Error during Excel sync: {e}")
        return 0, 0

@app.on_event("startup")
def startup_event():
    sync_excel_to_db()
    # Initialize Scheduler
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(check_missing_departure, 'cron', hour=22, minute=0)
    scheduler.add_job(send_daily_summary, 'cron', hour=22, minute=30)
    scheduler.start()
    logger.info("Background Scheduler started.")

def check_missing_departure():
    logger.info("Running check_missing_departure...")
    db = SessionLocal()
    try:
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        students = db.query(Student).all()
        for s in students:
            last_att = db.query(Attendance).filter(
                Attendance.student_id == s.id,
                Attendance.timestamp >= today_start
            ).order_by(Attendance.timestamp.desc()).first()
            
            if last_att and last_att.status == "已進班":
                if s.parent and s.parent.is_bound and s.parent.line_user_id:
                    with ApiClient(configuration) as api_client:
                        line_bot_api = MessagingApi(api_client)
                        msg_text = f"【防走失警示】\n⚠️ 您的孩子 {s.name} 今天已進班，但至今(22:00)尚未有離班打卡紀錄。\n請留意孩子是否還在班上或忘記打卡。"
                        push_req = PushMessageRequest(
                            to=s.parent.line_user_id,
                            messages=[TextMessage(text=msg_text)]
                        )
                        line_bot_api.push_message(push_req)
    except Exception as e:
        logger.error(f"Error in check_missing_departure: {e}", exc_info=True)
    finally:
        db.close()

def send_daily_summary():
    logger.info("Running send_daily_summary...")
    db = SessionLocal()
    try:
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        parents = db.query(Parent).filter(Parent.is_bound == True, Parent.line_user_id != None).all()
        for p in parents:
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
    except Exception as e:
        logger.error(f"Error in send_daily_summary: {e}", exc_info=True)
    finally:
        db.close()

# Mock OTP Storage
MOCK_OTP_DB = {}

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
                if len(parts) < 3:
                    reply_text = (
                        "【智慧親師通 - 格式錯誤】\n"
                        "❌ 綁定指令格式有誤。\n\n"
                        "請輸入完整的指令，例如：\n"
                        "綁定 王小明 0912345678"
                    )
                else:
                    phone = parts[-1]
                    student_name = " ".join(parts[1:-1])
                    
                    # Find the student
                    student = db.query(Student).filter(Student.name == student_name).first()
                    if not student:
                        reply_text = (
                            "【智慧親師通 - 綁定失敗】\n"
                            f"❌ 系統查無名為「{student_name}」的學生資料。\n\n"
                            "請確認您輸入的學生姓名是否與本班登記之資料完全相符，或洽詢櫃台人員協助。"
                        )
                    else:
                        parent = student.parent
                        if not parent or parent.phone_number != phone:
                            reply_text = (
                                "【智慧親師通 - 綁定失敗】\n"
                                "❌ 身分驗證失敗！\n\n"
                                "您輸入的手機號碼與該名學生登記的家長聯絡電話不相符，基於資安考量無法為您綁定。若有疑問請聯繫櫃台更新資料。"
                            )
                        else:
                            # Clear old binding for this LINE user if any
                            old_parent = db.query(Parent).filter(Parent.line_user_id == user_id).first()
                            if old_parent and old_parent.id != parent.id:
                                old_parent.is_bound = False
                                old_parent.line_user_id = None
                                old_parent.bound_at = None
                                
                            parent.line_user_id = user_id
                            parent.is_bound = True
                            parent.bound_at = datetime.datetime.utcnow()
                            db.commit()
                            
                            reply_text = (
                                "【智慧親師通 - 綁定成功】\n"
                                f"✅ 已成功為您綁定學生「{student.name}」之親屬身分。\n\n"
                                "您現在可隨時點擊下方選單查詢出勤狀態，系統亦將於學生進退班時，自動發送推播通知給您。"
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

# --- Phase 3 & 4 APIs ---

@app.post("/api/otp/request")
def request_otp(req: schemas.OTPRequest, db: Session = Depends(get_db)):
    parent = db.query(Parent).filter(Parent.phone_number == req.phone_number).first()
    if not parent:
        raise HTTPException(status_code=404, detail="找不到該手機號碼，請確認是否為註冊家長")
    
    mock_otp = "123456"
    MOCK_OTP_DB[req.phone_number] = mock_otp
    logger.info(f"Generated OTP {mock_otp} for {req.phone_number}")
    return {"status": "success", "mock_otp": mock_otp}

@app.post("/api/bind")
def bind_account(req: schemas.BindRequest, db: Session = Depends(get_db)):
    stored_otp = MOCK_OTP_DB.get(req.phone_number)
    if not stored_otp or stored_otp != req.otp:
        raise HTTPException(status_code=400, detail="驗證碼錯誤或已失效")
    
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
    db.commit()
    
    if req.phone_number in MOCK_OTP_DB:
        del MOCK_OTP_DB[req.phone_number]
    
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
def swipe_card(req: schemas.SwipeRequest, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.card_number == req.card_number).first()
    if not student:
        raise HTTPException(status_code=404, detail="找不到該感應卡號")
    
    # Check latest attendance for today
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    last_attendance = db.query(Attendance)\
        .filter(Attendance.student_id == student.id, Attendance.timestamp >= today_start)\
        .order_by(Attendance.timestamp.desc()).first()
    
    if last_attendance and last_attendance.status == "已進班":
        new_status = "已離班"
    else:
        new_status = "已進班"
        
    new_record = Attendance(student_id=student.id, status=new_status)
    db.add(new_record)
    db.commit()
    
    # 移除即時推播，轉為純查詢制與批次通知模式
    
    return {"status": "success", "student_name": student.name, "new_status": new_status}

@app.get("/api/attendance/today")
def get_today_attendance(db: Session = Depends(get_db)):
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
def api_sync_excel():
    p_count, s_count = sync_excel_to_db()
    return {"status": "success", "parents_updated": p_count, "students_updated": s_count}

@app.post("/api/attendance/export")
def export_attendance(db: Session = Depends(get_db)):
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
    date_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d')
    file_name = f"{date_str}_出勤紀錄.xlsx"
    
    # 確保 excels/Students 目錄存在
    export_dir = os.path.join("excels", "Students")
    os.makedirs(export_dir, exist_ok=True)
    
    file_path = os.path.join(export_dir, file_name)
    
    df.to_excel(file_path, index=False)
    
    # Return success message instead of downloading
    return {"status": "success", "detail": f"報表已儲存至 {file_path}", "file_name": file_name}
