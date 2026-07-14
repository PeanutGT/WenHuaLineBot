from pydantic import BaseModel

class OTPRequest(BaseModel):
    phone_number: str

class BindRequest(BaseModel):
    phone_number: str
    otp: str
    line_user_id: str

class PushMessageReq(BaseModel):
    line_user_id: str
    message: str

class SwipeRequest(BaseModel):
    card_number: str
    offline_timestamp: str = None
    client_swipe_id: str = None
