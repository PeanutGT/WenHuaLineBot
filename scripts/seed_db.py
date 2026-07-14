from database import SessionLocal, engine, Base
from models import Parent, Student
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if dummy parent exists
        if not db.query(Parent).filter(Parent.phone_number == '0912345678').first():
            p = Parent(name='王大明', phone_number='0912345678')
            db.add(p)
            db.commit()
            db.refresh(p)
            s = Student(name='王小明', student_number='112001', parent_id=p.id)
            db.add(s)
            db.commit()
            logger.info("Database seeded with mock parent: 0912345678")
        else:
            logger.info("Mock parent already exists.")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
