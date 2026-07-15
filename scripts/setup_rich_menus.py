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

def get_static_menu_image():
    image_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'rich_menu.jpg')
    with open(image_path, 'rb') as f:
        return f.read()

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
            img_bytes = get_static_menu_image()
            
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
