import os
import logging
import datetime
import re
from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from database import SessionLocal
import models
from models import Parent, Student, Attendance

# 避免 circular import，我們把 clean_phone 放這裡或共用 util 裡
def clean_phone_webhook(val):
    if not val:
        return None
    try:
        if isinstance(val, (float, int)):
            s = str(int(val))
        else:
            s = str(val).strip()
            s = re.split(r'[#\*ext分機]', s, flags=re.IGNORECASE)[0]
            s = ''.join(filter(str.isdigit, s))
            
        if not s:
            return None
        if len(s) == 9 and s.startswith('9'):
            return '0' + s
        if len(s) > 10 and s.startswith('09'):
            return s[:10]
        elif len(s) > 10 and s.startswith('0'):
            return s[:10]
        return s
    except Exception:
        return None

logger = logging.getLogger(__name__)
router = APIRouter()

channel_secret = os.getenv('LINE_CHANNEL_SECRET', 'test')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'test')
handler = WebhookHandler(channel_secret)
configuration = Configuration(access_token=channel_access_token)

@router.post("/webhook")
async def callback(request: Request, x_line_signature: str = Header(None)):
    if x_line_signature is None:
        logger.warning("Webhook called without X-Line-Signature header.")
        raise HTTPException(status_code=400, detail="X-Line-Signature header missing")

    body = await request.body()
    body_str = body.decode('utf-8')
    logger.info(f"Received Webhook Event: {body_str}")

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
        elif text == "查詢成績":
            db = SessionLocal()
            try:
                parent = db.query(Parent).filter(Parent.line_user_id == user_id).first()
                if not parent:
                    reply_text = "您目前尚未綁定家長身分，請先進行綁定。"
                else:
                    if not parent.students:
                        reply_text = "您目前名下沒有綁定的學生資料。"
                    else:
                        reply_messages = []
                        for s in parent.students:
                            recent_scores = db.query(models.ExamScore)\
                                .filter(models.ExamScore.student_id == s.id)\
                                .order_by(models.ExamScore.date.desc())\
                                .limit(5).all()
                            
                            if not recent_scores:
                                reply_messages.append(f"👨‍🎓 學生：{s.name}\n尚無成績紀錄")
                            else:
                                score_lines = [f"👨‍🎓 學生：{s.name}"]
                                for sc in recent_scores:
                                    subj_str = f" ({sc.subject})" if sc.subject else ""
                                    score_lines.append(f"• {sc.exam_name}{subj_str}：{sc.score}")
                                reply_messages.append("\n".join(score_lines))
                        
                        reply_text = "【近期成績紀錄】\n\n" + "\n\n".join(reply_messages)
                
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
            except Exception as e:
                logger.error(f"Error querying grades: {e}", exc_info=True)
            finally:
                db.close()
        elif text.startswith("綁定 "):
            parts = text.split()
            db = SessionLocal()
            try:
                if len(parts) != 3:
                    reply_text = "⚠️ 格式錯誤。\n正確格式為（中間請加一個半形空白）：\n綁定 學生姓名 手機號碼\n\n範例：綁定 王小明 0912345678"
                else:
                    student_name = parts[1]
                    phone_number = parts[2]
                    
                    phone = clean_phone_webhook(phone_number)
                    if not phone:
                        reply_text = "⚠️ 無效的手機號碼格式。\n請確認您輸入的手機號碼是否正確，並重新輸入。"
                    else:
                        parent = db.query(Parent).filter(Parent.phone_number == phone).first()
                        if not parent:
                            reply_text = (
                                "❌ 綁定失敗\n\n"
                                "找不到該手機號碼對應的家長資料。\n"
                                "可能原因：\n"
                                "1. 您輸入的手機號碼有誤，請重新檢查。\n"
                                "2. 補習班尚未將您的資料建檔，或登錄的號碼與您輸入的不同。\n\n"
                                "👉 請來電或前往補習班櫃檯，與行政老師確認您的聯絡電話資料是否正確。"
                            )
                        else:
                            student = db.query(Student).filter(Student.parent_id == parent.id, Student.name == student_name).first()
                            if not student:
                                reply_text = (
                                    "❌ 綁定失敗\n\n"
                                    f"找不到名為「{student_name}」且關聯至該手機號碼的學生資料。\n"
                                    "可能原因：\n"
                                    "1. 學生姓名打錯字（請確認有無錯別字）。\n"
                                    "2. 補習班建檔時的學生姓名與您輸入的不同。\n\n"
                                    "👉 請重新輸入，或向補習班老師確認建檔的學生姓名。"
                                )
                            else:
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
