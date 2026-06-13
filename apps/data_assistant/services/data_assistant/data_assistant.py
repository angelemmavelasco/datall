import json
from openai import AsyncOpenAI
from config.settings import DEEPSEEK_API_KEY
from apps.data_assistant.prompts.system_prompts import SYSTEM_PROMPTS

class DataAssistant:
    def __init__(self, system_context: str = None):
        self.client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY, 
            base_url="https://api.deepseek.com/v1"
        )
        self.system_context = system_context or "Eres un asistente experto en análisis de datos comerciales."

    def ask(self, question: str) -> str:
        pass

    async def analyze_view_data(self, template_data: dict) -> str:

        data_str = json.dumps(template_data, default=str)
        system_prompt = SYSTEM_PROMPTS.get('data_assistant')
        prompt = system_prompt + data_str
        

        response = await self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": self.system_context},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        return response.choices[0].message.content