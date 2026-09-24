"""설정 파일 형식 오류는 앱 종료 대신 백업과 기본값으로 복구한다."""
import json

import pytest

import storage


@pytest.mark.parametrize('payload', [[],{'calculators':['broken']},
                                     {'calculators':{'motor':None}}])
def test_corrupt_settings_are_backed_up(monkeypatch,tmp_path,payload):
    data=tmp_path/'user_data.json'
    data.write_text(json.dumps(payload),encoding='utf-8')
    monkeypatch.setattr(storage,'get_data_file_path',lambda:data)
    result=storage.PersistentStore()
    assert result.data['theme']=='light'
    assert result.load_warning
    assert list(tmp_path.glob('user_data_corrupt_*.json'))
