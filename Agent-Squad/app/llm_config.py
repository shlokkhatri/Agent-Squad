import os

from dotenv import load_dotenv
from crewai import LLM

load_dotenv()

# Select provider from environment
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

TEMPERATURE = 0.2
MAX_TOKENS = 4000
TIMEOUT = 120

if LLM_PROVIDER == "gemini":

    from google.genai import types

    API_KEY = os.getenv("GEMINI_API_KEY")

    MODEL_NAME = os.getenv(
        "GEMINI_LLM_MODEL",
        "gemini/gemini-2.5-flash"
    )

    if not API_KEY:
        raise ValueError(
            "Gemini's API key is missing from the .env file."
        )

    http_options = types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts= 3,
        )
    )

    llm = LLM(
        model = MODEL_NAME,
        api_key = API_KEY,
        temperature=TEMPERATURE,
        max_tokens = MAX_TOKENS,
        timeout = TIMEOUT,
        num_retries = 0,
        client_param = {
            "http_options" : http_options
        },
    )

elif LLM_PROVIDER == "groq":

    API_KEY = os.getenv("GROQ_API_KEY")

    MODEL_NAME = os.getenv(
        "GROQ_LLM_MODEL",
        "groq/openai/gpt-oss-120b",
    )

    if not API_KEY:
        raise ValueError(
            "Groq API key is missing from the .env file"
        )

    llm = LLM(
        model = MODEL_NAME,
        api_key = API_KEY,
        temperature=TEMPERATURE,
        max_tokens = MAX_TOKENS,
        timeout = TIMEOUT,
        num_retries = 2
    )

else :
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}"
        "Supported provider: gemini, groq"
    )

gemini_llm = llm
