import logging
import asyncio
import os
import re
import threading
import time
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Configure Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 39097979))
API_HASH = os.environ.get("API_HASH", "f23c7abd6d08744a52da529dd566f1f9")

# ৪টি StringSession load করার ব্যবস্থা
session_keys = ["STRING_SESSION_1", "STRING_SESSION_2", "STRING_SESSION_3", "STRING_SESSION_4"]
clients = []

for key in session_keys:
    session_val = os.environ.get(key, "")
    if session_val:
        clients.append(TelegramClient(StringSession(session_val), API_ID, API_HASH))

BOT_USERNAME = 'klyxx_bot'

# Duplicate prevention-এর জন্য dictionary ও lock (৩০ মিনিটের মেমোরি সিস্টেম)
processed_codes = {}
lock = asyncio.Lock()

# কোড মেমোরিতে কতক্ষণ থাকবে (৩০ মিনিট = ১৮০০ সেকেন্ড)
CODE_EXPIRY_SECONDS = 1800

# Flask Web Server (Render-এর জন্য)
app = Flask(__name__)

@app.route('/')
def home():
    return f"Telegram Multi-Claimer is Active with {len(clients)} accounts!"

async def broadcast_action(extracted_code, event):
    """কোড বটে পাঠাবে এবং চ্যানেলের বাটনে (Participate/Activate) অটো ক্লিক করবে"""
    tasks = []
    
    # ১. যদি প্রোমো কোড থাকে তবে বট চ্যাটে সরাসরি কোডটি সেন্ড করা
    if extracted_code:
        for index, client in enumerate(clients, start=1):
            tasks.append(client.send_message(BOT_USERNAME, extracted_code))
            logging.info(f"⚡ [Account {index}] Instant Code '{extracted_code}' queueing...")

    # ২. চ্যানেল পোস্টে ইনলাইন বাটন (Participate / Activate in bot) থাকলে তাতেই ক্লিক করা
    if event.buttons:
        for row in event.buttons:
            for button in row:
                for index, client in enumerate(clients, start=1):
                    # Telethon এর event.click() বা button.click() ব্যবহার করে ক্লিকে অংশগ্রহণ
                    tasks.append(event.click(row.index(button)))
                    logging.info(f"🔘 [Account {index}] Clicking Giveaway Participate/Activate button!")

    await asyncio.gather(*tasks, return_exceptions=True)

async def handle_incoming_message(event):
    message_text = event.message.message or ""

    # কেস ১: প্রোমো কোড মেসেজ রিড ও এক্সট্র্যাক্ট করা (আপনার আগের ১০০% পারফেক্ট লজিক)
    if "NEW PROMO CODE" in message_text or "Code:" in message_text or "Code" in message_text:
        match = re.search(r'Code\s*[:\-]?\s*([A-Za-z0-9\-]{5,})', message_text, re.IGNORECASE)
        
        if match:
            extracted_code = match.group(1).strip()
            current_time = time.time()
            
            # SPAM PREVENTION & TIME-BASED EXPIRY SYSTEM (30 Min Lock)
            async with lock:
                expired_keys = [code for code, timestamp in processed_codes.items() if current_time - timestamp > CODE_EXPIRY_SECONDS]
                for code in expired_keys:
                    del processed_codes[code]

                if extracted_code in processed_codes:
                    return 

                processed_codes[extracted_code] = current_time

            logging.info(f"🚀 New Code Detected: {extracted_code}. Triggering all {len(clients)} accounts!")
            await broadcast_action(extracted_code, event)
            return

    # কেস ২: ডাইরেক্ট গিভঅ্যাওয়ে বাটন পোস্ট (যেমন: Giveaway, Press the button to join, Participate)
    if event.buttons or "Giveaway" in message_text or "Participate" in message_text:
        logging.info(f"🎉 New Giveaway Post Detected! Triggering participate buttons for all accounts...")
        await broadcast_action(None, event)

# ৪টি অ্যাকাউন্টেই ইভেন্ট হ্যান্ডলার যুক্ত করা
for client in clients:
    client.add_event_handler(handle_incoming_message, events.NewMessage())

def run_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def main_bot():
        print(f"🚀 Render Multi-Account Auto-Claimer Active with {len(clients)} Accounts...")
        if clients:
            await asyncio.gather(*(c.start() for c in clients))
            await asyncio.gather(*(c.run_until_disconnected() for c in clients))
        else:
            print("⚠️ No String Sessions found!")
        
    loop.run_until_complete(main_bot())

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    
