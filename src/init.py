from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from deep_translator import GoogleTranslator
from httpx import AsyncClient
from openai import AsyncOpenAI
from redis.asyncio import Redis
from redisvl.index import AsyncSearchIndex
from sentence_transformers import SentenceTransformer
from components.pydantic_models import Connection, RedisConnection
from components.tools import find_near_question
from config import REDISVL_YAML_URL, AI_API_TOKEN, PROXY6NET_PROXIES, REDIS_URL, BOT_TOKEN, SECRET_QS


async def init_conn() -> Connection:
    """
    Функция для создания индекса и подключений к redis, боту, ai.
    :return:
    """

    index: AsyncSearchIndex = AsyncSearchIndex.from_yaml(REDISVL_YAML_URL)
    model = SentenceTransformer('all-MiniLM-L6-v2')
    # подключаемся к redis, берет REDIS_URL из env
    await index.connect(redis_url=REDIS_URL)
    # создаем индекс, с проверкой на наличие (по умолчанию не создает если есть, либо указать overwrite=True, если нужно пересоздать)
    exist_index = await index.exists()

    if not exist_index:
        await index.create()

    # Проверяем наличие секретных вопросов в бд, если нет, добавляем
    vector, result = await find_near_question(model=model, index=index, question=SECRET_QS[0]["question"])

    if result is None:
        await index.load(SECRET_QS)

    # новые вопросы хранятся в бд 14
    conn = Connection(
        bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)),
        ai_client=AsyncOpenAI(api_key=AI_API_TOKEN, http_client=AsyncClient(proxies=PROXY6NET_PROXIES)),
        rs=RedisConnection(questions=Redis.from_url(url=REDIS_URL, db=0, decode_responses=True), index=index),
        model=model,  # Задаем Модель для ИИ
        gt_to_ru=GoogleTranslator(source='en', target='ru')  # Задаем Google Translator
    )

    return conn
