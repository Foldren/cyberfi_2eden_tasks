from typing import Any
from redisvl.index import AsyncSearchIndex
from redisvl.query import VectorQuery
from sentence_transformers import SentenceTransformer


def split_list(input_list, chunk_size):
    """
    Функция для разделения списка на сублисты.
    @param input_list: входной list
    @param chunk_size: размер чанка
    @return:
    """
    sublists = []
    for i in range(0, len(input_list), max(chunk_size, 1)):
        sublists.append(input_list[i:i + max(chunk_size, 1)])

    return sublists


async def find_near_question(model: SentenceTransformer, index: AsyncSearchIndex, question: str) -> tuple[Any, str]:
    """
    Функция для поиска схожего вопроса в redis.
    :param index: соединение Redis с индексом AsyncSearchIndex
    :param question: вопрос, заданный юзером через бот
    :return:
    """
    vector = model.encode(question, convert_to_tensor=True).numpy().tolist()
    query = VectorQuery(
        vector=vector,
        vector_field_name="embedding",
        return_fields=["answer"],
        num_results=1
    )
    result = await index.query(query)

    if result:
        if float(result[0]['vector_distance']) <= 0.031:
            result = result[0]['answer']
        else:
            result = None
    else:
        result = None

    return vector, result
