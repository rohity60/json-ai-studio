import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'zoom-rooms-qsys-json-profile',
    title: 'Control a Q-SYS Core from Zoom Rooms with a JSON profile',
    description:
      'How a Zoom Rooms Controls profile talks to Q-SYS: GenericNetworkAdapter on TCP 1702, ECP commands against Named Controls, % parameters, and rules that fire on meeting and mute events — plus the mistakes that make Zoom reject the profile.',
    updatedAt: '2026-10-21',
    author: 'JSON AI Studio',
    tags: ['zoom-rooms', 'q-sys', 'room-control', 'av'],
    readingTime: '8 min',
    aiSummary:
      'Zoom Rooms Controls profiles are JSON pasted into the Zoom web portal. For Q-SYS, use one adapter with model "GenericNetworkAdapter" and ip "tcp://<core>:1702", put the device under ports[], and write methods whose command is a Q-SYS ECP line (csv / ct) ending in \\n. % in a command is replaced by the chosen param value. Every control must be a Named Control in Q-SYS Designer. rules map Zoom events (meeting_started, meeting_ended, microphone_muted, microphone_unmuted, video_started, video_stopped, operation_time_started, operation_time_ended) to commands. No content-sharing event is documented. Control is one-way.',
    relatedTemplates: ['zoom-rooms-qsys-controls'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Which port does Zoom Rooms use to talk to a Q-SYS Core?',
        a: 'TCP 1702 — the Q-SYS External Control Protocol (ECP), a plain-text protocol. TCP 1710 is the JSON-RPC protocol (QRC); Zoom profiles send ECP lines, so use 1702.',
      },
      {
        q: 'Can a rule fire when someone starts or stops sharing content?',
        a: 'Not as far as Zoom documents. The rule events in Zoom\'s sample profile and staff answers are meeting_started, meeting_ended, microphone_muted, microphone_unmuted, video_started, video_stopped, operation_time_started and operation_time_ended. "sharing_started" is a Zoom webhook event name, not a Room Controls rule — test in your room before relying on any other event.',
      },
      {
        q: 'Why do my Q-SYS buttons not show the current state?',
        a: 'Zoom Rooms native control is one-way: it sends commands to Q-SYS but does not read control values back.',
      },
    ],
  },
  body: `A **Zoom Rooms Controls profile** is a JSON document you paste into the Zoom web portal. It puts buttons for your room equipment on the Zoom Rooms controller and can run commands automatically when a meeting starts or the microphone is muted. With a Q-SYS Core in the room, the profile speaks Q-SYS's **External Control Protocol (ECP)** directly — no extra control processor needed.

Zoom never published a full schema for these profiles; the reference is Zoom's own commented sample. Everything below follows that sample and the Q-SYS ECP documentation.

## 1. Prepare the Q-SYS design

ECP addresses controls **by name**, so every control the profile touches must be a **Named Control** in Q-SYS Designer: drag the control (a mute button, a gain, a snapshot trigger) into the Named Controls pane and give it a name such as \`RoomMute\` or \`SceneMeeting\`. Names are case-sensitive. Save the design to the Core and run it.

QSC also ships a ready-made **Zoom Rooms Sample Design** in Designer's Asset Manager. Its example profile only needs the Core IP edited.

## 2. The profile structure

\`\`\`json
{
  "adapters": [
    {
      "model": "GenericNetworkAdapter",
      "ip": "tcp://192.168.1.50:1702",
      "ports": [
        {
          "id": "qsys_core",
          "name": "Room Audio",
          "methods": [
            {
              "id": "mute",
              "name": "Room Mute",
              "command": "csv RoomMute %\\n",
              "params": [
                { "id": "mute", "name": "Mute", "value": "1" },
                { "id": "unmute", "name": "Unmute", "value": "0" }
              ],
              "type": "actions"
            }
          ]
        }
      ]
    }
  ],
  "rules": {
    "microphone_muted": ["qsys_core.mute.mute"],
    "microphone_unmuted": ["qsys_core.mute.unmute"]
  }
}
\`\`\`

- **adapters** — one per connection. \`model\` must be one of \`iTachIP2SL\`, \`iTachIP2CC\` or \`GenericNetworkAdapter\`; anything that is not a Global Cache iTach is a \`GenericNetworkAdapter\`.
- **ip** — for a generic adapter it is a URL with the port: \`tcp://<core-ip>:1702\`. Zoom refuses public IPs.
- **ports** — the device. Each needs a unique \`id\`; the controller shows its \`name\`.
- **methods** — the buttons. \`command\` is what gets sent; \`%\` is replaced by the \`value\` of the param the user taps. \`type\` is \`"action"\` for a single button and \`"actions"\` when there are params.

## 3. ECP commands that work in a profile

| Goal | ECP line | Notes |
|---|---|---|
| Set a value (mute, gain) | \`csv RoomMute 1\` | Number value |
| Set from text | \`css Input "HDMI 1"\` | Quote values with spaces |
| Press a trigger (snapshot, preset, volume step) | \`ct SceneMeeting\` | Trigger-type controls only |

Every command must end with a **line feed** — \`\\n\` in JSON. The Core ignores a carriage return before it, so \`\\r\\n\` also works. Without the terminator the Core waits and nothing happens.

Test each line first: \`telnet <core-ip> 1702\`, type \`csv RoomMute 1\`, and watch the control move in Q-SYS. If it answers \`bad_id\`, the Named Control name is wrong.

## 4. Rules: automate on Zoom events

\`rules\` maps a Zoom event to a list of \`device.method.param\` commands:

\`\`\`json
"rules": {
  "meeting_started": ["qsys_core.scene.meeting"],
  "meeting_ended": ["qsys_core.scene.off"]
}
\`\`\`

Documented events: \`meeting_started\`, \`meeting_ended\`, \`microphone_muted\`, \`microphone_unmuted\`, \`video_started\`, \`video_stopped\`, \`operation_time_started\` and \`operation_time_ended\` (Zoom Rooms 4.7.0+). There is **no documented content-sharing event** — names like \`sharing_started\` come from Zoom's webhook API, not from Room Controls.

## 5. Load it in Zoom

Zoom web portal → **Room Management → Zoom Rooms** → **Edit** on the room → **Devices** → enable **Room Controls** → **Create Profile** → paste the JSON → **Save**. A **Room Controls** icon appears on the controller.

## Common mistakes

These are the errors we see most in profiles people bring to JSON AI Studio:

- **Inventing a model name.** \`"model": "Q-SYS Core110f"\` or \`"GenericNetworkDevice"\` is rejected. Use \`"GenericNetworkAdapter"\` and put the Core's details in \`ip\`.
- **Methods directly on the adapter.** They belong inside \`ports[].methods\`.
- **Template syntax that is not Zoom's.** \`{{param}}\` placeholders are not substituted — Zoom only replaces \`%\`.
- **Using \`sg\` as a command.** \`sg\` is ECP's status/keep-alive request; it does not change anything. Use \`csv\`, \`css\` or \`ct\`.
- **Missing \`\\n\`.** The Core never executes a line without the terminator.
- **Controls that are not Named Controls.** ECP replies \`bad_id\`; export the control in Designer.
- **Port 1710.** That is the JSON-RPC protocol; Zoom profiles send ECP text, which is port 1702.

## Edit it with AI

Open the template in JSON AI Studio and describe the change — "add a scene that recalls the presentation preset", "mute the room when Zoom mutes". Paste your own profile and ask "is this valid for Zoom Rooms?" to get each suggested fix with the reason behind it.`,
};
