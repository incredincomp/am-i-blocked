import os
import stat


def test_panos_script_exists_and_executable():
    path = os.path.join(os.getcwd(), "scripts", "gather_panos_fixtures.sh")
    assert os.path.isfile(path), "fixture-gather script should exist"
    mode = os.stat(path).st_mode
    assert mode & stat.S_IXUSR, "script should be executable by owner"


def test_panos_orchestration_script_exists_and_executable():
    path = os.path.join(os.getcwd(), "scripts", "panos_observe_and_validate.py")
    assert os.path.isfile(path), "observe-and-validate script should exist"
    mode = os.stat(path).st_mode
    assert mode & stat.S_IXUSR, "script should be executable by owner"
