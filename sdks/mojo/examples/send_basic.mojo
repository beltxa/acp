from std.python import Python
from std.python import PythonObject

fn main() raises:
    var builtins = Python.import_module("builtins")
    var bridge = Python.import_module("acp_sdk_mojo")
    var agent = bridge.load_or_create_agent("agent:demo")

    var recipients = builtins.list()
    recipients.append("agent:other")

    var payload = builtins.dict()
    payload["message"] = "hello"

    _ = bridge.send(
        agent,
        recipients,
        payload,
        PythonObject("ping"),
        PythonObject("SEND"),
        PythonObject(300),
        PythonObject(None),
        PythonObject(None),
        PythonObject("auto"),
    )
