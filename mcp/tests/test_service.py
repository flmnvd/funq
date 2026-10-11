import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from funq_mcp.errors import AdapterError
from funq_mcp.selectors import Selector


def named(name):
    return Selector(object_name=name)


def test_attach_identity_and_duplicate(service, fake, session):
    assert service.list_sessions()[0]["connected"]
    with pytest.raises(AdapterError, match="existing session") as caught:
        service.attach(fake.port)
    assert caught.value.code == "AlreadyAttached"
    assert caught.value.details["session_id"] == session


def test_wrong_application_releases_connection(service, fake):
    with pytest.raises(AdapterError) as caught:
        service.attach(fake.port, expected_class="AnotherWindow")
    assert caught.value.code == "UnexpectedApplication"
    assert service.list_sessions() == []
    assert service.attach(fake.port)["session_id"]


def test_host_alias_cannot_attach_twice(service, fake, session):
    with pytest.raises(AdapterError) as caught:
        service.attach(fake.port, host="localhost")
    assert caught.value.code == "AlreadyAttached"


def test_missing_commands_releases_connection(service, fake):
    fake.overrides["list_commands"] = lambda req: {"commands": ["widgets_list(QtJson::JsonObject)"]}
    with pytest.raises(AdapterError) as caught:
        service.attach(fake.port)
    assert caught.value.code == "IncompatibleServer"
    assert service.list_sessions() == []


def test_selectors_require_one_lookup():
    for fields in ({}, {"path": "p", "object_name": "n"}, {"object_name": ""},
                   {"path": "p", "class_name": "QWidget"}, {"oid": 42}):
        with pytest.raises(ValidationError):
            Selector(**fields)


def test_resolves_again_after_pointer_change(service, fake, session):
    assert service.find(session, named("apply"))["path"] == "main/apply"
    fake.objects["apply"]["oid"] = 999
    service.click(session, named("apply"))
    assert fake.requests[-1]["oid"] == 999
    assert "oid" not in service.find(session, named("apply"))


def test_ambiguity_is_error_with_diagnostics(service, fake, session):
    fake.objects["duplicate"] = fake.obj(100, "apply", ["QPushButton", "QWidget"])
    with pytest.raises(AdapterError) as caught:
        service.click(session, named("apply"))
    assert caught.value.code == "AmbiguousObjectMatch"
    assert not any(req["action"] == "widget_click" for req in fake.requests)
    artifacts = caught.value.details["artifacts"]
    assert Path(artifacts["widgets"]).is_file()
    assert Path(artifacts["screenshot"]).is_file()
    assert json.loads(Path(artifacts["events"]).read_text())[0]["operation"] == "click"


def test_modal_trigger_wait_and_close(service, fake, session):
    result = service.trigger(session, named("Tools::s_pSettings"))
    assert result["status"] == "dispatched"
    assert next(r for r in fake.requests if r["action"] == "action_trigger")["blocking"] is False
    assert service.wait(session, named("settingsDialog"), {"visible": True})["matched"]
    service.close_widget(session, named("settingsDialog"))
    assert service.wait(session, named("settingsDialog"), {"visible": False})["matched"]


def test_disabled_target_is_not_clicked(service, fake, session):
    fake.objects["apply"]["properties"]["enabled"] = False
    with pytest.raises(AdapterError) as caught:
        service.click(session, named("apply"))
    assert caught.value.code == "TargetInactive"
    assert not any(r["action"] == "widget_click" for r in fake.requests)


def test_text_replace_and_property_setup(service, fake, session):
    service.type_text(session, named("edit"), "Привет 🌍", replace=True)
    assert service.inspect(session, named("edit"))["properties"]["text"] == "Привет 🌍"
    assert [r["keysequence"] for r in fake.requests if r["action"] == "shortcut"] == ["Ctrl+A", "Backspace"]
    assert service.set_properties(session, named("edit"), {"text": "fixture"})["verified"]


def test_property_assignment_must_be_verified(service, fake, session):
    fake.overrides["object_set_properties"] = lambda req: {}
    with pytest.raises(AdapterError) as caught:
        service.set_properties(session, named("edit"), {"text": "new"})
    assert caught.value.code == "PropertyVerificationFailed"


def test_snapshot_pagination_and_hidden_widgets(service, fake, session):
    fake.objects["apply"]["properties"]["visible"] = False
    page = service.snapshot(session, limit=1)
    assert page["total"] == 3
    assert page["next_offset"] == 1
    assert Path(page["artifact"]).is_file()
    assert service.snapshot(session, offset=1, limit=10)["next_offset"] is None
    assert service.snapshot(session, visible_only=False)["total"] == 4


def test_snapshot_long_text_saves_complete_values(service, fake, session):
    fake.objects["edit"]["properties"]["text"] = "x" * 5000
    result = service.snapshot(session)
    edit = next(n for n in result["widgets"] if n["path"] == "main/edit")
    assert edit["properties_truncated"]
    tree = json.loads(Path(result["artifact"]).read_text())
    assert len(tree["main/edit"]["properties"]["text"]) == 5000


def test_wait_absent_and_condition_timeout(service, fake, session):
    assert service.wait(session, named("missing"), exists=False)["exists"] is False
    start = time.monotonic()
    with pytest.raises(AdapterError) as caught:
        service.wait(session, named("edit"), {"text": "never"}, timeout=0.08, interval=0.05)
    assert caught.value.code == "ConditionTimeout"
    assert time.monotonic() - start < 0.5
    assert service.list_sessions()[0]["connected"]


def test_model_paths_and_selection(service, fake, session):
    result = service.model_read(session, named("tree"), offset=1, limit=1)
    assert result["items"][0]["itempath"] == "0-0"
    assert result["items"][0]["value"] == "file.txt"
    assert result["server_pagination"] is False
    service.model_select(session, named("tree"), row=1, itempath="0-0")
    assert fake.requests[-1]["itempath"] == "0-0"
    assert fake.requests[-1]["itemaction"] == "select"


@pytest.mark.parametrize("path", ["-1", "1-", "-1-0", "1-0/", "0-0/2147483648-0"])
def test_invalid_model_parent_path_never_selects(service, fake, session, path):
    with pytest.raises(AdapterError) as caught:
        service.model_select(session, named("tree"), row=0, itempath=path)
    assert caught.value.code == "InvalidItemPath"
    assert not any(r["action"] == "model_item_action" for r in fake.requests)


def test_screenshot_widget_and_detach(service, fake, session):
    screenshot = service.screenshot(session, named("main"))
    assert Path(screenshot["path"]).read_bytes().startswith(b"\x89PNG")
    assert fake.requests[-1]["oid"] == 42
    service.detach(session)
    assert service.list_sessions() == []
    assert not any(r["action"] == "quit" for r in fake.requests)


def test_gui_operations_are_serialized(service, fake, session):
    def click(req):
        time.sleep(0.04)
        return {}
    fake.overrides["widget_click"] = click
    before = len(fake.requests)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: service.click(session, named("apply")), range(2)))
    names = [r["action"] for r in fake.requests[before:]]
    assert names == ["object_find", "object_properties", "widget_click"] * 2
