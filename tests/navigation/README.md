# Hierarchical screen controller regression

Run `python tests/navigation/run.py` from the project root. The test drives the
production controller with trusted UART receive bytes and independently decodes
the physical UART TX pin, including frame, sequence, status and XOR checks.
It also drives local rotary/button events and PDF/monitor handshakes.

Run `python tests/navigation/run_integration.py` for the real-module integration
regression. It connects the controller's commands and feedback to the production
`guide_player` and `performance_looper`, then checks actual transport position,
play state, playback speed, recorded layers, undo, clear confirmation, and mute.

Coverage includes the six menu pages, per-page cursor wrapping, parent return,
direct sound/effect presets, audio ownership, Loop commands and two-step clear,
PDF transport backpressure, unavailable-PDF notice, spectrum-overlay priority,
pitch gestures, volume target selection, legacy flat commands, input validation,
and queueing local navigation at UART packet boundaries.

## Controller interface

New outputs are `ui_page[2:0]`, `ui_cursor[3:0]`, and `ui_confirm`. Pages 0–5 are
home, timbre, effects, Loop, songs, and settings. Each has six rows, except songs
with five. Submenu row 0 returns to the corresponding home row; entering a
submenu selects row 1. Rotation cancels confirmation. Emergency mute returns
home to row 0.

Local action 1 moves forward; 9 moves backward; 2 executes. Action 3 retains
emergency mute. Actions 7, 13 and 15 retain volume, pitch bend and vibrato.
The same actions may be sent with opcode 10. Opcode 10 action 5 executes the
legacy flat row immediately without leaving a selection latch; action 6 selects
a legacy flat row for a following host action 2. Physical B always executes the
visible hierarchical selection. Local rotation or opcode 36 selection releases
the compatibility latch. Monitor and visible-PDF controls take precedence over
underlying menus.

## Opcode 36

Uses the existing 28-byte protocol, with 20-byte payload. Request payload byte 0:

| Value | Operation |
| --- | --- |
| 0 | Read navigation state |
| 1 | Select page in byte 1 and row in byte 2; optional byte 3 = 1 checks the expected epoch in byte 4 |
| 2 | Execute current selection, returning state after application; optional byte 1 = 1 checks the expected epoch in byte 2 |
| 3 | Return from overlay/submenu, returning state after application |

Selecting the same page and row preserves a pending clear confirmation, allowing
a touch client to select then execute on both confirmation taps. Selecting a
different page or row cancels it. Read-only queries preserve it. Invalid page,
row or subcommand returns status 3; a mutating request while another local action
is queued returns status 4. An enabled epoch check also returns status 4 when
the interaction state has changed. These rejections leave the selection and
audio state unchanged. Query is still accepted when an action is queued.

Touch clients read the current epoch, send a guarded selection, then execute
with the new epoch returned by that selection. Both writes need the check so
an intervening physical mute or knob action cancels the stale click. A client
must discard a rejected click rather than retry it automatically. The 8-bit
epoch is for this short transaction window and wraps after 256 accepted intents.
Read-only status polling does not change it. Zero or omitted guard flags retain
the original unconditional request behavior for legacy diagnostic clients.

Response payload:

| Byte | Meaning |
| --- | --- |
| 0 | Existing result code |
| 1 | Page |
| 2 | Cursor |
| 3 | bit 0 confirmation; bit 1 monitor open; bit 2 PDF visible; bit 3 UI pending |
| 4 | Page row count |
| 5 | Legacy flat focus |
| 6 | Navigation protocol revision, 1 |
| 7 | Interaction epoch, unsigned 8-bit |
| 8–17 | Zero |
| 18 | Existing firmware major version, 32 |
| 19 | Echoed opcode, 36 |

`ui_notice=3` means no cached PDF is available. The controller emits no show
command in that case. `ui_confirm` indicates only the pending Loop clear.

The songs page uses guide action 4 for play/pause, action 3 for returning to the
beginning and stopping, and action 8 for cycling playback speed. Its second
transport entry is therefore labelled “返回开头”. Legacy flat entries retain
their original next-group and reset meanings.

The existing `tests/score_controller/run.py` is also retained as a regression for
PDF/PCM access, monitor transitions, and pending fade acknowledgements.

## Host and touchscreen compatibility

Run the offline host regressions from `realtime_synth/host`.

```powershell
python -m unittest test_navigation test_touch.ControllerTests test_host test_keypad.ControllerTests test_output_gain
```

On each connection, the host probes opcode 36 on firmware major 32. A valid
revision-1 reply enables hierarchical controls and adds `navigation` to the
existing state response. An unsupported reply to this read-only probe keeps the
connection active and uses the earlier flat menu. Reconnecting clears the cached
capability before probing the newly connected firmware.

The 1024×600 touchscreen uses the right-hand menu area `672 <= x < 1000`, with
row `i` covering `330 + 36*i <= y < 366 + 36*i`. The songs page has five rows and
the other pages have six. Submenu row 0 returns home. The bridge recognizes one
finger's release within the same row. A page, cursor, epoch, confirmation, or
overlay change during the gesture cancels that touch.

A `touch_click` request carries its `index`, `page`, `epoch`, and `confirm` state
alongside the existing receiver session. The host queries navigation again and
checks that snapshot. It sends a guarded select with the queried epoch, then a
guarded execute with the selection reply's epoch. A selection reply with a
pending action, an overlay, or a different page/cursor cancels execution. A stale
guard response refreshes state and drops that action. Repeated clear taps retain
the same selected row so the second explicit tap can confirm.

Web-page confirmation and PC-keypad confirmation also use guarded opcode 36.
The PC play/stop shortcut uses the existing ARM/PANIC session commands. Merged
menu rotation wraps within the current page. Rotation during a pending Loop
clear uses actual encoder-step commands so a complete turn also cancels the
confirmation. PDF uploads temporarily defer confirmation of the sheet viewer.

J18's FPGA decoder handles the physical gestures, including held-B rotation for
volume and held-A rotation for vibrato. The PC keypad bridge uses the saved
mapping in its configuration page. Its default A rotation adjusts volume, B
rotation moves selection, and B press executes on button-down. Touch forwarding
and J18 direct control share the hierarchical screen layout.

`test_navigation.py` exercises capability detection, reconnects, both confirmation
entry points, exact touch geometry, epoch-guarded commands, rejection after a
physical action, queued selection replies, full-turn clear cancellation, and
PDF/monitor overlay priority. These are offline protocol and gesture tests.
