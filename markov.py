import random
import logging
import os

from dotenv import load_dotenv
import aiogram.utils.markdown as md
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import json
from asyncio import sleep

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN must be set in .env")

# Initialize the bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# Create a dictionary to store Markov chains for each chat
markov_chain = {}

# JSON file names for saving and loading Markov chains
CHAIN_FILE = "markov_chain.json"
STATS_FILE = "stats.json"

# Set the number of words in the Markov chain
MARKOV_ORDER = 2

# Counters for statistics
total_messages = 0
generated_messages = 0

# Function to save the Markov chain to a JSON file
async def save_markov_chain(dispatcher):
    logging.info('Saving Markov chain...')
    # Convert tuple keys to strings for JSON serialization
    serializable_chain = {str(key): value for key, value in markov_chain.items()}
    with open(CHAIN_FILE, 'w') as file:
        json.dump(serializable_chain, file, indent=4, ensure_ascii=False)
    with open(STATS_FILE, 'w') as file:
        stats = {
            'total_msgs': total_messages,
            'gen_msgs': generated_messages
        }
        json.dump(stats, file, indent=4, ensure_ascii=False)


# Function to load the Markov chain from a JSON file and convert keys back to tuples
def load_markov_chain():
    logging.info('Loading Markov chain...')
    try:
        with open(CHAIN_FILE, 'r') as file:
            serialized_chain = json.load(file)
            # Convert string keys back to tuples
            markov_chain = {eval(key): value for key, value in serialized_chain.items()}
        logging.info('Chain file loaded.')
    except FileNotFoundError:
        logging.info('Chain file not found.')
        markov_chain = {}
    try:
        with open(STATS_FILE, 'r') as file:
            stats = json.load(file)
            # Convert string keys back to tuples
            total_messages = stats['total_msgs']
            generated_messages = stats['gen_msgs']
        logging.info('Stats file loaded.')
    except FileNotFoundError:
        total_messages = 0
        generated_messages = 0
        logging.info('Stats file not found.')
    return markov_chain, total_messages, generated_messages


# Function to generate text using a Markov chain
def generate_markov_text(chain, max_words=50):
    current_word = random.choice(list(chain.keys()))
    text = list(current_word)

    for _ in range(max_words):
        if tuple(text[-MARKOV_ORDER:]) in chain:
            next_word = random.choice(chain[tuple(text[-MARKOV_ORDER:])])
            text.append(next_word)
        else:
            break

    return ' '.join(text)

# Handler for the /мудрость command
@dp.message_handler(text=['мудрость'])
async def wisdom(message: types.Message):
    global total_messages
    global generated_messages
    total_words = len(markov_chain)
    chain_size = sum(len(values) for values in markov_chain.values())
    
    stats_message = (
        f"Total Messages: {total_messages}\n"
        f"Generated Messages: {generated_messages}\n"
        f"Total Combinations in Vocab: {total_words}\n"
        f"Markov Chain Size: {chain_size}\n"
        f"Variability coefficient: {chain_size/total_words:.2f}"
    )
    await message.reply(stats_message)
    
# Handler for every message in chat
@dp.message_handler()
async def on_message(message: types.Message):
    logging.info('Logged message...')
    global total_messages
    total_messages += 1

    chat_id = message.chat.id

    # Update the Markov chain for the chat
    text = message.text.split()
    text.append("")  # Add an empty string to the end
    for i in range(len(text) - MARKOV_ORDER):
        key = tuple(text[i:i+MARKOV_ORDER])
        if key not in markov_chain:
            markov_chain[key] = []
        if text[i + MARKOV_ORDER] not in markov_chain[key]:
            markov_chain[key].append(text[i + MARKOV_ORDER])
    
    # Occasionally generate and send Markov-generated text
    if not (('@mudrets_robot' in message.text) or (message.chat.type == 'private') or (message.text == 'мудрец')):
        if random.random() > 0.1:
            return 
        await sleep(random.randint(5, 20))
    logging.info('Called...')
    global generated_messages
    generated_messages += 1
    generated_text = generate_markov_text(markov_chain, 100)
    await message.reply(generated_text)
    await save_markov_chain(dp)



if __name__ == '__main__':
    markov_chain, total_messages, generated_messages = load_markov_chain()  # Load Markov chain on startup
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, on_shutdown=save_markov_chain)  # Save Markov chain on shutdown
