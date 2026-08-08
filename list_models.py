"""List available Claude models on this Bedrock account."""
import os
from dotenv import load_dotenv
load_dotenv()

import boto3

# Use AWS credentials (not Bedrock API key)
aws_access_key = os.environ["AWS_ACCESS_KEY_ID"]
aws_secret_key = os.environ["AWS_SECRET_ACCESS_KEY"]
region         = os.environ.get("AWS_REGION", "us-east-1")

client = boto3.client(
    "bedrock",
    region_name=region,
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
)

try:
    resp = client.list_foundation_models(byProvider="Anthropic", byOutputModality="TEXT")
    models = resp.get("modelSummaries", [])
    print(f"Found {len(models)} Anthropic text models:\n")
    for m in models:
        status = m.get("modelLifecycle", {}).get("status", "?")
        print(f"  [{status}] {m['modelId']}")
except Exception as exc:
    # Try with bedrock-runtime instead
    print(f"bedrock list failed: {exc}")
    print("\nTrying inference profiles...")
    try:
        client2 = boto3.client("bedrock", region_name=region, api_key=api_key)
        resp2 = client2.list_inference_profiles()
        profiles = resp2.get("inferenceProfileSummaries", [])
        for p in profiles:
            if "claude" in p.get("inferenceProfileId", "").lower():
                print(f"  {p['inferenceProfileId']} — {p.get('status','?')}")
    except Exception as exc2:
        print(f"inference profiles also failed: {exc2}")
