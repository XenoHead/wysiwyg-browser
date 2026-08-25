import os
import asyncio
from dotenv import load_dotenv, find_dotenv
from google import genai

# Locate and load the .env file automatically
load_dotenv(find_dotenv())

# Retrieve key and validate it's present
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("API Key is missing! Check your .env file or environment variables.")

# Initialize client explicitly with key
client = genai.Client(api_key=api_key)

config = {
    "response_modalities": ["AUDIO"],
    "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Puck"}}}
}

async def voice_chat():
    async with client.aio.live.connect(
        model="gemini-2.5-flash-native-audio", 
        config=config
    ) as session:
        print("Connected to Live API successfully!")

if __name__ == "__main__":
    asyncio.run(voice_chat())