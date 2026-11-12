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

# Session keys loading (4 accounts, some services have 3)
session_keys = ["STRING_SESSION_1", "STRING_SESSION_2", "STRING_SESSION_3", "STRING_SESSION_4"]
clients = []
client_session_names = []

for key in session_keys:
    session_val = os.environ.get(key, "")
    if session_val:
        clients.append(TelegramClient(StringSession(session_val), API_ID, API_HASH))
        client_session_names.append(key)

BOT_USERNAME = 'klyxx_bot'

# Target Channel Configuration
TARGET_CHANNEL_USERNAME = 'klyx_news'

# --- FAST PATH: precompiled regex, cached entities ---
# Original code recompiled the regex and did 3 substring checks per message.
# Precompile once, and extract ALL codes in a message (original only took the first).
CODE_RE = re.compile(r'Code\s*[:\-]?\s*([A-Za-z0-9\-]{5,})', re.IGNORECASE)
GIVEAWAY_KEYWORDS = ("participate", "join", "giveaway", "enter")

# Duplicate prevention
# processed_codes: code -> timestamp. Cleanup only every 60s, NOT on every
# message. The original scanned the whole dict on every single message.
processed_codes = {}
processed_giveaways = set()
lock = asyncio.Lock()
_last_cleanup = [0.0]

CODE_EXPIRY_SECONDS = 86400

# Cached entities - resolved once at startup, never per-message.
# Original: await event.get_chat() on EVERY message + send_message(BOT_USERNAME)
# resolved the bot username on EVERY send. Both are extra Telegram API
# round-trips (100-300ms each) before the code is even sent.
target_channel_id = None
bot_peers = [None] * len(clients)

app = Flask(__name__)

@app.route('/')
def home():
    return f"Telegram Multi-Claimer is Active with {len(clients)} accounts!"


async def click_participate_button(event):
    """
    Giveaway button logic - UNCHANGED timing.
    20-30 second delay is kept exactly as the user asked, because
    giveaways can be joined within 2-3 hours.
    This is now NEVER awaited on the promo-code path - it runs as a
    background task so it cannot slow down a promo code.
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
                    if any(keyword in btn_text.lower() for keyword in GIVEAWAY_KEYWORDS):
                        button_found = True
                        processed_giveaways.add(giveaway_key)

                        async def delayed_click():
                            wait_time = random.uniform(20.0, 30.0)
                            logging.info(f"Giveaway detected in channel! Waiting {wait_time:.1f} seconds before clicking...")
                            await asyncio.sleep(wait_time)

                            for idx, (client, session_name) in enumerate(zip(clients, client_session_names), start=1):
                                try:
                                    await asyncio.sleep(0.1 * idx)
                                    msg_obj = await client.get_messages(event.chat_id, ids=event.id)
                                    if msg_obj:
                                        await msg_obj.click(i=row_idx, j=col_idx)
                                        logging.info(f"[{session_name}] Successfully Clicked Giveaway Button after delay!")
                                except Exception as client_err:
                                    logging.error(f"{session_name} click error: {client_err}")

                        asyncio.create_task(delayed_click())
                        break
                if button_found:
                    break
        except Exception as e:
            logging.error(f"Giveaway Handler Error: {e}")


async def send_code_fast(code):
    """Send one code from all accounts in parallel, using cached bot peer."""
    tasks = []
    for client, peer in zip(clients, bot_peers):
        tasks.append(client.send_message(peer or BOT_USERNAME, code))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for session_name, res in zip(client_session_names, results):
        if isinstance(res, Exception):
            logging.error(f"[{session_name}] Promo send error for {code}: {res}")
        else:
            logging.info(f"[{session_name}] Promo Code Sent: {code}")


async def claim_code(code):
    """Dedup under a tiny lock, then send OUTSIDE the lock.

    Original bug: asyncio.gather(send...) was INSIDE `async with lock:`,
    so while one code was being sent (network I/O), every other code
    waited behind the lock. With a burst of 120-200 codes, that queues
    everything and you get 'already claimed'.
    """
    now = time.time()
    async with lock:
        # Cleanup at most once per 60 seconds, not per message.
        if now - _last_cleanup[0] > 60:
            expired = [c for c, ts in processed_codes.items()
                       if now - ts > CODE_EXPIRY_SECONDS]
            for c in expired:
                del processed_codes[c]
            _last_cleanup[0] = now

        if code in processed_codes:
            return
        processed_codes[code] = now

    # Lock is released here - sends run in parallel with other codes.
    await send_code_fast(code)


async def handle_incoming_message(event):
    # Fast channel check - NO await event.get_chat() anymore.
    # The handler is already filtered to TARGET_CHANNEL_USERNAME below,
    # and target_channel_id is cached at startup. If we know the id,
    # compare it directly (pure integer compare, ~0ms).
    if target_channel_id is not None and event.chat_id != target_channel_id:
        return
    if event.is_private:
        return
    if event.chat and getattr(event.chat, 'username', '') == BOT_USERNAME:
        return

    # Giveaway: fire-and-forget, NEVER await it here.
    # Original code did `await click_participate_button(event)` BEFORE
    # promo-code extraction, delaying the code path.
    if event.reply_markup:
        asyncio.create_task(click_participate_button(event))

    # Fast promo-code path - first thing after the giveaway task is queued.
    message_text = event.raw_text or (event.message.message if event.message else "") or ""
    if not message_text:
        return

    # Cheap pre-check: if there is no "code" in any case, return immediately.
    # Avoids regex on most non-promo messages.
    if "Code" not in message_text and "CODE" not in message_text and "code" not in message_text:
        return

    # Extract ALL codes in the message, not just the first one.
    # If the channel posts 120 / 150 / 200 codes in one burst / one message,
    # the original only claimed the first and dropped the rest.
    codes = CODE_RE.findall(message_text)
    if not codes:
        return

    # Fire each code as its own task - do not await them serially here,
    # so the handler returns instantly and the next message can be processed.
    for candidate_code in codes:
        candidate_code = candidate_code.strip()
        if candidate_code:
            asyncio.create_task(claim_code(candidate_code))


async def resolve_entities():
    """Resolve channel id + bot peer once at startup."""
    global target_channel_id
    if not clients:
        return
    try:
        entity = await clients[0].get_entity(TARGET_CHANNEL_USERNAME)
        target_channel_id = entity.id
        logging.info(f"Target channel id cached: {target_channel_id}")
    except Exception as e:
        logging.warning(f"Could not cache target channel id, will rely on chats filter: {e}")

    # Log each account's Telegram DC, named by its STRING_SESSION key -
    # so you can tell exactly which session / account it is.
    # DC1/DC3 = Miami, DC2/DC4 = Amsterdam, DC5 = Singapore.
    # DC2/DC4 accounts -> use Render Frankfurt. DC5 accounts -> use Render Singapore.
    # DC1/DC3 accounts -> use Render Virginia / Ohio.
    for client, session_name in zip(clients, client_session_names):
        try:
            dc_id = getattr(client.session, 'dc_id', 'unknown')
            logging.info(f"{session_name} Telegram DC: {dc_id} (DC1/DC3=Miami, DC2/DC4=Amsterdam, DC5=Singapore)")
        except Exception:
            pass

    for i, client in enumerate(clients):
        try:
            bot_peers[i] = await client.get_input_entity(BOT_USERNAME)
        except Exception as e:
            session_name = client_session_names[i] if i < len(client_session_names) else f"Account {i+1}"
            logging.warning(f"Could not cache bot peer for {session_name}: {e}")
            bot_peers[i] = BOT_USERNAME


# --- KEY CHANGE: only ONE listener client ---
# Original: all 4 clients registered the same handler, so the same message
# was processed 4 times, each doing get_chat() + regex + lock contention.
# Now: only clients[0] listens. The other 3 are send-only.
# That cuts 4x duplicate work on the hot path.
if clients:
    primary = clients[0]
    primary.add_event_handler(handle_incoming_message, events.NewMessage(chats=TARGET_CHANNEL_USERNAME))
    primary.add_event_handler(handle_incoming_message, events.MessageEdited(chats=TARGET_CHANNEL_USERNAME))


def run_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def main_bot():
        print(f"Telethon Auto-Claimer Active with {len(clients)} Accounts...")
        if clients:
            await asyncio.gather(*(c.start() for c in clients))
            await resolve_entities()
            await asyncio.gather(*(c.run_until_disconnected() for c in clients))

    loop.run_until_complete(main_bot())

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
                            
