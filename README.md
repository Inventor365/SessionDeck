<div align="center">

# SessionDeck

**Run many terminal sessions on a remote Linux server at once, and switch between them from a small Windows app.**

![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![tmux](https://img.shields.io/badge/server-tmux-1BB91F?logo=tmux&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

</div>

---

## Why

When an AI coding agent such as **Claude Code**, a long **compile**, a **ROM build** or a deploy is running in your SSH window, that window is busy until it finishes. You end up opening more SSH windows, losing track of which is which, and losing everything when the connection drops.

**SessionDeck fixes this.** Every task gets its own **tmux** session on the server and opens in its own Windows Terminal tab. One window lists all of them and shows what each one is doing.

- Sessions **keep running on the server** when you close the tab, your PC sleeps or the Wi-Fi drops.
- Reopen a session later, from this app, Termius, PuTTY or your phone, and it is exactly where you left it.

```
 Windows PC                                         Linux server
┌──────────────────────────────┐   ssh (key)   ┌──────────────────────────┐
│ SessionDeck                  │ ────────────▶ │ tmux                     │
│  ├─ session list + preview   │               │  ├─ build      (make -j) │
│  └─ Windows Terminal tabs ───┼─────────────▶ │  ├─ agent-1    (claude)  │
│       build | agent-1 | ...  │               │  ├─ agent-2    (claude)  │
└──────────────────────────────┘               │  └─ logs       (tail -f) │
                                               └──────────────────────────┘
```

## Features

| | |
|---|---|
| 🖥️ **Multiple servers** | Store any number of servers (address, port, username) and switch between them from a dropdown |
| 🔑 **One-click key login** | Enter your password once and SessionDeck creates an SSH key and installs it on the server. **Passwords are never saved** |
| 📋 **Session browser** | Every tmux session with its running command, whether it is open somewhere, last activity and folder. Refreshes every 5 s |
| 👀 **Live preview** | See the latest output of any session without opening it, handy for checking on a running agent |
| ⌨️ **Send to session** | Type a command or a reply to an agent, or send **Ctrl-C** or **Esc**, straight from the app |
| ➕ **New session** | Choose a name, a starting folder and optionally a program to start (`claude`, `htop` and so on). It opens in a new tab |
| 🪟 **Attach anywhere** | Open in a Windows Terminal tab or a new window. *Independent view* opens the same session again so you can look at a different window of it |
| ✏️ **Manage** | Rename or kill sessions, or open a plain shell that doesn't use tmux |
| 💻 **CLI too** | `sessiondeck ls`, `sessiondeck new build ~/project make`, `sessiondeck a build` |
| 📦 **Standalone .exe** | Runs on a PC without Python |

---

## Requirements

| Where | Requirement | Notes |
|---|---|---|
| Windows 10/11 | **OpenSSH Client** | Built in. If it's missing: *Settings → System → Optional features → Add → "OpenSSH Client"* |
| Windows | **Windows Terminal** *(recommended)* | `winget install Microsoft.WindowsTerminal`. Without it, sessions open in console windows |
| Windows | **Python 3.9+ with tkinter** | *Only needed if you run from source.* The `.exe` needs nothing else |
| Server | **tmux** | `sudo apt install tmux` (Debian/Ubuntu), `sudo dnf install tmux` (Fedora/RHEL), `brew install tmux` (macOS) |

---

## Installation

### Option A: download the .exe (easiest)
1. Go to [**Releases**](../../releases) and download `SessionDeck.exe`.
2. Put it anywhere, for example `C:\Tools\SessionDeck\`, and double-click it.
3. Windows SmartScreen may warn you because the exe isn't code-signed. Click **More info → Run anyway**.

### Option B: from source
```bat
git clone https://github.com/Inventor365/SessionDeck.git
cd SessionDeck
install.cmd
```
`install.cmd` does four things:
- checks for OpenSSH, Windows Terminal and Python/tkinter, and tells you what's missing
- creates **Desktop** and **Start Menu** shortcuts
- adds the folder to your user `PATH` so `sessiondeck` works in any new terminal
- needs **no admin rights**

### Option C: build the .exe yourself
```bat
build_exe.cmd
```
This installs PyInstaller and produces `dist\SessionDeck.exe`. If you run `install.cmd` afterwards, the shortcuts use the exe.

---

## First-time setup

1. Launch **SessionDeck**. On first run the **Servers** window opens automatically.
2. Fill in:
   | Field | Example |
   |---|---|
   | Display name | `buildbox` |
   | Server address | `myserver.example.com` or `192.168.1.50` |
   | Port | `22` |
   | Username | `alice` |
   | Password | *(your SSH password; used once, never saved)* |
   | Key file | *(leave empty)* |
3. Click **Set up key login**. SessionDeck generates `%USERPROFILE%\.ssh\sessiondeck_<name>_ed25519` and adds it to `~/.ssh/authorized_keys` on the server. ✔ means it worked.
4. Click **Use this server**. Your sessions appear in the list.

> **Already use SSH keys?** Skip the password. Either point **Key file** at your private key, or leave it empty to use your normal `~/.ssh` keys and ssh-agent. Then click **Test connection**.

> **The server only allows key login (no passwords)?** Add your public key to the server another way, then select it under **Key file**.

---

## Daily use

1. **Ctrl+N → New session.** Name it (for example `agent-1`), pick a folder and choose `claude` under *Run*. It opens in a new tab and starts working.
2. Need to do something else while it runs? **Ctrl+N** again. Each task gets its own session and tab.
3. Closed the tab? The session keeps running. **Double-click** it in the list to reopen it.
4. Want to see progress without switching? Click a session and watch the **Live preview**.
5. An agent is waiting for a "yes"? Type it in **Send to session** and press Enter.
6. Done with a task? Select it and press **Del** to kill it.

### Keyboard shortcuts
| Key | Action |
|---|---|
| `Ctrl+N` | New session |
| `Enter` / double-click | Attach (opens a terminal tab) |
| `F2` | Rename session |
| `Del` | Kill session |
| `Ctrl+T` | Plain shell (no tmux) |
| `F5` | Refresh now |

### tmux basics (inside a session)
| Keys | Action |
|---|---|
| `Ctrl+B` then `D` | **Detach.** Leave the session running and close the view |
| `Ctrl+B` then `[` | Scroll mode (arrows/PgUp; `q` to exit) |
| `Ctrl+B` then `C` | New window inside the session |
| `Ctrl+B` then `N` / `P` | Next / previous window |

From **any other SSH client** (Termius, PuTTY, a phone app), you can join the same sessions:
```bash
tmux ls              # list sessions
tmux a -t agent-1    # attach to one
```

### Command line
```
sessiondeck                              open the GUI
sessiondeck servers                      list saved servers (* = active)
sessiondeck ls                           list sessions on the active server
sessiondeck new NAME [DIR] [CMD...]      create a session and open it
sessiondeck a NAME                       attach to a session
sessiondeck kill NAME                    kill a session
sessiondeck sh                           plain shell
sessiondeck -s SERVER ls                 use a specific saved server
```
Example: `sessiondeck new agent-2 ~/myproject claude --continue`

---

## Configuration

Settings live in **`%APPDATA%\SessionDeck\config.json`** and you can edit the file by hand:

```json
{
  "active": "buildbox",
  "profiles": [
    { "name": "buildbox", "host": "myserver.example.com", "port": 22,
      "user": "alice", "key": "C:\\Users\\alice\\.ssh\\sessiondeck_buildbox_ed25519" }
  ],
  "refresh_seconds": 5,
  "preview_lines": 200,
  "quick_commands": ["", "claude", "claude --continue", "claude --resume", "htop", "bash"]
}
```
| Key | Meaning |
|---|---|
| `refresh_seconds` | How often the session list and preview update |
| `preview_lines` | How many lines of scrollback the preview shows |
| `quick_commands` | Choices in the *Run* dropdown of the New session dialog |

---

## Security

- **Passwords are never written to disk.** During key setup the password reaches `ssh` through an environment variable read by a temporary helper script. The script contains no secrets and is deleted right away.
- Each server gets its **own ed25519 key**, so you can revoke one without affecting the others.
- **To revoke access:** on the server, delete the line ending in `sessiondeck-<name>` from `~/.ssh/authorized_keys`. Locally, delete the matching key files in `%USERPROFILE%\.ssh\`.
- New host keys are accepted on first connect (`StrictHostKeyChecking=accept-new`). If a known host's key changes later, the connection is refused.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| *"Login failed"* in the status bar | Open **Servers...**, enter the password and click **Set up key login** again |
| *"Wrong username or password"* | Check the username and password. Some servers disable password login, in which case add the key manually |
| *"tmux is not installed on the server"* | `sudo apt install tmux` (or your distro's equivalent) |
| *"OpenSSH client not found"* | Install **OpenSSH Client** from Windows Optional features |
| Sessions open in old console windows | Install Windows Terminal |
| SmartScreen blocks the exe | **More info → Run anyway**, or run from source |
| Keys behave oddly in Claude Code inside tmux | Add `set -g extended-keys on` to `~/.tmux.conf` on the server |
| Mouse scrolling doesn't work in a session | Add `set -g mouse on` to `~/.tmux.conf` on the server |

---

## Uninstall

1. Delete the **SessionDeck** shortcuts from the Desktop and Start Menu.
2. Delete the program folder and `%APPDATA%\SessionDeck\`.
3. Remove the folder from your user `PATH` (*Settings → System → About → Advanced system settings → Environment Variables*).
4. Optionally, revoke the keys as described under [Security](#security).

---

## Project layout

```
sessiondeck.pyw   the app (GUI + CLI), a single file using only the standard library
sessiondeck.cmd   `sessiondeck` command launcher (uses the exe if built, otherwise Python)
install.cmd/.ps1  installer: requirement checks, shortcuts, PATH
build_exe.cmd     builds dist\SessionDeck.exe with PyInstaller
```

## License

[MIT](LICENSE). Use it, fork it, improve it.
