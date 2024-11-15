from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from db import clean_all_transcripts_except, append_segment_to_transcript, remove_transcript

app = FastAPI()

@app.post('/news-checker')
def news_checker_endpoint(uid: str, data: dict):
    print(uid, data)
    session_id = data['session_id']  # use session id in case your plugin needs the whole conversation context
    new_segments = data['segments']
    clean_all_transcripts_except(uid, session_id)

    transcript: list[dict] = append_segment_to_transcript(uid, session_id, new_segments)
    print(transcript)
    return {'message': 'I love you Mik'}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=80, reload=True)
