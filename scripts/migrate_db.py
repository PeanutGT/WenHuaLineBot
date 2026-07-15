import sqlite3
import os

# Go up one directory from scripts/ to the app root
db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "linebot.db")

def migrate():
    print(f"Migrating database at {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN class_name VARCHAR")
        print("Added class_name to students")
    except Exception as e:
        print(f"Skipped class_name: {e}")
        
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN enrolled_subjects VARCHAR")
        print("Added enrolled_subjects to students")
    except Exception as e:
        print(f"Skipped enrolled_subjects: {e}")
        
    try:
        cursor.execute("ALTER TABLE exam_scores ADD COLUMN subject VARCHAR")
        print("Added subject to exam_scores")
    except Exception as e:
        print(f"Skipped subject: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
