"""Convert participant B's extraction snapshot into the core's input model."""

import re

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
    for index, item in enumerate(extraction.get("flows", []), 1):
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
        is_ntp = item.get("application_protocol") == "NTP" or re.search(
            r"\bNTP\b", description or "", re.IGNORECASE
        )
        if payload == "data" and protocol == "UDP" and is_ntp:
            protocol = "NTP"
        if payload == "data" and protocol == "unknown":
            protocol = None
        flow = {
            "id": item.get("id") or f"flow-{index}",
            "source_network_id": source,
            "target_network_id": target,
            "payload": payload,
            "direction": MODE.get(item.get("mode")),
            "initiator_network_id": initiator,
            "recipient": item.get("recipient"),
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
                   manual_file_users=extraction.get("manual_file_users"),
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
