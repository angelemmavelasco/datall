import os
import json
import uuid
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from openai import OpenAI
from django.conf import settings
from . import tools
from apps.data_assistant.prompts.system_prompts import SYSTEM_PROMPTS

class DatallAssistantService:
    def __init__(self, user, thread_id=None):
        self.user = user
        self.thread_id = thread_id if thread_id else str(uuid.uuid4())
        self.file_path = f"assistant_threads/{self.thread_id}.json"
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY, 
            base_url="https://api.deepseek.com"
        )
        
        self._load_history()
        self.tools_registry = self._load_tools_registry()

    def _load_history(self):
        if default_storage.exists(self.file_path):
            with default_storage.open(self.file_path, 'r') as f:
                self.history = json.loads(f.read())
        else:
            first_name = self.user.first_name if self.user.first_name else self.user.username
            
            self.history = [
                {"role": "system", "content": SYSTEM_PROMPTS['datall_chat'].format(first_name=first_name)}
            ]
            self._save_history()

    def _save_history(self):
        content = json.dumps(self.history, ensure_ascii=False, indent=2)
        if default_storage.exists(self.file_path):
            default_storage.delete(self.file_path)
        default_storage.save(self.file_path, ContentFile(content.encode('utf-8')))

    def _load_tools_registry(self):
        registry_path = os.path.join(os.path.dirname(__file__), 'tool_registry.json')
        with open(registry_path, 'r') as f:
            return json.load(f)

    def process_message_stream(self, text_content=None):
        if text_content:
            self.history.append({"role": "user", "content": text_content})
            self._save_history()

        stream = self._call_llm()

        tool_calls_accumulator = {}
        final_content = ""
        is_tool_call = False

        for chunk in stream:
            delta = chunk.choices[0].delta
            
            if delta.content:
                final_content += delta.content
                yield delta.content
            if delta.tool_calls:
                is_tool_call = True
                for tcchunk in delta.tool_calls:
                    index = tcchunk.index
                    if index not in tool_calls_accumulator:
                        tool_calls_accumulator[index] = {
                            "id": tcchunk.id,
                            "type": "function",
                            "function": {
                                "name": "",
                                "arguments": ""
                            }
                        }
                    
                    if tcchunk.function.name:
                        tool_calls_accumulator[index]["function"]["name"] += tcchunk.function.name
                    if tcchunk.function.arguments:
                        tool_calls_accumulator[index]["function"]["arguments"] += tcchunk.function.arguments

        if is_tool_call:
            tool_calls = list(tool_calls_accumulator.values())
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls
            }
            self.history.append(assistant_msg)

            for tc in tool_calls:
                function_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    arguments = {}

                if hasattr(tools, function_name):
                    func = getattr(tools, function_name)
                    try:
                        result = func(user=self.user, **arguments)
                    except Exception as e:
                        result = f"Error ejecutando la herramienta: {str(e)}"
                else:
                    result = f"Error: La herramienta {function_name} no existe."
                
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": function_name,
                    "content": str(result)
                })

            self._save_history()
            
            yield from self.process_message_stream(text_content=None)
            
        else:
            if final_content:
                self.history.append({"role": "assistant", "content": final_content})
                self._save_history()

    def _call_llm(self):
        return self.client.chat.completions.create(
            model="deepseek-chat",
            messages=self.history,
            tools=self.tools_registry,
            temperature=0.0,
            stream=True
        )