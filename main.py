from fastapi import FastAPI, Request
import uvicorn
import os
import sys
import time
import logging
import asyncio
import openai
from typing import Any
from pydantic import BaseModel

from db import (
    clean_all_transcripts_except,
    append_segment_to_transcript,
    remove_transcript,
    get_last_call_time,
    set_last_call_time,
    get_full_transcript,
    add_pending_message,
    get_pending_messages,
    r,
)

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from cdp_langchain.agent_toolkits import CdpToolkit
from cdp_langchain.utils import CdpAgentkitWrapper

from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Initialize agent once
agent_executor = None
config = None
openai.api_key = os.getenv("OPENAI_API_KEY")

class Answer(BaseModel):
    is_advice_request: bool
    is_image_request: bool
    is_transfer_funds: bool
    response_string: str

def categorize_request(request, model="gpt-4o-mini") -> Any | None:
    print(f"categorize_request: {request}")

    messages = [
        {
            "role": "system",
            "content": """You are an assistant responsible for identifying the type of an initial query. 
            You will receive a query and must determine which category it belongs to and add response_string 
            corresponding to the category.
            
            1) If the query contains a request to get an advice, return is_advice_request = true, and in 
            response_string give the requested advice: imagine that you are are a person that is mentioned in request 
            and give an advice on a requested topic.
            
            2) If the query is a request for image creation, return is_image_request = true, and in response_string 
            store the extended prompt for the image generation. 
                        
            3) If the query is a request to transfer fund, return is_transfer_funds = true and in response_string
            return the query like:
            Transfer 100 usdc to 0x6236726372367346
            Transfer 1 000 000 gwei to 0x734737467346
            If in initial request there is something sounds like usdc, gwei, etc. commot crypto currencies - fix the
            name to the correct. And if mentioned grandson or something sound like it - change grandson to  
            0x61813b2a30580DE2695611fCa6a2e38e09E92B7D
            
            4) In all other cases just answer the initial request and store the answer to response_string.
            """
        },
        {
            "role": "user",
            "content": f"This is the text for categorization:\n\n{request}"
        }
    ]

    try:
        response = openai.beta.chat.completions.parse(model=model,
                                                      messages=messages,
                                                      response_format=Answer,
                                                      )
        answer_value = response.choices[0].message.parsed

        if answer_value:
            print(f"Categorized query: {answer_value}")
            return answer_value
        else:
            print(f"Failed to categorize query: {response.choices[0].message.refusal}")
            return None
    except Exception as e:
        print(f"Failed to categorize query: {e}")
        return None

@app.post('/start')
async def start_endpoint():
    # Simplified start endpoint
    return {'message': 'Conversation started!'}


@app.post('/wai-api-call')
async def wai_call_endpoint(request: Request):
    data = await request.json()
    session_id = data['session_id']
    new_segments = data['segments']
    clean_all_transcripts_except(session_id)
    append_segment_to_transcript(session_id, new_segments)
    current_time = time.time()
    set_last_call_time(session_id, current_time)
    return {'message': 'Transcript updated.'}


async def call_from_transcript(transcript):
    logging.debug('Entered call_from_transcript function.')
    logging.info(f'Processing Transcript:\n{transcript}')
    categorized_request = categorize_request(transcript)

    if categorized_request:
        if categorized_request.is_image_request:
            logging.debug('Image request')
        elif categorized_request.is_advice_request:
            logging.debug('is_advice_request request')
        elif categorized_request.is_transfer_funds:
            logging.debug('is_transfer_funds request')
        logging.debug("Request (fixed with llm):", categorized_request.response_string)
        
        run_chat_mode(agent_executor=agent_executor, config=config, user_input=categorized_request.response_string)
        logging.debug('Exiting call_from_transcript function.')


# Background Task to Process Idle Transcripts
async def background_task():
    while True:
        await asyncio.sleep(5)
        logging.debug('Running background task to check for idle sessions.')
        for key in r.scan_iter(f'last_call_time:*'):
            key_decoded = key.decode()
            _, session_id = key_decoded.split(':')
            last_call_time = get_last_call_time(session_id)
            if last_call_time is None:
                continue
            current_time = time.time()
            time_difference = current_time - last_call_time
            if time_difference > 5:
                logging.info(f'Processing transcript for session_id: {session_id}.')
                full_transcript = get_full_transcript(session_id)
                await call_from_transcript(full_transcript)
                remove_transcript(session_id)
            else:
                logging.debug(f'Session {session_id} is still active.')


@app.on_event("startup")
async def startup_event():
    global agent_executor, config
    set_env_vars_from_dotenv()
    agent_executor, config = initialize_agent()
    asyncio.create_task(background_task())


@app.get('/get-pending-messages')
async def get_pending_messages_endpoint():
    messages = get_pending_messages()
    logging.debug(f"Pending messages: {messages}")
    return {'messages': messages}


@app.post('/user-message')x
async def user_message_endpoint(request: Request):
    logging.debug('user_message_endpoint')
    data = await request.json()
    message = data['message']
    await call_from_transcript(message)
    return {'message': 'Message received'}


# @app.post('/ask-llm')
# async def ask_llm_endpoint(request: Request):
#     logging.debug('ask_llm_endpoint')
#     data = await request.json()
#     question = data.get('question', '')
#     if not question:
#         return {'error': 'Question is required.'}
#     try:
#         llm = ChatOpenAI(model="gpt-4o-mini")
#         response = llm([HumanMessage(content=question)])
#         answer = response.content
#         return {'answer': answer}
#     except Exception as e:
#         logging.error('Error in ask_llm_endpoint.', exc_info=True)
#         return {'error': 'An error occurred while processing your request.'}


@app.get('/random-friend')
async def random_friend_endpoint():
    # For simplicity, returning a static friend
    friend = {
        'name': 'Alice',
        'ens_address': 'alice.eth'
    }
    return friend


def initialize_agent():
    logging.debug('Initializing agent.')
    llm = ChatOpenAI(model="gpt-4o-mini")
    wallet_data = None
    wallet_data_file = "wallet_data.txt"

    if os.path.exists(wallet_data_file):
        logging.debug(f'Loading wallet data from {wallet_data_file}.')
        with open(wallet_data_file) as f:
            wallet_data = f.read()

    values = {}
    if wallet_data is not None:
        values = {"cdp_wallet_data": wallet_data}
        logging.debug('Loaded wallet data for CDP Agentkit Wrapper.')

    agentkit = CdpAgentkitWrapper(**values)
    logging.debug('Initialized CDP Agentkit Wrapper.')

    wallet_data = agentkit.export_wallet()
    with open(wallet_data_file, "w") as f:
        f.write(wallet_data)
        logging.debug('Persisted wallet data to file.')

    cdp_toolkit = CdpToolkit.from_cdp_agentkit_wrapper(agentkit)
    tools = cdp_toolkit.get_tools()
    logging.debug('Initialized CDP Toolkit and retrieved tools.')

    memory = MemorySaver()
    config = {"configurable": {"thread_id": "CDP Agentkit Chatbot Example!"}}

    agent_executor = create_react_agent(
        llm,
        tools=tools,
        checkpointer=memory,
        state_modifier=(
            "You are a helpful agent that can interact onchain using the Coinbase Developer Platform Agentkit. "
            "You are empowered to interact onchain using your tools. If you ever need funds, you can request them "
            "from the faucet if you are on network ID `base-sepolia`. If not, you can provide your wallet details "
            "and request funds from the user. If someone asks you to do something you can't do with your currently "
            "available tools, you must say so, and encourage them to implement it themselves using the CDP SDK + "
            "Agentkit, recommend they go to docs.cdp.coinbase.com for more information. Be concise and helpful with "
            "your responses. Refrain from restating your tools' descriptions unless it is explicitly requested."
        ),
    )
    logging.debug('Created ReAct agent executor.')
    return agent_executor, config


def run_chat_mode(agent_executor, config, user_input):
    logging.debug('Starting chat mode.')
    messages = []

    try:
        if user_input.lower() == "exit":
            logging.debug('User chose to exit chat mode.')
            return

        for chunk in agent_executor.stream(
            {"messages": [HumanMessage(content=user_input)]}, config
        ):
            logging.debug(f'Received chunk: {chunk}')
            if "agent" in chunk:
                message_content = chunk["agent"]["messages"][0].content
                logging.debug(f'Agent message: {message_content}')
                messages.append(message_content)
            elif "tools" in chunk:
                message_content = chunk["tools"]["messages"][0].content
                logging.debug(f'Tool message: {message_content}')
                messages.append(message_content)

    except Exception as e:
        logging.error('Error in chat mode.', exc_info=True)
        # Optionally, add an error message to pending messages
        add_pending_message("An error occurred while processing your request.")
        return

    # Store messages in pending_messages
    for message in messages:
        add_pending_message(message)


def set_env_vars_from_dotenv():
    required_vars = ["CDP_API_KEY_PRIVATE_KEY", "CDP_API_KEY_NAME"]
    for var in required_vars:
        value = os.getenv(var)
        if value:
            os.environ[var] = value
            logging.debug(f'{var} is set.')
        else:
            logging.error(f'{var} is not found in .env or environment variables.')
            raise ValueError(f'{var} is not found in .env or environment variables.')


if __name__ == "__main__":
    logging.debug('Starting application.')
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=80,
        timeout_keep_alive=600
    )