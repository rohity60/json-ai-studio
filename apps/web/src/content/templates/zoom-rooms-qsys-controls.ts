import type { Template } from '@/content/types';

/** Zoom Rooms Controls profile driving a Q-SYS Core over ECP.
 *  Schema follows Zoom's commented sample profile
 *  (assets.zoom.us/docs/sample/zrcs-profile-commented.json) and Q-SYS ECP
 *  syntax (help.qsys.com, ECP Commands). Research notes:
 *  apps/web/ai/feature/templates/research/zoom-rooms-qsys.md */
export const template: Template = {
  meta: {
    id: 'zoom-rooms-qsys-controls',
    slug: 'zoom-rooms-qsys-controls',
    title: 'Zoom Rooms Controls profile for Q-SYS',
    description:
      'A Zoom Rooms Controls JSON profile that drives a Q-SYS Core over the External Control Protocol (TCP 1702) — room mute, volume and scene presets on the Zoom Rooms controller, plus rules that fire on meeting start/end and microphone mute.',
    category: 'AV / Room Systems',
    provider: 'Zoom Rooms',
    difficulty: 'intermediate',
    estimatedReadTime: '7 min',
    tags: ['zoom-rooms', 'q-sys', 'room-control', 'av', 'ecp'],
    schemaVersion: 'zoom-rooms-controls-profile',
    featured: false,
    updatedAt: '2026-10-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Change the Q-SYS Core IP to 192.168.1.140',
      'Add a scene that recalls a presentation preset',
      'Turn the room speakers off when the meeting ends',
      'Is this profile valid for Zoom Rooms? Fix anything that is wrong',
    ],
    relatedTemplates: [],
    relatedBlogs: ['zoom-rooms-qsys-json-profile'],
    formatSignature: ['/adapters/*/model', '/adapters/*/ip'],
    purpose:
      'Give the Zoom Rooms controller native buttons for your Q-SYS room — mute, volume, scene presets — and automate them on Zoom events, without a separate control processor.',
    whenToUse:
      'A Zoom Room whose audio/video is handled by a Q-SYS Core. The Core runs a design with the controls you want exported as Named Controls; this profile is pasted into the Zoom web portal under Room Management → Zoom Rooms → Edit → Devices → Enable Room Controls → Create Profile.',
    requiredFields: [
      'adapters — one entry per control endpoint; for Q-SYS use model "GenericNetworkAdapter"',
      'adapters[].ip — "tcp://<core-ip>:1702" (the Q-SYS ECP port; private IPs only)',
      'adapters[].ports[] — the device: unique id, name and its methods',
      'ports[].methods[] — id, name, command, type ("action" or "actions" with params)',
    ],
    optionalFields: [
      'methods[].params — choices substituted for % in command (e.g. 1/0 for mute)',
      'styles — main button, names and icons, e.g. "qsys_core.main_method=mute"',
      'rules — Zoom events → device commands: meeting_started, meeting_ended, microphone_muted, microphone_unmuted, video_started, video_stopped, operation_time_started, operation_time_ended',
    ],
    bestPractices: [
      'Export every control the profile uses as a Named Control in Q-SYS Designer — ECP addresses controls by that exact, case-sensitive name.',
      'End each ECP command with \\n (LF). A \\r before it is ignored, so \\r\\n also works.',
      'Use % in command plus params for on/off or up/down variants instead of duplicating methods.',
      'Keep model exactly "GenericNetworkAdapter" — Zoom only accepts iTachIP2SL, iTachIP2CC and GenericNetworkAdapter.',
      'Test commands with a telnet session to the Core on port 1702 before pasting the profile into Zoom.',
    ],
    security: [
      'Zoom rejects public IP addresses in a profile — keep the Core on the room network.',
      'Anything that can reach TCP 1702 on the Core can send control commands unless Core access control requires an ECP login — keep the Core on a restricted room network/VLAN.',
      'Control is one-way: Zoom sends commands but does not read Q-SYS state back, so buttons do not show live status.',
    ],
  },
  json: {
    adapters: [
      {
        model: 'GenericNetworkAdapter',
        ip: 'tcp://192.168.1.50:1702',
        ports: [
          {
            id: 'qsys_core',
            name: 'Room Audio',
            methods: [
              {
                id: 'mute',
                name: 'Room Mute',
                command: 'csv RoomMute %\n',
                params: [
                  { id: 'mute', name: 'Mute', value: '1' },
                  { id: 'unmute', name: 'Unmute', value: '0' },
                ],
                type: 'actions',
              },
              {
                id: 'volume',
                name: 'Volume',
                command: 'ct %\n',
                params: [
                  { id: 'up', name: 'Up', value: 'RoomVolumeUp' },
                  { id: 'down', name: 'Down', value: 'RoomVolumeDown' },
                ],
                type: 'actions',
              },
              {
                id: 'scene',
                name: 'Scene',
                command: 'ct %\n',
                params: [
                  { id: 'meeting', name: 'Meeting', value: 'SceneMeeting' },
                  { id: 'off', name: 'Room Off', value: 'SceneOff' },
                ],
                type: 'actions',
              },
            ],
          },
        ],
      },
    ],
    styles: [
      'qsys_core.main_method=mute',
      'qsys_core.volume.up.icon=icon_up',
      'qsys_core.volume.down.icon=icon_down',
    ],
    rules: {
      meeting_started: ['qsys_core.scene.meeting'],
      meeting_ended: ['qsys_core.scene.off'],
      microphone_muted: ['qsys_core.mute.mute'],
      microphone_unmuted: ['qsys_core.mute.unmute'],
    },
  },
};
