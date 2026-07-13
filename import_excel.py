import pandas as pd
import math
from database import SessionLocal, engine, Base
from models import Parent, Student

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

def import_data():
    db = SessionLocal()
    df = pd.read_excel('excels/學生資料.xlsx')
    
    parents_created = 0
    students_created = 0
    
    for index, row in df.iterrows():
        student_number = str(row['學號']).strip() if pd.notna(row['學號']) else None
        student_name = str(row['姓名']).strip() if pd.notna(row['姓名']) else None
        
        # 尋找主要聯絡電話 (優先使用 簡訊電話1)
        phone = clean_phone(row.get('簡訊電話1'))
        if not phone:
            phone = clean_phone(row.get('媽媽手機'))
        if not phone:
            phone = clean_phone(row.get('爸爸手機'))
            
        if not student_number or not student_name or not phone:
            continue
            
        # 確保家長存在
        parent = db.query(Parent).filter(Parent.phone_number == phone).first()
        if not parent:
            # 若無家長姓名，自動生成
            parent_name = str(row['家長姓名']).strip() if '家長姓名' in row and pd.notna(row['家長姓名']) else f"{student_name}的家長"
            parent = Parent(name=parent_name, phone_number=phone)
            db.add(parent)
            db.commit()
            db.refresh(parent)
            parents_created += 1
            
        # 確保學生存在
        student = db.query(Student).filter(Student.student_number == student_number).first()
        if not student:
            student = Student(name=student_name, student_number=student_number, parent_id=parent.id)
            db.add(student)
            students_created += 1
            
    db.commit()
    print(f"匯入完成！成功建立/更新了 {parents_created} 位家長，以及 {students_created} 名學生。")
    db.close()

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("開始讀取 Excel 並匯入資料...")
    import_data()
