import time

import pytest

from funq_mcp.errors import AdapterError
from funq_mcp.selectors import Selector


def test_fragmented_utf8_frames(service, fake, session):
    fake.fragment = True
    fake.objects["edit"]["properties"]["text"] = "Тест 🌍"
    assert service.inspect(session, Selector(object_name="edit"))["properties"]["text"] == "Тест 🌍"


@pytest.mark.parametrize("response", [b"bad\n{}", b"-1\n{}", b"0\n", b"9999999999\n", b"3\n[] ", b"1\n{",
                                      b"16\n{\"event\":\"pick\"}", b"9\n{\"x\":NaN}"])
def test_bad_frames_invalidate_session(service, fake, session, response):
    fake.overrides["object_find"] = lambda req: response
    with pytest.raises(AdapterError) as caught:
        service.find(session, Selector(object_name="edit"), timeout=0.1)
    assert caught.value.code == "ProtocolError"
    assert not service.list_sessions()[0]["connected"]
    assert caught.value.details["reattach_required"]


def test_partial_frame_times_out(service, fake, session):
    fake.overrides["object_find"] = lambda req: b"100\n{}"
    # The fake keeps the connection open; a partial payload must time out.
    with pytest.raises(AdapterError) as caught:
        service.find(session, Selector(object_name="edit"), timeout=0.05)
    assert caught.value.code == "RequestTimeout"
    assert caught.value.details["outcome"] == "unknown"


def test_eof_invalidates_connection(service, fake, session):
    fake.overrides["object_find"] = lambda req: None
    with pytest.raises(AdapterError) as caught:
        service.find(session, Selector(object_name="edit"))
    assert caught.value.code == "ConnectionLost"
    assert not service.list_sessions()[0]["connected"]


def test_slow_fragments_cannot_extend_deadline(service, fake, session):
    fake.fragment = True
    fake.fragment_delay = 0.02
    start = time.monotonic()
    with pytest.raises(AdapterError) as caught:
        service.find(session, Selector(object_name="edit"), timeout=0.06)
    assert caught.value.code == "RequestTimeout"
    assert time.monotonic() - start < 0.25


def test_failed_mutation_is_never_replayed(service, fake, session):
    def delayed(req):
        time.sleep(0.2)
        return {}
    fake.overrides["widget_click"] = delayed
    with pytest.raises(AdapterError) as caught:
        service.click(session, Selector(object_name="apply"), timeout=0.05)
    assert caught.value.code == "RequestTimeout"
    assert len([r for r in fake.requests if r["action"] == "widget_click"]) == 1
    with pytest.raises(AdapterError) as second:
        service.click(session, Selector(object_name="apply"))
    assert second.value.code == "SessionDisconnected"
    service.detach(session)
    assert service.attach(fake.port)["session_id"] != session


def test_server_error_preserves_connection(service, fake, session):
    fake.overrides["object_find"] = lambda req: fake.failure("ObjectNotFound", "gone")
    with pytest.raises(AdapterError) as caught:
        service.find(session, Selector(object_name="edit"))
    assert caught.value.code == "ObjectNotFound"
    assert service.list_sessions()[0]["connected"]


def test_unsupported_command_does_not_break_transport(service, fake, session):
    service._get(session).client.commands.remove("widget_click")
    with pytest.raises(AdapterError) as caught:
        service.click(session, Selector(object_name="apply"))
    assert caught.value.code == "UnsupportedCommand"
    assert service.list_sessions()[0]["connected"]
