"""Test LLM with IAM credentials only (no API key)."""
import os
from dotenv import load_dotenv
load_dotenv()

# Remove BEDROCK_API_KEY so only IAM credentials are used
os.environ.pop("BEDROCK_API_KEY", None)

from agent.llm import get_llm

llm = get_llm()
print(f"LLM configured with model: {llm.model_id}")
print("Testing LLM...")

# Simple test
result = llm.invoke("Say 'hello' in 3 words")
print(f"Result: {result.content}")
