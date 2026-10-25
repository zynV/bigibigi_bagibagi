"""Run BEFORE deployment to discover Telegram user IDs and chat IDs.

Only reacts to /id; stop this helper before starting the normal bot.
Don't paste BOT_TOKEN into Telegram chats or issue logs.
"""
from __future__ import annotations

import asyncio
import os
from aiogram import Bot
from dotenv import load_dotenv


async def main():
    load_dotenv()
    bot = Bot(os.environ["BOT_TOKEN"])
    print("Send /id in the private group from each family account. Press Ctrl+C to finish.", flush=True)
    offset = None
    try:
        while True:
            updates = await bot.get_updates(offset=offset, timeout=25,
                                            allowed_updates=["message"])
            for update in updates:
                offset = update.update_id + 1
                msg = update.message
                if msg and msg.text and msg.text.split()[0].split("@")[0] == "/id":
                    print(f"GROUP_CHAT_ID={msg.chat.id}  USER_ID={msg.from_user.id}", flush=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
