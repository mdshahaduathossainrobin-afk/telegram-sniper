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

# Session keys loading
session_keys = ["STRING_SESSION_1", "STRING_SESSION_2", "STRING_SESSION_3", "STRING_SESSION_4"]
clients = []

for key in session_keys:
    session_val = os.environ.get(key, "")
    if session_val:
        clients.append(TelegramClient(StringSession(session_val), API_ID, API_HASH))

BOT_USERNAME = 'klyxx_bot'

# Duplicate prevention & Memory lock
processed_codes = {}
processed_giveaways = set()
lock = asyncio.Lock()

CODE_EXPIRY_SECONDS = 1800

app = Flask(__name__)

@app.route('/')
def home():
    return f"Telegram Multi-Claimer is Active with {len(clients)} accounts!"

async def broadcast_action(extracted_code, event):
    tasks = []
    
    # 1. Promo Code Direct Bot-e Send Kora
    if extracted_code:
        for index, client in enumerate(clients, start=1):
            tasks.append(client.send_message(BOT_USERNAME, extracted_code))
            logging.info(f"⚡ [Account {index}] Instant Code '{extracted_code}' sending...")

    # 2. STRICT PARTICIPATE BUTTON AUTO-CLICK
    if event and event.buttons:
        giveaway_key = f"{event.chat_id}_{event.id}"
        if giveaway_key not in processed_giveaways:
            for row in event.buttons:
                for button in row:
                    btn_text = (button.text or "").lower()
                    # Strictly check only for 'participate'
                    if "participate" in btn_text:
                        processed_giveaways.add(giveaway_key)
                        for index, client in enumerate(clients, start=1):
                            tasks.append(button.click())
                            logging.info(f"🔘 [Account {index}] Auto-Clicked Participate Button: {button.text}")

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def handle_incoming_message(event):
    # Bot Auto-Verification (Members Only handling)
    if event.sender_id and event.chat and getattr(event.chat, 'username', '') == BOT_USERNAME:
        msg_text = event.message.message or ""
        if "Members only" in msg_text or "subscribed" in msg_text:
            if event.buttons:
                for row in event.buttons:
                    for button in row:
                        if "subscribed" in (button.text or "").lower():
                            await button.click()
                            logging.info("✅ Auto-clicked 'I've subscribed' button in bot!")
            return

    message_text = event.message.message or ""
    extracted_code = None

    # Code Extraction
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
                    extracted_code = candidate_code
                    logging.info(f"🚀 New Code Detected: {extracted_code}")

    # Process Code and/or Participate Button
    await broadcast_action(extracted_code, event)

# NewMessage & MessageEdited Duto Event-i Catch Korbe
for client in clients:
    client.add_event_handler(handle_incoming_message, events.NewMessage())
    client.add_event_handler(handle_incoming_message, events.MessageEdited())

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
