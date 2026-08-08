"""
Centralised LLM factory — all nodes import from here.

Uses AWS Bedrock via langchain-aws ChatBedrock with a Bedrock API key
(ABSK... format), not IAM credentials.
"""
import os
from functools import lru_cache

from langchain_aws import ChatBedrock

BEDROCK_API_KEY = os.environ["BEDROCK_API_KEY"]
AWS_REGION      = os.environ.get("AWS_REGION", "us-east-1")

# Bedrock model IDs
MODEL_FAST    = "anthropic.claude-3-5-sonnet-20241022-v2:0"
MODEL_CAPABLE = "anthropic.claude-3-5-sonnet-20241022-v2:0"   # use same — opus not available via API key


@lru_cache(maxsize=4)
def get_llm(
    model_id: str = MODEL_FAST,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> ChatBedrock:
    return ChatBedrock(
        model_id=model_id,
        region_name=AWS_REGION,
        api_key=BEDROCK_API_KEY,
        model_kwargs={
            "temperature": temperature,
            "max_tokens": max_tokens,
            "anthropic_version": "bedrock-2023-05-31",
        },
    )
