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

# 4-ti StringSession load kora হচ্ছে
session_keys = ["STRING_SESSION_1", "STRING_SESSION_2", "STRING_SESSION_3", "STRING_SESSION_4"]
clients = []

for key in session_keys:
    session_val = os.environ.get(key, "")
    if session_val:
        clients.append(TelegramClient(StringSession(session_val), API_ID, API_HASH))

BOT_USERNAME = 'klyxx_bot'

# Flask Web Server
app = Flask(__name__)

@app.route('/')
def home():
    return f"Telegram Multi-Claimer is Active with {len(clients)} accounts!"

async def process_account_action(client, message_text, buttons):
    try:
        # 1. PROMO CODE EXTRACTION
        if "NEW PROMO CODE" in message_text or "Code:" in message_text:
            match = re.search(r'Code\s*:\s*([A-Za-z0-9\-]{5,})', message_text, re.IGNORECASE)

            if match:
                extracted_code = match.group(1).strip()
                await client.send_message(BOT_USERNAME, extracted_code)
                logging.info(f"⚡ Instant Code '{extracted_code}' sent from an account!")
                return

        # 2. GIVEAWAY AUTO-PARTICIPATE
        if buttons:
            for i, row in enumerate(buttons):
                for j, button in enumerate(row):
                    button_text = getattr(button, 'text', '') or ''
                    
                    if "participate" in button_text.lower() or "join" in button_text.lower():
                        await client.click(i, j)
                        logging.info("🎉 Clicked 'Participate' button!")
                        return

                    target_url = getattr(button, 'url', None) or getattr(button.button, 'url', None)
                    if target_url and "start=" in target_url:
                        promo_payload = target_url.split("start=")[-1]
                        await client.send_message(BOT_USERNAME, f"/start {promo_payload}")
                        logging.info(f"⚡ Instant Fallback payload sent!")
                        return

    except Exception as e:
        logging.error(f"⚠️ Error processing account: {e}")

# Sob client-er jonno event handler set kora
for client in clients:
    @client.on(events.NewMessage())
    async def global_handler(event, current_client=client):
        message_text = event.message.message or ""
        buttons = event.message.buttons
        asyncio.create_task(process_account_action(current_client, message_text, buttons))

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
    
