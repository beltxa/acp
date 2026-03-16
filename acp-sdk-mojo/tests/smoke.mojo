from python import PythonObject

from acp_sdk_mojo import build_well_known_document
from acp_sdk_mojo import load_or_create_agent


fn main() raises:
    var agent = load_or_create_agent("agent:mojo.smoke@localhost:9071")
    var well_known = build_well_known_document(
        agent,
        PythonObject("http://localhost:9071"),
        PythonObject(None),
    )
    print(well_known["agent_id"])
