import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async, async_to_sync
from apps.data_assistant.services.datall_assistant.datall_assistant_service import DatallAssistantService

class DatallAssistantConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get('message', '')
        thread_id = text_data_json.get('thread_id', None)
        if not message:
            return
        await self.send(text_data=json.dumps({
            'type': 'start_message'
        }))
        def _process_sync(msg, t_id, user):
            service = DatallAssistantService(user=user, thread_id=t_id)
            async_to_sync(self.send)(text_data=json.dumps({
                'type': 'thread_id',
                'thread_id': service.thread_id
            }))
            for chunk in service.process_message_stream(msg):
                async_to_sync(self.send)(text_data=json.dumps({
                    'type': 'chunk',
                    'content': chunk
                }))
                
        await sync_to_async(_process_sync)(message, thread_id, self.scope["user"])

        await self.send(text_data=json.dumps({
            'type': 'end_message'
        }))
