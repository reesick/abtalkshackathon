"""
Style reference system — the visual consistency contract for all generated
media. Per spec section 6: "treat the reference as a consistency constraint,
not loose inspiration."

These 3 reference images were uploaded to Flora and confirmed status=ready
during manual validation. They anchor every image generation call so the
paper-cut collage style stays consistent across topics.
"""

STYLE_REFERENCE_IMAGES = [
    "https://media.flora.ai/api-uploads/2026/8/8/user_3EadOsAEAmxHxI72qlQBunOv4jv/95bb8a35-00c3-4f0d-b24f-97e259bf5a3c.png",
    "https://media.flora.ai/api-uploads/2026/8/8/user_3EadOsAEAmxHxI72qlQBunOv4jv/685dc085-d194-49fa-b3e8-476275eb30b4.png",
    "https://media.flora.ai/api-uploads/2026/8/8/user_3EadOsAEAmxHxI72qlQBunOv4jv/48dfc48e-33aa-4b65-a0ab-2dfa9cf317d1.png",
]

STYLE_REFERENCE_NAME = "paper-cut-collage-v1"

STYLE_GRAMMAR = {
    "rendering_method": "Flat paper-cut collage illustration",
    "character_construction": "a black-and-white halftone photographic head and hands, flat colored paper body and suit",
    "materials": "torn, rough hand-cut paper edges with visible fiber texture on every shape",
    "depth": "each paper layer casts a hard-edged directional drop shadow onto the layer beneath it, giving real physical stacked-paper depth",
    "palette": "mustard yellow, slate gray, bone cream, with a deep-red accent used sparingly",
    "lighting": "flat, evenly lit studio lighting",
    "camera": "locked-off straight-on camera, centered symmetrical composition, medium-square framing",
    "editorial_reference": "Vox/New Yorker editorial collage style",
    "frame": "portrait frame (9:16)",
}


def build_negative_constraints() -> str:
    """Shared negative-constraint clause appended to every asset prompt."""
    return (
        "Do not introduce new characters, palette shifts, added text, logos, "
        "or photorealistic elements not described above."
    )
