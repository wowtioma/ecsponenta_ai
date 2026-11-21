"""Convert participant B's extraction snapshot into the core's input model."""

from rules import Flow, Network, Session

MODE = {"one-way": "one_way", "two-way": "two_way"}
FILE_MODE = {"manual": "manual", "pull": "PULL", "push": "PUSH", "usb": "USB"}


def session_from_extraction(session_id: str, extraction: dict) -> Session:
    """Adapt one extraction. Missing engineering facts remain unset."""
    networks = [
        Network(id=item["id"], name=item["name"],
                kind=item["trust"] if item.get("trust") in ("open", "closed") else None)
        for item in extraction.get("networks", [])
    ]
    networks_by_id = {network.id: network for network in networks}
    fallback = extraction.get("_fallback") or (
        "направление/режим каждого потока (regex-фолбэк)" in extraction.get("unknowns", [])
    )
    flows = []
    items = extraction.get("flows", [])
    reserved_ids = {item["id"] for item in items if isinstance(item.get("id"), str) and item["id"].strip()}
    used_ids = set()
    next_id = 1
    for item in items:
        flow_id = item.get("id")
        if not isinstance(flow_id, str) or not flow_id.strip() or flow_id in used_ids:
            while f"flow-{next_id}" in reserved_ids | used_ids:
                next_id += 1
            flow_id = f"flow-{next_id}"
        used_ids.add(flow_id)
        source = item.get("from")
        target = item.get("to")
        if source not in networks_by_id:
            source = None
        if target not in networks_by_id:
            target = None
        initiator = item.get("initiator_network_id")
        if initiator not in networks_by_id:
            initiator = None
        payload = {"data": "data", "file": "files"}.get(item.get("type"))
        description = item.get("description") or None
        protocol = item.get("protocol")
        port = item.get("port")
        if fallback:
            # B's regex fallback can attach one text-wide port to every protocol.
            port = None
        is_ntp = item.get("application_protocol") == "NTP"
        if payload == "data" and protocol == "UDP" and is_ntp:
            protocol = "NTP"
        if payload == "data" and protocol == "unknown":
            protocol = None
        recipient = item.get("recipient")
        if isinstance(recipient, str):
            label = recipient.strip().casefold().strip('«»"').strip()
            target_network = networks_by_id.get(target)
            network_labels = {"офис", "цех", "офисная сеть", "сеть цеха", "открытая сеть", "закрытая сеть"}
            if target_network:
                network_labels.add(target_network.name.strip().casefold())
            if payload == "data" and label in network_labels and not item.get("recipient_confirmed_role"):
                recipient = None
        source_device = item.get("source_device")
        if isinstance(source_device, str):
            source_device = source_device.strip() or None
            source_network = networks_by_id.get(source)
            if source_network and source_device and source_device.casefold() == source_network.name.strip().casefold():
                source_device = None
        else:
            source_device = None
        flow = {
            "id": flow_id,
            "source_network_id": source,
            "target_network_id": target,
            "payload": payload,
            "direction": MODE.get(item.get("mode")),
            "initiator_network_id": initiator,
            "recipient": recipient,
            "source_device": source_device,
            "description": description,
            "reverse_forbidden": item.get("reverse_forbidden"),
        }
        if payload == "data":
            flow.update(protocol=protocol, port=port)
        if payload == "files":
            flow.update(
                source_methods=file_methods(item, networks_by_id.get(source), "source"),
                target_methods=file_methods(item, networks_by_id.get(target), "target"),
                source_checks=item.get("source_checks"),
                target_checks=item.get("target_checks"),
                access_group=item.get("access_group"),
            )
        flows.append(Flow.model_validate(flow))
    return Session(session_id=session_id, networks=networks, flows=flows,
                   assumptions={"same_file_checks": "yes"} if extraction.get("same_file_checks") else {},
                   manual_file_users=extraction.get("manual_file_users"),
                   unknown_answers=[
                       f"{flow.id}.port" for flow in flows
                       if flow.port is None and flow.protocol in extraction.get("confirmed_unknown_ports", [])
                   ],
                   requests_for_vendor=extraction.get("requests_for_vendor", []))


def file_methods(item: dict, network: Network | None, side: str):
    explicit = item.get(f"{side}_methods")
    if explicit is not None:
        return explicit
    if network is None or network.kind is None:
        return None
    mode = FILE_MODE.get(item.get(f"method_{network.kind}"))
    if mode is None:
        return None
    protocols = item.get("protocol")
    protocol = protocols.get(network.kind) if isinstance(protocols, dict) else None
    if protocol not in ("SFTP", "FTP", "SMB"):
        protocol = None
    return [{"mode": mode, "protocol": protocol}]
