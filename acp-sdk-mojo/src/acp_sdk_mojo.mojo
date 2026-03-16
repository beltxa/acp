from std.python import Python
from std.python import PythonObject


fn _bridge() raises -> PythonObject:
    return Python.import_module("python_bridge")


fn load_or_create_agent(agent_id: String) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.load_or_create_agent(agent_id)


fn load_or_create_agent_with_options(agent_id: String, options: PythonObject) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.load_or_create_agent(agent_id, options)


fn send(
    agent: PythonObject,
    recipients: PythonObject,
    payload: PythonObject,
    context: PythonObject,
    message_class: PythonObject,
    expires_in_seconds: PythonObject,
    correlation_id: PythonObject,
    in_reply_to: PythonObject,
    delivery_mode: PythonObject,
) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.send(
        agent,
        recipients,
        payload,
        context,
        message_class,
        expires_in_seconds,
        correlation_id,
        in_reply_to,
        delivery_mode,
    )


fn send_basic(agent: PythonObject, recipients: PythonObject, payload: PythonObject, context: PythonObject) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.send_basic(agent, recipients, payload, context)


fn receive(agent: PythonObject, raw_message: PythonObject, handler: PythonObject) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.receive(agent, raw_message, handler)


fn request_capabilities(agent: PythonObject, recipient: String) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.request_capabilities(agent, recipient)


fn build_well_known_document(
    agent: PythonObject,
    base_url: PythonObject,
    identity_document_url: PythonObject,
) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.build_well_known_document(agent, base_url, identity_document_url)


fn resolve_well_known(agent: PythonObject, base_url: String, expected_agent_id: PythonObject) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.resolve_well_known(agent, base_url, expected_agent_id)


fn register_identity_document(agent: PythonObject, identity_document: PythonObject) raises:
    var bridge = _bridge()
    _ = bridge.register_identity_document(agent, identity_document)


fn create_overlay_runtime(
    agent: PythonObject,
    base_url: String,
    business_handler: PythonObject,
    passthrough_handler: PythonObject,
) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.create_overlay_runtime(agent, base_url, business_handler, passthrough_handler)


fn create_overlay_client(agent: PythonObject) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.create_overlay_client(agent)


fn overlay_send_acp(
    overlay_client: PythonObject,
    target_url: String,
    payload: PythonObject,
    recipient_agent_id: PythonObject,
    context: PythonObject,
    delivery_mode: String,
    expires_in_seconds: Int,
) raises -> PythonObject:
    var bridge = _bridge()
    return bridge.overlay_send_acp(
        overlay_client,
        target_url,
        payload,
        recipient_agent_id,
        context,
        delivery_mode,
        expires_in_seconds,
    )


fn is_acp_http_message(payload: PythonObject) raises -> Bool:
    var bridge = _bridge()
    return bridge.is_acp_http_message(payload)
