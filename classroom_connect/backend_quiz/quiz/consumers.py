import json
from channels.generic.websocket import AsyncWebsocketConsumer

class QuizConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f"quiz_{self.room_name}"

        # Join quiz group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave quiz group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']

        # Broadcast message to group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "quiz_message",
                "message": message
            }
        )

    async def quiz_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"]
        }))
