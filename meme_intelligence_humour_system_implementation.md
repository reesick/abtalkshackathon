# Meme Intelligence & Humour System
## Implementation Specification for the AI Influencer

**Status:** Implementation specification  
**Scope:** Meme selection, meme-template memory, humour generation skill, meme composition, evaluation, repetition control, and rendering  
**Existing discovery system:** Already implemented — **do not rebuild discovery**  
**Primary objective:** Turn discovered AI/tech topics into genuinely appropriate, non-repetitive memes using a structured humour skill derived from current AI humour research.

---

# 0. READ THIS FIRST

You are implementing a **meme subsystem** inside an existing autonomous AI influencer.

The discovery/source layer is already integrated.

Do **not** modify or rebuild the existing discovery system unless a tiny interface change is strictly necessary.

This task is specifically about:

1. deciding whether a discovered topic should become a meme;
2. understanding the topic;
3. retrieving appropriate meme templates;
4. maintaining a persistent meme-template registry;
5. preventing repetitive template/joke usage;
6. generating humour using a dedicated **Humour Skill**;
7. adapting humour to the visual grammar of the selected template;
8. generating multiple candidates;
9. judging candidates;
10. rendering the final meme;
11. storing what was used;
12. learning from previous meme performance;
13. making the system progressively better.

The humour system must be designed using the research paper:

**AI Humor Generation: Cognitive, Social and Creative Skills for Effective Humor**  
Sean Kim and Lydia B. Chilton, 2025  
https://arxiv.org/html/2502.07981v1

This paper is not merely a citation. Its workflow should directly influence the architecture of the humour skill.

The paper describes a system called **HumorSkills** that separates visual detail extraction, visual humour ideation, narrative/conflict extrapolation, caption generation, and ranking. Its study found that the humour-skilled system outperformed basic GPT-4o captioning in their evaluated settings and approached highly rated human Instagram captions. These results should be treated as research evidence motivating the architecture, **not as a guarantee that this implementation will be funny**.

Source:
https://arxiv.org/html/2502.07981v1

---

# 1. CORE DESIGN PRINCIPLE

Do NOT build this:

```text
topic
  ↓
LLM
  ↓
"make a funny meme"
  ↓
Drake
```

That is exactly the sort of pipeline that produces generic AI slop.

Build this:

```text
DISCOVERED TOPIC
      ↓
TOPIC UNDERSTANDING
      ↓
MEME OPPORTUNITY DETECTION
      ↓
COMEDIC ANGLE / HUMOUR MODE
      ↓
TEMPLATE RETRIEVAL
      ↓
TEMPLATE SEMANTIC RANKING
      ↓
VISUAL + NARRATIVE HUMOUR IDEATION
      ↓
MULTIPLE HUMOUR CANDIDATES
      ↓
CAPTION / TEMPLATE ADAPTATION
      ↓
MULTIMODAL HUMOUR JUDGE
      ↓
REPETITION + MEMORY CHECK
      ↓
RENDER
      ↓
POST
      ↓
PERFORMANCE MEMORY
      ↓
BETTER FUTURE SELECTION
```

The system should deliberately separate:

```text
WHAT IS HAPPENING?
WHAT IS FUNNY ABOUT IT?
WHICH MEME FORMAT EXPRESSES THAT?
HOW SHOULD THE JOKE BE WRITTEN?
IS THE RESULT ACTUALLY GOOD?
HAVE WE DONE THIS TOO MANY TIMES?
```

---

# 2. RESEARCH BASIS: HUMORSKILLS

## 2.1 What the research says

The paper argues that humour requires more than linguistic pattern matching.

It identifies capabilities including:

- cognitive reasoning;
- social understanding;
- creativity;
- audience understanding;
- cultural knowledge;
- multiple perspectives;
- awareness of what is socially appropriate;
- observation;
- surprise;
- relating situations to broader human experiences.

The paper's system deliberately uses divergent and convergent creativity stages.

The basic workflow is:

```text
observation
    ↓
humorous ideation
    ↓
narrative / conflict extrapolation
    ↓
generate many captions
    ↓
rank them with a humour-focused agent
```

This is the most important architectural lesson from the paper.

Do not collapse all of those stages into one prompt.

---

# 3. ADAPTING THE PAPER TO MEMES

The paper works primarily from an image and generates captions.

Our system starts from a **topic** and must choose a meme template.

Therefore we extend the research architecture:

```text
TOPIC
  ↓
TOPIC DETAIL EXTRACTION
  ↓
COMEDIC OPPORTUNITY
  ↓
TEMPLATE RETRIEVAL
  ↓
TEMPLATE VISUAL DETAIL EXTRACTION
  ↓
VISUAL HUMOUR IDEATION
  ↓
NARRATIVE / CONFLICT EXTRAPOLATION
  ↓
HUMOUR ANGLE GENERATION
  ↓
CAPTION GENERATION
  ↓
HUMOUR RANKING
```

The template becomes the equivalent of the research paper's input image.

This is important:

> The selected meme template is not merely a background image. It has a visual grammar that constrains what jokes work.

---

# 4. SYSTEM ARCHITECTURE

Recommended project structure:

```text
agent/
│
├── nodes/
│   ├── discover.py                 # EXISTING — DO NOT REBUILD
│   ├── meme_opportunity.py
│   ├── meme_select.py
│   ├── meme_generate.py
│   └── meme_judge.py
│
├── meme/
│   │
│   ├── __init__.py
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── imgflip.py
│   │   └── justmeme.py             # optional provider
│   │
│   ├── templates/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── ingestion.py
│   │   ├── retrieval.py
│   │   ├── ranking.py
│   │   ├── semantics.py
│   │   └── cooldown.py
│   │
│   ├── humour/
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   ├── observation.py
│   │   ├── ideation.py
│   │   ├── narrative.py
│   │   ├── generation.py
│   │   ├── caption.py
│   │   ├── ranking.py
│   │   └── safety.py
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── usage.py
│   │   ├── repetition.py
│   │   └── performance.py
│   │
│   └── renderer/
│       ├── __init__.py
│       └── render.py
│
├── skills/
│   └── humour/
│       ├── SKILL.md
│       ├── mechanisms.md
│       ├── audience.md
│       └── examples.md
│
└── data/
    └── meme_templates/
```

Use the project's existing conventions if the repository has an established structure.

Do not blindly create this exact structure if equivalent modules already exist.

---

# 5. TEMPLATE PROVIDER

## 5.1 Primary provider: Imgflip

Use the official Imgflip API:

https://imgflip.com/api

The current API exposes:

- `/get_memes`
- `/caption_image`
- `/search_memes` — premium
- `/get_meme` — premium
- `/automeme` — premium
- `/ai_meme` — premium

The free `/get_memes` endpoint returns popular captionable meme templates. Imgflip documents that its returned list can change and currently describes the result as popular memes ordered by recent caption usage.

The API is REST + JSON.

The free meme-generation endpoint is `/caption_image`.

Do NOT use Imgflip's AI meme endpoint as the primary humour engine.

We are explicitly building our own humour intelligence.

Imgflip should primarily be:

```text
template provider
+
renderer
```

not:

```text
entire humour brain
```

---

# 6. IMGFLIP INTEGRATION

## Fetch templates

Use:

```text
GET https://api.imgflip.com/get_memes
```

The response contains:

```text
id
name
url
width
height
box_count
```

Store those fields.

Do not assume the API response schema can never gain fields.

---

# 7. TEMPLATE REGISTRY

Do NOT use the live Imgflip list directly every time a meme is generated.

Maintain a local persistent registry.

Reason:

The system needs memory.

It needs to know:

```text
which templates exist
what they mean
what humour works with them
when they were last used
how often they were used
how well they performed
```

---

# 8. TEMPLATE DATABASE

Use the existing project's database if one exists.

If there is no suitable persistent store, create a small meme-template persistence layer.

Suggested schema:

```text
meme_templates

id
provider
provider_template_id

name
image_url

width
height
box_count

semantic_format
visual_grammar

humour_mechanisms
best_for
bad_for

caption_structure
text_constraints

tags

popularity_score
freshness_score

times_selected
times_rendered
times_posted

last_used_at
cooldown_until

average_humour_score
average_engagement_score

active

created_at
updated_at
```

---

# 9. TEMPLATE SEMANTICS

Every template should eventually have semantic metadata.

Example:

```json
{
  "name": "Drake",
  "semantic_format": "comparison",
  "visual_grammar": {
    "panel_1": "reject",
    "panel_2": "approve"
  },
  "humour_mechanisms": [
    "contrast",
    "preference",
    "irony"
  ],
  "best_for": [
    "old vs new",
    "bad vs good",
    "traditional workflow vs AI workflow",
    "choosing between tools"
  ],
  "bad_for": [
    "serious announcements",
    "long explanations"
  ],
  "caption_structure": {
    "text_areas": 2,
    "short_text_preferred": true
  }
}
```

Another:

```json
{
  "name": "This Is Fine",
  "semantic_format": "underreaction",
  "visual_grammar": {
    "situation": "character remains calm during obvious disaster"
  },
  "humour_mechanisms": [
    "understatement",
    "irony",
    "escalation"
  ],
  "best_for": [
    "bugs",
    "production failures",
    "AI hallucinations",
    "startup chaos",
    "broken infrastructure"
  ]
}
```

Another:

```json
{
  "name": "Two Buttons",
  "semantic_format": "impossible_choice",
  "visual_grammar": {
    "character": "forced to choose between two options"
  },
  "humour_mechanisms": [
    "choice",
    "conflict",
    "tradeoff"
  ],
  "best_for": [
    "developer decisions",
    "AI model comparisons",
    "tool choices",
    "contradictory requirements"
  ]
}
```

---

# 10. DO NOT MANUALLY ANNOTATE 1 MILLION TEMPLATES

The full Imgflip catalogue is huge.

Do not build a giant manual database.

Start with:

```text
top popular templates
+
curated templates
+
templates discovered later
```

A practical initial target:

```text
50–150 templates
```

Then progressively enrich metadata.

---

# 11. TEMPLATE SEMANTIC ENRICHMENT

For each new template, use a vision-capable model to inspect the template and produce:

```text
template meaning
visual structure
number of panels
text locations
character roles
emotional expression
likely comedic situations
humour mechanisms
best topics
bad topics
```

The output should be stored.

Do not repeat this expensive analysis on every generation.

This is a **one-time / infrequent enrichment task**.

---

# 12. TEMPLATE RETRIEVAL

When a topic arrives:

```text
topic
+
topic category
+
humour angle
+
desired tone
```

retrieve approximately:

```text
15–30 candidate templates
```

Do not immediately ask the LLM to choose from 1,000 templates.

---

# 13. TEMPLATE FILTERING

Remove templates that:

```text
were used too recently
are inactive
are broken
have bad dimensions
are unsafe
have insufficient text space
are incompatible with the desired humour mechanism
are already overused
```

---

# 14. TEMPLATE REPETITION

Maintain a cooldown.

Example:

```text
same template:
minimum 5 posts between uses
```

But do not hard-code this forever.

Make it configurable.

Example:

```python
MEME_TEMPLATE_COOLDOWN_POSTS = 5
```

For highly overused templates:

```text
Drake
Distracted Boyfriend
This Is Fine
```

consider longer cooldowns.

---

# 15. REPETITION MUST BE MORE THAN TEMPLATE NAME

Avoid:

```text
Drake
↓
different Drake
↓
different Drake
```

But also avoid:

```text
Drake comparison
↓
Two Buttons comparison
↓
Distracted Boyfriend comparison
```

These are technically different templates but essentially the same joke format.

Track:

```text
template repetition
format repetition
humour mechanism repetition
topic repetition
joke pattern repetition
```

---

# 16. HUMOUR MECHANISMS

Create a controlled vocabulary.

Initial mechanisms:

```text
absurdity
irony
contrast
understatement
overstatement
expectation_vs_reality
role_reversal
misdirection
incongruity
self_deprecation
observational
social_comparison
false_equivalence
escalation
deadpan
sarcasm
parody
wordplay
double_meaning
relatable_struggle
insider_reference
status_inversion
literal_interpretation
analogy
callback
```

Do not force a mechanism if it doesn't fit the topic.

The humour classifier should be allowed to say:

```text
NONE
```

---

# 17. MEME OPPORTUNITY DETECTOR

Not every topic should become a meme.

Create:

```python
meme_opportunity(topic) -> MemeOpportunity
```

Output:

```json
{
  "is_meme_worthy": true,
  "confidence": 0.87,
  "humour_potential": 8,
  "recommended_mechanisms": [
    "irony",
    "contrast"
  ],
  "reason": "The event creates a strong contrast between developer expectations and actual behaviour."
}
```

---

# 18. MEME OPPORTUNITY RULES

Strong meme candidates often contain:

```text
absurdity
unexpected behaviour
developer pain
AI hype
AI failure
ridiculous product behaviour
contradiction
strong before/after
unexpected benchmark result
human-vs-AI contrast
industry irony
relatable workflow pain
```

Weak candidates:

```text
routine product update
minor API change
dry corporate announcement
complex research detail with no relatable hook
sensitive tragedy
serious safety incident
```

The system should be able to say:

```text
NO MEME
```

This is a feature, not a failure.

---

# 19. TOPIC NORMALISATION

Before humour generation, produce:

```text
event
actors
action
impact
why people care
unexpected element
human consequence
developer consequence
potential contradiction
potential absurdity
```

Example:

```json
{
  "event": "new AI coding agent gains rapid adoption",
  "unexpected_element": "developers are delegating increasingly large parts of coding",
  "human_angle": "people who insisted they would never use AI are now using it",
  "developer_angle": "manual coding vs agent delegation",
  "contradiction": "more code written by people who type less code"
}
```

This gives the humour engine material.

---

# 20. HUMOUR SKILL

Create a dedicated skill:

```text
skills/humour/SKILL.md
```

The skill must be based on the research paper:

https://arxiv.org/html/2502.07981v1

The skill should **not** simply say:

> Be funny.

It should define a repeatable cognitive workflow.

---

# 21. HUMOUR SKILL — STAGE 1: OBSERVATION

The paper's first stage is **Visual Detail Extraction**.

Adapt this to meme generation.

Input:

```text
topic
template image
template metadata
```

Output:

```text
literal visual observations
visual structure
facial expressions
objects
relationships
text areas
visual asymmetry
unexpected visual details
```

Do not jump directly to jokes.

---

# 22. OBSERVATION PROMPT BEHAVIOUR

The observation agent should answer:

```text
WHO/WHAT is present?
WHAT is happening?
WHERE is it happening?
WHAT is visually unusual?
WHAT relationship exists between the visual elements?
WHAT emotion does the image communicate?
WHAT is the obvious interpretation?
WHAT is a less obvious interpretation?
```

Important:

Separate:

```text
OBSERVATION
```

from:

```text
INTERPRETATION
```

Do not hallucinate facts about the image.

---

# 23. HUMOUR SKILL — STAGE 2: VISUAL HUMOUR IDEATION

The paper explicitly adds a separate stage for finding potentially humorous visual elements.

Implement:

```python
ideate_visual_humour(observation) -> list[HumourAngle]
```

Look for:

```text
odd proportions
facial expressions
body language
visual contrast
unexpected objects
social relationships
power relationships
emotional mismatch
visual absurdity
```

For meme templates, also inspect:

```text
panel relationship
character role
reaction
direction of gaze
emotional expression
text-box position
```

---

# 24. HUMOUR SKILL — STAGE 3: NARRATIVE / CONFLICT EXTRAPOLATION

This is one of the most important parts of the paper.

Do not restrict the joke to the literal image.

The paper describes finding narratives outside the image that can be related to it through analogy.

For this AI influencer, use:

```text
topic
+
developer culture
+
AI culture
+
internet culture
+
work culture
+
startup culture
+
relatable human situations
```

Example:

```text
Template:
person struggling between two buttons

Literal:
person choosing

Topic:
developer choosing between models

Narrative extrapolation:
"me choosing between the model that is smarter and the model whose API doesn't randomly explode"
```

The joke becomes relatable rather than merely descriptive.

---

# 25. NARRATIVE ANGLE TYPES

Generate possible analogies from:

```text
developer life
student life
startup life
workplace behaviour
internet culture
AI hype
AI anxiety
tool addiction
procrastination
technical debt
shipping
bugs
documentation
meetings
deadlines
performance anxiety
career anxiety
```

Use only what naturally fits the audience/persona.

Do not force Gen-Z slang into every joke.

---

# 26. HUMOUR SKILL — DIVERGENT PHASE

The research explicitly favours quantity and diversity before ranking.

Follow that principle.

Generate multiple angles.

Target:

```text
8–12 humour angles
```

Each angle should be meaningfully different.

Example:

```text
Angle 1: irony
Angle 2: developer pain
Angle 3: absurd escalation
Angle 4: social contradiction
Angle 5: self-deprecation
Angle 6: understatement
Angle 7: analogy
Angle 8: role reversal
```

Do not produce:

```text
8 slightly different versions of the same joke.
```

---

# 27. HUMOUR SKILL — CAPTION GENERATION

The research generates a large candidate pool before ranking.

For this system:

```text
8–12 humour angles
×
2–3 caption variants
```

Target:

```text
20–30 raw captions
```

This is deliberately more than the final output.

Do not render every candidate through Imgflip.

Generate text candidates first.

---

# 28. CAPTION TYPES

Generate at least two broad classes when appropriate:

## Image/template-focused

The joke directly uses the visual structure.

Example:

```text
Drake:
manual debugging
AI agent fixing it
```

## Narrative-driven

The visual acts as a metaphor for a broader situation.

Example:

```text
This Is Fine:
me watching my AI agent rewrite half the codebase
```

The research specifically distinguishes image-focused and narrative-driven captions and emphasises variety.

---

# 29. HUMOUR GENERATION RULES

The generator should favour:

```text
specificity
surprise
brevity
recognisable human behaviour
clear setup
unexpected punchline
natural language
cultural relevance
template compatibility
```

Avoid:

```text
explaining the joke
"POV:" everywhere
"bro really said..."
"AI is taking over 😂"
"this is literally me"
"we are cooked 💀"
generic corporate humour
generic inspirational language
obvious AI jokes
```

Slang should be used only when it genuinely improves the joke.

---

# 30. HUMOUR PERSONAS

The skill may generate from multiple internal perspectives.

Use:

```text
OBSERVATIONAL
DEADPAN
ABSURDIST
CYNICAL
SELF-DEPRECATING
DEVELOPER
INTERNET-NATIVE
UNDERSTATED
```

These are not separate permanent personalities.

They are **idea-generation lenses**.

Do not make every final meme sound like a different person.

The final selected joke must still match the influencer's established voice.

---

# 31. HUMOUR SKILL — CONVERGENT PHASE

After generating the candidate pool:

```text
20–30 candidates
       ↓
quality filters
       ↓
10 candidates
       ↓
humour judge
       ↓
top 3–5
       ↓
final selection
```

This mirrors the paper's divergent → convergent creative process.

---

# 32. HUMOUR JUDGE

The judge must NOT simply score:

```text
funny: yes/no
```

Use multiple dimensions.

Suggested:

```text
humour_score
originality_score
surprise_score
relevance_score
template_fit_score
relatability_score
brevity_score
naturalness_score
cultural_fit_score
clarity_score
```

Penalties:

```text
generic_ai_penalty
overused_joke_penalty
forced_slang_penalty
explanation_penalty
repetition_penalty
cringe_penalty
```

---

# 33. HUMOUR JUDGE INPUT

The judge should receive:

```text
TOPIC
+
TOPIC CONTEXT
+
TEMPLATE IMAGE
+
TEMPLATE SEMANTICS
+
CAPTION
+
RECENT MEME HISTORY
```

The judge should NOT judge the caption in isolation.

A caption can be funny in plain text and terrible on the selected meme.

---

# 34. FINAL SCORE

Suggested starting formula:

```python
final_score = (
    humour_score * 0.25
    + template_fit_score * 0.20
    + originality_score * 0.15
    + relevance_score * 0.10
    + surprise_score * 0.10
    + relatability_score * 0.08
    + naturalness_score * 0.07
    + clarity_score * 0.05
)
```

Then subtract:

```python
final_score -= generic_ai_penalty
final_score -= repetition_penalty
final_score -= forced_slang_penalty
```

Keep the raw dimensions in memory.

Do not only store the final number.

---

# 35. NO-MEME THRESHOLD

The humour judge should be allowed to reject everything.

Example:

```text
if best_score < MIN_MEME_SCORE:
    return NO_MEME
```

Do not force a meme because the system entered the meme node.

---

# 36. TEMPLATE SELECTION SCORE

Use a separate ranking formula.

Example:

```python
template_score = (
    semantic_fit * 0.30
    + humour_mechanism_fit * 0.20
    + visual_fit * 0.15
    + popularity * 0.10
    + freshness * 0.10
    + historical_performance * 0.15
)
```

Subtract:

```python
template_score -= repetition_penalty
template_score -= recent_format_penalty
```

The weights should be configurable.

---

# 37. TEMPLATE VS JOKE SELECTION

Do not permanently decide:

```text
topic → template → joke
```

The system should be able to explore:

```text
topic
  ↓
humour angles
  ↓
candidate template families
  ↓
template + angle combinations
```

For difficult topics, compare:

```text
template A + angle 1
template A + angle 2
template B + angle 1
template B + angle 3
```

This prevents a bad template choice from contaminating the entire generation process.

---

# 38. TEMPLATE FAMILY

Store a higher-level format:

```text
comparison
reaction
choice
escalation
underreaction
before_after
role_reversal
confession
expectation_reality
visual_pun
```

This allows repetition control.

Example:

```text
Monday:
Drake → comparison

Tuesday:
Two Buttons → choice

Wednesday:
Distracted Boyfriend → comparison
```

The third post should receive a comparison-family penalty even though the template is different.

---

# 39. HUMOUR MECHANISM MEMORY

Store the humour mechanism.

Example:

```text
post 1:
ironic_contrast

post 2:
ironic_contrast

post 3:
ironic_contrast
```

Penalise the fourth.

This prevents the agent from producing:

```text
different meme
same joke
```

---

# 40. MEME MEMORY TABLE

Suggested:

```text
meme_usage

id
post_id

template_id
template_family

humour_mechanism

topic_id
topic_category

caption
humour_score
judge_score

published_at

engagement_metrics

created_at
```

---

# 41. TEMPLATE PERFORMANCE TABLE

Suggested:

```text
meme_template_performance

template_id

times_used
times_posted

average_humour_score
average_engagement

shares
likes
comments
saves

last_used_at

updated_at
```

Use this to improve future selection.

---

# 42. JOKE MEMORY

Store:

```text
joke_signature
semantic_embedding
humour_mechanism
template_family
caption
topic
```

The goal is not exact duplicate detection only.

Detect semantically similar jokes.

For example:

```text
"me letting AI write the whole function"

vs

"when you realise the AI agent wrote the entire thing"
```

These are effectively the same joke.

Apply a similarity penalty.

---

# 43. EMBEDDING-BASED REPETITION

If the project already has an embedding system, reuse it.

Do not introduce a new embedding provider unnecessarily.

Store embeddings for:

```text
caption
topic
humour angle
```

Then compare new candidates against recent history.

Suggested:

```text
high similarity → strong penalty
medium similarity → moderate penalty
low similarity → no penalty
```

The exact threshold should be configurable and tested.

---

# 44. TEMPLATE COOLDOWN

At minimum:

```python
same_template_cooldown_posts = 5
same_template_family_cooldown_posts = 2
same_humour_mechanism_cooldown_posts = 2
```

These are starting values only.

Make them configuration values.

Do not hard-code assumptions into business logic.

---

# 45. DAILY DIVERSITY

If multiple memes are generated in one day, enforce diversity.

For example:

```text
no more than 1 identical template/day
no more than 2 templates from same family/day
no more than 2 identical humour mechanisms/day
```

Again, configuration.

---

# 46. HUMOUR SKILL FILE

`skills/humour/SKILL.md` should document:

```text
purpose
audience
workflow
observation
visual humour ideation
narrative extrapolation
angle generation
caption generation
ranking
cultural judgement
repetition awareness
style rules
failure modes
```

The skill should explain the process in operational terms.

It should NOT contain one gigantic static prompt.

Break prompts into stages.

---

# 47. HUMOUR SKILL PROMPT CONTRACTS

Each stage should have a clear input/output contract.

Example:

```text
Observation
INPUT:
- template image
- topic

OUTPUT:
- observations[]
- visual_relationships[]
- notable_details[]
```

Then:

```text
Humour Ideation
INPUT:
- observations
- topic

OUTPUT:
- humour_angles[]
```

Then:

```text
Narrative Extrapolation
INPUT:
- topic
- observations
- humour_angles

OUTPUT:
- analogies[]
- conflicts[]
- relatable_situations[]
```

Then:

```text
Caption Generation
INPUT:
- selected template
- humour angles
- narratives

OUTPUT:
- captions[]
```

Then:

```text
Judge
INPUT:
- template
- caption
- topic
- recent history

OUTPUT:
- score
- reasoning
- failure flags
```

---

# 48. STRUCTURED OUTPUT

Prefer structured JSON / Pydantic models if the existing project uses them.

Example:

```python
class HumourAngle:
    mechanism: str
    premise: str
    setup: str
    punchline_direction: str
    relatability: float
```

Example:

```python
class MemeCandidate:
    template_id: str
    humour_mechanism: str
    caption: str
    score: float
```

Use the project's existing schema conventions if present.

---

# 49. TOPIC → HUMOUR ANGLES

Example input:

```text
New AI coding agent becomes extremely popular.
```

Possible angles:

```text
1. developers pretending they still understand their own code
2. manual coding becoming the "old way"
3. AI agent writing code faster than the developer can review it
4. developer delegating everything
5. dependency on AI becoming absurd
6. people who hated AI suddenly using it
```

The system should then map these to template families.

---

# 50. TEMPLATE SELECTION EXAMPLE

Suppose:

```text
angle:
developers increasingly delegating coding
```

Possible templates:

```text
Drake
Two Buttons
This Is Fine
Distracted Boyfriend
Galaxy Brain
```

Ranking might produce:

```text
Drake:
semantic fit 9
humour fit 9
visual fit 9
repetition 0
→ 9.1

Two Buttons:
semantic fit 7
humour fit 8
visual fit 8
→ 7.7

This Is Fine:
semantic fit 5
humour fit 6
→ 5.8
```

Select Drake.

---

# 51. CAPTION GENERATION EXAMPLE

Template:

```text
Drake
```

Angle:

```text
old coding workflow vs AI agent
```

Do not generate:

```text
TOP:
Old coding

BOTTOM:
AI coding
```

That's technically correct and painfully unfunny.

Generate multiple variants:

```text
writing the function myself
letting the agent "handle one small thing"
```

```text
reading the 400-line function
asking the agent who wrote it
```

```text
spending 45 minutes debugging
asking the agent to fix the bug it created
```

The system then judges them.

---

# 52. AI-ISHNESS DETECTOR

Add an explicit penalty for captions that sound machine-written.

Flags:

```text
generic phrasing
over-explaining
forced setup
excessive punctuation
unnecessary emoji
LinkedIn-style wording
obvious "AI vs human" framing
generic "POV" constructions
too many slang markers
```

The humour judge should be able to say:

```text
ai_ish: true
```

and assign a penalty.

---

# 53. SLANG

Do not assume:

```text
Gen Z = slang everywhere.
```

The paper studies a Gen-Z audience, but your influencer's exact audience may differ.

Treat audience as configurable.

Store:

```text
audience_profile
```

with:

```text
age_band
platform
technicality
humour_style
slang_tolerance
cultural_context
```

The humour skill should adapt to this.

---

# 54. CULTURAL CONTEXT

The paper emphasises audience understanding and cultural knowledge.

Therefore the humour skill should know:

```text
platform culture
AI community culture
developer culture
internet culture
current memes
current references
```

But don't force references into jokes.

A cultural reference should be used only when it improves the punchline.

---

# 55. CURRENT-MEME FRESHNESS

Template popularity and cultural freshness are different.

A template can be:

```text
popular but stale
```

or:

```text
less popular but currently relevant
```

Store both:

```text
popularity_score
freshness_score
```

Freshness can later be updated from:

```text
template provider
meme discovery source
manual curation
social performance
```

---

# 56. ORIGINAL CAPTION REQUIREMENT

Do not simply copy existing captions from template websites.

The system should use:

```text
template
+
topic
+
humour generation
```

to create original caption text.

The template provider is supplying the visual format.

---

# 57. LEGAL / PROVENANCE CONSIDERATION

Do not build the system around scraping finished memes from random social accounts and modifying them.

Prefer:

```text
recognised meme template
+
original generated caption
```

Maintain provider metadata:

```text
provider
provider_template_id
source_url
```

Do not claim ownership of template imagery.

If the project has a commercial publishing use case, review the provider's current terms and the rights associated with each template/source before relying on it at scale.

---

# 58. RENDERING

Primary renderer:

```text
Imgflip /caption_image
```

Official documentation:

https://imgflip.com/api

The endpoint accepts a template ID and text.

For templates with more than two text boxes, use the `boxes` structure rather than assuming `text0` and `text1`.

The renderer should receive:

```json
{
  "template_id": "...",
  "boxes": [
    {
      "text": "..."
    }
  ]
}
```

or the project's equivalent provider-specific representation.

Do not hard-code a two-box assumption.

---

# 59. RENDERING SHOULD BE A PROVIDER ABSTRACTION

Create:

```python
class MemeRenderer:
    async def render(
        self,
        template_id,
        text_boxes,
        options=None
    ):
        ...
```

Then:

```text
ImgflipRenderer
JustMemeRenderer
LocalRenderer
```

can exist independently.

The humour system should not care which provider renders the image.

---

# 60. PROVIDER FALLBACK

If Imgflip fails:

```text
do not regenerate the joke
```

Instead:

```text
retry provider
↓
fallback renderer/provider
↓
if unavailable → no meme
```

Do not waste LLM calls simply because an image API timed out.

---

# 61. MEME GENERATION STATE

A meme-generation run should have a state object roughly like:

```python
MemeGenerationState(
    topic=...,
    opportunity=...,
    observations=...,
    humour_angles=...,
    template_candidates=...,
    selected_template=...,
    captions=...,
    ranked_candidates=...,
    final_candidate=...,
    rendered_asset=...,
)
```

Use the project's existing state model if one exists.

---

# 62. FAILURE MODES

The system must explicitly handle:

```text
no meme opportunity
no suitable templates
template metadata unavailable
humour generation failure
all captions score too low
caption too long
caption doesn't fit template
provider rendering failure
template recently used
joke too similar to previous joke
unsafe content
cultural mismatch
```

Every failure should result in:

```text
NO MEME
```

or a controlled fallback.

Never crash the whole agent.

---

# 63. COST CONTROL

This system is specifically replacing expensive video generation.

Keep it cheap.

Use expensive vision/model calls only where they provide meaningful value.

## Cache permanently:

```text
template semantic analysis
template visual grammar
template tags
template metadata
```

## Cache within a generation:

```text
topic analysis
visual observations
humour angles
```

Do not call the vision model repeatedly on the same template image.

---

# 64. MODEL ROUTING

Do not assume one model must do everything.

Possible routing:

```text
cheap text model:
topic normalisation
humour angle generation

vision-capable model:
template observation
final meme evaluation

stronger model:
final humour ranking
```

Use the project's existing model provider abstraction.

Do not introduce a new provider solely for this feature unless necessary.

---

# 65. HUMOUR QUALITY OVER COST

Do not reduce the system to:

```text
cheap model → one joke → publish
```

Better:

```text
cheap model:
20 ideas

stronger model:
rank 20

vision model:
judge top 3
```

This can still be substantially cheaper than video generation while providing much better quality.

---

# 66. HUMOUR JUDGE SHOULD BE MULTIMODAL

This is important.

The final judge must see the actual rendered meme if possible.

Pipeline:

```text
caption candidate
     ↓
render preview
     ↓
vision judge
     ↓
final score
```

For cost efficiency:

```text
20 text candidates
↓
rank to 3
↓
render only 3
↓
multimodal judge
```

Do not render 30 images.

---

# 67. FINAL MULTIMODAL CHECK

Judge:

```text
Does the text fit the image?
Does the visual make the joke better?
Does the caption use the template's structure?
Is the punchline immediately understandable?
Is the text too long?
Is there accidental ambiguity?
Does it look like a generic meme?
Does it feel current?
Is the joke actually funny?
```

---

# 68. HUMAN-LIKE HUMOUR QUALITY

Do not optimise solely for:

```text
semantic relevance
```

A relevant meme can still be boring.

The final judge should favour:

```text
surprise
specificity
social insight
relatability
incongruity
brevity
```

when appropriate.

---

# 69. PERFORMANCE LEARNING

After publication, store:

```text
impressions
likes
comments
shares
saves
reposts
engagement_rate
```

If available.

Then associate those metrics with:

```text
template
template family
humour mechanism
caption style
topic type
```

---

# 70. LEARNING LOOP

Future selection:

```text
template_score
+
humour_fit
+
freshness
+
historical_performance
-
repetition
```

Example:

```text
This Is Fine
historical engagement = high

Drake
historical engagement = average

Two Buttons
historical engagement = very high
```

Then Two Buttons gets a modest performance boost.

Do NOT let historical performance dominate forever.

Otherwise the agent converges on the same two memes.

---

# 71. EXPLORATION VS EXPLOITATION

Reserve some probability for exploration.

Example:

```text
80%:
high-confidence templates

20%:
new / underused templates
```

Make configurable.

This prevents template monoculture.

---

# 72. TEMPLATE HEALTH

A template should be marked:

```text
active
inactive
broken
stale
unsafe
```

A failed render should not permanently delete the template.

Store the failure reason.

---

# 73. TEMPLATE INGESTION JOB

Add an ingestion operation:

```python
sync_meme_templates()
```

It should:

1. fetch provider templates;
2. upsert metadata;
3. preserve existing semantic annotations;
4. update popularity;
5. detect new templates;
6. mark missing templates carefully;
7. avoid wiping usage history.

Do not reset:

```text
last_used_at
times_used
performance
semantic metadata
```

during sync.

---

# 74. TEMPLATE ENRICHMENT JOB

Separate:

```python
sync_meme_templates()
```

from:

```python
enrich_meme_templates()
```

This matters.

Syncing is cheap.

Semantic vision analysis may be expensive.

Do not run semantic enrichment every time the provider list changes.

Only enrich:

```text
new template
missing metadata
explicitly refreshed template
```

---

# 75. HUMOUR SKILL TEST DATA

Create a small fixture set.

Example:

```text
topic:
AI coding agent gains popularity

template:
Drake

expected family:
comparison

possible mechanisms:
contrast
irony
developer relatability
```

Another:

```text
topic:
AI model experiences embarrassing production outage

template:
This Is Fine

expected family:
underreaction

possible mechanisms:
irony
understatement
escalation
```

Another:

```text
topic:
developers choose between faster model and cheaper model

template:
Two Buttons

expected family:
choice

possible mechanisms:
conflict
tradeoff
absurdity
```

---

# 76. UNIT TESTS

Test:

```text
template parsing
template upsert
template metadata preservation
cooldown
repetition detection
template family repetition
humour mechanism repetition
candidate scoring
NO MEME threshold
caption length validation
provider payload generation
```

---

# 77. HUMOUR SKILL TESTS

Mock the model outputs.

Verify:

```text
observation stage returns structured observations
ideation returns multiple distinct angles
narrative stage produces analogies
generation produces multiple captions
ranking selects valid captions
repetition penalty works
judge can reject all candidates
```

---

# 78. LIVE TESTS

Do not spam the provider.

Run a small smoke test.

Test:

```text
1. fetch Imgflip templates
2. select one known template
3. render one test meme
4. validate returned URL
5. do not publish
```

If credentials are absent:

```text
SKIP
```

not fake PASS.

---

# 79. END-TO-END DRY RUN

Add a dry-run mode:

```bash
python -m ... --meme-dry-run
```

or whatever convention the repository uses.

Dry run should:

```text
use real topic
↓
select meme
↓
generate captions
↓
rank
↓
render
↓
save result locally / temporary output
↓
DO NOT POST
```

Print:

```text
TOPIC
MEME OPPORTUNITY
HUMOUR MECHANISM
TOP TEMPLATE CANDIDATES
SELECTED TEMPLATE
GENERATED CAPTIONS
SCORES
FINAL CAPTION
REPETITION CHECK
RENDER RESULT
```

---

# 80. EXAMPLE DRY RUN

```text
MEME DRY RUN
============

Topic:
New AI coding agent gains 8,000 GitHub stars.

Meme opportunity:
YES
Confidence:
0.91

Humour mechanisms:
- developer relatability
- contrast
- irony

Template candidates:
1. Drake                 8.9
2. Two Buttons           8.1
3. This Is Fine          6.9
4. Distracted Boyfriend  6.5

Selected:
Drake

Humour angles:
1. manual coding → agent delegation
2. pretending to understand generated code
3. people who hated AI now using it

Generated:
20 captions

Top 3:
...

Multimodal scores:
...

Repetition:
PASS

Render:
PASS

Publishing:
SKIPPED — DRY RUN
```

---

# 81. OBSERVABILITY

Log enough to debug bad humour.

Store:

```text
topic_id
generation_id
template_candidates
selected_template
humour_angles
candidate_scores
rejected_candidates
final_caption
render_result
```

Do not log:

```text
API secrets
passwords
private credentials
```

---

# 82. DEBUGGING BAD MEMES

When a meme performs badly, the system should let us inspect:

```text
Was the topic unsuitable?
Was the template wrong?
Was the humour mechanism wrong?
Was the caption weak?
Was the joke too predictable?
Was the meme overused?
Was the visual relationship weak?
```

This is why stages must remain separate.

---

# 83. DON'T TRAIN A MODEL YET

Do NOT immediately fine-tune a humour model.

The paper discusses fine-tuning and Gen-Z examples, but your system does not need training in v1.

Start with:

```text
structured skill
+
good prompting
+
multiple candidates
+
ranking
+
memory
+
performance feedback
```

Only consider fine-tuning once enough real examples have been collected.

---

# 84. FUTURE TRAINING DATA

Store:

```text
topic
template
humour mechanism
caption candidates
judge scores
human approval/rejection
engagement
```

Eventually this becomes:

```text
successful meme dataset
```

and:

```text
failed meme dataset
```

This is much more valuable than randomly collecting internet memes.

---

# 85. HUMAN FEEDBACK

If the product eventually has a human approval step, capture:

```text
approved
rejected
edited
reason
```

Especially:

```text
"not funny"
"too forced"
"wrong template"
"too long"
"too cringe"
"too generic"
"too repetitive"
```

These labels are gold for future improvement.

---

# 86. DO NOT COPY THE PAPER BLINDLY

The paper targets:

```text
Gen-Z Instagram caption humour
```

Your influencer may operate on:

```text
X
LinkedIn
Instagram
```

and may target:

```text
AI builders
developers
students
startup people
tech audience
```

Therefore:

```text
paper architecture = foundation
```

not:

```text
paper audience = automatically our audience
```

The skill must expose audience configuration.

---

# 87. HUMOUR STYLE CONFIG

Create something like:

```yaml
humour:
  audience:
    technicality: high
    slang_tolerance: medium
    internet_native: high

  style:
    concise: true
    deadpan: true
    absurdity: medium
    sarcasm: medium
    wholesome: low

  generation:
    angle_count: 10
    caption_count: 24
    finalists: 3

  repetition:
    template_cooldown_posts: 5
    family_cooldown_posts: 2
    mechanism_cooldown_posts: 2
```

Use the project's existing configuration system.

---

# 88. HUMOUR SKILL — REQUIRED BEHAVIOUR

The skill should internally follow:

```text
1. Understand
2. Observe
3. Find unusual details
4. Find possible humorous interpretations
5. Extrapolate relatable narratives/conflicts
6. Generate diverse humour angles
7. Generate many captions
8. Adapt captions to template grammar
9. Rank
10. Inspect visually
11. Reject weak jokes
12. Check repetition
13. Render
14. Remember outcome
```

This is the core of the system.

---

# 89. IMPORTANT RESEARCH-INSPIRED DETAIL

The paper specifically reports that its visual-detail and visual-humour stages helped the system focus on meaningful visual abnormalities rather than merely describing obvious scene content.

Therefore the implementation should not ask:

```text
"Describe this meme."
```

and then immediately generate a caption.

Instead:

```text
"What is visually unusual here?"
"What relationship is visually funny?"
"What expectation does the image establish?"
"What could be subverted?"
```

This should be built into the humour skill.

---

# 90. IMPORTANT RESEARCH-INSPIRED DETAIL: NARRATIVE EXTRAPOLATION

Do not limit jokes to:

```text
what is literally in the image.
```

Ask:

```text
"What real-world situation has the same emotional/conflict structure?"
```

For an AI influencer this is particularly useful.

Example:

```text
visual:
person sweating while choosing

narrative:
developer choosing between:
- model that is smart
- model that doesn't bankrupt the API budget
```

The meme becomes culturally relatable.

---

# 91. IMPORTANT RESEARCH-INSPIRED DETAIL: DIVERSITY

The paper explicitly notes that variety matters because humour depends on surprise.

Therefore candidate generation must deliberately diversify:

```text
mechanism
angle
wording
narrative
reference
tone
```

Do not simply sample 20 temperature variants of the same joke.

---

# 92. IMPORTANT RESEARCH-INSPIRED DETAIL: RANKING

The paper uses a specialised humour-ranking agent.

Implement a dedicated judge.

Do not let the same generation prompt decide:

```text
"I wrote this, therefore it is funny."
```

Generation and evaluation should be separate calls/stages.

---

# 93. MEME SELECTION SHOULD ALSO BE JUDGED

The system should evaluate:

```text
Does this template amplify the joke?
```

not just:

```text
Does this template match the topic?
```

A semantically relevant template can still be visually wrong.

---

# 94. TEMPLATE VISUAL GRAMMAR

Store:

```text
roles
positions
expressions
panel relationships
text areas
expected reading order
```

Example:

```json
{
  "reading_order": [
    "top_left",
    "top_right"
  ],
  "character_role": "decision_maker",
  "emotional_state": "panic",
  "visual_conflict": true
}
```

This allows caption generation to respect the image.

---

# 95. CAPTION LENGTH

Implement validation.

For every template:

```text
max characters per text box
preferred characters per text box
max words
```

If exact visual constraints are unknown:

```text
use conservative defaults
```

Then inspect rendered output.

A joke that needs a paragraph is not a meme.

---

# 96. MEME QUALITY GATE

Before final output:

```text
[ ] meme-worthy topic
[ ] suitable template
[ ] original caption
[ ] humour score above threshold
[ ] template fit above threshold
[ ] not too similar to recent joke
[ ] template not recently used
[ ] no unsafe content
[ ] text fits
[ ] visual joke works
[ ] audience fit
```

If any critical gate fails:

```text
NO MEME
```

---

# 97. SAFETY / CULTURAL SANITY

The humour system should reject or carefully handle:

```text
tragedies
deaths
active disasters
serious personal suffering
protected-class targeting
sexual exploitation
graphic violence
harassment
defamatory claims
unverified allegations
```

Do not let "being edgy" become an excuse for reckless output.

The agent can still be witty without making a PR nightmare.

---

# 98. PROVIDER OPTIONS

## Primary

Imgflip:

https://imgflip.com/api

Use for:

```text
popular template retrieval
template IDs
meme rendering
```

Imgflip currently states that its free API supports getting top memes and making memes, while premium unlocks broader template search and AI meme features.

## Secondary

If a second provider is used, hide it behind:

```python
MemeProvider
```

Do not couple humour logic directly to Imgflip.

---

# 99. DO NOT USE IMGFLIP AI MEME AS THE MAIN SYSTEM

Imgflip currently provides:

```text
/automeme
/ai_meme
```

but those are Premium features.

More importantly, using them as the central intelligence would bypass the system being built here.

We want:

```text
our topic understanding
+
our humour skill
+
our template memory
+
our repetition system
+
our judge
```

then:

```text
Imgflip = renderer
```

---

# 100. API CREDENTIALS

If using Imgflip authenticated endpoints:

```env
IMGFLIP_USERNAME=
IMGFLIP_PASSWORD=
```

Use a dedicated API account.

Never commit credentials.

Never log credentials.

Never place credentials in URLs.

Use POST body authentication as required by the provider documentation.

---

# 101. DATABASE MIGRATION

If the project uses a database migration system:

Create migrations for:

```text
meme_templates
meme_usage
meme_performance
```

If equivalent tables already exist:

```text
extend them
```

Do not duplicate data models.

---

# 102. CACHE STRATEGY

Cache:

```text
template provider response
template images
template semantics
```

Do not repeatedly download the same template image.

Suggested cache key:

```text
provider:template_id
```

---

# 103. PROVIDER SYNC FREQUENCY

Template sync does not need to happen every post.

Suggested:

```text
daily
```

or:

```text
every few hours
```

depending on the existing scheduler.

Semantic enrichment:

```text
only when required
```

---

# 104. HUMOUR GENERATION FREQUENCY

Humour generation happens per candidate topic.

But expensive template analysis should not.

The architecture must distinguish:

```text
template knowledge
```

from:

```text
per-post humour generation
```

---

# 105. TESTING THE REPETITION SYSTEM

Create a deterministic test:

```text
history:
Drake used 2 posts ago

new candidate:
Drake

expected:
strong penalty / rejection
```

Another:

```text
history:
comparison, comparison

new candidate:
Two Buttons

expected:
family penalty
```

Another:

```text
history:
irony, irony

new candidate:
irony

expected:
mechanism penalty
```

---

# 106. TESTING JOKE SIMILARITY

Fixture:

```text
"me letting the AI write the code"
"me asking the AI to write everything"
```

Expected:

```text
high semantic similarity
```

The new joke should be penalised.

---

# 107. TESTING HUMOUR GENERATION

Mock the model and verify that:

```text
20+ candidates can be represented
multiple mechanisms exist
multiple angles exist
duplicates are removed
```

Do not require the unit test itself to prove that the joke is genuinely funny.

That requires human/performance evaluation.

---

# 108. TESTING THE FINAL JUDGE

Use fixed fixtures:

```text
obviously generic caption
good template-fitting caption
too-long caption
unrelated caption
repeated caption
```

Verify the judge flags them appropriately.

Do not overfit the scoring weights to one fixture.

---

# 109. LIVE DRY RUN REQUIREMENT

Before declaring implementation complete:

```text
run one real topic
↓
meme opportunity
↓
template retrieval
↓
humour generation
↓
ranking
↓
render
```

Do not publish.

The output should be inspected manually.

---

# 110. REQUIRED IMPLEMENTATION REPORT

After coding, report:

```text
1. Files changed
2. Database changes
3. Providers integrated
4. Template ingestion status
5. Humour skill stages implemented
6. Repetition system implemented
7. Judge implemented
8. Tests passed
9. Live dry-run result
10. Environment variables required
11. Known limitations
```

---

# 111. DO NOT TOUCH THE EXISTING DISCOVERY SYSTEM

The existing discovery engine is already done.

It already supplies topics from:

```text
Product Hunt
GitHub
Hacker News
research
news
other sources
```

The meme subsystem should consume the discovered candidate/topic object.

Do not duplicate source discovery.

---

# 112. EXPECTED INTERFACE WITH DISCOVERY

Something roughly like:

```python
meme_result = await meme_engine.process(topic)
```

Where:

```python
topic
```

is an existing discovery result.

Possible return:

```python
{
    "should_make_meme": True,
    "template_id": "...",
    "template_name": "Drake",
    "humour_mechanism": "contrast",
    "caption": {
        "top": "...",
        "bottom": "..."
    },
    "score": 8.4,
    "rendered_url": "...",
}
```

Adapt this to the existing codebase.

---

# 113. MEME ENGINE HIGH-LEVEL API

Recommended:

```python
class MemeEngine:

    async def assess_opportunity(topic):
        ...

    async def select_template(topic, humour_context):
        ...

    async def generate_candidates(topic, template):
        ...

    async def judge_candidates(topic, template, candidates):
        ...

    async def render(candidate):
        ...

    async def record_usage(result):
        ...
```

Do not force these exact method names if the repository has different conventions.

---

# 114. FINAL PIPELINE

The complete runtime path should be:

```text
existing discovery result
        ↓
MemeOpportunityDetector
        ↓
NO ───────────── YES
                  ↓
          Topic Normaliser
                  ↓
          Humour Context
                  ↓
        Template Retrieval
                  ↓
        Template Filtering
                  ↓
        Template Ranking
                  ↓
         Top 3–5 templates
                  ↓
       Humour Skill / Observation
                  ↓
       Visual Humour Ideation
                  ↓
    Narrative / Conflict Extrapolation
                  ↓
          8–12 angles
                  ↓
          20–30 captions
                  ↓
          Text-level ranking
                  ↓
              Top 3
                  ↓
           Render previews
                  ↓
        Multimodal humour judge
                  ↓
        Repetition / memory check
                  ↓
          FINAL MEME / NO MEME
                  ↓
               Publish
                  ↓
          Record performance
```

---

# 115. RECOMMENDED DEFAULTS

Use configuration rather than hard-coded values.

Suggested initial defaults:

```yaml
meme:
  enabled: true

  opportunity:
    minimum_confidence: 0.70

  templates:
    retrieval_count: 25
    ranking_count: 5
    template_cooldown_posts: 5
    family_cooldown_posts: 2

  humour:
    angle_count: 10
    raw_caption_count: 24
    finalists: 3

  quality:
    minimum_humour_score: 6.5
    minimum_template_fit: 6.0

  repetition:
    mechanism_cooldown_posts: 2
    similarity_penalty_enabled: true

  exploration:
    enabled: true
    exploration_rate: 0.20
```

These are starting values.

Tune them using actual performance.

---

# 116. IMPORTANT: NO FORCED MEMES

The highest-quality behaviour is:

```text
Topic → no meme.
```

when appropriate.

The agent should not believe:

```text
"Every discovered AI story must become a meme."
```

Instead:

```text
"Make a meme when the topic has a strong comedic opportunity."
```

---

# 117. IMPORTANT: NO TEMPLATE OBSESSION

The system must not repeatedly select:

```text
Drake
This Is Fine
Distracted Boyfriend
```

just because they have strong priors.

Popularity should be one factor.

Freshness + semantic fit + humour fit + historical performance + repetition should jointly determine selection.

---

# 118. IMPORTANT: NO GENERIC AI HUMOUR

Avoid:

```text
"AI is taking over 😂"
"POV: AI replaces you"
"me when ChatGPT..."
"bro really thought..."
"we are cooked"
```

unless the specific context genuinely makes it funny.

The system should prefer a **specific observation about the actual event**.

---

# 119. IMPORTANT: HUMOUR SHOULD COME FROM THE TOPIC

Example:

Bad:

```text
Topic:
new inference optimisation

Meme:
AI is fast now lol
```

Better:

```text
Topic:
new inference optimisation cuts latency

Angle:
developers discovering they can finally afford to run the model

Meme:
developer staring at cloud bill
```

The humour should be grounded in the event.

---

# 120. IMPORTANT: MEME TEMPLATE IS A COMEDIC DEVICE

Treat templates as:

```text
visual rhetorical structures
```

not just:

```text
images with text boxes
```

A template says something before text is added.

The humour system should exploit that.

---

# 121. FUTURE EXTENSIONS

Do not implement unless needed, but leave architecture open for:

```text
custom generated templates
GIF memes
video memes
AI-generated visual backgrounds
reaction images
platform-specific meme styles
human approval
A/B meme testing
multi-language humour
personalised audience humour
fine-tuned humour model
```

---

# 122. RESEARCH REFERENCES

## Primary research used for this implementation

**Kim, Sean & Chilton, Lydia B. — AI Humor Generation: Cognitive, Social and Creative Skills for Effective Humor**

https://arxiv.org/html/2502.07981v1

Key ideas incorporated:

- visual detail extraction;
- visual humour ideation;
- narrative/conflict extrapolation;
- divergent ideation;
- multiple caption generation;
- dedicated humour ranking;
- audience-aware humour;
- cultural knowledge;
- creativity through multiple angles.

The paper reports that its HumorSkills system produced captions rated higher than GPT-4o in its main comparison and close to highly rated Instagram captions in the studied Gen-Z setting. Those findings motivate the architecture but should not be treated as universal evidence of humour quality.

---

# 123. ADDITIONAL RESEARCH NOTE

The system should remain sceptical of its own humour.

Current research continues to show that language models can recognise surface patterns associated with humour without necessarily understanding the underlying wordplay, double meanings, or cultural context.

Therefore:

```text
model confidence ≠ human funniness
```

This is another reason to use:

```text
multiple candidates
+
specialised judge
+
visual evaluation
+
real performance feedback
```

rather than trusting one generation call.

---

# 124. IMPLEMENTATION ORDER

Implement in this order:

## Phase 1 — Foundation

```text
1. inspect existing code
2. inspect existing DB
3. inspect existing model/provider abstraction
4. inspect existing state/candidate schema
```

## Phase 2 — Templates

```text
5. Imgflip provider
6. template sync
7. template registry
8. semantic metadata
9. retrieval
10. ranking
11. cooldown
```

## Phase 3 — Humour Skill

```text
12. observation
13. visual humour ideation
14. narrative extrapolation
15. humour mechanisms
16. divergent generation
17. caption generation
18. humour ranking
```

## Phase 4 — Memory

```text
19. usage memory
20. joke similarity
21. mechanism memory
22. template family memory
23. performance tracking
```

## Phase 5 — Rendering

```text
24. Imgflip renderer
25. preview generation
26. multimodal final judge
```

## Phase 6 — Testing

```text
27. unit tests
28. repetition tests
29. humour-skill tests
30. provider smoke test
31. full meme dry run
```

---

# 125. DEFINITION OF DONE

The subsystem is complete when:

- [ ] existing discovery is untouched except for required interface integration
- [ ] meme opportunity detection exists
- [ ] Imgflip provider exists
- [ ] template registry exists
- [ ] template metadata is persistent
- [ ] template semantic enrichment exists
- [ ] template retrieval exists
- [ ] template ranking exists
- [ ] template cooldown exists
- [ ] template-family repetition exists
- [ ] humour-mechanism repetition exists
- [ ] joke similarity detection exists
- [ ] dedicated Humour Skill exists
- [ ] Humour Skill follows the research-inspired staged workflow
- [ ] visual observation exists
- [ ] visual humour ideation exists
- [ ] narrative/conflict extrapolation exists
- [ ] multiple humour angles are generated
- [ ] multiple caption candidates are generated
- [ ] dedicated humour judge exists
- [ ] final judge receives visual context
- [ ] captions are validated for template fit
- [ ] weak memes can be rejected
- [ ] rendered output can be produced
- [ ] meme usage is persisted
- [ ] meme performance is persisted
- [ ] tests exist
- [ ] live provider smoke test exists
- [ ] dry-run mode exists
- [ ] no meme is published during tests
- [ ] no expensive video generation is introduced
- [ ] no discovery-source work is duplicated

---

# 126. FINAL INSTRUCTION TO THE CODING AGENT

**Implement this meme subsystem now.**

Before writing code:

1. inspect the existing repository;
2. inspect `agent/nodes/discover.py`;
3. identify the existing topic/candidate schema;
4. identify the existing database/persistence layer;
5. identify the existing model abstraction;
6. identify the existing skill/prompt architecture;
7. identify existing HTTP/API utilities;
8. identify existing testing conventions.

Then implement the smallest clean integration that satisfies this specification.

### Critical research instruction

Read the full paper before implementing the Humour Skill:

https://arxiv.org/html/2502.07981v1

Do not skim only the abstract.

Pay particular attention to:

```text
3.1.1 Visual Detail Extraction
3.1.2 Visual Humor Ideation
3.1.3 Narrative and Conflict Extrapolation
3.1.4 Humorous Caption Generation
3.1.5 Caption Ranking using Gen Z Agent
3.1.6 Fine-tuning
5.3 Narrative Extrapolation
5.4 Visual Detail Extraction and Visual Humor Ideation
6.1 Giving Human-like Skills to AI
7 Limitations
```

Translate the useful architectural ideas into the project's humour skill.

Do **not** claim to reproduce the paper's model or results.

---

# 127. TESTING INSTRUCTION

After implementation, test **ONLY this meme subsystem**.

Do NOT:

- run the entire autonomous agent;
- publish to social media;
- run the normal posting pipeline;
- run video generation;
- call unrelated expensive generation;
- modify the existing discovery-source tests unless required;
- post anything publicly.

Run:

```text
template sync test
template retrieval test
template ranking test
cooldown test
repetition test
humour skill test
candidate ranking test
Imgflip smoke test
meme dry run
```

The final dry run must stop before publishing.

---

# 128. FINAL TEST REPORT FORMAT

Return:

```text
MEME SUBSYSTEM IMPLEMENTATION
=============================

Files changed:
...

Database changes:
...

Providers:
...

Template registry:
PASS / FAIL

Template semantic enrichment:
PASS / FAIL

Template ranking:
PASS / FAIL

Template repetition:
PASS / FAIL

Humour Skill:
PASS / FAIL

Visual observation:
PASS / FAIL

Visual humour ideation:
PASS / FAIL

Narrative extrapolation:
PASS / FAIL

Divergent generation:
PASS / FAIL

Humour ranking:
PASS / FAIL

Joke similarity:
PASS / FAIL

Imgflip:
PASS / FAIL / SKIP

Dry run:
PASS / FAIL

Publishing:
SKIPPED — REQUIRED

Known issues:
...
```

---

# 129. THE ONE-SENTENCE PRODUCT PRINCIPLE

The system should behave like:

> **A meme editor that understands why a topic is funny, understands why a template is funny, generates many possibilities, rejects its own rubbish, remembers what it already used, and learns which humour actually works.**

Not:

> **An LLM that puts text on Drake.**

