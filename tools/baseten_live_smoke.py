"""Explicit, single-inference Baseten smoke; NOT collected by normal pytest.

Only sanitized metrics are printed. No content, reasoning, headers or keys.
The management GET precedes inference; it does not confirm remaining credits.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.providers.core import Config, MetaRecommendations, ProviderError
from app.providers.baseten import CHAT_ENDPOINT, HACKATHON_MODEL, validate_ranking
import httpx


def verified_context():
    from app.layout_api import calculate, LayoutRequest, TEMPLATES
    material={'type':'Polygon','coordinates':[[[0,0],[10,0],[10,10],[0,10],[0,0]]]}
    result=calculate(LayoutRequest(material_mm=material,template_id='square-tabs'))
    if result['status']!='success' or not result['verification']['valid']:
        raise ValueError('smoke geometry did not verify')
    return {'material_type':'synthetic test square','width_mm':10,'height_mm':10,
            'material_mm':material,'preferences':'Rank the single verified project; explanation under six words.',
            'verified_templates':[{'project_id':'square-tabs',**TEMPLATES['square-tabs']}]}


async def check_billing(key, transport=None):
    """Read documented spend history only. No undocumented balance URL guesses."""
    result={'http_status':None,'credit_confirmation':'unconfirmed','remaining_credit':None,
            'reason':'usage_history_does_not_confirm_remaining_credit'}
    now=datetime.now(timezone.utc)
    params={'start_date':(now-timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'end_date':now.strftime('%Y-%m-%dT%H:%M:%SZ')}
    try:
        async with httpx.AsyncClient(transport=transport,timeout=10,follow_redirects=False,trust_env=False) as client:
            async with client.stream('GET','https://api.baseten.co/v1/billing/usage_summary',
                    params=params,headers={'Authorization':'Bearer '+key}) as response:
                result['http_status']=response.status_code
                # Do not print/store account data. Status alone cannot establish balance.
                if response.status_code!=200:result['reason']='billing_status_unavailable'
    except (httpx.HTTPError,ValueError,UnicodeError):result['reason']='billing_unreachable'
    return result


async def run(environ=None,transport=None):
    env=os.environ if environ is None else environ
    report={'model':HACKATHON_MODEL,'inference_requests':0,'live_inference_performed':False,
            'billing':{'credit_confirmation':'unconfirmed','reason':'not_checked'},
            'http_status':None,'latency_ms':None,'token_usage':None,
            'finish_reason':None,'visible_content_present':False,'visible_content_length':0,
            'reasoning_tokens':None,'completion_tokens':None}
    if env.get('LIVE_AI_TEST')!='1':return {**report,'status':'blocked','reason':'LIVE_AI_TEST=1_required'}
    key=env.get('BASETEN_API_KEY','')
    if not key:return {**report,'status':'blocked','reason':'BASETEN_API_KEY_missing'}
    # Fixed official destination and exact hackathon model: never substitute or retry.
    if env.get('RECOMMENDATION_MODEL_ID',HACKATHON_MODEL) not in ('',HACKATHON_MODEL):
        return {**report,'status':'blocked','reason':'hackathon_model_mismatch'}
    if env.get('RECOMMENDATION_ENDPOINT_URL',CHAT_ENDPOINT) not in ('',CHAT_ENDPOINT):
        return {**report,'status':'blocked','reason':'official_endpoint_required'}
    config=Config(provider='baseten',endpoint=CHAT_ENDPOINT,model=HACKATHON_MODEL,
                  token=key,auth='bearer',protocol='openai',max_tokens=1024)
    if config.problem('recommendation'):
        return {**report,'status':'blocked','reason':'invalid_configuration'}
    try:context=verified_context()
    except (ImportError,ValueError):return {**report,'status':'blocked','reason':'geometry_unavailable'}
    report['billing']=await check_billing(key,transport)
    # Credit remains explicitly unconfirmed even if the read-only usage GET is 200.
    # LIVE_AI_TEST=1 opts into ONE capped inference, not a claim of free credits.
    adapter=MetaRecommendations(config,timeout=30,transport=transport)
    report['inference_requests']=1
    try:
        response=await adapter.recommend(context)
        validate_ranking(response,['square-tabs'])
        report.update(status='passed',structured_recommendation_valid=True)
    except (ProviderError,ValueError) as exc:
        report.update(status='failed',reason=exc.code if isinstance(exc,ProviderError) else 'invalid_recommendation_output')
    report.update(adapter.metrics)
    report['live_inference_performed']=adapter.metrics['http_status']==200
    return report


if __name__=='__main__':
    # Avoid HTTP/debug libraries logging destinations, query parameters or headers.
    logging.disable(logging.CRITICAL)
    from app.environment import load_environment
    load_environment()
    result=asyncio.run(run())
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result['status']=='passed' else 2)
