import asyncio
import re
import os
import json
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession

routes = web.RouteTableDef()

client = None
BOT = "OSINT_INFO_FATHER_BOT"

HISTORY_FILE = "history.json"


# ---------------- JSON ---------------- #

def j(data):
    return web.json_response(data)


# ---------------- HISTORY ---------------- #

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []


def save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------- PARSER ---------------- #

def parse_leak(text):

    telephones = re.findall(r'Telephone:\s*(\d+)', text)
    addresses = re.findall(r'Adres:\s*(.+)', text)
    docs = re.findall(r'Document number:\s*(\d+)', text)
    names = re.findall(r'Full name:\s*(.+)', text)
    fathers = re.findall(r'The name of the father:\s*(.+)', text)
    regions = re.findall(r'Region:\s*(.+)', text)

    return {
        "telephones": list(set(telephones)),
        "addresses": list(set(addresses)),
        "document_numbers": docs,
        "full_names": names,
        "father_names": fathers,
        "regions": regions
    }


# ---------------- CONNECTION ---------------- #

async def ensure_connected():
    if not client.is_connected():
        await client.connect()


# ---------------- FETCH BOT DATA ---------------- #

async def fetch_all_pages(number):

    await ensure_connected()

    all_messages = []
    last_id = 0

    await client.send_message(BOT, number)
    await asyncio.sleep(5)

    while True:

        msgs = await client.get_messages(BOT, limit=10)

        new_msgs = [m for m in msgs if m.id > last_id and m.text]

        if not new_msgs:
            break

        new_msgs.reverse()

        for m in new_msgs:
            all_messages.append(m.text)
            last_id = m.id

        message = new_msgs[-1]

        # NEXT BUTTON
        if message.buttons:

            next_btn = None

            for row in message.buttons:
                for btn in row:
                    if "➡" in btn.text or ">" in btn.text:
                        next_btn = btn.text
                        break

            if next_btn:
                await message.click(text=next_btn)
                await asyncio.sleep(4)
                continue

        break

    full_text = "\n".join(all_messages)

    return all_messages, full_text


# ---------------- LOGIN API ---------------- #

@routes.get("/login/start/{api_id}/{api_hash}/{session}")
async def login_start(request):
    global client

    try:
        api_id = int(request.match_info["api_id"])
        api_hash = request.match_info["api_hash"]
        session_string = request.match_info["session"]

        client = TelegramClient(
            StringSession(session_string),
            api_id,
            api_hash
        )

        await client.start()

        # Render sleep fix
        asyncio.create_task(client.run_until_disconnected())

        me = await client.get_me()

        return j({
            "status": True,
            "user": me.first_name
        })

    except Exception as e:
        return j({"status": False, "error": str(e)})


# ---------------- NUMBER API ---------------- #

@routes.get("/number")
async def number_info(request):
    global client

    try:
        if client is None:
            return j({"status": False, "error": "login required"})

        number = request.query.get("info")

        if not number:
            return j({"status": False, "error": "number missing"})

        number = "91" + number

        messages, text = await fetch_all_pages(number)

        if not text:
            return j({"status": True, "data": []})

        parsed = parse_leak(text)

        history = load_history()

        history.append({
            "number": number,
            "messages": messages,
            "parsed": parsed
        })

        save_history(history)

        return j({
            "status": True,
            "messages": messages,
            "parsed": parsed
        })

    except Exception as e:
        return j({"status": False, "error": str(e)})


# ---------------- HISTORY API ---------------- #

@routes.get("/")
async def home(request):

    history = load_history()

    return j({
        "status": True,
        "history": history[::-1]
    })


# ---------------- RUN APP ---------------- #

app = web.Application()
app.add_routes(routes)

web.run_app(app, port=int(os.environ.get("PORT", 8080)))
