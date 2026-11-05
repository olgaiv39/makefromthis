"""Stage 04B: exact Baseten hackathon profile; no inference at import time."""
BASE_URL = 'https://inference.baseten.co/v1'
CHAT_ENDPOINT = BASE_URL + '/chat/completions'
HACKATHON_MODEL = 'meta-models/muse-spark-open-1026'


def recommendation_format(context):
    ids = [t['project_id'] for t in context.get('verified_templates', [])]
    project_id = {'type': 'string', **({'enum': ids} if ids else {})}
    return {'type': 'json_schema', 'json_schema': {
        'name': 'project_recommendations', 'strict': True,
        'schema': {'type': 'object', 'additionalProperties': False,
                   'required': ['ranked_projects'], 'properties': {
                       'ranked_projects': {'type': 'array', 'minItems': 1,
                           'maxItems': max(1,len(ids)), 'items': {
                               'type': 'object', 'additionalProperties': False,
                               'required': ['project_id', 'explanation'], 'properties': {
                                   'project_id': project_id,
                                   'explanation': {'type':'string','minLength':1,'maxLength':300}}}}}}}}


def validate_ranking(response, feasible):
    """Authoritative acceptance of structured output; schema requests are hints.

    Called by the real API and the one-request smoke after actual nesting checks.
    Never accepts a model-created project or a project without a verified fit.
    """
    if not isinstance(response,dict) or set(response) != {'ranked_projects'}:
        raise ValueError('invalid recommendation object')
    ranking = response['ranked_projects']
    if not isinstance(ranking,list) or not 1 <= len(ranking) <= len(feasible):
        raise ValueError('invalid ranking size')
    seen=set(); result=[]
    for item in ranking:
        if not isinstance(item,dict) or set(item) != {'project_id','explanation'}:
            raise ValueError('invalid recommendation fields')
        key, explanation=item['project_id'],item['explanation']
        if not isinstance(key,str) or key not in feasible or key in seen:
            raise ValueError('unknown, infeasible or repeated project')
        if not isinstance(explanation,str) or not explanation.strip() or len(explanation)>300:
            raise ValueError('invalid explanation')
        seen.add(key);result.append({'project_id':key,'explanation':explanation})
    return result
