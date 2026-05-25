"""Supported UI/voice locales and their Google STT/TTS BCP-47 codes.

The frontend can switch among these via the language selector; each
locale is forwarded with every WS message and used to:
- pin the response language in the LLM system prompt,
- set `language_codes` on the Google STT v2 request,
- set `language_code` on the Google TTS request.

Picking a locale Google doesn't support would surface as a 400 at
synthesis time, so the validator below rejects unknown codes early.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Locale:
    code: str  # frontend-facing code, e.g. "en-US"
    language_name: str  # English name of the language for LLM instruction
    variant_label: str  # human-readable disambiguator, e.g. "British English"
    stt_code: str  # BCP-47 code for Google STT v2 `language_codes`
    tts_code: str  # BCP-47 code for Google TTS `language_code`


# Google STT chirp_2 supports a wide set of BCP-47 codes; TTS picks a
# default voice per locale if `name` is omitted. We DON'T pin a specific
# voice name per locale — that would force us to maintain a map of voice
# IDs that Google may rename or deprecate. Picking the default voice
# loses a touch of quality but is robust.
LOCALES: list[Locale] = [
    Locale(
        code="en-US",
        language_name="English",
        variant_label="American English",
        stt_code="en-US",
        tts_code="en-US",
    ),
    Locale(
        code="en-GB",
        language_name="English",
        variant_label="British English",
        stt_code="en-GB",
        tts_code="en-GB",
    ),
    Locale(
        code="es-ES",
        language_name="Spanish",
        variant_label="Castilian Spanish",
        stt_code="es-ES",
        tts_code="es-ES",
    ),
    Locale(
        # Google groups Latin American Spanish under es-US in its catalog.
        code="es-419",
        language_name="Spanish",
        variant_label="Latin American Spanish",
        stt_code="es-US",
        tts_code="es-US",
    ),
    Locale(
        code="fr-FR",
        language_name="French",
        variant_label="European French",
        stt_code="fr-FR",
        tts_code="fr-FR",
    ),
    Locale(
        code="fr-CA",
        language_name="French",
        variant_label="Canadian French",
        stt_code="fr-CA",
        tts_code="fr-CA",
    ),
    Locale(
        code="de-DE",
        language_name="German",
        variant_label="German",
        stt_code="de-DE",
        tts_code="de-DE",
    ),
]

_BY_CODE = {loc.code: loc for loc in LOCALES}

DEFAULT_LOCALE = "en-US"


def resolve(code: str | None) -> Locale:
    """Look up the Locale for a frontend code; fall back to en-US."""
    if code is None:
        return _BY_CODE[DEFAULT_LOCALE]
    return _BY_CODE.get(code, _BY_CODE[DEFAULT_LOCALE])
