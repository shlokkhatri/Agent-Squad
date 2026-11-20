import os

from dotenv import load_dotenv
from crewai import LLM
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")

if not API_KEY:
    raise ValueError(
        "GEMINI API KEY is missing. Add it to the project .env file."
    )

# Configure Google GenAI HTTP retries.
http_options = types.HttpOptions(
    retry_options=types.HttpRetryOptions(
        attempts=3,
    )
)

llm = LLM(
    model=MODEL_NAME,
    api_key=API_KEY,
    temperature=0.2,
    max_tokens=4000,
    timeout=120,
    num_retries=0,
    client_params={
        "http_options": http_options,
    },
)

# Backward-compatible alias.
gemini_llm = llm