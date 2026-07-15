from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Time
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
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    
    parent = relationship("Parent", back_populates="students")
    group = relationship("Group", back_populates="students")
    attendances = relationship("Attendance", back_populates="student")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    
    students = relationship("Student", back_populates="group")
    schedules = relationship("ClassSchedule", back_populates="group")

class ClassSchedule(Base):
    __tablename__ = "class_schedules"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    day_of_week = Column(Integer, nullable=False) # 0=Monday, 6=Sunday
    arrival_time = Column(Time, nullable=False)
    departure_time = Column(Time, nullable=False)
    is_active = Column(Boolean, default=True)
    
    group = relationship("Group", back_populates="schedules")

class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    notification_type = Column(String, nullable=False) # e.g. "missing_departure"
    date = Column(String, nullable=False) # e.g. "2026-07-14"
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class Attendance(Base):
    __tablename__ = "attendances"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    status = Column(String, nullable=False) # "已進班" or "已離班"
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    client_swipe_id = Column(String, index=True, nullable=True)

    student = relationship("Student", back_populates="attendances")

class OtpRecord(Base):
    __tablename__ = "otp_records"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    otp = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)

class ExamScore(Base):
    __tablename__ = "exam_scores"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    exam_name = Column(String, nullable=False)
    score = Column(String, nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    
    student = relationship("Student")


