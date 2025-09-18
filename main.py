import asyncio
import requests
import os
import json

from typing import TypedDict, Any, Mapping, Sequence

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")
WAIT_TIME = 10  # seconds
CHAT_FILE = "chat_ids.json"


def fetch_list():
    resp = requests.get(API_URL)
    data = resp.json()
    if data.get("success"):
        return data["data"]
    return None


class TokenInfo(TypedDict):
    tokenId: str
    name: str
    symbol: str
    price: str
    onlineTge: bool
    onlineAirdrop: bool


def _to_token_info(raw: Mapping[str, Any]) -> TokenInfo:
    return {
        "tokenId": str(raw.get("tokenId", "")),
        "name": str(raw.get("name", "")),
        "symbol": str(raw.get("symbol", "")),
        "price": str(raw.get("price", "")),  # cast to str just in case it's numeric
        "onlineTge": bool(raw.get("onlineTge", False)),
        "onlineAirdrop": bool(raw.get("onlineAirdrop", False)),
    }


# ---------- Chat ID persistence ----------

def load_all_chat_ids() -> list[int]:
    if not os.path.exists(CHAT_FILE):
        return []
    with open(CHAT_FILE, "r") as f:
        return json.load(f)


def save_chat_id(chat_id: int):
    chat_ids = load_all_chat_ids()
    if chat_id not in chat_ids:
        chat_ids.append(chat_id)
        with open(CHAT_FILE, "w") as f:
            json.dump(chat_ids, f)


# ---------- Bot monitor ----------

class MonitorClass:
    def __init__(self, bot_token: str):
        self.bot = Bot(bot_token)
        self.token_list = None

    async def compareLists(self, tokens) -> bool:
        old_ids = {t["tokenId"] for t in self.token_list}
        new_ids = {t["tokenId"] for t in tokens}
        return old_ids != new_ids

    async def findNewToken(self, tokens: Sequence[Mapping[str, Any]]) -> list[TokenInfo]:
        if not self.token_list:
            return []
        old_ids = {str(t.get("tokenId")) for t in self.token_list if "tokenId" in t}
        new_infos: list[TokenInfo] = []
        for t in tokens:
            tid = str(t.get("tokenId", ""))
            if tid and tid not in old_ids:
                new_infos.append(_to_token_info(t))
        return new_infos

    async def announce_bot(self, tokenInfo: TokenInfo):
        chat_ids = load_all_chat_ids()

        message = (
            f"🚀 *New Token Listed on Binance Alpha!*\n\n"
            f"**Name:** {tokenInfo['name']} ({tokenInfo['symbol']})\n"
            f"**Token ID:** `{tokenInfo['tokenId']}`\n"
            f"**Contract Address:** `{tokenInfo['contractAddress']}`\n"
            f"**Price:** {tokenInfo['price']}\n"
            f"**Listing Time:** {tokenInfo['listingTime']}\n"
            f"**TGE Live:** {'✅ Yes' if tokenInfo['onlineTge'] else '❌ No'}\n"
            f"**Airdrop Active:** {'🎁 Yes' if tokenInfo['onlineAirdrop'] else '—'}\n\n"
            f"Stay tuned for more updates!"
        )

        for chat_id in chat_ids:
            try:
                await self.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
            except Exception as e:
                print(f"Failed to send to {chat_id}: {e}")

    async def start_listen(self):
        while True:
            try:
                tokens = fetch_list()
                if tokens is None:
                    print("Something went wrong with Binance API")
                else:
                    print(f"Fetched {len(tokens)} tokens")
                    if self.token_list is None:
                        self.token_list = tokens
                    else:
                        isDifferent = await self.compareLists(tokens)
                        if isDifferent:
                            newTokens = await self.findNewToken(tokens)
                            for tokenInfo in newTokens:
                                await self.announce_bot(tokenInfo)
                        else:
                            print("the same list")
                        self.token_list = tokens

                await asyncio.sleep(WAIT_TIME)

            except Exception as e:
                print("A strange error happened:", e)


# ---------- Telegram handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    save_chat_id(chat_id)
    await update.message.reply_text("👋 You are now subscribed to token updates!")


def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL, start))  # save any chat that messages the bot
    return app


async def monitor_tokens():
    monitor_bot = MonitorClass(BOT_TOKEN)
    await monitor_bot.start_listen()


async def main():
    # create Telegram app
    app = run_bot()

    # initialize Telegram app
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # run Binance monitor in parallel
    monitor_task = asyncio.create_task(monitor_tokens())

    try:
        await monitor_task
    finally:
        # graceful shutdown
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
