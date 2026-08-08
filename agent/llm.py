"""
Centralised LLM factory — all nodes import from here.

Uses AWS Bedrock via langchain-aws ChatBedrock.
The credentials in .env use a non-standard key format
(BedrockAPIKey-...) rather than the usual AKIA... IAM key.
See the NOTE in .env — if requests fail with auth errors, the
key may need to be used as a gateway token instead (see
_gateway_fallback below).
"""
import os
from functools import lru_cache

from langchain_aws import ChatBedrock
from botocore.credentials import Credentials
import boto3

AWS_ACCESS_KEY_ID     = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
AWS_REGION            = os.environ.get("AWS_REGION", "us-east-1")

# Bedrock model IDs — Claude on Bedrock uses the anthropic.* namespace.
# Adjust if your account has cross-region inference profiles.
MODEL_FAST    = "anthropic.claude-3-5-sonnet-20241022-v2:0"   # judge, rationale, post
MODEL_CAPABLE = "anthropic.claude-3-opus-20240229-v1:0"        # write_script


def _bedrock_client(region: str = AWS_REGION):
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=region,
    )
    return session.client("bedrock-runtime")


@lru_cache(maxsize=4)
def get_llm(
    model_id: str = MODEL_FAST,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> ChatBedrock:
    """
    Return a cached ChatBedrock instance.
    lru_cache keyed on (model_id, temperature, max_tokens) so nodes that
    share the same config reuse the same object.
    """
    return ChatBedrock(
        model_id=model_id,
        client=_bedrock_client(),
        model_kwargs={
            "temperature": temperature,
            "max_tokens": max_tokens,
            "anthropic_version": "bedrock-2023-05-31",
        },
    )
