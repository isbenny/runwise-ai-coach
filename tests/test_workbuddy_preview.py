"""Only the safety boundaries of the new UI-preview adapter, no training fixtures."""
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('workbuddy_preview',Path(__file__).resolve().parents[1]/'tools/workbuddy_mcp_preview.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_preview_preserves_config_and_is_idempotent(tmp_path):
    config=tmp_path/'live.json';original=b'{"mcpServers":{"other":{"url":"https://service.invalid/mcp","headers":{"Authorization":"PRIVATE_TEST_SENTINEL"}}},"custom":true}'
    config.write_bytes(original)
    source=tmp_path/'source.json';source.write_text(json.dumps({'mcpServers':{'chosen':{'command':'/existing/python','args':['/existing/server.py']}}}))
    private=tmp_path/'private';private.mkdir(mode=0o700)
    output=private/'preview.json'
    first=module.stage(config,output,source_config=source,source_name='chosen',coros=True)
    assert config.read_bytes()==original
    parsed=json.loads(output.read_text());assert parsed['custom'] is True
    assert parsed['mcpServers']['other']==json.loads(original)['mcpServers']['other']
    assert parsed['mcpServers']['runwise-garmin']['disabledTools']==['sync_recent']
    assert parsed['mcpServers']['runwise-coros']['type']=='streamableHttp'
    assert not(output.stat().st_mode & 0o077)
    assert len(list(private.glob('mcp-before-*.json')))==1
    assert module.stage(config,output,source_config=source,source_name='chosen',coros=True)['status']=='unchanged'
    assert first['config_modified'] is False


def test_existing_product_entry_conflict_stops():
    current={'mcpServers':{'runwise-coros':{'url':'https://other.invalid/mcp'}}}
    with pytest.raises(ValueError,match='PRODUCT_ENTRY_CONFLICT'):module.merged(current,coros=True)
    assert current['mcpServers']['runwise-coros']['url']=='https://other.invalid/mcp'


def test_embedded_credential_source_rejected():
    with pytest.raises(ValueError,match='CREDENTIAL_ARGUMENT_REJECTED'):
        module.merged({'mcpServers':{}},{'command':'/python','args':['--token=PRIVATE_TEST_SENTINEL']})
    with pytest.raises(ValueError,match='CREDENTIAL_PATH_REQUIRED_NOT_TOKEN'):
        module.merged({'mcpServers':{}},{'command':'/python','env':{'GARMINTOKENS_BASE64':'PRIVATE_TEST_SENTINEL'}})
