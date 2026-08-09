from typing import TypedDict, Optional, Literal


class MediaAsset(TypedDict):
    asset_id: str
    scene_id: str
    asset_type: str
    script_beat: str
    visual_role: str
    prompt: str
    reference_asset: list[str]
    continuity_notes: str
    reuse: bool
    status: Literal["planned", "generating", "generated", "validating", "approved", "retry", "rejected"]
    output_url: Optional[str]
    validation_notes: Optional[str]
    retry_count: int


class TTSSegment(TypedDict):
    scene_id: str
    audio_url: str
    duration_seconds: float
    text: str


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
    # video_post removed: out of scope for this persona version
    # (ml_engineer_persona.md section 6, text + single static image only)
    content_type: Literal["image_post", "text_post"]

    # --- generation ---
    script: Optional[dict]            # {hook, beats[], narration, retention_notes}
    media_plan: list[MediaAsset]      # structured asset plan (spec section 4/5)
    image_assets: list[dict]          # [{url, prompt_used, beat_index}] — legacy, kept for text/image post path
    video_asset: Optional[dict]       # {url, prompt_used}
    tts_segments: list[TTSSegment]    # one per beat (spec section 7.5)
    omni_prompt: Optional[str]        # structured 9-section master brief (spec section 10), persisted for debugging

    # --- publishing ---
    post_text: Optional[str]
    rationale: Optional[dict]         # {why_selected, why_now, sources[]}

    # --- memory ---
    memory_context: list[dict]        # pulled from Breeth (recent posts + persona doc)
    persona_doc: Optional[dict]       # live persona memory doc from Breeth

    # --- meta ---
    tick_id: str                      # uuid for this scheduler tick
    error: Optional[str]              # set on any node failure; graph reads this to degrade
