from std.python import Python
from std.python import PythonObject

from acp_sdk_mojo import load_or_create_agent_with_options
from acp_sdk_mojo import create_overlay_client
from acp_sdk_mojo import overlay_send_acp


fn main() raises:
    var builtins = Python.import_module("builtins")
    var options = builtins.dict()
    options["storage_dir"] = ".acp-mojo-data"
    options["allow_insecure_http"] = True
    options["discovery_scheme"] = "http"

    var sender = load_or_create_agent_with_options("agent:overlay.mojo.sender@localhost:9061", options)
    var client = create_overlay_client(sender)

    var payload = builtins.dict()
    payload["kind"] = "overlay-mojo-demo"
    payload["from"] = "agent:overlay.mojo.sender@localhost:9061"

    var response = overlay_send_acp(
        client,
        "http://localhost:9010",
        payload,
        PythonObject(None),
        PythonObject("overlay:mojo:demo"),
        "auto",
        120,
    )
    print(response)
