import logging
import asyncio
import os
import threading
from flask import Flask
from telethon import TelegramClient
from telethon.sessions import StringSession

# Configure Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 39097979))
API_HASH = os.environ.get("API_HASH", "f23c7abd6d08744a52da529dd566f1f9")

# Session keys loading (4 accounts)
session_keys = ["STRING_SESSION_1", "STRING_SESSION_2", "STRING_SESSION_3", "STRING_SESSION_4"]
clients = []
client_session_names = []

for key in session_keys:
    session_val = os.environ.get(key, "")
    if session_val:
        clients.append(TelegramClient(StringSession(session_val), API_ID, API_HASH))
        client_session_names.append(key)

app = Flask(__name__)

@app.route('/')
def home():
    return f"DC Checker is Active with {len(clients)} accounts!"

async def check_dcs():
    if not clients:
        logging.info("No accounts found in environment variables!")
        return
    
    # সব অ্যাকাউন্ট স্টার্ট করা হচ্ছে ডিসি চেক করার জন্য
    await asyncio.gather(*(c.start() for c in clients))
    
    logging.info("==========================================")
    logging.info("          TELEGRAM DC CHECK RESULTS       ")
    logging.info("==========================================")
    
    for client, session_name in zip(clients, client_session_names):
        try:
            dc_id = getattr(client.session, 'dc_id', 'unknown')
            # ডিসি লোকেশন ম্যাপ: DC1/DC3 = Miami, DC2/DC4 = Amsterdam, DC5 = Singapore
            location = "Unknown"
            if dc_id in [1, 3]:
                location = "Miami (USA)"
            elif dc_id in [2, 4]:
                location = "Amsterdam (Netherlands)"
            elif dc_id == 5:
                location = "Singapore"
                
            logging.info(f"🔑 {session_name} -> Telegram DC: {dc_id} [{location}]")
        except Exception as e:
            logging.error(f"Could not fetch DC for {session_name}: {e}")
            
    logging.info("==========================================")

def run_checker():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_dcs())

if __name__ == '__main__':
    # ব্যাকগ্রাউন্ডে ডিসি চেক রান হবে
    threading.Thread(target=run_checker, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
*(c.run_until_disconnected() for c in clients))

    loop.run_until_complete(main_bot())

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
                            
