import logging
import asyncio
import os
import re
import threading
import time
import random
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Configure Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 39097979))
API_HASH = os.environ.get("API_HASH", "f23c7abd6d08744a52da529dd566f1f9")

# Session keys loading (4 accounts)
session_keys = ["STRING_SESSION_1", "STRING_SESSION_2", "STRING_SESSION_3", "STRING_SESSION_4"]
clients = []

for key in session_keys:
    session_val = os.environ.get(key, "")
    if session_val:
        clients.append(TelegramClient(StringSession(session_val), API_ID, API_HASH))

BOT_USERNAME = 'klyxx_bot'

# Target Channel Configuration (যে চ্যানেল থেকে বট মেসেজ রিড করবে)
# এখানে আপনার কাঙ্ক্ষিত চ্যানেলের ইউজারনেম বসিয়ে দেবেন (যেমন: 'klyx_news')
TARGET_CHANNEL_USERNAME = 'klyx_news'

# Duplicate prevention & Memory lock
processed_codes = {}
processed_giveaways = set()
lock = asyncio.Lock()

CODE_EXPIRY_SECONDS = 1800

app = Flask(__name__)

@app.route('/')
def home():
    return f"Telegram Multi-Claimer is Active with {len(clients)} accounts!"

async def click_participate_button(event):
    """
    চ্যানেল বা গ্রুপে আসা গিভঅ্যাওয়ে বাটন ২০-৩০ সেকেন্ড পর ক্লিক করার নিরাপদ লজিক
    """
    giveaway_key = f"{event.chat_id}_{event.id}"
    
    if giveaway_key in processed_giveaways:
        return

    button_found = False
    if event.reply_markup:
        try:
            for row_idx, row in enumerate(event.reply_markup.rows):
                for col_idx, button in enumerate(row.buttons):
                    btn_text = getattr(button, 'text', '') or ""
                    # গিভঅ্যাওয়ে বা পার্টিসিপেট সংক্রান্ত বাটনগুলো ফিল্টার করা
                    if any(keyword in btn_text.lower() for keyword in ["participate", "join", "giveaway", "enter"]):
                        button_found = True
                        processed_giveaways.add(giveaway_key)
                        
                        async def delayed_click():
                            wait_time = random.uniform(20.0, 30.0)
                            logging.info(f"⏳ Giveaway detected in channel! Waiting {wait_time:.1f} seconds before clicking...")
                            await asyncio.sleep(wait_time)
                            
                            for idx, client in enumerate(clients, start=1):
                                try:
                                    await asyncio.sleep(0.1 * idx)
                                    msg_obj = await client.get_messages(event.chat_id, ids=event.id)
                                    if msg_obj:
                                        await msg_obj.click(i=row_idx, j=col_idx)
                                        logging.info(f"🔘 [Account {idx}] Successfully Clicked Giveaway Button after delay!")
                                except Exception as client_err:
                                    logging.error(f"Account {idx} click error: {client_err}")

                        asyncio.create_task(delayed_click())
                        break
                if button_found:
                    break
        except Exception as e:
            logging.error(f"Giveaway Handler Error: {e}")

async def handle_incoming_message(event):
    # ১. প্রাইভেট চ্যাট বা বটের চ্যাট হলে ইগনোর করবে
    if event.is_private:
        return
    
    if event.chat and getattr(event.chat, 'username', '') == BOT_USERNAME:
        return

    # ২. [NEW] শুধুমাত্র নির্দিষ্ট চ্যানেল (TARGET_CHANNEL_USERNAME) থেকে আসা মেসেজই রিড করবে, বাকি সব ইগনোর করবে
    try:
        chat = await event.get_chat()
        chat_username = getattr(chat, 'username', None)
        if not chat_username or chat_username.lower() != TARGET_CHANNEL_USERNAME.lower():
            return
    except Exception:
        return

    # ৩. চ্যানেল বা গ্রুপে গিভঅ্যাওয়ে বাটন থাকলে ডিলে ক্লিকের জন্য পাঠাবে
    if event.reply_markup:
        await click_participate_button(event)

    # ৪. প্রমো কোড এক্সট্রাকশন ও সুপার-ফাস্ট সেন্ড করার লজিক
    message_text = event.message.message or ""
    if "NEW PROMO CODE" in message_text or "Code:" in message_text or "Code" in message_text:
        match = re.search(r'Code\s*[:\-]?\s*([A-Za-z0-9\-]{5,})', message_text, re.IGNORECASE)
        if match:
            candidate_code = match.group(1).strip()
            current_time = time.time()
            
            async with lock:
                expired_keys = [c for c, ts in processed_codes.items() if current_time - ts > CODE_EXPIRY_SECONDS]
                for c in expired_keys:
                    del processed_codes[c]

                if candidate_code not in processed_codes:
                    processed_codes[candidate_code] = current_time
                    
                    tasks = [client.send_message(BOT_USERNAME, candidate_code) for client in clients]
                    logging.info(f"🚀 Direct Promo Code Sent: {candidate_code}")
                    await asyncio.gather(*tasks, return_exceptions=True)

# Event Handlers (NewMessage + MessageEdited)
for client in clients:
    client.add_event_handler(handle_incoming_message, events.NewMessage())
    client.add_event_handler(handle_incoming_message, events.MessageEdited())

def run_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def main_bot():
        print(f"🚀 Telethon Auto-Claimer Active with {len(clients)} Accounts...")
        if clients:
            await asyncio.gather(*(c.start() for c in clients))
            await asyncio.gather(*(c.run_until_disconnected() for c in clients))
        
    loop.run_until_complete(main_bot())

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    
