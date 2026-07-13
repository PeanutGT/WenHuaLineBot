from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Parent(Base):
    __tablename__ = "parents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=False) # Used for OTP identity verification
    
    # LINE Binding specific fields (Phase 1 Requirements)
    line_user_id = Column(String, unique=True, index=True, nullable=True) # Only stores user ID, no PII
    is_bound = Column(Boolean, default=False)
    bound_at = Column(DateTime, nullable=True)

    students = relationship("Student", back_populates="parent")

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    student_number = Column(String, unique=True, index=True, nullable=False)
    card_number = Column(String, unique=True, index=True, nullable=True)
    
    # Foreign Key linking to Parent
    parent_id = Column(Integer, ForeignKey("parents.id"))
    parent = relationship("Parent", back_populates="students")
    attendances = relationship("Attendance", back_populates="student")

class Attendance(Base):
    __tablename__ = "attendances"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    status = Column(String, nullable=False) # "已進班" or "已離班"
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    student = relationship("Student", back_populates="attendances")
