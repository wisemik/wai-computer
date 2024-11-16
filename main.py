from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from db import clean_all_transcripts_except, append_segment_to_transcript, remove_transcript
import os
import sys
import time
from db import (
    clean_all_transcripts_except, append_segment_to_transcript, remove_transcript,
    get_last_call_time, set_last_call_time, delete_last_call_time
)
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

# Import CDP Agentkit Langchain Extension.
from cdp_langchain.agent_toolkits import CdpToolkit
from cdp_langchain.utils import CdpAgentkitWrapper

import os
import sys
import time

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

# Import CDP Agentkit Langchain Extension.
from cdp_langchain.agent_toolkits import CdpToolkit
from cdp_langchain.utils import CdpAgentkitWrapper

# Configure a file to persist the agent's CDP MPC Wallet Data.
wallet_data_file = "wallet_data.txt"

# Configure a file to persist the agent's CDP MPC Wallet Data.

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

wallet_data_file = "wallet_data.txt"
app = FastAPI()

@app.post('/wai-api-call')
def wai_call_endpoint(uid: str, data: dict):
    print(uid, data)
    session_id = data['session_id']
    new_segments = data['segments']
    clean_all_transcripts_except(uid, session_id)

    # Append the new segments to the transcript
    transcript: list[dict] = append_segment_to_transcript(uid, session_id, new_segments)
    print(transcript)

    # Get the current time
    current_time = time.time()

    # Get the last call time
    last_call_time = get_last_call_time(uid, session_id)

    if last_call_time is not None:
        time_difference = current_time - last_call_time
        if time_difference > 5:
            # More than 5 seconds have passed since the last call
            # Get the full transcript
            full_transcript = get_full_transcript(uid, session_id)
            # Process the transcript
            call_from_transcript(full_transcript)
            # Delete the transcript and last call time
            remove_transcript(uid, session_id)
    else:
        # This is the first call
        pass

    # Update the last call time to the current time
    set_last_call_time(uid, session_id, current_time)

    return {'message': 'I love you Mik'}

def call_from_transcript(transcript):
    print("Call: ", transcript)

def initialize_agent():
    """Initialize the agent with CDP Agentkit."""
    # Initialize LLM.
    llm = ChatOpenAI(model="gpt-4o-mini")

    wallet_data = None

    if os.path.exists(wallet_data_file):
        with open(wallet_data_file) as f:
            wallet_data = f.read()

    # Configure CDP Agentkit Langchain Extension.
    values = {}
    if wallet_data is not None:
        # If there is a persisted agentic wallet, load it and pass to the CDP Agentkit Wrapper.
        values = {"cdp_wallet_data": wallet_data}

    agentkit = CdpAgentkitWrapper(**values)

    # persist the agent's CDP MPC Wallet Data.
    wallet_data = agentkit.export_wallet()
    with open(wallet_data_file, "w") as f:
        f.write(wallet_data)

    # Initialize CDP Agentkit Toolkit and get tools.
    cdp_toolkit = CdpToolkit.from_cdp_agentkit_wrapper(agentkit)
    tools = cdp_toolkit.get_tools()

    # Store buffered conversation history in memory.
    memory = MemorySaver()
    config = {"configurable": {"thread_id": "CDP Agentkit Chatbot Example!"}}

    # Create ReAct Agent using the LLM and CDP Agentkit tools.
    return create_react_agent(
        llm,
        tools=tools,
        checkpointer=memory,
        state_modifier="You are a helpful agent that can interact onchain using the Coinbase Developer Platform Agentkit. You are empowered to interact onchain using your tools. If you ever need funds, you can request them from the faucet if you are on network ID `base-sepolia`. If not, you can provide your wallet details and request funds from the user. If someone asks you to do something you can't do with your currently available tools, you must say so, and encourage them to implement it themselves using the CDP SDK + Agentkit, recommend they go to docs.cdp.coinbase.com for more informaton. Be concise and helpful with your responses. Refrain from restating your tools' descriptions unless it is explicitly requested.",
    ), config


# Autonomous Mode
def run_autonomous_mode(agent_executor, config, interval=10):
    """Run the agent autonomously with specified intervals."""
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
            print("Goodbye Agent!")
            sys.exit(0)



# Chat Mode
def run_chat_mode(agent_executor, config, user_input):
    """Run the agent interactively based on user input."""
    print("Starting chat mode... Type 'exit' to end.")

    try:
        # user_input = input("\nUser: ")
        if user_input.lower() == "exit":
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
        print("Goodbye Agent!")
        sys.exit(0)





# Mode Selection
def choose_mode():
    """Choose whether to run in autonomous or chat mode based on user input."""
    while True:
        print("\nAvailable modes:")
        print("1. chat    - Interactive chat mode")
        print("2. auto    - Autonomous action mode")

        choice = input("\nChoose a mode (enter number or name): ").lower().strip()
        if choice in ["1", "chat"]:
            return "chat"
        elif choice in ["2", "auto"]:
            return "auto"
        print("Invalid choice. Please try again.")


# def main():
#     """Start the chatbot agent."""
#     agent_executor, config = initialize_agent()
#
#     mode = choose_mode()
#     if mode == "chat":
#         run_chat_mode(agent_executor=agent_executor, config=config)
#     elif mode == "auto":
#         run_autonomous_mode(agent_executor=agent_executor, config=config)


def set_env_vars_from_dotenv():
    required_vars = ["CDP_API_KEY_PRIVATE_KEY", "CDP_API_KEY_NAME"]
    for var in required_vars:
        value = os.getenv(var)
        if value:
            os.environ[var] = value
            print(f"{var} is set.")
        else:
            raise ValueError(f"{var} is not found in .env or environment variables.")

if __name__ == "__main__":
    set_env_vars_from_dotenv()
    agent_executor, config = initialize_agent()
    # run_chat_mode(agent_executor=agent_executor, config=config)
    uvicorn.run("main:app", host="0.0.0.0", port=80, reload=True)
