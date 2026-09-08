"""Structural gate, not a substitute for factual/human evaluation."""
import re


def validate_season_card(payload: dict) -> None:
    for key in ('headline', 'seasonality_brief', 'sample_caution', 'next_check'):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 700:
            raise ValueError(f'season card: invalid {key}')
    catalysts = payload.get('key_catalysts')
    if not isinstance(catalysts, list) or len(catalysts) > 8 or any(
        not isinstance(value, str) or not value.strip() or len(value) > 400 for value in catalysts
    ):
        raise ValueError('season card: invalid key_catalysts')
    text = ' '.join([payload[key] for key in ('headline', 'seasonality_brief', 'sample_caution', 'next_check')] + catalysts)
    if re.search(r'(?i)(?<![a-z])(nan|infinity|inf)(?![a-z])', text):
        raise ValueError('season card: non-finite number')
