import subprocess
import sys


def test_cli_rule_only_configuration(tmp_path):
    config = tmp_path/'rules.yaml'
    config.write_text('''version: 1
ner:
  enabled: false
rules:
  - name: name
    entity: PERSON
    deny_list: [王小明]
''')
    result = subprocess.run([sys.executable,'app.py','--config',str(config),'--text','王小明'],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert '[[PERSON_' in result.stdout
    assert 'ckip' not in result.stderr.lower()


def test_cli_invalid_config(tmp_path):
    config = tmp_path/'invalid.yaml'
    config.write_text('version: 99')
    result = subprocess.run([sys.executable,'app.py','--config',str(config)],capture_output=True,text=True)
    assert result.returncode != 0
    assert 'version' in result.stderr
