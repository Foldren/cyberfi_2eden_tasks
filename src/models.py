from datetime import datetime, timedelta
from uuid import uuid4
from pytz import timezone
from tortoise import Model, Tortoise
from tortoise.contrib.pydantic import pydantic_model_creator, pydantic_queryset_creator
from tortoise.fields import BigIntField, DateField, CharEnumField, CharField, DatetimeField, \
    OnDelete, ForeignKeyField, OneToOneField, OneToOneRelation, ReverseRelation, FloatField, BooleanField
from tortoise_vector.field import VectorField
from components.enums import RankName, RewardTypeName, VisibilityType, ConditionType, QuestionStatus


class User(Model):
    id = BigIntField(pk=True)  # chat_id в телеграм
    referrer = ForeignKeyField(model_name="models.User", on_delete=OnDelete.CASCADE, related_name="leads", null=True)
    leads: ReverseRelation["User"]
    stats: OneToOneRelation["Stats"]
    rewards: ReverseRelation["Reward"]
    questions: OneToOneRelation["Question"]
    leader_place: OneToOneRelation["Leader"]
    country = CharField(max_length=50)
    referral_code = CharField(max_length=40, default=uuid4, unique=True)


class Stats(Model):
    id = BigIntField(pk=True)
    user = OneToOneField(model_name="models.User", on_delete=OnDelete.CASCADE, related_name="stats")
    coins = BigIntField(default=1000)
    energy = FloatField(default=2000)
    earned_week_coins = BigIntField(default=0)
    invited_friends = BigIntField(default=0)
    inspirations = BigIntField(default=0)
    replenishments = BigIntField(default=0)


class Reward(Model):
    id = BigIntField(pk=True)
    user = ForeignKeyField(model_name="models.User", on_delete=OnDelete.CASCADE, related_name="rewards")
    type_name = CharEnumField(enum_type=RewardTypeName, default=RewardTypeName.REFERRAL, description='Награда')
    amount = BigIntField(default=0)
    inspirations = BigIntField(default=0)
    replenishments = BigIntField(default=0)


class Leader(Model):
    place = BigIntField(pk=True)
    user = OneToOneField(model_name="models.User", on_delete=OnDelete.CASCADE, related_name="leader_place")
    earned_week_coins = BigIntField(default=0)


class Question(Model):
    id = BigIntField(pk=True)
    creator = ForeignKeyField('models.User', on_delete=OnDelete.CASCADE, related_name='questions')
    date_sent = DateField(auto_now_add=True)
    u_text = CharField(max_length=1000)  # На пользовательском языке
    text = CharField(max_length=1000)   # Всегда на английском
    answer = CharField(max_length=1000)  # Всегда на русском
    embedding = VectorField(vector_size=384)
    secret = BooleanField(default=0)
    status = CharEnumField(enum_type=QuestionStatus, default=QuestionStatus.IN_PROGRESS, description='Статус')