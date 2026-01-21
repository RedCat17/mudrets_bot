import random
import logging
import asyncio
import os

from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import List, Tuple, Optional, AsyncGenerator
from sqlalchemy import Column, String, Integer, func, select, update
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

# Configuration
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN must be set in .env")
REPLY_CHANCE = os.getenv("REPLY_CHANCE")
if not REPLY_CHANCE:
    raise RuntimeError("REPLY_CHANCE must be set in .env")
MARKOV_ORDER = 2
MAX_WORDS = 100
DATABASE_URL = "sqlite+aiosqlite:///markov_chain.db"
SAVE_INTERVAL = 300

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

Base = declarative_base()

# SQLAlchemy Models
class Chain(Base):
    __tablename__ = "chain"
    key = Column(String, primary_key=True)
    next_words = Column(String)

class Stat(Base):
    __tablename__ = "stats"
    key = Column(String, primary_key=True)
    value = Column(Integer)

# Async engine and session
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Bot setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")

async def update_stat(key: str, value: int) -> None:
    async with get_session() as session:
        stmt = (
            update(Stat)
            .where(Stat.key == key)
            .values(value=value)
            .execution_options(synchronize_session="fetch")
        )
        await session.execute(stmt)

async def get_stat(key: str) -> int:
    async with get_session() as session:
        result = await session.execute(select(Stat.value).where(Stat.key == key))
        return result.scalar() or 0

async def build_markov_chain(words: List[str]) -> None:
    words = words + [""]
    async with get_session() as session:
        for i in range(len(words) - MARKOV_ORDER):
            key = tuple(words[i:i + MARKOV_ORDER])
            next_word = words[i + MARKOV_ORDER]
            key_str = str(key)

            # Get or create chain entry
            chain_entry = await session.get(Chain, key_str)
            if chain_entry:
                next_words = eval(chain_entry.next_words)
                if next_word not in next_words:
                    next_words.append(next_word)
                    chain_entry.next_words = str(next_words)
            else:
                session.add(Chain(key=key_str, next_words=str([next_word])))

async def get_random_key() -> Tuple[str, ...]:
    async with get_session() as session:
        result = await session.execute(
            select(Chain.key).order_by(func.random()).limit(1)
        )
        key = result.scalar()
        return eval(key) if key else ("start", "here")

async def generate_text(max_words: int = MAX_WORDS) -> str:
    async with get_session() as session:
        current_key = await get_random_key()
        result = list(current_key)

        for _ in range(max_words):
            key_str = str(tuple(result[-MARKOV_ORDER:]))
            chain_entry = await session.get(Chain, key_str)
            
            if not chain_entry or not chain_entry.next_words:
                break

            next_words = eval(chain_entry.next_words)
            next_word = random.choice(next_words)
            result.append(next_word)
            
            if not next_word:
                break

        return " ".join(result).strip()

@dp.message(Command("wisdom", "мудрость"))
async def wisdom_command(message: Message) -> None:
    total_messages = await get_stat("total_messages")
    generated_messages = await get_stat("generated_messages")
    
    async with get_session() as session:
        chain_count = await session.scalar(select(func.count(Chain.key)))
        chain_size = await session.scalar(
            select(func.sum(
                func.length(Chain.next_words) - 
                func.length(func.replace(Chain.next_words, ',', '')) + 1
            ))
        )

    variability = chain_size / chain_count if chain_count > 0 else 0
    stats_message = (
        f"<b>Total Messages:</b> {total_messages}\n"
        f"<b>Generated Messages:</b> {generated_messages}\n"
        f"<b>Total Combinations:</b> {chain_count}\n"
        f"<b>Markov Chain Size:</b> {chain_size or 0}\n"
        f"<b>Variability:</b> {variability:.2f}"
    )
    await message.reply(stats_message)

@dp.message(F.text)
async def handle_message(message: Message) -> None:
    # Update message count
    total = await get_stat("total_messages") + 1
    await update_stat("total_messages", total)
    
    # Process message
    await build_markov_chain(message.text.split())

    # Check triggers
    trigger_conditions = (
        message.chat.type == 'private' or
        message.text.lower() == 'мудрец' or
        '@mudrets_robot' in message.text.lower()
    )

    if not trigger_conditions and random.random() > REPLY_CHANCE:
        return

    await asyncio.sleep(random.uniform(1, 3))
    generated_text = await generate_text()
    
    # Update generated count
    generated = await get_stat("generated_messages") + 1
    await update_stat("generated_messages", generated)
    
    await message.reply(generated_text)

async def periodic_save():
    while True:
        await asyncio.sleep(SAVE_INTERVAL)
        async with engine.begin() as conn:
            await conn.commit()
        logger.info("Database changes committed")

async def on_startup():
    await init_db()
    asyncio.create_task(periodic_save())
    logger.info("Bot started")

async def on_shutdown():
    await engine.dispose()
    logger.info("Bot stopped")

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")