from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from db import (
    clean_all_transcripts_except,
    append_segment_to_transcript,
    remove_transcript,
    get_last_call_time,
    set_last_call_time,
    delete_last_call_time,
    get_full_transcript,
    r,  # Import Redis instance
)
import os
import sys
import time
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s'
)

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

# Import CDP Agentkit Langchain Extension.
from cdp_langchain.agent_toolkits import CdpToolkit
from cdp_langchain.utils import CdpAgentkitWrapper

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Configure a file to persist the agent's CDP MPC Wallet Data.
wallet_data_file = "wallet_data.txt"

@app.post('/wai-api-call')
def wai_call_endpoint(uid: str, data: dict):
    logging.debug(f'Received request for uid: {uid} with data: {data}')
    session_id = data['session_id']
    new_segments = data['segments']
    logging.debug(f'Cleaning all transcripts except for session_id: {session_id}')
    clean_all_transcripts_except(uid, session_id)

    # Append the new segments to the transcript
    logging.debug('Appending new segments to transcript.')
    transcript: list[dict] = append_segment_to_transcript(uid, session_id, new_segments)
    logging.debug(f'Current transcript: {transcript}')

    # Get the current time
    current_time = time.time()
    logging.debug(f'Current time: {current_time}')

    # Update the last call time to the current time
    set_last_call_time(uid, session_id, current_time)
    logging.debug(f'Updated last call time for uid: {uid}, session_id: {session_id}')

    return {'message': 'I love you Mik'}

def call_from_transcript(transcript):
    logging.debug('Entered call_from_transcript function.')
    logging.info(f'Processing Transcript:\n{transcript}')
    # Add your processing logic here
    # For example, you might pass the transcript to the agent
    agent_executor, config = initialize_agent()
    run_chat_mode(agent_executor=agent_executor, config=config, user_input=transcript)
    logging.debug('Exiting call_from_transcript function.')

# Background Task to Process Idle Transcripts
async def background_task():
    while True:
        await asyncio.sleep(5)
        logging.debug('Running background task to check for idle sessions.')
        # Get all last call times from Redis
        for key in r.scan_iter('last_call_time:*'):
            uid_session = key.decode().split(':')[1:]
            uid = uid_session[0]
            session_id = uid_session[1]
            last_call_time = get_last_call_time(uid, session_id)
            if last_call_time is None:
                continue
            current_time = time.time()
            time_difference = current_time - last_call_time
            if time_difference > 5:
                logging.info(f'More than 5 seconds have passed since last call for uid: {uid}, session_id: {session_id}. Processing transcript.')
                full_transcript = get_full_transcript(uid, session_id)
                call_from_transcript(full_transcript)
                remove_transcript(uid, session_id)
            else:
                logging.debug(f'Less than 5 seconds since last call for uid: {uid}, session_id: {session_id}. Not processing transcript yet.')

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_task())

def initialize_agent():
    """Initialize the agent with CDP Agentkit."""
    logging.debug('Initializing agent.')
    # Initialize LLM.
    llm = ChatOpenAI(model="gpt-4o-mini")

    wallet_data = None

    if os.path.exists(wallet_data_file):
        logging.debug(f'Wallet data file {wallet_data_file} exists. Loading data.')
        with open(wallet_data_file) as f:
            wallet_data = f.read()
    else:
        logging.debug(f'Wallet data file {wallet_data_file} does not exist.')

    # Configure CDP Agentkit Langchain Extension.
    values = {}
    if wallet_data is not None:
        # If there is a persisted agentic wallet, load it and pass to the CDP Agentkit Wrapper.
        values = {"cdp_wallet_data": wallet_data}
        logging.debug('Loaded wallet data for CDP Agentkit Wrapper.')

    agentkit = CdpAgentkitWrapper(**values)
    logging.debug('Initialized CDP Agentkit Wrapper.')

    # Persist the agent's CDP MPC Wallet Data.
    wallet_data = agentkit.export_wallet()
    with open(wallet_data_file, "w") as f:
        f.write(wallet_data)
        logging.debug('Persisted wallet data to file.')

    # Initialize CDP Agentkit Toolkit and get tools.
    cdp_toolkit = CdpToolkit.from_cdp_agentkit_wrapper(agentkit)
    tools = cdp_toolkit.get_tools()
    logging.debug('Initialized CDP Toolkit and retrieved tools.')

    # Store buffered conversation history in memory.
    memory = MemorySaver()
    config = {"configurable": {"thread_id": "CDP Agentkit Chatbot Example!"}}

    # Create ReAct Agent using the LLM and CDP Agentkit tools.
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

# Autonomous Mode
def run_autonomous_mode(agent_executor, config, interval=10):
    """Run the agent autonomously with specified intervals."""
    logging.debug('Starting autonomous mode.')
    print("Starting autonomous mode...")
    while True:
        try:
            # Provide instructions autonomously
            thought = (
                "Be creative and do something interesting on the blockchain. "
                "Choose an action or set of actions and execute it that highlights your abilities."
            )

            # Run agent in autonomous mode
            for chunk in agent_executor.stream(
                {"messages": [HumanMessage(content=thought)]}, config
            ):
                if "agent" in chunk:
                    print(chunk["agent"]["messages"][0].content)
                elif "tools" in chunk:
                    print(chunk["tools"]["messages"][0].content)
                print("-------------------")

            # Wait before the next action
            time.sleep(interval)

        except KeyboardInterrupt:
            logging.info('Autonomous mode interrupted by user.')
            print("Goodbye Agent!")
            sys.exit(0)
        except Exception as e:
            logging.error('Error in autonomous mode.', exc_info=True)
            sys.exit(1)

# Chat Mode
def run_chat_mode(agent_executor, config, user_input):
    """Run the agent interactively based on user input."""
    logging.debug('Starting chat mode.')
    print("Starting chat mode... Type 'exit' to end.")

    try:
        if user_input.lower() == "exit":
            logging.debug('User chose to exit chat mode.')
            return

        # Run agent with the user's input in chat mode
        for chunk in agent_executor.stream(
            {"messages": [HumanMessage(content=user_input)]}, config
        ):
            if "agent" in chunk:
                print(chunk["agent"]["messages"][0].content)
            elif "tools" in chunk:
                print(chunk["tools"]["messages"][0].content)
            print("-------------------")

    except KeyboardInterrupt:
        logging.info('Chat mode interrupted by user.')
        print("Goodbye Agent!")
        sys.exit(0)
    except Exception as e:
        logging.error('Error in chat mode.', exc_info=True)
        sys.exit(1)

# Mode Selection
def choose_mode():
    """Choose whether to run in autonomous or chat mode based on user input."""
    logging.debug('Prompting user to choose mode.')
    while True:
        print("\nAvailable modes:")
        print("1. chat    - Interactive chat mode")
        print("2. auto    - Autonomous action mode")

        choice = input("\nChoose a mode (enter number or name): ").lower().strip()
        logging.debug(f'User selected mode: {choice}')
        if choice in ["1", "chat"]:
            return "chat"
        elif choice in ["2", "auto"]:
            return "auto"
        print("Invalid choice. Please try again.")
        logging.warning('User made invalid mode selection.')

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
    set_env_vars_from_dotenv()
    agent_executor, config = initialize_agent()
    # Uncomment the following lines if you want to use mode selection
    # mode = choose_mode()
    # if mode == "chat":
    #     user_input = input("\nUser: ")
    #     run_chat_mode(agent_executor=agent_executor, config=config, user_input=user_input)
    # elif mode == "auto":
    #     run_autonomous_mode(agent_executor=agent_executor, config=config)
    logging.debug('Running Uvicorn server.')
    uvicorn.run("main:app", host="0.0.0.0", port=80, reload=True)
