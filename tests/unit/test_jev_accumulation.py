import copy
import json
import pytest
from kr_quant.research import jev_accumulation as acc
from kr_quant.research import jev_calibration as cal

def row(ticker, state):
    return {'sample_id':cal.make_sample_id('typesafe_direct','jev-latest','season-jev-shadow-v1',state),
            'ticker':ticker,'state_hash':state,'split':cal.assign_split(ticker=ticker,state_hash=state),
            'jev_answers':{'sealed':True},'annotation_version':1}

def tranche(i):
    return {'source_generation_id':f'source{i}','season_generation_id':f'season{i}',
            'source_bundle_hash':f'hash{i}','source_as_of':f'2026-10-{i:02}',
            'selection_date':f'2026-10-{i:02}','shadow_artifact_sha256':'a'*64,
            'natural_update_verified':True,'consecutive_verified':True,'status':'success'}

def test_dedupe_and_prior_saved_judgment_exclusion():
    r = row('001','state')
    got = acc.append_tranche([],[],tranche(1),[r,r],set())
    assert len(got['rows']) == 1
    excluded = acc.append_tranche([],[],tranche(1),[r],{r['sample_id']})
    assert excluded['summary']['previously_judged_excluded'] == 1
    assert excluded['rows'] == []

def test_ticker_and_state_split_conflicts_fail_closed():
    r = row('001','state')
    bad = copy.deepcopy(r); bad['split']='holdout' if r['split']=='calibration' else 'calibration'
    with pytest.raises(cal.CalibrationError):
        acc.append_tranche([],[],tranche(1),[r,bad],set())

def test_first_sufficient_stops_and_rejects_more():
    rows=[]
    for i in range(2000):
        r=row(str(i),f'state{i}')
        if sum(x['split']==r['split'] for x in rows)<129: rows.append(r)
        if len(rows)==258: break
    got=acc.append_tranche([],[],tranche(1),rows,set())
    assert got['summary']['first_sufficient_generation']=='season1'
    with pytest.raises(ValueError,match='ALREADY_SUFFICIENT'):
        acc.append_tranche(got['rows'],got['tranches'],tranche(2),[],set())
    chosen=acc.reference_selection(got['rows'])
    assert len(chosen['selected'])==258
    assert chosen==acc.reference_selection(list(reversed(got['rows'])))

def test_duplicate_source_and_generation_rejected():
    got=acc.append_tranche([],[],tranche(1),[],set())
    for field in ('source_generation_id','source_bundle_hash','season_generation_id'):
        next_tranche=tranche(2); next_tranche[field]=tranche(1)[field]
        with pytest.raises(ValueError,match='DUPLICATE_GENERATION_OR_SOURCE'):
            acc.append_tranche([],got['tranches'],next_tranche,[],set())

def test_summary_blindness_and_no_split_candidate_selection():
    rows=[row(str(i),f's{i}') for i in range(50)]
    got=acc.append_tranche([],[],tranche(1),rows,set())
    assert len(got['rows'])==50
    output=json.dumps(got['summary'])
    assert 'jev_answers' not in output and 'probability' not in output and 'sealed' not in output

def test_natural_and_consecutive_required():
    for field in ('natural_update_verified','consecutive_verified'):
        t=tranche(1); t[field]=False
        with pytest.raises(ValueError,match='NATURAL_CONSECUTIVE_GENERATION_REQUIRED'):
            acc.append_tranche([],[],t,[],set())

def test_ticker_conflict_independent_of_sample_id():
    a=row('001','a'); b=row('001','b')
    b['split']='holdout' if a['split']=='calibration' else 'calibration'
    with pytest.raises(cal.CalibrationError,match='SPLIT_TICKER_CONFLICT'):
        acc.append_tranche([],[],tranche(1),[a,b],set())

def test_state_conflict_independent_of_ticker():
    a=row('001','a')
    b=next(row(str(i),'b') for i in range(100) if row(str(i),'b')['split']!=a['split'])
    b['state_hash']=a['state_hash']
    with pytest.raises(cal.CalibrationError,match='SPLIT_STATE_HASH_CONFLICT'):
        acc.append_tranche([],[],tranche(1),[a,b],set())

def test_exclusion_accounting_survives_next_tranche():
    a=row('001','a'); excluded={a['sample_id']}
    first=acc.append_tranche([],[],tranche(1),[a],excluded)
    second=acc.append_tranche(first['all_complete_rows'],first['tranches'],tranche(2),[a,row('002','b')],excluded)
    assert second['summary']['previously_judged_excluded']==1
    assert len(second['rows'])==1
