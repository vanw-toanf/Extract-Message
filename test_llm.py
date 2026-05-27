from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

llm_link = os.getenv("LLM_LINK")
model = os.getenv("LLM_MODEL")

client = OpenAI(
    base_url=llm_link, 
    api_key='ollama',
)

response = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "Bạn là một trợ lý AI hữu ích. Hãy trả lời bằng tiếng việt."},
        {"role": "user", "content": "Chào Agent, bạn đang chạy trên phần cứng nào vậy?"}
    ]
)
print(response.choices[0].message.content)