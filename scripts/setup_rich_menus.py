import os
import sys
import logging
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    RichMenuRequest,
    RichMenuArea,
    RichMenuBounds,
    RichMenuSize,
    MessageAction,
    URIAction
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
liff_url = os.getenv('LIFF_URL', 'https://liff.line.me/YOUR_LIFF_ID')

if not channel_access_token:
    logger.error("Missing LINE_CHANNEL_ACCESS_TOKEN")
    sys.exit(1)

configuration = Configuration(access_token=channel_access_token)

def generate_split_menu_image():
    width, height = 2500, 1686
    bg_color = (15, 23, 42) 
    text_color = (56, 189, 248)
    
    img = Image.new('RGB', (width, height), color=bg_color)
    d = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("C:\\Windows\\Fonts\\msjh.ttc", 200)
    except:
        font = ImageFont.load_default()
            
    # Left Side: Bind Account
    text1 = "1. 綁定身分"
    bbox1 = d.textbbox((0, 0), text1, font=font)
    text_w1 = bbox1[2] - bbox1[0]
    text_h1 = bbox1[3] - bbox1[1]
    x1 = (833 - text_w1) / 2
    y1 = (height - text_h1) / 2
    d.text((x1, y1), text1, font=font, fill=text_color)
    
    # Middle Side: Query Attendance
    text2 = "2. 查詢出勤"
    bbox2 = d.textbbox((0, 0), text2, font=font)
    text_w2 = bbox2[2] - bbox2[0]
    text_h2 = bbox2[3] - bbox2[1]
    x2 = 833 + (833 - text_w2) / 2
    y2 = (height - text_h2) / 2
    d.text((x2, y2), text2, font=font, fill=text_color)
    
    # Right Side: Query Grades
    text3 = "3. 查詢成績"
    bbox3 = d.textbbox((0, 0), text3, font=font)
    text_w3 = bbox3[2] - bbox3[0]
    text_h3 = bbox3[3] - bbox3[1]
    x3 = 1666 + (834 - text_w3) / 2
    y3 = (height - text_h3) / 2
    d.text((x3, y3), text3, font=font, fill=text_color)
    
    # Dividers
    d.line([(833, 100), (833, height-100)], fill=text_color, width=10)
    d.line([(1666, 100), (1666, height-100)], fill=text_color, width=10)
    
    # Outer Border
    d.rectangle([(80, 80), (width-80, height-80)], outline=text_color, width=15)
    
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()

def create_and_set_rich_menu():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob_api = MessagingApiBlob(api_client)
        
        logger.info("Initializing Rich Menu configuration...")
        
        rich_menu = RichMenuRequest(
            size=RichMenuSize(width=2500, height=1686),
            selected=True,
            name="Main Menu Split",
            chat_bar_text="智慧親師通",
            areas=[
                RichMenuArea(
                    bounds=RichMenuBounds(x=0, y=0, width=833, height=1686),
                    action=MessageAction(type="message", text="綁定身分")
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=833, y=0, width=833, height=1686),
                    action=MessageAction(type="message", text="查詢孩子資料")
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1666, y=0, width=834, height=1686),
                    action=MessageAction(type="message", text="查詢成績")
                )
            ]
        )
        
        response = line_bot_api.create_rich_menu(rich_menu)
        menu_id = response.rich_menu_id
        logger.info(f"Created Rich Menu ID: {menu_id}")
        
        try:
            img_bytes = generate_split_menu_image()
            
            logger.info("Uploading image to LINE...")
            line_bot_blob_api.set_rich_menu_image(
                rich_menu_id=menu_id,
                body=img_bytes,
                _headers={'Content-Type': 'image/jpeg'}
            )
            
            line_bot_api.set_default_rich_menu(menu_id)
            logger.info("Rich Menu successfully deployed with LIFF bindings!")
        except Exception as e:
            logger.error(f"Failed to set rich menu: {e}", exc_info=True)

if __name__ == "__main__":
    create_and_set_rich_menu()
