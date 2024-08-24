import logging
import asyncio
import requests

class LaravelTalker:
    def __init__(self):
        self.host = 'https://tgplan.ru/api/'

    async def execute_request(self, method, path, json=None):
        request_method = getattr(requests, method)
        response = request_method(self.host + path, json=json, verify=True)
        log_msg = f"Request: {method} {self.host + path}; "
        logging.info(log_msg + f"Response: {response.content if response.status_code == 200 else response}")
        if response.status_code == 200:
            return response.json()
        else:
            return None

    async def execute_ifdancoder_request(self, method, path, json=None):
        response = await self.execute_request(method, path, json=json)
        if response:
            return response['data']
        else:
            return None

    async def register_user(self, tg_name, tg_username, tg_id, timezone_id=None):
        return await self.execute_ifdancoder_request('post', 'users', json={'tg_name': tg_name, 'tg_username': tg_username, 'tg_id': tg_id, 'timezone_id': timezone_id})

    async def get_user_by_tg_id(self, tg_id):
        return await self.execute_ifdancoder_request('get', f'users/{tg_id}')

    async def update_user_timezone(self, tg_id, timezone_id):
        return await self.execute_ifdancoder_request('put', f'users/{tg_id}', json={'timezone_id': timezone_id})

    async def get_timezones(self):
        return await self.execute_ifdancoder_request('get', 'timezones')
    
    async def get_statuses(self):
        return await self.execute_ifdancoder_request('get', 'statuses')
    
    async def get_task(self, peer_id, task_id):
        return await self.execute_ifdancoder_request('get', f'chats/{peer_id}/tasks/{task_id}')
    
    async def update_task_status(self, peer_id, task_id, status_id):
        return await self.execute_ifdancoder_request('put', f'chats/{peer_id}/tasks/{task_id}', json={'status_id': status_id})
    
    async def get_task_link(self, client, peer_id, task_id):
        return f"https://t.me/{(await client.get_me()).username}/Plan?startapp={peer_id}_{task_id}"
    