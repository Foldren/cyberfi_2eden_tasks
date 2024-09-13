from asyncio import get_event_loop
import aiocron
from deep_translator import GoogleTranslator
from tortoise import run_async, Tortoise
from tortoise.exceptions import OperationalError
from ujson import loads
from components.enums import QuestionStatus, RewardTypeName
from components.pydantic_models import Connection
from config import APP_NAME, GPT_SYSTEM_MESSAGES
from config import PG_URL
from init import init_conn
from models import Question, Stats, Leader, Reward
from modules.logger import Logger

# Задаем подключения Redis, Google
conn = init_conn()
gt = GoogleTranslator(source='en', target='ru')


@aiocron.crontab("0 3 * * */1")
async def send_reward_to_leaders():
    """
    Таск на отправку наград первым 50 лидерам по добычи в неделю, обнуляет добычу в неделю у игроков.
    Выполняется в 3:00 каждой понедельник.
    """

    leaders_stats = await Stats.all().order_by('-earned_week_coins').limit(50)

    # Начисляем награды
    rewards = []
    for i, stats in enumerate(leaders_stats, 1):
        if i == 1:
            stats.coins += int(stats.earned_week_coins * 0.5)
        if i <= 3:
            stats.coins += int(stats.earned_week_coins * 0.4)
        if i <= 5:
            stats.coins += int(stats.earned_week_coins * 0.3)
        if i <= 10:
            stats.coins += int(stats.earned_week_coins * 0.2)
        if i <= 15:
            stats.coins += int(stats.earned_week_coins * 0.1)
        if i <= 25:
            stats.coins += 10000

        rewards.append(Reward(type_name=RewardTypeName.LEADERBOARD, user_id=stats.user_id, amount=stats.coins,
                              replenishments=1))

    await Reward.bulk_create(rewards, ignore_conflicts=True)

    # Добавляем новых лидеров в таблицу, чтобы смотреть предыдущих
    try:
        await Leader.all().delete()
    except OperationalError:
        pass

    leaders = []
    for i, stats in enumerate(leaders_stats, 1):
        leaders.append(Leader(place=i, user_id=stats.user_id, earned_week_coins=stats.earned_week_coins))

    await Leader.bulk_create(leaders)

    # Обновляем еженедельный доход у юзеров
    users_stats = await Stats.all()
    for stats in users_stats:
        stats.earned_week_coins = 0

    await Stats.bulk_update(users_stats, ['earned_week_coins'])

    await Logger(APP_NAME).info(msg="Награды лидерам выплачены, следующие будут через неделю.",
                                func_name="leaderboard_reward")


@aiocron.crontab("0 */1 * * *", start=False)
async def get_ai_answers(**kwargs):
    """
    Запускаем таск на получение ответов на вопросы юзеров через OpenAI с проверкой каждый час.
    """

    conn: Connection = kwargs['conn']  # Redis, OpenAI подключения
    gt: GoogleTranslator = kwargs['gt']  # Google

    try:
        questions = await Question(status=QuestionStatus.IN_PROGRESS).all()

        # Если нет вопросов ждем 1 час и смотрим вопросы снова
        if not questions:
            await Logger(APP_NAME).info(msg="Вопросов нет, ожидание 60 минут.", func_name="get_ai_questions")
            return

        # Формируем ответы через OpenAI
        gpt_quests = [{"question": q.text, "acolyte_id": q.user_id} for q in questions]
        gpt_msgs = GPT_SYSTEM_MESSAGES + ({"role": "system", "content": f"Questions:{gpt_quests}"},)
        gpt_resp = await conn.ai_client.chat.completions.create(model="gpt-3.5-turbo",
                                                             messages=gpt_msgs,
                                                             max_tokens=100,
                                                             temperature=1,
                                                             stop=None,
                                                             timeout=30)

        gpt_dict_resp = loads(gpt_resp.choices[0].message.content)

        # Формируем список вопросов для загрузки в бд + сохраняем ответы
        loads_new_answ = []
        for q, answ in zip(questions, gpt_dict_resp):
            ru_answ = gt.translate(answ['answer'])
            loads_new_answ.append({"question": q.text, "answer": ru_answ, "embedding": q.embedding})

        #todo Сделать
        await Reward.create(user_id=user_id, inspirations=1, replenishments=(1 if last_question.secret else 0))

        # Загружаем ответы в db 0
        await conn.rs.index.load(loads_new_answ)
        # Удаляем вопросы из db 14
        await conn.rs.questions.delete(*lst_chat_id)

        await Logger(APP_NAME).success(msg="AI сгенерировал ответы, ожидание вопросов.",
                                       func_name="get_ai_questions")
    except Exception as e:
        await Logger(APP_NAME).error(msg=str(e),
                                     func_name="get_ai_questions")


if __name__ == '__main__':
    loop = get_event_loop()
    loop.run_until_complete(Logger(APP_NAME).success(msg="Планировщик запущен.", func_name="startup"))
    run_async(Tortoise.init(db_url=PG_URL, modules={'api': ['models']}))
    get_event_loop().run_forever()
