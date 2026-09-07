"""Presentation-only projections; never change seasonal eligibility or ranking."""
from copy import deepcopy


LIST_FIELDS = frozenset('''ticker company market pattern_id signal_id generation_id
window_name pre_entry_rank entry_stage entry_stage_label current_status grade
sample_count win_rate median_return median_alpha seasonality_score
entry_window_str exit_window_str years_track price_as_of'''.split())
EXPLANATION_FIELDS = LIST_FIELDS | frozenset('''failed_analysis event_explanation_mode
event_confidence common_event_cluster secondary_cluster event_explanation_source
invalidating_conditions'''.split())


def project_page(rows, *, view='full', offset=0, limit=None, lookback=5):
    if view not in ('full', 'summary', 'explanation'):
        raise ValueError('지원 목록 형식: full, summary, explanation')
    if offset < 0 or (limit is not None and not 1 <= limit <= 100):
        raise ValueError('offset은 0 이상, limit은 1~100이어야 합니다.')
    if view != 'full' and limit is None:
        limit = 50 if view == 'summary' else 30
    page = rows[offset:] if limit is None else rows[offset:offset + limit]
    if view != 'full':
        fields = LIST_FIELDS if view == 'summary' else EXPLANATION_FIELDS
        page = [{**{key: deepcopy(row[key]) for key in fields if key in row},
                 'detail_required': True, 'lookback_years': lookback} for row in page]
    else:
        page = deepcopy(page)
    end = offset + len(page)
    return {'rows': page, 'count': len(rows), 'returned_count': len(page),
            'offset': offset, 'limit': limit, 'view': view,
            'next_offset': end if end < len(rows) else None}
