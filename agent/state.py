from typing import TypedDict, Optional, Literal


class AgentState(TypedDict):
    # --- identity ---
    agent_id: str
    persona: dict                     # name, domain, voice_rules, stable_interests, pushback

    # --- discovery ---
    candidates: list[dict]            # {title, url, source, summary, published_at}
    rejected_topics: list[dict]       # {title, url, reason}

    # --- selection ---
    selected_topic: Optional[dict]    # one candidate after editorial_judge

    # --- routing ---
    content_type: Literal["image_post", "video_post", "text_post"]

    # --- generation ---
    script: Optional[dict]            # {hook, beats[], narration, retention_notes}
    image_assets: list[dict]          # [{url, prompt_used, beat_index}]
    video_asset: Optional[dict]       # {url, prompt_used}

    # --- publishing ---
    post_text: Optional[str]
    rationale: Optional[dict]         # {why_selected, why_now, sources[]}

    # --- memory ---
    memory_context: list[dict]        # pulled from Breeth (recent posts + persona doc)
    persona_doc: Optional[dict]       # live persona memory doc from Breeth

    # --- meta ---
    tick_id: str                      # uuid for this scheduler tick
    error: Optional[str]              # set on any node failure; graph reads this to degrade
