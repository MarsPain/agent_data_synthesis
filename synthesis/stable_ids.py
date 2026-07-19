from __future__ import annotations


def stable_id(value: str) -> str:
    """Shared slugify primitive for environment-minted and derived identifiers.

    Lowercases the value, keeps alphanumeric characters, maps every other
    character to ``_``, and strips leading/trailing ``_``. Both environment ID
    minting and generation-time final-answer derivation must use this single
    primitive so their outputs cannot drift apart.
    """
    return "".join(
        character.lower() if character.isalnum() else "_" for character in value
    ).strip("_")
