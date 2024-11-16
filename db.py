import os
from dotenv import load_dotenv
import redis

load_dotenv()

r = redis.Redis(
    host=os.getenv('REDIS_DB_HOST'),
    port=int(os.getenv('REDIS_DB_PORT')) if os.getenv('REDIS_DB_PORT') is not None else 6379,
    username='default',
    password=os.getenv('REDIS_DB_PASSWORD'),
    health_check_interval=30
)


def try_catch_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f'Error calling {func.__name__}', e)
            return None

    return wrapper


def append_segment_to_transcript(uid: str, session_id: str, new_segments: list[dict]):
    key = f'transcript:{uid}:{session_id}'
    segments = r.get(key)
    if not segments:
        segments = []
    else:
        segments = eval(segments)

    segments.extend(new_segments)
    # order the segments by start time, in case they are not ordered, and save them
    # segments = sorted(segments, key=lambda x: x['start'])
    r.set(key, str(segments))
    return segments


def remove_transcript(uid: str = "BTQXyVbC7SRF9p5D2ceuC9TXDCC3", session_id: str = "BTQXyVbC7SRF9p5D2ceuC9TXDCC3"):
    r.delete(f'transcript:{uid}:{session_id}')


def clean_all_transcripts_except(uid: str, session_id: str):
    for key in r.scan_iter(f'transcript:{uid}:*'):
        if key.decode().split(':')[2] != session_id:
            r.delete(key)

def get_full_transcript(uid: str = "BTQXyVbC7SRF9p5D2ceuC9TXDCC3", session_id: str = "BTQXyVbC7SRF9p5D2ceuC9TXDCC3"):
    key = f'transcript:{uid}:{session_id}'
    segments = r.get(key)
    if not segments:
        print('')
        return ''
    else:
        # Convert the stored string back to a list of dictionaries
        segments = eval(segments)
        # Sort the segments by their 'start' time
        segments = sorted(segments, key=lambda x: x['start'])
        # Concatenate the 'text' fields from each segment with a space
        full_text = ' '.join([segment['text'] for segment in segments if segment['text'].strip()])
        print(full_text)
        return full_text

