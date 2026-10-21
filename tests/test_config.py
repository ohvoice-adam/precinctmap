import pytest

from precinctmap.config import load_settings


def test_port_and_host_come_from_the_environment():
    s = load_settings({"PRECINCTMAP_PORT": "9100", "PRECINCTMAP_HOST": "10.0.0.5"})
    assert (s.host, s.port) == ("10.0.0.5", 9100)
    assert (load_settings({}).host, load_settings({}).port) == ("127.0.0.1", 8000)


@pytest.mark.parametrize("bad", ["", "http", "0", "70000"])
def test_bad_port_fails_loudly(bad):
    with pytest.raises(ValueError, match="PRECINCTMAP_PORT"):
        load_settings({"PRECINCTMAP_PORT": bad})
