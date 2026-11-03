"""Connected-state G2 sweep for the net profile (r60abd1-host-net).

One port open, gap-tolerant calls throughout. Covers: truthful WIFI_STATUS
(F-8 fix), scan coexistence while connected, full config transactions, the
device-web-server external write entry, the job lifecycle, telemetry
observation, noise/backpressure recovery, and restart persistence.
"""

import json
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote


def web_get_number(ip, name):
    with urllib.request.urlopen(f"http://{ip}/number/{quote(name)}", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def web_set_number(ip, name, value):
    req = urllib.request.Request(f"http://{ip}/number/{quote(name)}/set?value={value}",
                                 data=b"", method="POST")  # empty body => Content-Length: 0
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def build(run_g2):
    """Return cmd_connected wired to the runner's helpers."""
    Result = run_g2.Result
    connect = run_g2.connect
    gap_call = run_g2.gap_call
    wait_job_terminal = run_g2.wait_job_terminal
    read_all_config = run_g2.read_all_config
    convex_polygon = run_g2.convex_polygon
    wait_quiet = run_g2.wait_quiet
    mwcp = run_g2.mwcp

    def cmd_connected(args):
        import uuid as _uuid
        result = Result("g2-connected")
        client, evidence = connect(args, "g2-connected", allow_write=True)
        outcome = None
        try:
            client.hello(timeout_ms=30000)
            result.check("hello", True, f"boot={client.boot_id}")
            wait_quiet(client, max_wait_s=240)

            # --- truthful connected status (F-8 fix)
            st = gap_call(client, "WIFI_STATUS").get("result", {})
            result.check("wifi_connected_truth", st.get("state") == "connected" and st.get("ip"),
                         f"state={st.get('state')} ip={st.get('ip')} rssi={st.get('rssi_dbm')}")
            device_ip = st.get("ip")
            evidence.note({"event": "device_ip", "ip": device_ip})

            # --- G2-06: scan coexistence x10 while connected
            rounds_ok = 0
            for i in range(10):
                op = str(_uuid.uuid4())
                r = gap_call(client, "WIFI_SCAN", {"op_id": op})
                if not r.get("ok"):
                    result.notes.append(f"coexist round {i}: refused {json.dumps(r)[:80]}")
                    time.sleep(3)
                    continue
                job = r["result"]["job_id"]
                term = wait_job_terminal(client, job, 60000)
                page = gap_call(client, "WIFI_SCAN_RESULTS", {"job_id": job, "cursor": None})
                stc = gap_call(client, "WIFI_STATUS").get("result", {})
                if term and term.get("state") in ("succeeded", "failed") and page.get("ok") is not None and stc.get("state"):
                    rounds_ok += 1
            result.check("coexist_10_rounds", rounds_ok == 10, f"{rounds_ok}/10")
            st = gap_call(client, "WIFI_STATUS").get("result", {})
            result.check("still_connected_after_scans", st.get("state") == "connected", json.dumps(st)[:100])

            # --- one full paginated result set: sorted, aliased
            op = str(_uuid.uuid4())
            r = gap_call(client, "WIFI_SCAN", {"op_id": op})
            items, cursor, pages = [], None, 0
            if r.get("ok"):
                job = r["result"]["job_id"]
                wait_job_terminal(client, job, 60000)
                while pages < 24:
                    page = gap_call(client, "WIFI_SCAN_RESULTS", {"job_id": job, "cursor": cursor})
                    if not page.get("ok"):
                        break
                    res = page["result"]
                    items += res.get("items", [])
                    pages += 1
                    cursor = res.get("next_cursor")
                    if cursor is None:
                        break
            rssis = [i.get("rssi_dbm") for i in items]
            result.check("scan_results_sorted_desc", len(items) > 0 and all(a >= b for a, b in zip(rssis, rssis[1:])),
                         f"items={len(items)} pages={pages}")
            result.check("scan_ssids_aliased",
                         all(s is None or s.startswith("AP-") or s == "TEST_AP"
                             for s in (i.get("ssid") for i in items)),
                         str([i.get("ssid") for i in items[:6]]))

            # --- G2-04 core transactions
            base_cfg, rev0, cfg_pages = read_all_config(client)
            result.check("config_read_8_keys", len(base_cfg) == 8, f"keys={len(base_cfg)} pages={cfg_pages}")
            max_changes = {
                "install.x_cm": 120.0, "install.y_cm": -80.0, "install.z_cm": 280.0,
                "install.yaw_deg": 15.0, "install.pitch_deg": -5.0, "install.roll_deg": 3.0,
                "geometry.boundary_cm": convex_polygon(64),
                "areas.definitions": [
                    {"slot": 0, "enabled": True, "name": "g2-door", "points_cm": convex_polygon(12, 150)},
                    {"slot": 1, "enabled": True, "name": "g2-desk", "points_cm": convex_polygon(12, 200)},
                    {"slot": 2, "enabled": True, "name": "g2-sofa", "points_cm": convex_polygon(12, 300)},
                ],
            }
            val = gap_call(client, "CONFIG_VALIDATE", {"base_revision": rev0, "changes": max_changes})
            result.check("validate_max_ok", val.get("ok") is True, json.dumps(val)[:120])
            _, rev_after_val, _ = read_all_config(client)
            result.check("validate_no_side_effect", rev_after_val == rev0, f"{rev0}->{rev_after_val}")
            for name, changes in [
                ("self_intersect", {"geometry.boundary_cm": [[0, 0], [100, 100], [100, 0], [0, 100]]}),
                ("65_points", {"geometry.boundary_cm": convex_polygon(65)}),
                ("out_of_range", {"install.z_cm": 601}),
                ("unknown_field", {"install bogus": 1}),
                ("dup_slot", {"areas.definitions": [
                    {"slot": 0, "enabled": True, "name": "a", "points_cm": convex_polygon(3, 100)},
                    {"slot": 0, "enabled": True, "name": "b", "points_cm": convex_polygon(3, 100)}]}),
            ]:
                resp = gap_call(client, "CONFIG_VALIDATE", {"base_revision": rev0, "changes": changes})
                result.check(f"illegal_{name}",
                             resp.get("ok") is False and resp.get("error", {}).get("code") in
                             ("INVALID_ARGUMENT", "OUT_OF_RANGE", "UNKNOWN_FIELD"), json.dumps(resp)[:110])
            op1 = str(_uuid.uuid4())
            commit = gap_call(client, "CONFIG_COMMIT", {"base_revision": rev0, "op_id": op1, "changes": max_changes})
            rev1 = commit.get("result", {}).get("revision")
            result.check("commit_max_persisted",
                         commit.get("ok") is True and commit.get("result", {}).get("persisted") is True,
                         json.dumps(commit)[:160])
            back, rev_now, _ = read_all_config(client)
            result.check("commit_readback",
                         back.get("install.x_cm") == 120.0 and isinstance(back.get("geometry.boundary_cm"), list)
                         and len(back["geometry.boundary_cm"]) == 64 and len(back.get("areas.definitions") or []) == 3,
                         f"boundary={len(back.get('geometry.boundary_cm') or [])} areas={len(back.get('areas.definitions') or [])}")
            replay = gap_call(client, "CONFIG_COMMIT", {"base_revision": rev0, "op_id": op1, "changes": max_changes})
            result.check("op_id_replay_idempotent",
                         replay.get("ok") is True and replay.get("result", {}).get("revision") == rev1,
                         json.dumps(replay)[:140])
            small = dict(max_changes)
            small["install.x_cm"] = 121.0
            reuse = gap_call(client, "CONFIG_COMMIT", {"base_revision": rev1, "op_id": op1, "changes": small})
            result.check("op_id_reuse_rejected", reuse.get("error", {}).get("code") == "OP_ID_REUSE",
                         json.dumps(reuse)[:120])
            conflict = gap_call(client, "CONFIG_COMMIT", {"base_revision": rev0, "op_id": str(_uuid.uuid4()),
                                                          "changes": {"install.x_cm": 999.0}})
            result.check("stale_base_conflict", conflict.get("error", {}).get("code") == "REVISION_CONFLICT",
                         json.dumps(conflict)[:120])
            back2, _, _ = read_all_config(client)
            result.check("external_update_preserved", back2.get("install.x_cm") == 120.0, str(back2.get("install.x_cm")))

            # --- G2-04 device-web external entry
            if device_ip:
                base_web = web_get_number(device_ip, "Mount X")
                result.check("web_read_baseline", base_web.get("value") is not None, json.dumps(base_web)[:120])
                web_set_number(device_ip, "Mount X", 123)
                time.sleep(2.5)
                web_after = web_get_number(device_ip, "Mount X")
                result.check("web_write_applied", web_after.get("value") == "123", json.dumps(web_after)[:120])
                cas = gap_call(client, "CONFIG_COMMIT", {"base_revision": rev1, "op_id": str(_uuid.uuid4()),
                                                         "changes": {"install.x_cm": 111.0}})
                result.check("web_write_causes_cas_conflict", cas.get("error", {}).get("code") == "REVISION_CONFLICT",
                             json.dumps(cas)[:130])
                back3, rev3, _ = read_all_config(client)
                result.check("web_value_preserved_on_conflict", back3.get("install.x_cm") == 123.0,
                             f"x={back3.get('install.x_cm')} rev={rev3}")
                usb_commit = gap_call(client, "CONFIG_COMMIT", {"base_revision": rev3, "op_id": str(_uuid.uuid4()),
                                                                "changes": {"install.x_cm": 140.0}})
                result.check("usb_commit_after_web", usb_commit.get("ok") is True, json.dumps(usb_commit)[:120])
                time.sleep(2.5)
                web_final = web_get_number(device_ip, "Mount X")
                result.check("web_reads_back_usb_write", web_final.get("value") == "140", json.dumps(web_final)[:120])
            else:
                result.check("web_entry_skipped_no_ip", False, "device had no IP")

            # --- G2-05 job lifecycle
            nc = gap_call(client, "ACTION_START", {"action_id": "radar.reset_module", "op_id": str(_uuid.uuid4()),
                                                   "params": {}, "confirm": None})
            result.check("reset_no_confirm_rejected", nc.get("error", {}).get("code") == "INVALID_ARGUMENT",
                         json.dumps(nc)[:110])
            wc = gap_call(client, "ACTION_START", {"action_id": "radar.reset_module", "op_id": str(_uuid.uuid4()),
                                                   "params": {}, "confirm": "device.restart"})
            result.check("reset_wrong_confirm_rejected", wc.get("error", {}).get("code") == "INVALID_ARGUMENT",
                         json.dumps(wc)[:110])
            op_reset = str(_uuid.uuid4())
            rs = gap_call(client, "ACTION_START", {"action_id": "radar.reset_module", "op_id": op_reset,
                                                   "params": {}, "confirm": "radar.reset_module"})
            job_reset = rs.get("result", {}).get("job_id")
            term = wait_job_terminal(client, job_reset, 60000)
            result.check("reset_terminal_unverified",
                         term is not None and term.get("state") == "succeeded"
                         and term.get("result") == {"verified": False, "verification": "none"},
                         json.dumps(term)[:160] if term else "timeout")
            again = gap_call(client, "ACTION_START", {"action_id": "radar.reset_module", "op_id": op_reset,
                                                      "params": {}, "confirm": "radar.reset_module"})
            result.check("reset_op_id_idempotent",
                         again.get("ok") is True and again.get("result", {}).get("job_id") == job_reset,
                         json.dumps(again)[:120])
            misuse = gap_call(client, "ACTION_START", {"action_id": "device.restart", "op_id": op_reset,
                                                       "params": {}, "confirm": "device.restart"})
            result.check("op_id_cross_action_rejected", misuse.get("error", {}).get("code") == "OP_ID_REUSE",
                         json.dumps(misuse)[:110])

            # --- G2-03 telemetry observation (60 s)
            sub = gap_call(client, "SUBSCRIBE", {"streams": [{"id": "telemetry", "max_rate_hz": 1}],
                                                 "event_budget_bps": 8000})
            result.check("subscribe_ok", sub.get("ok") is True, "")
            events = client.drain_events(60000)
            telemetry = [e for e in events if e["meta"]["code"] == mwcp.CODE["TELEMETRY"]]
            result.check("telemetry_received", len(telemetry) > 0, f"n={len(telemetry)} in 60s")
            if telemetry:
                seqs = [e["payload"].get("source_seq") for e in telemetry]
                result.check("source_seq_nondecreasing", all(b >= a for a, b in zip(seqs, seqs[1:])), f"n={len(seqs)}")
                speeds = [t.get("speed_cm_s") for e in telemetry for t in (e["payload"].get("targets") or [])]
                result.check("speed_null_for_r60", all(s is None for s in speeds), "")
                result.notes.append(f"no_target_frames={sum(1 for e in telemetry if e['payload'].get('targets') in ([], None))}/{len(telemetry)}")
                result.notes.append(f"targets_quality={telemetry[0]['payload'].get('targets_quality')}")
            gap_call(client, "UNSUBSCRIBE", {"streams": ["telemetry"]})

            # --- noise + recovery, then backpressure
            good = mwcp.encode_frame(1, client.session_id, client._req + 1, 2, b"{}", 0)
            bad = bytearray(good)
            bad[-2] ^= 0xFF
            client.write_raw(bytes(bad), "noise-bad-crc")
            client.write_raw(b"plain noise\r\n", "noise-plain")
            client.write_raw(good[: len(good) // 2], "noise-half")
            time.sleep(2.4)
            client.write_raw(good[len(good) // 2:], "noise-half-tail")
            ok = client.soft_call("PING")
            result.check("recovery_after_noise", ok.get("uptime_ms") is not None, "")
            gap_call(client, "SUBSCRIBE", {"streams": [{"id": "telemetry", "max_rate_hz": 5}],
                                           "event_budget_bps": 8000})
            bbase = gap_call(client, "STATUS_GET").get("result", {})
            time.sleep(12)
            client.resume_reads()
            bafter = gap_call(client, "STATUS_GET").get("result", {})
            result.check("rpc_after_backpressure", bafter.get("uptime_ms", 0) > bbase.get("uptime_ms", 10 ** 12),
                         f"{bbase.get('uptime_ms')} -> {bafter.get('uptime_ms')}")
            gap_call(client, "UNSUBSCRIBE", {"streams": ["telemetry"]})

            # --- restart persistence leg
            boot_before = client.boot_id
            rjob = gap_call(client, "ACTION_START", {"action_id": "device.restart", "op_id": str(_uuid.uuid4()),
                                                     "params": {}, "confirm": "device.restart"})
            result.check("restart_accepted", rjob.get("ok") is True, json.dumps(rjob)[:110])
            client.close()
            time.sleep(12)
            client2, _ev2 = connect(args, "g2-connected-r2", allow_write=True)
            client2.hello(timeout_ms=30000)
            result.check("boot_id_changed", client2.boot_id != boot_before, "")
            back4, rev4, _ = read_all_config(client2)
            result.check("config_survives_restart", back4.get("install.x_cm") == 140.0 and rev4 == rev3,
                         f"rev {rev3}->{rev4} x={back4.get('install.x_cm')}")
            cs2 = gap_call(client2, "COMMIT_STATUS", {"op_id": op1})
            result.check("commit_history_survives_restart", cs2.get("result", {}).get("found") is True,
                         json.dumps(cs2)[:130])
            old = gap_call(client2, "JOB_GET", {"job_id": job_reset})
            result.check("old_job_unknown_after_reboot",
                         old.get("ok") and old.get("result", {}).get("state") == "unknown", json.dumps(old)[:130])
            st2 = None
            for _ in range(15):
                st2 = gap_call(client2, "WIFI_STATUS").get("result", {})
                if st2.get("state") == "connected":
                    break
                time.sleep(2)
            result.check("wifi_reconnects_after_restart", st2 is not None and st2.get("state") == "connected",
                         json.dumps(st2)[:110])
            status = "pass" if all(c["pass"] for c in result.checks) else "fail"
            ev2s = _ev2.close()
            client2.close()
            outcome = {**result.finish(status), "evidence": None, "evidence_2": ev2s}
        except Exception as error:  # noqa: BLE001
            result.notes.append(f"exception: {error!r}")
            outcome = {**result.finish("fail")}
        summary = evidence.close()
        client.close()
        return {**outcome, "evidence": summary}

    return cmd_connected
