from asyncio import run
from contextlib import asynccontextmanager
from aioclock import AioClock
from tortoise import Tortoise
from config import PG_URL, APP_NAME
from groups.two_eden import group as two_eden
from modules.logger import Logger

# Подключения Redis
# db0 - для хранения индексов


@asynccontextmanager
async def lifespan(_: AioClock):
    await Tortoise.init(db_url=PG_URL, modules={'api': ['models']})
    await Logger(APP_NAME).success(msg="Планировщик запущен.", func_name="startup")
    yield _

app = AioClock(lifespan=lifespan)

# Подключаем группы тасков
app.include_group(two_eden)

if __name__ == '__main__':
    run(app.serve())
