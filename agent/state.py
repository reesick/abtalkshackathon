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


class MemeOpportunity(TypedDict):
    """Output of assess_opportunity() — see meme/engine.py."""
    is_meme_worthy: bool
    confidence: float
    humour_potential: int  # 0-10
    recommended_mechanisms: list[str]
    reason: str


class MemeTemplateCandidate(TypedDict):
    """A scored template candidate during selection."""
    template_id: str
    name: str
    semantic_fit: float
    humour_mechanism_fit: float
    visual_fit: float
    popularity: float
    freshness: float
    historical_performance: float
    repetition_penalty: float
    final_score: float


class MemeCaptionCandidate(TypedDict):
    """One raw caption candidate before ranking."""
    template_id: str
    humour_mechanism: str
    angle_type: Literal["image_focused", "narrative_driven"]
    text_boxes: list[str]  # ordered, matches the template's box_count
    narrative_used: Optional[str]


class MemeJudgeScore(TypedDict):
    """Multi-dimensional judge output for one caption candidate."""
    humour_score: float
    originality_score: float
    surprise_score: float
    relevance_score: float
    template_fit_score: float
    relatability_score: float
    brevity_score: float
    naturalness_score: float
    clarity_score: float
    generic_ai_penalty: float
    repetition_penalty: float
    forced_slang_penalty: float
    final_score: float
    reasoning: str
    ai_ish: bool


class MemeResult(TypedDict):
    """Final output of the meme engine for one topic — see meme/engine.py."""
    should_make_meme: bool
    template_id: Optional[str]
    template_name: Optional[str]
    template_family: Optional[str]
    humour_mechanism: Optional[str]
    text_boxes: list[str]
    caption_flat: Optional[str]  # human-readable joined caption, for post text/logging
    score: Optional[float]
    rendered_url: Optional[str]
    reason: Optional[str]  # why should_make_meme is False, or a summary if True


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
    # video_post and image_post removed: video was never wired into this
    # graph; image generation is disconnected as of the meme subsystem
    # integration (see meme_intelligence_humour_system_implementation.md).
    # Both node files remain on disk as a clean seam for later.
    content_type: Literal["meme_post", "text_post"]

    # --- generation (image/video path — disconnected, kept for the seam) ---
    script: Optional[dict]            # {hook, beats[], narration, retention_notes}
    media_plan: list[MediaAsset]      # structured asset plan (spec section 4/5)
    image_assets: list[dict]          # [{url, prompt_used, beat_index}] — legacy
    video_asset: Optional[dict]       # {url, prompt_used}
    tts_segments: list[TTSSegment]    # one per beat (spec section 7.5) — kept, not disconnected
    omni_prompt: Optional[str]        # structured 9-section master brief, persisted for debugging

    # --- meme subsystem ---
    meme_opportunity: Optional[MemeOpportunity]
    meme_result: Optional[MemeResult]

    # --- publishing ---
    post_text: Optional[str]
    rationale: Optional[dict]         # {selected_because, relevant_now_because, rejected_alternatives, sources[]}

    # --- memory ---
    memory_context: list[dict]        # pulled from Breeth (recent posts + persona doc)
    persona_doc: Optional[dict]       # live persona memory doc from Breeth

    # --- meta ---
    tick_id: str                      # uuid for this scheduler tick
    error: Optional[str]              # set on any node failure; graph reads this to degrade
