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
    MessageAction
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
if not channel_access_token:
    logger.error("Missing LINE_CHANNEL_ACCESS_TOKEN")
    sys.exit(1)

configuration = Configuration(access_token=channel_access_token)

def generate_simple_menu_image():
    width, height = 2500, 1686
    # 現代感的深色背景與亮藍色文字 (對應網頁版設計)
    bg_color = (15, 23, 42) 
    text_color = (56, 189, 248)
    
    img = Image.new('RGB', (width, height), color=bg_color)
    d = ImageDraw.Draw(img)
    
    # 嘗試載入微軟正黑體以支援中文
    try:
        font = ImageFont.truetype("C:\\Windows\\Fonts\\msjh.ttc", 240)
    except:
        try:
            font = ImageFont.truetype("C:\\Windows\\Fonts\\mingliu.ttc", 240)
        except:
            font = ImageFont.load_default()
            
    text = "查詢孩子資料"
    
    # 計算文字置中位置
    bbox = d.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (width - text_w) / 2
    y = (height - text_h) / 2
    
    # 畫出文字
    d.text((x, y), text, font=font, fill=text_color)
    
    # 畫一個外框增加點擊感
    d.rectangle([(80, 80), (width-80, height-80)], outline=text_color, width=15)
    
    # 存入 BytesIO
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()

def create_and_set_rich_menu():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob_api = MessagingApiBlob(api_client)
        
        logger.info("Initializing Rich Menu configuration...")
        
        # 1. 定義圖文選單
        rich_menu = RichMenuRequest(
            size=RichMenuSize(width=2500, height=1686),
            selected=True,
            name="Main Menu Simple",
            chat_bar_text="智慧親師通",
            areas=[
                RichMenuArea(
                    bounds=RichMenuBounds(x=0, y=0, width=2500, height=1686),
                    action=MessageAction(type="message", text="查詢孩子資料")
                )
            ]
        )
        
        # 2. 建立 Rich Menu 並取得 ID
        response = line_bot_api.create_rich_menu(rich_menu)
        menu_id = response.rich_menu_id
        logger.info(f"Created Rich Menu ID: {menu_id}")
        
        # 3. 生成簡約文字圖片並上傳
        try:
            img_bytes = generate_simple_menu_image()
            
            logger.info("Uploading image to LINE...")
            line_bot_blob_api.set_rich_menu_image(
                rich_menu_id=menu_id,
                body=img_bytes,
                _headers={'Content-Type': 'image/jpeg'}
            )
            logger.info("Image uploaded successfully!")
            
            # 4. 設為官方帳號的預設圖文選單
            line_bot_api.set_default_rich_menu(menu_id)
            logger.info("Rich Menu is now set as DEFAULT for all users!")
        except Exception as e:
            logger.error(f"Failed to set rich menu image or default: {e}", exc_info=True)

if __name__ == "__main__":
    create_and_set_rich_menu()
