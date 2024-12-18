from typing import Annotated
from warnings import filterwarnings
from aioclock import Group, Cron, Every
from tortoise.exceptions import OperationalError
from ujson import loads
from components.pydantic_models import Connection
from components.tools import find_near_question, split_list
from config import APP_NAME, GPT_SYSTEM_MESSAGES, SECRET_QS
from init import init_conn
from models import Question, Stats, Leader, Reward, RewardType, QuestionStatus
from modules.logger import Logger
from aioclock import Depends

group = Group()
filterwarnings("ignore", category=FutureWarning, message=r".*clean_up_tokenization_spaces.*")


@group.task(trigger=Cron(cron="0 3 * * */1", tz="Europe/Moscow"))
async def send_reward_to_leaders():
    """
    Таск на отправку наград первым 50 лидерам по добычи в неделю, обнуляет добычу в неделю у игроков.
    Выполняется в 3:00 каждый понедельник.
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

        rewards.append(Reward(type_name=RewardType.LEADERBOARD, user_id=stats.user_id, amount=stats.coins,
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


@group.task(trigger=Every(seconds=15))
async def get_ai_answers(conn: Annotated[Connection, Depends(init_conn, cast=False)]):
    """
    Запускаем таск на получение ответов на вопросы юзеров через OpenAI с проверкой каждый час.
    """

    try:
        questions = await Question.filter(status=QuestionStatus.IN_PROGRESS).all()

        # Если нет вопросов ждем 1 час и смотрим вопросы снова
        if not questions:
            await Logger(APP_NAME).info(msg="Вопросов нет, ожидание 60 минут.", func_name="get_ai_questions")
            return
        else:
            await Logger(APP_NAME).info(msg="Старт разбора вопросов юзеров.", func_name="get_ai_questions")

        # Сперва проверка на похожий вопрос в Redis --------------------------------------------------------------------
        gpt_questions = []
        gpt_model_qs = []
        index_model_qs = []
        rewards = []
        for q in questions:
            vector, index_answer = await find_near_question(model=conn.model, index=conn.rs.index, question=q.text)
            # Сохраняем вектор в бд и меняем статус
            q.embedding = vector
            q.status = QuestionStatus.HAVE_ANSWER
            # Проверяем секретный ли вопрос
            if index_answer in [qst["answer"] for qst in SECRET_QS]:
                q.secret = True

            # Формируем список наград
            rewards.append(Reward(user_id=q.user_id, inspirations=1, replenishments=(1 if q.secret else 0),
                                  type=RewardType.AI_QUESTION))

            # Если нет похожего, тогда добавляем вопрос в список для AI
            if index_answer is None:
                gpt_questions.append({"question": q.text, "acolyte_id": q.user_id})
                gpt_model_qs.append(q)
            else:
                q.answer = index_answer
                index_model_qs.append(q)

        chunk_quests = split_list(gpt_questions, len(gpt_questions) // 40)  # делим список вопросов на чанки по 40

        # Теперь ищем ответы у AI --------------------------------------------------------------------------------------
        gpt_answers = []
        for questions in chunk_quests:  # отправляем вопросы пачками в ai
            gpt_msgs = GPT_SYSTEM_MESSAGES + ({"role": "system", "content": f"Questions:{questions}"},)
            gpt_resp = await conn.ai_client.chat.completions.create(model="gpt-3.5-turbo",
                                                                    messages=gpt_msgs,
                                                                    max_tokens=100,
                                                                    temperature=1,
                                                                    stop=None,
                                                                    timeout=30)

            gpt_answers += loads(gpt_resp.choices[0].message.content)

        # Формируем список вопросов для загрузки в бд + сохраняем ответы
        index_load_answers = []
        for q, a in zip(gpt_model_qs, gpt_answers):
            q.answer = conn.gt_to_ru.translate(a['answer'])
            index_load_answers.append({"question": q.text, "answer": q.answer, "embedding": q.embedding})
            q.embedding = str(q.embedding)  # Для записи переводим в строку

        # Загружаем ответы в db 0
        await conn.rs.index.load(index_load_answers)
        # Обновляем атрибуты вопросов
        await Question.bulk_update(gpt_model_qs + index_model_qs, fields=['answer', "status", "embedding", "secret"])
        # Создаем награды
        await Reward.bulk_create(rewards, ignore_conflicts=True)

        await Logger(APP_NAME).success(msg="AI сгенерировал ответы, ожидание вопросов.",
                                       func_name="get_ai_questions")
    except Exception as e:
        await Logger(APP_NAME).error(msg=str(e),
                                     func_name="get_ai_questions")
