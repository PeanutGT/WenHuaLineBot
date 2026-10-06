import pandas as pd
import io
import re
import logging
from database import SessionLocal
from models import Parent, Student

logger = logging.getLogger(__name__)

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

def sync_excel_to_db_from_file(file_content: bytes):
    logger.info("Starting stateless Excel sync...")
    try:
        db = SessionLocal()
        df = pd.read_excel(io.BytesIO(file_content), dtype=str)
        
        # Normalize column names to strip any accidental spaces
        df.columns = [str(c).strip() for c in df.columns]
        
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
            
            phone = clean_phone(row.get('聯絡電話'))
            if not phone:
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
                
                # Only update class and subjects if they are explicitly provided in the file (not empty)
                if class_name is not None and student.class_name != class_name: 
                    student.class_name = class_name
                    updated = True
                if enrolled_subjects is not None and student.enrolled_subjects != enrolled_subjects: 
                    student.enrolled_subjects = enrolled_subjects
                    updated = True
                
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
