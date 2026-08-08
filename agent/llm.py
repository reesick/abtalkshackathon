"""
Centralised LLM factory — all nodes import from here.

Uses AWS Bedrock via langchain-aws with Bedrock API key.
"""
import os
from functools import lru_cache

from langchain_aws import ChatBedrock

BEDROCK_API_KEY = os.environ["BEDROCK_API_KEY"]
AWS_REGION      = os.environ.get("AWS_REGION", "us-east-1")

# Bedrock model IDs - try Mistral first (often more available)
MODEL_FAST    = "mistral.mistral-7b-instruct-v0:2"
MODEL_CAPABLE = "mistral.mixtral-8x7b-instruct-v0:1"


@lru_cache(maxsize=4)
def get_llm(
    model_id: str = MODEL_FAST,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> ChatBedrock:
    # Only add anthropic_version for Anthropic models
    model_kwargs = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if "anthropic" in model_id:
        model_kwargs["anthropic_version"] = "bedrock-2023-05-31"
    
    return ChatBedrock(
        model_id=model_id,
        region_name=AWS_REGION,
        api_key=BEDROCK_API_KEY,
        model_kwargs=model_kwargs,
    )
