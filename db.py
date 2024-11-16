import os
from dotenv import load_dotenv
import redis
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

r = redis.Redis(
    host=os.getenv('REDIS_DB_HOST'),
    port=int(os.getenv('REDIS_DB_PORT')) if os.getenv('REDIS_DB_PORT') else 6379,
    username='default',
    password=os.getenv('REDIS_DB_PASSWORD'),
    health_check_interval=30,
)

def try_catch_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            logging.debug(
                f'Entering function: {func.__name__} with args: {args}, kwargs: {kwargs}'
            )
            result = func(*args, **kwargs)
            logging.debug(f'Exiting function: {func.__name__} with result: {result}')
            return result
        except Exception as e:
            logging.error(f'Error calling {func.__name__}', exc_info=True)
            raise e  # Re-raise the exception to handle it appropriately
    return wrapper

@try_catch_decorator
def append_segment_to_transcript(session_id: str, new_segments: list[dict]):
    key = f'transcript:{session_id}'
    logging.debug(f'Appending new segments to key: {key}')
    segments = r.get(key)
    if not segments:
        logging.debug('No existing segments found. Initializing new list.')
        segments = []
    else:
        logging.debug(f'Existing segments retrieved: {segments}')
        segments = eval(segments.decode('utf-8'))
    segments.extend(new_segments)
    r.set(key, str(segments))
    logging.debug(f'Updated segments stored: {segments}')
    return segments

@try_catch_decorator
def remove_transcript(session_id: str):
    logging.debug(f'Removing transcript for session_id: {session_id}')
    r.delete(f'transcript:{session_id}')
    delete_last_call_time(session_id)

@try_catch_decorator
def clean_all_transcripts_except(session_id: str):
    logging.debug(f'Cleaning all transcripts except session_id: {session_id}')
    pattern = f'transcript:*'
    for key in r.scan_iter(pattern):
        key_decoded = key.decode()
        current_session_id = key_decoded.split(':')[1]
        if current_session_id != session_id:
            logging.debug(f'Deleting transcript key: {key_decoded}')
            r.delete(key)
            last_call_time_key = f'last_call_time:{current_session_id}'
            logging.debug(f'Deleting last call time key: {last_call_time_key}')
            r.delete(last_call_time_key)

@try_catch_decorator
def get_full_transcript(session_id: str):
    key = f'transcript:{session_id}'
    logging.debug(f'Getting full transcript for key: {key}')
    segments = r.get(key)
    if not segments:
        logging.debug('No segments found.')
        return ''
    else:
        segments = eval(segments.decode('utf-8'))
        logging.debug(f'Segments retrieved: {segments}')
        segments = sorted(segments, key=lambda x: x['start'])
        full_text = ' '.join(
            [segment['text'] for segment in segments if segment['text'].strip()]
        )
        logging.debug(f'Full transcript text: {full_text}')
        return full_text

@try_catch_decorator
def set_last_call_time(session_id: str, timestamp: float):
    key = f'last_call_time:{session_id}'
    r.set(key, str(timestamp))
    logging.debug(f'Set last call time for key: {key} to timestamp: {timestamp}')

@try_catch_decorator
def get_last_call_time(session_id: str):
    key = f'last_call_time:{session_id}'
    logging.debug(f'Getting last call time for key: {key}')
    timestamp = r.get(key)
    if timestamp:
        logging.debug(f'Last call time retrieved: {timestamp}')
        return float(timestamp)
    else:
        logging.debug('No last call time found.')
        return None

@try_catch_decorator
def delete_last_call_time(session_id: str):
    key = f'last_call_time:{session_id}'
    r.delete(key)
    logging.debug(f'Deleted last call time for key: {key}')

@try_catch_decorator
def add_pending_message(message: str):
    pending_messages_key = 'pending_messages'
    r.lpush(pending_messages_key, message)
    logging.debug('Added pending message')

@try_catch_decorator
def get_pending_messages():
    pending_messages_key = 'pending_messages'
    messages = []
    while True:
        message = r.rpop(pending_messages_key)
        if message:
            messages.append(message.decode('utf-8'))
        else:
            break
    logging.debug(f'Pending messages retrieved: {messages}')
    return messages
