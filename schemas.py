from pydantic import BaseModel
from typing import List, Optional

class BindRequest(BaseModel):
    phone_number: str
    line_user_id: str
    student_name: str

class PushMessageReq(BaseModel):
    line_user_id: str
    message: str

class SwipeRequest(BaseModel):
    card_number: str
    offline_timestamp: str = None
    client_swipe_id: str = None

class ClassScheduleBase(BaseModel):
    day_of_week: int
    arrival_time: str
    departure_time: str

class GroupCreate(BaseModel):
    name: str
    schedules: List[ClassScheduleBase]

class ClassScheduleResponse(ClassScheduleBase):
    id: int
    class Config:
        orm_mode = True

class GroupResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    schedules: List[ClassScheduleResponse]
    class Config:
        orm_mode = True

class ExamScoreCreate(BaseModel):
    student_id: int
    exam_name: str
    subject: Optional[str] = None
    score: str

class ExamScoreResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    exam_name: str
    subject: Optional[str] = None
    score: str
    date: str
    
    class Config:
        orm_mode = True

class StudentScoreInput(BaseModel):
    student_id: int
    score: str

class ExamScoreBulkCreate(BaseModel):
    exam_name: str
    subject: Optional[str] = None
    scores: List[StudentScoreInput]
