from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

@app.post('/news-checker')
def news_checker_endpoint(uid: str, data: dict):
    print(uid, data)

    return {'message': 'I love you Mik'}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=80, reload=True)
