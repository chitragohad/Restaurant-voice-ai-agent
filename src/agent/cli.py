"""CLI voice agent using Gemini Live API (microphone)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def run_cli_agent() -> None:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("Error: pip install google-genai (requires Python 3.10+)")
        sys.exit(1)

    from src.agent.gemini_tools import execute_booking_tool, tool_result_text
    from src.agent.voice_agent import get_gemini_api_key, get_live_config, get_live_model

    client = genai.Client(api_key=get_gemini_api_key())
    model = get_live_model()
    config = get_live_config()

    print("Shiv Sagar Voice Reservation Agent (Gemini Live)")
    print("Press Ctrl+C to exit. Speak into your microphone.\n")

    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part(text=config["system_instruction"])]
        ),
        tools=[types.Tool(function_declarations=config["tools"])],
    )

    async with client.aio.live.connect(model=model, config=live_config) as session:
        print("Connected. Say hello to book a table.")

        async def receive_loop():
            async for message in session.receive():
                if message.tool_call:
                    responses = []
                    for fc in message.tool_call.function_calls:
                        args = dict(fc.args) if fc.args else {}
                        result = execute_booking_tool(fc.name, args)
                        responses.append(
                            types.FunctionResponse(
                                id=fc.id,
                                name=fc.name,
                                response={"result": tool_result_text(result)},
                            )
                        )
                    await session.send_tool_response(
                        function_responses=responses
                    )
                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.text:
                            print(f"Agent: {part.text}")

        recv_task = asyncio.create_task(receive_loop())
        try:
            while True:
                text = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("You (type to send text): ")
                )
                if text.strip():
                    await session.send_client_content(
                        turns=types.Content(
                            role="user", parts=[types.Part(text=text)]
                        ),
                        turn_complete=True,
                    )
        except KeyboardInterrupt:
            print("\nGoodbye!")
        finally:
            recv_task.cancel()


if __name__ == "__main__":
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: Set GEMINI_API_KEY in .env")
        sys.exit(1)
    asyncio.run(run_cli_agent())
