import os
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument
import dotenv
import logging
import speech_recognition as sr
from pydub import AudioSegment
import requests
import io
import shutil
import timezones_orm
from telethon.tl.types import InputPeerUser, MessageEntityMention
import json
from datetime import datetime, timedelta
from telethon.tl.types import PeerUser, PeerChannel, KeyboardButtonRow, KeyboardButtonCallback, ReplyKeyboardMarkup, UpdateChannelParticipant, InputPeerUser, ChannelParticipantBanned, ChannelParticipantAdmin
from telethon.tl.custom import Button
from laravel_talker import LaravelTalker
from ollama import Client
import re
from fuzzywuzzy import fuzz

dotenv.load_dotenv()


logging.basicConfig(level=logging.INFO)

audio_folder = 'audio/'
bot_token = os.getenv('BOT_TOKEN')
api_hash = os.getenv('API_HASH')
app_id = os.getenv('APP_ID')
app_title = os.getenv('APP_TITLE')

client = TelegramClient('session_name', app_id, api_hash)
oclient = Client(host='http://ollama:11434')

ltalker = LaravelTalker()

def is_user_peer(handler):
    async def wrapper(event):
        if isinstance(event.peer_id, PeerUser):
            return await handler(event)
    return wrapper

def is_chat_peer(handler):
    async def wrapper(event):
        if isinstance(event.peer_id, PeerChannel):
            return await handler(event)
    return wrapper

@client.on(events.NewMessage(pattern=r'.*#[Зз][Аа][Дд][Аа][Чч]'))
@is_chat_peer
async def handle_task_message(event):
    message = event.message
    peer_id = event.chat_id
    if message.text:
        microresponse = await process_message(event)
        
        if microresponse and not ('not_found' in microresponse):
            logging.info(microresponse)
            response = await ltalker.execute_ifdancoder_request('post', f"chats/{peer_id}/tasks", json=microresponse)
            if response:
                data = response
                task_id = data['chat_order_id']

                buttons = [Button.url('Открыть задачу', f"https://t.me/{(await client.get_me()).username}/Plan?startapp={peer_id}_{task_id}")]

                await event.reply(f"Задача #{task_id} создана!", buttons=buttons)
                
                ollama_response = await ollama_process(event)

                if ollama_response:
                    response = await ltalker.execute_ifdancoder_request('put', f"chats/{event.chat_id}/tasks/{task_id}", json=ollama_response)
                    data = response
                    if response:
                        tg_id = microresponse['tg_user_id']
                        mentions = microresponse['mentions']

                        tg_id_peer = await client.get_entity(tg_id)

                        not_subscribed = set()

                        await client.send_message(tg_id_peer, f"Задача #{task_id} успешно создана вами!\nНазвание задачи: {data['title']}\nИсполнители: {', '.join(['@' + m['mn_tg_user_name'] for m in mentions])}\nДата создания задачи: {microresponse['date']}\nДата сдачи задания: {data['due_date']}\nТекст задания: {data['description']}")
                        try:
                            await client.send_message(tg_id_peer, f"Задача #{task_id} успешно создана вами!\nНазвание задачи: {data['title']}\nИсполнители: {', '.join(['@' + m['mn_tg_user_name'] for m in mentions])}\nДата создания задачи: {microresponse['date']}\nДата сдачи задания: {data['due_date']}\nТекст задания: {data['description']}")
                        except:
                            not_subscribed.add(event.sender.username)
                        
                        mention_peers = [(await client.get_entity(m['mn_tg_user_id']), m['mn_tg_user_name']) for m in mentions]
                        for peer, username in mention_peers:
                            await client.send_message(peer, f"Вам поступило задание #{task_id} от @{event.sender.username}!\nНазвание задачи: {data['title']}\nИсполнители: {', '.join(['@' + m['mn_tg_user_name'] for m in mentions])}\nДата создания задачи: {microresponse['date']}\nДата сдачи задания: {data['due_date']}\nТекст задания: {data['description']}")
                            try:
                                await client.send_message(peer, f"Вам поступило задание #{task_id} от @{event.sender.username}!\nНазвание задачи: {data['title']}\nИсполнители: {', '.join(['@' + m['mn_tg_user_name'] for m in mentions])}\nДата создания задачи: {microresponse['date']}\nДата сдачи задания: {data['due_date']}\nТекст задания: {data['description']}")
                            except:
                                not_subscribed.add(username)

                        if len(not_subscribed) > 0:
                            button = Button.url("Перейти в чат с ботом", f"t.me/{(await client.get_me()).username}")
                            await client.send_message(await client.get_input_entity(event.chat_id), f"Не удалось оповестить {', '.join(map(lambda x: '@' + x, not_subscribed))} о задаче (\nПожалуйста, подпишитесь на бота для получения уведомлений о новых заданиях!)", buttons=[button])
                        return
        if 'not_found' in microresponse:
            if len(microresponse['not_found']) > 1:
                await event.reply(f"Не получилось создать задачу, поскольку не найдены пользователи с никнеймами {', '.join(microresponse['not_found'])} ((")
            else:
                await event.reply(f"Не получилось создать задачу, поскольку не найден пользователь с никнеймом {', '.join(microresponse['not_found'])} ((")
        else:
            await event.reply("Не получилось создать задачу ((")

@client.on(events.NewMessage(pattern=r'.*#[Сс][Тт][Аа][Тт][Уу][Сс]'))
@is_chat_peer
async def handle_status_message(event):
    message = event.message.text
    peer_id = event.chat_id
    
    match = re.search(r'\d+', message)

    statuses = await ltalker.get_statuses()

    if match:
        number = int(match.group())
        message = message.replace(match.group(), '')

        task_id = number

        task = await ltalker.get_task(peer_id, task_id)

        if not task:
            await event.reply(f"Задача #{task_id} не найдена ((")
            return

        logging.info(f"Task #{task_id}: {task}")

        if task['status']['id'] == 1:
            await event.reply(f"[Задача #{task_id}]({await ltalker.get_task_link(client, peer_id, task_id)}) находится в обработке ((", link_preview=False)
            return

        pairs = []
        for status in statuses:
            similarity = fuzz.ratio(message.lower(), status['name'].lower())
            pairs.append((similarity, status))

        pairs.sort(key=lambda x: x[0], reverse=True)

        if len(pairs) > 0:
            if pairs[0][0] < 50:
                task = await ltalker.get_task(peer_id, task_id)

                await event.reply(f"Статус [задачи #{task_id}]({await ltalker.get_task_link(client, peer_id, task_id)}): {task['status']['name']}", link_preview=False)
                return

            status_id = pairs[0][1]['id']

            if status_id == task['status']['id']:
                await event.reply(f"Статус [задачи #{task_id}]({await ltalker.get_task_link(client, peer_id, task_id)}) уже {pairs[0][1]['name']}!", link_preview=False)
                return

            if status_id == 1:
                await event.reply(f"[Задача #{task_id}]({await ltalker.get_task_link(client, peer_id, task_id)}) не может быть в статусе {pairs[0][1]['name']} ((", link_preview=False)
                return

            response = await ltalker.update_task_status(peer_id, task_id, status_id)

            if response:
                await event.reply(f"Статус [задачи #{task_id}]({await ltalker.get_task_link(client, peer_id, task_id)}) изменен на {pairs[0][1]['name']}!", link_preview=False)
            else:
                await event.reply("Не получилось поменять статус задачи ((")

    else:
        await event.reply("Не получилось поменять статус задачи ((")

    

@client.on(events.NewMessage(pattern=r'.*#[Нн][Аа][Йй][Тт][Ии]'))
@is_chat_peer
async def handle_find_message(event):
    message = event.message

    text = message.text
    chat_id = event.chat_id
    if text:
        words = text.split()
        for word in words:
            if word.startswith('#'):
                words.remove(word)
        
        text = ' '.join(words)
        tasks = await ltalker.execute_ifdancoder_request('get', f'/chats/{chat_id}/tasks', json={'text': text})
        if tasks:
            if len(tasks) > 0:
                task = tasks[0]
                message = ''
                message += f"Найдено {len(tasks)} задач(и):\n\n"
                message += '\n\n'.join([f"[Задача #{t['id']}]({await ltalker.get_task_link(client, chat_id, t['chat_order_id'])})\nЗаголовок задачи: {t['title']}\nДедлайн: {t['due_date']}\nОписание задачи: {t['description']}" for t in tasks])
                await event.reply(message, link_preview=False)
                return
            else:
                await event.reply(f"Задачи по запросу не найдены")
                return
        await event.reply(f"Ошибка при поиске задач")
        return

@client.on(events.NewMessage(incoming=True))
@is_chat_peer
async def handle_new_message(event):
    if event.message.media and isinstance(event.message.media, MessageMediaDocument):
        if event.message.media.document.mime_type.startswith('audio'):
            audio_file = await event.message.download_media()
            audio = AudioSegment.from_file(audio_file, format='ogg')
            os.remove(audio_file)

            r = sr.Recognizer()
            with sr.AudioFile(io.BytesIO(audio.export(format="wav").read())) as source:
                audio_data = r.record(source)
                recognized_text  = r.recognize_google(audio_data, language='ru-RU')
                if recognized_text:
                    response = await process_message(event, recognized_text)
                    if response:
                        try:
                            response = ltalker.execute_ifdancoder_request('post', f"chats/{event.chat_id}/tasks", json=response)
                        except:
                            pass
                    await event.reply("Аудиосообщение получено и сохранено! Распознанное сообщение: " + recognized_text)

async def get_user_id(username):
    user = await client.get_entity(username)
    user_id = user.id
    return user_id

async def timezone_message(peer_id):
    timezones = await ltalker.get_timezones()
    buttons = []
    tmp_buttons = []
    for i, tz in enumerate(timezones):
        tmp_buttons.append(Button.inline(tz['name'], 'tz_' + str(tz['id'])))
        if (i + 1) % 3 == 0 or i == len(timezones) - 1:
            buttons.append(tmp_buttons)
            tmp_buttons = []

    await client.send_message(peer_id, f"Выберите часовой пояс", buttons=buttons)

@client.on(events.NewMessage(incoming=True, pattern='/change-timezone'))
@is_user_peer
async def change_timezone(event):
    chat_id = event.chat_id
    await timezone_message(chat_id)

@client.on(events.CallbackQuery)
@is_user_peer
async def handle_callback_query(event):
    sender_id = event.sender_id

    if event.data.startswith(b'tz_'):
        tz_id = event.data.split(b'_')[1].decode('utf-8')
        tz_info = await ltalker.update_user_timezone(sender_id, tz_id)

        user = await ltalker.get_user_by_tg_id(sender_id)
        message_text = f"Выбранный часовой пояс: {user['timezone']['name']}"
        
        await event.answer(message_text, cache_time=0)

@client.on(events.NewMessage(incoming=True, pattern='/start'))
@is_user_peer
async def start(event):
    logging.info(event)
    chat_id = event.chat_id

    await client.send_message(chat_id, f"Привет, {event.sender.first_name}! Я бот TGPlan. Я могу помочь вам с заданиями")

    first_name = event.sender.first_name
    last_name = event.sender.last_name
    name = first_name if last_name is None else (last_name if first_name is None else (first_name + ' ' + last_name))
    username = event.sender.username
    tg_id = event.sender_id

    user = await ltalker.register_user(name, username, tg_id)

    buttons = [
        Button.url("Добавить бота", f"https://t.me/{(await client.get_me()).username}?startgroup=true"),
    ]

    message_to_pin = await client.send_message(chat_id, f"Основные действия бота:", buttons=buttons)
    await client.pin_message(chat_id, message_to_pin)

    await timezone_message(chat_id)
    

async def ollama_process(event, recognized_text = None):
    sender_id = event.sender_id
    user = await ltalker.get_user_by_tg_id(sender_id)

    offset_in_minutes = user['timezone']['offset']
    time_now = datetime.now()
    time_with_offset = time_now + timedelta(minutes=offset_in_minutes)
    formatted_time = time_with_offset.strftime("%d.%m.%Y %H:%M:%S")

    message_text = recognized_text if recognized_text else event.message.text

    response = oclient.generate(model='llama3', prompt=f'В кавычках представлено сообщение: "{message_text}". Сейчас {formatted_time}. Вытащи из сообщения суть задачи без упоминания времени дедлайна (чтобы она была написана понятным языком). Если информация о дедлайне есть в сообщении, отдельно рассчитай дату и время дедлайна с учетом заданной мной даты ранее в формате DD.MM.YYYY hh:mm:ss, иначе не пиши дедлайн вообще. Пиши на русском только результат безо всякого лишнего текста')
    logging.info(response)

    jsn_obj = {'type': 'задача'}
    if response:
        response = response['response']
        response = response.split('\n')
        title = response[0]
        title = title.split(': ')[-1].replace('"', '').replace("'", '').replace('«', '').replace('»', ' ').replace('.', ' ')
        if not title[0].isupper():
            title = title[0].upper() + title[1:]

        due_date_isoformat = None
        try:
            due_date = response[-1]
            due_date = due_date.split(': ')[-1].replace('"', '').replace("'", '')
            due_date_obj = datetime.strptime(due_date, "%d.%m.%Y %H:%M:%S")
            due_date_obj = due_date_obj - timedelta(minutes=offset_in_minutes)
            due_date_isoformat = due_date_obj.isoformat()
        except:
            pass

        jsn_obj['text'] = title
        jsn_obj['due_date'] = due_date_isoformat

        logging.info(jsn_obj)
    return jsn_obj

async def process_message(event, recognized_text = None):
    sender_id = event.sender_id

    entities = event.message.entities
    mentions = [event.message.text[ e.offset : e.offset + e.length ] for e in entities if type(e) == MessageEntityMention]
    users = []
    not_found = []
    for mention in mentions:
        try:
            user_id = await get_user_id(mention)
            users.append({'mn_tg_user_id': user_id, 'mn_tg_user_name': mention[1:]})
        except:
            not_found.append(mention)
    jsn_obj = {}
    jsn_obj['mentions'] = users
    jsn_obj['peer_id'] = event.chat_id
    jsn_obj['chat_name'] = event.chat.title
    jsn_obj['tg_user_id'] = event.sender_id
    jsn_obj['date'] = event.date.isoformat()
    jsn_obj['tg_user_name'] = event.sender.username

    if not_found:
        jsn_obj['not_found'] = not_found
        
    return jsn_obj

event_counter = 0
@client.on(events.Raw(UpdateChannelParticipant))
async def raw(update):
    logging.info('Event: ' + str(update))

    my_bot_id = (await client.get_me()).id
    logging.info('My Bot ID: ' + str(my_bot_id))

    if not hasattr(update, 'user_id'):
        return
    
    user_id = update.user_id
    logging.info('Event User: ' + str(user_id))

    if not hasattr(update, 'actor_id'):
        return

    inviter_id = update.actor_id
    logging.info('Inviter ID: ' + str(inviter_id))
    inviter = await client.get_entity(inviter_id)
    
    if my_bot_id != user_id:
        logging.info('Not my bot')
        return
    
    prev_participant = update.prev_participant
    new_participant = update.new_participant

    if prev_participant and prev_participant.user_id == my_bot_id and (not new_participant or isinstance(new_participant, ChannelParticipantBanned)):
        logging.info('Bot left')
        inviter_chat = await client.get_input_entity(inviter)
        await client.send_message(inviter_chat, 'Жаль, что я был выгнан из группы ((')
        return

    if not hasattr(update, 'channel_id'):
        return

    chat_id = update.channel_id
    logging.info('Chat ID: ' + str(chat_id))
    chat = await client.get_entity(chat_id)

    if isinstance(new_participant, ChannelParticipantAdmin):
        admin_rights = new_participant.admin_rights
        permissions = (admin_rights.change_info, admin_rights.post_messages, admin_rights.edit_messages, admin_rights.delete_messages, admin_rights.ban_users, admin_rights.invite_users, admin_rights.pin_messages, admin_rights.add_admins, admin_rights.anonymous, admin_rights.manage_call, admin_rights.other, admin_rights.manage_topics, admin_rights.post_stories, admin_rights.edit_stories, admin_rights.delete_stories)
        needed_permissions = (False, False, False, True, False, True, True, False, False, False, False, False, False, False, False)

        inviter_chat = await client.get_input_entity(inviter)

        if all(needed_permissions[i] == permissions[i] for i in range(len(needed_permissions)) if needed_permissions[i] == True):
            logging.info('Permissions are fine')
            await client.send_message(inviter_chat, 'Спасибо, что выдали все необходимые боту права!\nНачинаем работу!')

            buttons = [
                Button.url("Просмотреть задачи", f"https://t.me/{(await client.get_me()).username}/Plan?startapp={chat_id}"),
            ]

            message_to_pin = await client.send_message(chat_id, f"Основные действия бота-планировщика:", buttons=buttons)
            await client.pin_message(chat_id, message_to_pin)
        else:
            logging.info('Permissions are not fine')
            await client.send_message(inviter_chat, 'К сожалению, этих прав недостаточно для работы бота ((\nВыдайте все необходимые права!')

    if not prev_participant and new_participant and new_participant.user_id == my_bot_id:
        logging.info('Bot joined')

        inviter_chat = await client.get_input_entity(inviter)
        await client.send_message(inviter_chat, 'Теперь сделайте нашего бота администратором группы и выдайте все права. Это необходимо для работы')

        jsn_obj = {
            'peer_id': chat_id,
            'chat_name': chat.title,
            'chat_username': chat.username,
            'tg_user_id': inviter.id,
            'tg_user_name': inviter.username,
            'date' : datetime.now().isoformat()
        }
        try:
            response = ltalker.execute_ifdancoder_request('post', "chats", data=jsn_obj)
        except:
            pass

    return

client.start(bot_token=bot_token)

client.run_until_disconnected()