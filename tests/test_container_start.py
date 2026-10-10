from pathlib import Path


def test_first_start_initializes_config_and_preserves_edits(tmp_path):
    from docker_start import initialize_config
    source = tmp_path/'defaults.yaml'
    source.write_text('version: 1\nner: {enabled: false}\nrules: []\n')
    target = tmp_path/'data/config/rules.yaml'
    initialize_config(target,source)
    assert target.read_bytes() == source.read_bytes()
    target.write_text('version: 1\n# user settings\n')
    initialize_config(target,source)
    assert '# user settings' in target.read_text()


def test_missing_defaults_leave_no_partial_config(tmp_path):
    import pytest
    from docker_start import initialize_config
    target = tmp_path/'data/config/rules.yaml'
    with pytest.raises(FileNotFoundError): initialize_config(target,tmp_path/'missing.yaml')
    assert not target.exists()
