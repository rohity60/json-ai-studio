# Research — Zoom Rooms Controls profile + Q-SYS (2026-10-21)

Source for a planned template ("Zoom Rooms Controls profile — Q-SYS Core") and blog
("Control a Q-SYS Core from Zoom Rooms with a JSON profile"). Trigger: prod chat
2026-10-19 ("make this code work with qsys to control zoom room").

## 1. Zoom Rooms Controls profile schema

Authoritative reference: Zoom's commented sample
<https://assets.zoom.us/docs/sample/zrcs-profile-commented.json> (Zoom never published a
full schema doc — devforum staff acknowledged the gap, ticket ZOOM-131766).

Top level: `adapters` (required), `styles` (optional), `rules` (optional).

**adapters[]**
- `model` — only `iTachIP2SL`, `iTachIP2CC`, `GenericNetworkAdapter` are supported
  ("Currently, we only support iTachIP2SL/iTachIP2CC/GenericNetworkAdapter(tcp)").
- `ip` — for `GenericNetworkAdapter` a URL: `"tcp://10.100.87.99:4998"` (or `udp://`).
  iTach may use `uuid` (`GlobalCache_<MAC>`) for auto-discovery instead.
- Public IPs are rejected (`ZRCSErrorCode_IP_Is_Public`).
- `ports[]` — each device: `id` (unique), `name`, optional `settings` (serial: `baud_rate`,
  `flow_control`, `parity` — IP2SL only), `methods[]`. IP2CC ports use `position` and get an
  auto-generated `power` method.
- GenericNetworkAdapter: one port (device) per TCP connection; multiple devices → same port,
  multiple methods. A method `init` is used for generic adapter configuration.

**methods[]**: `id`, `name`, `command`, optional `params[]` (`id`, `name`, `value`), `type`
(`"action"` single button / `"actions"` with params). `%` in `command` is replaced by the
chosen param `value` — e.g. `"command": "setstate,1:3,%\r"` with params on=1/off=0.
Hex commands use `"\\x99\\xA2..."`. Optional `invisible: true` hides a method (devforum staff).

**styles[]**: strings — `"<device>.main_method=power"`, `"<device>.icon=icon_curtain"`,
`"<device>.<method>.icon=icon_power"`, `"<device>.<method>.<param>.icon=icon_up"`.

**rules{}**: event → list of `"<deviceId>.<methodId>[.<paramId>]"` (also `=paramId` /
`=paramValue` forms). Documented events (Zoom sample + Zoom staff devforum post):
`meeting_started`, `meeting_ended`, `microphone_muted`, `microphone_unmuted`,
`video_started`, `video_stopped`, `operation_time_started`, `operation_time_ended`
(ZR ≥ 4.7.0). **No content-sharing (share start/stop) event is documented** — unverified
whether newer releases added one; do not ship `sharing_started` as a rule without
confirmation.

Constraints: one button controls one device command; JSON must be strict (no comments
in the real profile). Error codes include Json_Syntax_Error, Json_Config_Error, IP_Error,
DeviceID/MethodID/ParamID_Error, Empty_Device_Error.

Portal: Admin → Room Management → Zoom Rooms → Edit → Devices → Enable Room Controls →
Create Profile → paste JSON → Save. Controller shows a "Room Controls" icon.

## 2. Q-SYS side

- Zoom → Q-SYS control uses **ECP** (External Control Protocol), ASCII over **TCP 1702**
  (TCP 1710 is the JSON-RPC QRC protocol — not what Zoom profiles use). Control is
  **one-way** (QSC guide).
- Each device control must be exported as a **Named Control** in Q-SYS Designer; ECP
  addresses controls by that name.
- ECP syntax (help.qsys.com ECP Commands): `csv ID VALUE`, `csp ID POSITION`,
  `css ID STRING`, `ct ID` (trigger), `cg ID` (get). Terminator **LF**; a CR before LF is
  ignored, so `\r\n` works. Case-sensitive; names/strings with spaces in double quotes.
  `sg` = status get (keep-alive), not a control command.
- Core closes idle sockets after 60 s.
- QSC ships a "Zoom Rooms Sample Design" in Designer's Asset Manager containing a sample
  JSON profile; edit line 5 `<CORE IP ADDRESS HERE>`.

## 3. Prod chat 2026-10-19 — what the user's profile got wrong

User JSON (2 top-level keys) + our model's 4 diffs:

| Diff | Verdict |
|---|---|
| `/adapters/0/name` `Core-Salon` → `Q-SYS Core110f` | Harmless; adapter-level `name` isn't in Zoom's sample. |
| `/adapters/0/model` `GenericNetworkDevice` → `Q-SYS Core110f` | **Breaks the profile.** Both values invalid; must be `GenericNetworkAdapter`. |
| `/adapters/0/ip` unchanged `tcp://192.168.1.140:1702` | No-op diff (known no-op bug). IP/port were already right. |
| command `sg "{{_param1}}" {{_param2}}\r\n` → `{{_param1}}\r\n` | Both wrong: `{{…}}` isn't Zoom syntax (`%` is); `sg` isn't a control command; result sends raw text. Should be e.g. `ct ShareStart\n` / `csv "Room Mute" %\n`. |
| (structure) `methods` directly on the adapter | Should be `adapters[].ports[].methods`. |
| "sharing_started / sharing_ended" | Not a documented Zoom rule event; user likely conflated with Zoom webhooks (`meeting.sharing_started`). |

Takeaways: users arrive with AI-generated, invalid profiles; our model edits them without
schema knowledge. Template + blog should lead with a valid profile and a "common mistakes"
section; product-side, consider format-aware validation hints for known templates.

## Sources

- Zoom commented sample profile — https://assets.zoom.us/docs/sample/zrcs-profile-commented.json
- Zoom devforum "Room Controls" — https://devforum.zoom.us/t/room-controls/7472
- Zoom devforum "Room controls Rules" (#22, staff) — https://devforum.zoom.us/t/room-controls-rules/29582/22
- Q-SYS: How To Setup Zoom Rooms Native Controls (JSON) — https://support.qsys.com/en_US/alliances-partnerships/how-to-%7C-setup-zoom-rooms-native-controls-json
- QSC Solutions Application Guide: Zoom Rooms Native Room Controls with Q-SYS — https://www.qscaudio.com/resource-files/productresources/dn/qsys_solutions/q_dn_qsys-solutions_zoom_room_3rd_party_control_application_guide.pdf
- Q-SYS ECP Commands — https://help.qsys.com/Content/External_Control_APIs/ECP/ECP_Commands.htm
- Q-SYS Remote Connectivity (ports 1702/1710) — https://help.qsys.com/Content/Networking/Remote_Connectivity.htm
- Biamp: Integrate Biamp Control with Zoom Rooms Room Control — https://support.biamp.com/Biamp_Control/Control_configuration/Integrate_Biamp_Control_with_Zoom_Rooms_Room_Control
- kielthecoder: Zoom Room Controls — https://kielthecoder.com/2023/12/01/zoom-room-controls/
