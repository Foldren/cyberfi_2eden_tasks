from asyncio import run
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from httpx import AsyncClient
from openai import AsyncOpenAI
from redis.asyncio import Redis
from redisvl.index import AsyncSearchIndex
from components.pydantic_models import Connection, RedisConnection
from config import REDISVL_YAML_URL, AI_API_TOKEN, PROXY6NET_PROXIES, REDIS_URL, BOT_TOKEN


def init_conn() -> Connection:
    """
    Функция для создания индекса и подключений к redis, боту, ai.
    :return:
    """
    index: AsyncSearchIndex = AsyncSearchIndex.from_yaml(REDISVL_YAML_URL)
    # подключаемся к redis, берет REDIS_URL из env
    run(index.connect())
    # создаем индекс (по умолчанию не создает если есть, либо указать overwrite=True, если нужно пересоздать)
    run(index.create())

    # новые вопросы хранятся в бд 14
    conn = Connection(
        bot=Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)),
        ai_client=AsyncOpenAI(api_key=AI_API_TOKEN, http_client=AsyncClient(proxies=PROXY6NET_PROXIES)),
        rs=RedisConnection(questions=Redis.from_url(url=REDIS_URL, db=0, decode_responses=True), index=index)
    )

    return conn
