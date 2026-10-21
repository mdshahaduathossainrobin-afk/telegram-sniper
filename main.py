import logging
import asyncio
import os
import re
import threading
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Configure Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 39097979))
API_HASH = os.environ.get("API_HASH", "f23c7abd6d08744a52da529dd566f1f9")
STRING_SESSION = os.environ.get("STRING_SESSION", "")

# StringSession ব্যবহার করা হয়েছে যাতে Render-এ ফাইল ডিলেট হলেও লগইন থাকে
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

BOT_USERNAME = 'klyxx_bot'

# Flask Web Server (Render-কে সচল রাখার জন্য)
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Auto-Claimer is Active!"

@client.on(events.NewMessage())
async def promo_handler(event):
    try:
        message_text = event.message.message or ""
        
        if message_text:
            logging.info(f"📩 New Message Arrived: {message_text[:30].replace(chr(10), ' ')}...")

        # 1. PROMO CODE EXTRACTION
        if "NEW PROMO CODE" in message_text or "Code:" in message_text:
            match = re.search(r'Code\s*:\s*([A-Za-z0-9\-]{5,})', message_text, re.IGNORECASE)

            if match:
                extracted_code = match.group(1).strip()
                logging.info(f"🎯 Extracted Promo Code: {extracted_code}")

                # Send code to target bot instantly
                await client.send_message(BOT_USERNAME, extracted_code)
                logging.info(f"⚡ Instant Sent code '{extracted_code}' to @{BOT_USERNAME}!")
                return

        # 2. GIVEAWAY AUTO-PARTICIPATE
        if event.message.buttons:
            for i, row in enumerate(event.message.buttons):
                for j, button in enumerate(row):
    
                    button_text = getattr(button, 'text', '') or ''
                    
                    if "participate" in button_text.lower() or "join" in button_text.lower():
                        await event.click(i, j)
                        logging.info("🎉 Successfully clicked 'Participate' button for Giveaway!")
                        return

                    target_url = getattr(button, 'url', None) or getattr(button.button, 'url', None)
                    if target_url and "start=" in target_url:
                        promo_payload = target_url.split("start=")[-1]
                        await client.send_message(BOT_USERNAME, f"/start {promo_payload}")
                        logging.info(f"⚡ Instant Fallback payload sent to @{BOT_USERNAME}!")
                        return

    except Exception as e:
        logging.error(f"⚠️ Error in handler: {e}")

def run_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def main_bot():
        print("🚀 Render Auto-Claimer Active...")
        await client.start()
        await client.run_until_disconnected()
        
    loop.run_until_complete(main_bot())

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
                  
