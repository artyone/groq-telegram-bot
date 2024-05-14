import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, html, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.filters.command import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils import markdown
from environs import Env
from groq import Groq

env = Env()
env.read_env()

bot_token = env.str("BOT_TOKEN")
groq_token = env.str("GROQ_TOKEN")
admin_id = env.int("ADMIN_ID")


groq_client = Groq(api_key=groq_token)
telegram_bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

context = {"role": "system",
           "content": "Always answer in Russian. Постоянно отвечай на русском."}

users = {
    admin_id:
    {
        "context": context,
        "messages": []
    }
}

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()
storage = MemoryStorage()

class Settings(StatesGroup):
    waiting_for_settings = State()


def log_to_txt(message):
    if not os.path.exists("logs.txt"):
        with open("logs.txt", "w", encoding="utf-8") as f:
            print(message, file=f)
    else:
        with open("logs.txt", "a", encoding="utf-8") as f:
            print(message, file=f)


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    print(message.chat.id)
    if message.from_user.id not in users:
        users[message.from_user.id] = {
            "context": context,
            "messages": []
        }
        await telegram_bot.send_message(chat_id=admin_id, text=f'{message.from_user.id} {message.from_user.username} Присоединился к боту!')
    await state.clear()
    await message.answer("Привет! Это самый лучший бот! Мяу :3")


@dp.message(~F.from_user.id.in_(users))
async def register_error(message: types.Message):
    await message.reply("Пожалуйста, нажмите /start повторно")


@dp.message(Command('reset'), F.from_user.id.in_(users))
async def cmd_clear(message: types.Message, state: FSMContext):
    users[message.from_user.id]['messages'] = []
    users[message.from_user.id]['context'] = context
    await state.clear()
    await message.reply("Настройки контекста сброшены!")


@dp.message(Command('new'), F.from_user.id.in_(users))
async def new(message: types.Message, state: FSMContext):
    users[message.from_user.id]['messages'] = []
    await state.clear()
    await message.reply("Новый диалог начался!")


@dp.message(Command('current'), F.from_user.id.in_(users))
async def current_context(message: types.Message, state: FSMContext):
    await state.clear()
    await message.reply(f"Текущий контекст: \n{html.code(users[message.from_user.id]['context']['content'])}")


@dp.message(Command('set'), F.from_user.id.in_(users))
async def set_command(message: types.Message, state: FSMContext):
    last_context = users[message.from_user.id]['context']['content']
    await message.reply("Готов принять настройку контекста. Пожалуйста, отправьте мне сообщение с настройками.")
    await message.answer(f"Последний контекст: {html.code(last_context)}")
    await state.set_state(Settings.waiting_for_settings)


@dp.message(StateFilter(Settings.waiting_for_settings))
async def process_settings(message: types.Message, state: FSMContext):
    users[message.from_user.id]['context'] = {
        "role": 'system', "content": message.text}
    users[message.from_user.id]['messages'] = []
    await state.clear()
    await message.reply("Настройки приняты!")


@dp.message(F.text, F.from_user.id.in_(users))
async def grok_message(message: types.Message):
    log_to_txt(
        f'--> {message.from_user.id} {message.from_user.username} {message.date.isoformat()}: {message.text}')
    # print(
    #     f'--> {message.from_user.id} {message.date.isoformat()}: {message.text}')
    context = [users[message.from_user.id]['context']]
    messages = users[message.from_user.id]['messages']
    if len(messages) > 20:
        messages = messages[-20:]
    messages.append({"role": 'user', "content": message.text})
    command = context + messages
    response = groq_client.chat.completions.create(
        model='llama3-70b-8192', messages=command, temperature=0.1)
    messages.append(
        {"role": 'assistant', "content": response.choices[0].message.content})
    users[message.from_user.id]['messages'] = messages
    log_to_txt(f'<-- {response.choices[0].message.content}')
    # print(f'<-- {response.choices[0].message.content}')
    await message.answer(response.choices[0].message.content, parse_mode=ParseMode.MARKDOWN)


@dp.message(F.text)
async def handler_message(message: types.Message):
    await message.reply('Вам доступ не разрешён. Наберите /start. По вопросам: @artyone')


async def set_main_menu(bot: Bot):
    main_menu_commands = [
        types.BotCommand(command='/start',
                         description='Старт'),
        types.BotCommand(command='/new',
                         description='Новый диалог'),
        types.BotCommand(command='/current',
                         description='Показать текущий контекст'),
        types.BotCommand(command='/set',
                         description='Задать свой контекст'),
        types.BotCommand(command='/reset',
                         description='Сбросить контекст на начальное состояние'),
    ]
    await bot.set_my_commands(main_menu_commands)

# Запуск процесса поллинга новых апдейтов
async def main():
    # Диспетчер
    # await bot.delete_webhook(drop_pending_updates=True)
    dp.startup.register(set_main_menu)
    await dp.start_polling(telegram_bot)

if __name__ == "__main__":
    asyncio.run(main())
