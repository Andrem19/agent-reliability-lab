from arl.config import load_config
from arl.doctor import doctor_ok, run_doctor


def test_doctor_core_gate_passes(tmp_path) -> None:
    config = load_config(root=None)
    data = config.model_dump()
    data["paths"]["state_dir"] = tmp_path
    config = type(config).model_validate(data)
    results = run_doctor(config)
    assert doctor_ok(results)
    assert any(item.name == "Target contracts" and item.status == "PASS" for item in results)
    assert any(item.name == "SQLite" and item.status == "PASS" for item in results)
