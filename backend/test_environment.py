"""Local environment parsing only. No credentials, network or inference."""
import pytest
from app.environment import load_environment


def test_no_implicit_environment_file(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'.env').write_text('AI_ENABLED=true\n')
    env={};load_environment(environ=env)
    assert env=={}


def test_explicit_file_loads_backend_configuration_without_overriding_host(tmp_path,capsys):
    source=tmp_path/'.env'
    source.write_text('# private settings\nexport BASETEN_API_KEY="TEST_ONLY_FILE_KEY"\nAI_ENABLED=false\nRECOMMENDATION_PROVIDER=baseten\n')
    env={'MFT_ENV_FILE':str(source),'BASETEN_API_KEY':'TEST_ONLY_HOST_KEY'}
    load_environment(environ=env)
    assert env['BASETEN_API_KEY']=='TEST_ONLY_HOST_KEY'
    assert env['AI_ENABLED']=='false' and env['RECOMMENDATION_PROVIDER']=='baseten'
    captured=capsys.readouterr();assert captured.out==captured.err==''


def test_environment_values_are_literal_and_never_executed(tmp_path):
    marker=tmp_path/'MUST_NOT_EXIST'
    source=tmp_path/'.env'
    value=f'$(touch {marker})'
    source.write_text("BASETEN_API_KEY='"+value+"'\n")
    env={};load_environment(source,env)
    assert env['BASETEN_API_KEY']==value and not marker.exists()


@pytest.mark.parametrize('bad_line',[
    'VITE_API_KEY=TEST_ONLY_SECRET',
    'not-a-setting TEST_ONLY_SECRET',
    'BASETEN_API_KEY="TEST_ONLY_SECRET',
    'AI_ENABLED=false\nAI_ENABLED=true',
])
def test_invalid_environment_file_is_atomic_and_errors_are_sanitized(tmp_path,bad_line):
    source=tmp_path/'.env';source.write_text('PORT=8000\n'+bad_line+'\n')
    env={}
    with pytest.raises(ValueError,match='^environment_file_invalid_line_') as error:
        load_environment(source,env)
    assert 'TEST_ONLY_SECRET' not in str(error.value) and env=={}


def test_environment_file_size_and_missing_file_are_bounded(tmp_path):
    with pytest.raises(ValueError,match='environment_file_unavailable'):
        load_environment(tmp_path/'absent',{})
    source=tmp_path/'.env';source.write_bytes(b'x'*65537)
    with pytest.raises(ValueError,match='environment_file_too_large'):
        load_environment(source,{})


def test_private_file_reaches_existing_provider_configuration_without_enabling_inference(tmp_path,monkeypatch):
    from app.providers.core import Config, Runtime
    from app.providers.baseten import CHAT_ENDPOINT, HACKATHON_MODEL
    source=tmp_path/'.env'
    source.write_text('RECOMMENDATION_PROVIDER=baseten\nBASETEN_API_KEY=TEST_ONLY_FILE_KEY\nAI_ENABLED=false\n')
    for key in ('RECOMMENDATION_PROVIDER','RECOMMENDATION_ENDPOINT_URL','RECOMMENDATION_MODEL_ID','BASETEN_API_KEY'):
        monkeypatch.setenv(key,'');monkeypatch.delenv(key)
    monkeypatch.setenv('MFT_ENV_FILE',str(source));monkeypatch.setenv('AI_ENABLED','false')
    load_environment()
    config=Config.env('RECOMMENDATION')
    assert config.token=='TEST_ONLY_FILE_KEY' and config.model==HACKATHON_MODEL
    assert config.endpoint==CHAT_ENDPOINT and config.problem('recommendation') is None
    assert Runtime().availability('recommendation')['reason']=='ai_disabled'
