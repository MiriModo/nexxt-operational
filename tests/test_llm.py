import json
import os
from copy import deepcopy

import httpx
import pytest

from retailagent.llm import LLMError, genereaza, optiuni


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setattr('retailagent.llm.configurare', lambda: dict(os.environ))
    for name in ('ALL_PROXY', 'HTTPS_PROXY', 'HTTP_PROXY', 'all_proxy', 'https_proxy', 'http_proxy'):
        monkeypatch.delenv(name, raising=False)


def case():
    return {'case': {'blocaje': [], 'semnale': []},
            'client': {'nume': 'SECRET', 'nivel': 'standard'}, 'loan': None,
            'check': {'verificare_picata': None, 'concluzii': {}},
            'rec': {'recomandare': 'oferta_minima'},
            'offer': {'interventii': [{'id': 'fix', 'fezabil': True}, {'id': 'bad', 'fezabil': False}],
                      'legaturi': {}, 'motiv_alegere': 'motiv'}}


def test_blocaje():
    c = case()
    assert [i['id'] for i in optiuni(c)] == ['fix']
    for rec in ['blocat', 'respins_escaladat', 'nu_interveni']:
        x = deepcopy(c); x['rec']['recomandare'] = rec
        assert optiuni(x) == []
    c['case']['blocaje'] = ['documente']
    assert optiuni(c) == []


@pytest.mark.parametrize('selected', ['fix', 'bad'])
def test_transport_si_validare(monkeypatch, selected):
    monkeypatch.setenv('RETAILAGENT_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    for name in ('ALL_PROXY', 'HTTPS_PROXY', 'HTTP_PROXY', 'all_proxy', 'https_proxy', 'http_proxy'):
        monkeypatch.delenv(name, raising=False)
    def post(self, url, **kwargs):
        payload = kwargs['json']
        assert 'SECRET' not in payload['input']
        assert payload['store'] is False
        assert payload['text']['format']['schema']['properties']['interventie']['enum'] == [None, 'fix']
        result = {'interventie': selected, 'titlu': 'Titlu', 'motiv': 'Motiv', 'indicii': [],
                  'mesaj_client': 'Mesaj', 'atentionari': []}
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': json.dumps(result)}]}]})
    monkeypatch.setattr(httpx.Client, 'post', post)
    if selected == 'bad':
        with pytest.raises(LLMError, match='neeligibilă'):
            genereaza(case())
    else:
        assert genereaza(case())['interventie'] == 'fix'


@pytest.mark.parametrize('selected,reason', [('fix', 'tool_use'), ('bad', 'tool_use'), ('fix', 'max_tokens')])
def test_bedrock(monkeypatch, selected, reason):
    monkeypatch.setenv('RETAILAGENT_LLM_PROVIDER', 'bedrock')
    monkeypatch.setenv('AWS_BEARER_TOKEN_BEDROCK', 'fake-bedrock-key')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')
    monkeypatch.setenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0')
    def post(self, url, **kwargs):
        assert url == 'https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-haiku-4-5-20251001-v1%3A0/invoke'
        assert kwargs['headers']['Authorization'] == 'Bearer fake-bedrock-key'
        payload = kwargs['json']
        assert payload['anthropic_version'] == 'bedrock-2023-05-31'
        assert payload['tool_choice']['name'] == 'propune_oferta'
        assert 'SECRET' not in json.dumps(payload)
        result = {'interventie': selected, 'titlu': 'Titlu', 'motiv': 'Motiv', 'indicii': [],
                  'mesaj_client': 'Mesaj', 'atentionari': []}
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'stop_reason': reason, 'content': [{'type': 'tool_use', 'name': 'propune_oferta', 'input': result}]})
    monkeypatch.setattr(httpx.Client, 'post', post)
    if selected == 'bad' or reason != 'tool_use':
        with pytest.raises(LLMError):
            genereaza(case())
    else:
        assert genereaza(case())['interventie'] == 'fix'
