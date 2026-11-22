"""
SessionDeck - run and juggle many persistent terminal sessions on remote Linux
servers from Windows. Sessions live in tmux on the server, so they keep running
while you work elsewhere, close the tab, or lose your connection.

GUI:  double-click sessiondeck.pyw (or SessionDeck.exe)
CLI:  sessiondeck [-s SERVER] ls | new NAME [DIR] [CMD...] | a NAME | kill NAME | sh | servers
"""
import ctypes
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

APP_NAME = "SessionDeck"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
SSH_DIR = os.path.join(os.path.expanduser("~"), ".ssh")
DEFAULT_CONFIG = {
    "active": "",
    "profiles": [],   # [{"name","host","port","user","key"}]  - passwords are never stored
    "refresh_seconds": 5,
    "preview_lines": 200,
    "quick_commands": ["", "claude", "claude --continue", "claude --resume", "htop", "bash"],
}
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---------------------------------------------------------------------- config
def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Could not read {CONFIG_PATH}: {e}", file=sys.stderr)
    return cfg


def save_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(CFG, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


CFG = load_config()


def get_profile(name=None):
    name = name or CFG.get("active")
    for p in CFG["profiles"]:
        if p["name"] == name:
            return p
    return CFG["profiles"][0] if CFG["profiles"] and not name else None


def slug(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-") or "server"


def default_key_path(profile_name):
    return os.path.join(SSH_DIR, f"sessiondeck_{slug(profile_name)}_ed25519")


# ----------------------------------------------------------------- ssh helpers
def ssh_exe():
    return shutil.which("ssh") or shutil.which("ssh.exe")


def ssh_base(p, tty=False):
    args = ["ssh", "-p", str(p.get("port") or 22), "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=4", "-o", "StrictHostKeyChecking=accept-new"]
    key = os.path.expandvars(os.path.expanduser(p.get("key") or ""))
    if key and os.path.exists(key):
        args += ["-i", key, "-o", "IdentitiesOnly=yes"]
    if tty:
        args.append("-t")
    args.append(f"{p['user']}@{p['host']}" if p.get("user") else p["host"])
    return args


def run_remote(p, cmd, timeout=20):
    """Run a command on the server non-interactively. Returns (rc, stdout, stderr)."""
    if not ssh_exe():
        return 127, "", "OpenSSH client (ssh.exe) not found - see README"
    args = ssh_base(p) + ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", cmd]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=NO_WINDOW,
                           stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Timed out talking to server"


def friendly_error(err):
    e = (err or "").strip()
    if "Permission denied" in e:
        return "Login failed - open Servers... and use 'Set up key login' with your password"
    if "Could not resolve" in e:
        return "Cannot resolve server address - check the host name"
    if "Connection refused" in e or "timed out" in e.lower():
        return "Cannot reach server - check host/port and your connection"
    return e.splitlines()[-1] if e else "ssh failed"


def setup_key_login(p, password):
    """Create a key for this profile (if needed) and install it on the server using the
    password once. The password is passed via an environment variable to a throwaway
    SSH_ASKPASS helper and is never written to disk."""
    if not ssh_exe():
        return False, "OpenSSH client (ssh.exe) not found - see README"
    key = os.path.expandvars(os.path.expanduser(p.get("key") or "")) or default_key_path(p["name"])
    os.makedirs(SSH_DIR, exist_ok=True)
    if not os.path.exists(key):
        r = subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", key,
                            "-C", f"sessiondeck-{slug(p['name'])}"],
                           capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode:
            return False, f"ssh-keygen failed: {r.stderr.strip()}"
    p["key"] = key
    with open(key + ".pub", "r", encoding="utf-8") as f:
        pub = f.read().strip()

    fd, helper = tempfile.mkstemp(suffix=".cmd", prefix="sd_askpass_")
    with os.fdopen(fd, "w") as f:
        f.write('@powershell -NoProfile -NonInteractive -Command "[Console]::Out.Write($env:SD_PW)"\r\n')
    env = dict(os.environ, SSH_ASKPASS=helper, SSH_ASKPASS_REQUIRE="force",
               DISPLAY=os.environ.get("DISPLAY", "localhost:0"), SD_PW=password)
    remote = ("umask 077; mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && "
              f"(grep -qxF {shlex.quote(pub)} ~/.ssh/authorized_keys || "
              f"echo {shlex.quote(pub)} >> ~/.ssh/authorized_keys) && echo SD_KEY_OK")
    args = ["ssh", "-p", str(p.get("port") or 22), "-o", "StrictHostKeyChecking=accept-new",
            "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1",
            "-o", "PreferredAuthentications=password,keyboard-interactive",
            "-o", "ConnectTimeout=15", f"{p['user']}@{p['host']}", remote]
    try:
        r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=45,
                           stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        out, err = r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        out, err = "", "timed out"
    finally:
        env["SD_PW"] = ""
        try:
            os.remove(helper)
        except OSError:
            pass
    if "SD_KEY_OK" not in out:
        if "Permission denied" in err:
            return False, "Wrong username or password."
        return False, friendly_error(err) or "Key setup failed"
    ok, msg = test_connection(p)
    return ok, ("Key login set up. " + msg) if ok else msg


def test_connection(p):
    rc, out, err = run_remote(p, "echo SD_OK; command -v tmux >/dev/null && tmux -V || echo SD_NOTMUX")
    if "SD_OK" not in out:
        return False, friendly_error(err)
    if "SD_NOTMUX" in out:
        return True, "Connected, but tmux is NOT installed on the server. Install it, e.g. 'sudo apt install tmux'."
    return True, f"Connected OK ({out.split('SD_OK', 1)[1].strip()})."


# ----------------------------------------------------------------- tmux layer
def valid_name(name):
    return bool(re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", name or ""))


def q(s):
    return shlex.quote(s)


def tgt(name, pane=False):
    return q("=" + name + (":" if pane else ""))


def remote_dir_arg(d):
    d = (d or "").strip()
    if not d:
        return None
    if d == "~":
        return '"$HOME"'
    if d.startswith("~/"):
        return '"$HOME"/' + q(d[2:])
    return q(d)


SEP = "<|>"  # tmux escapes control chars, so use a printable separator
LIST_FMT = SEP.join(["#{session_name}", "#{session_windows}", "#{session_attached}",
                     "#{session_activity}", "#{session_group}", "#{pane_current_command}",
                     "#{pane_current_path}"])


def list_sessions(p):
    rc, out, err = run_remote(p, "command -v tmux >/dev/null || echo __NOTMUX__; "
                                 f"tmux list-sessions -F {q(LIST_FMT)} 2>/dev/null; echo __OK__")
    if "__OK__" not in out:
        raise RuntimeError(friendly_error(err or out))
    if "__NOTMUX__" in out:
        raise RuntimeError("tmux is not installed on the server (e.g. 'sudo apt install tmux')")
    sessions = []
    for line in out.splitlines():
        parts = line.split(SEP)
        if len(parts) < 7:
            continue
        name, wins, att, act, group, cmd, path = parts[:7]
        sessions.append(dict(name=name, windows=wins, attached=int(att or 0),
                             activity=int(act or 0), group=group, cmd=cmd, path=path))
    return sessions


def create_session(p, name, directory="", command=""):
    cmd = f"tmux new-session -d -s {q(name)}"
    d = remote_dir_arg(directory)
    if d:
        cmd += f" -c {d}"
    if command.strip():
        # send-keys (not a session command) so the shell survives when the program exits
        cmd += f" && tmux send-keys -t {tgt(name, True)} {q(command.strip())} Enter"
    return run_remote(p, cmd)


def kill_session(p, name):
    return run_remote(p, f"tmux kill-session -t {tgt(name)}")


def rename_session(p, old, new):
    return run_remote(p, f"tmux rename-session -t {tgt(old)} {q(new)}")


def capture(p, name, lines):
    return run_remote(p, f"tmux capture-pane -p -J -t {tgt(name, True)} -S -{int(lines)}", timeout=15)


def send_text(p, name, text, enter=True):
    cmd = f"tmux send-keys -t {tgt(name, True)} -l {q(text)}"
    if enter:
        cmd += f" && tmux send-keys -t {tgt(name, True)} Enter"
    return run_remote(p, cmd)


def send_key(p, name, key):
    return run_remote(p, f"tmux send-keys -t {tgt(name, True)} {key}")


def open_terminal(p, title, remote_cmd=None, new_window=False):
    """Open an interactive ssh tab in Windows Terminal (falls back to a console window)."""
    ssh_args = ssh_base(p, tty=True)
    if remote_cmd:
        ssh_args.append(remote_cmd)  # must not contain ';' (Windows Terminal separator)
    wt = shutil.which("wt") or shutil.which("wt.exe")
    if wt:
        win = "new" if new_window else f"sd-{slug(p['name'])}"
        subprocess.Popen([wt, "-w", win, "new-tab", "--title", title,
                          "--suppressApplicationTitle"] + ssh_args, creationflags=NO_WINDOW)
    else:
        subprocess.Popen(["cmd", "/c", "start", title] + ssh_args)


def attach(p, name, new_window=False):
    open_terminal(p, name, f"tmux new-session -A -s {q(name)}", new_window)


def attach_independent(p, name):
    """Grouped session: same windows, but this client can look at a different window."""
    view = f"{name}-v{int(time.time()) % 100000}"
    open_terminal(p, f"{name} (view)",
                  f"tmux new-session -d -t {tgt(name)} -s {q(view)} && "
                  f"tmux set-option -t {tgt(view)} destroy-unattached on && "
                  f"tmux attach-session -t {tgt(view)}")


def ago(ts):
    if not ts:
        return ""
    d = max(0, int(time.time()) - ts)
    if d < 60:
        return f"{d}s ago"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h {d % 3600 // 60}m ago"
    return f"{d // 86400}d ago"


# ------------------------------------------------------------------------ GUI
BG, FG, ACC, PANEL, MUTED = "#1e1f22", "#dcdcdc", "#4f8cff", "#2b2d31", "#9aa0a6"


def run_bg(root, fn, done=None):
    def worker():
        try:
            res, err = fn(), None
        except Exception as e:
            res, err = None, e
        if done:
            root.after(0, lambda: done(res, err))
    threading.Thread(target=worker, daemon=True).start()


class ServersDialog(tk.Toplevel):
    FIELDS = [("name", "Display name"), ("host", "Server address"), ("port", "Port"),
              ("user", "Username"), ("password", "Password"), ("key", "Key file")]

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Servers")
        self.configure(bg=BG)
        self.transient(app.root)
        self.resizable(False, False)
        self.editing = None  # index into CFG["profiles"] or None for new

        left = ttk.Frame(self, style="P.TFrame", padding=10)
        left.grid(row=0, column=0, sticky="ns")
        self.lb = tk.Listbox(left, width=24, height=12, bg=PANEL, fg=FG, selectbackground=ACC,
                             relief="flat", highlightthickness=0, exportselection=False)
        self.lb.pack(fill="both", expand=True)
        self.lb.bind("<<ListboxSelect>>", self.on_pick)
        lb_btns = ttk.Frame(left, style="P.TFrame")
        lb_btns.pack(fill="x", pady=(6, 0))
        ttk.Button(lb_btns, text="+ Add", command=self.new).pack(side="left", expand=True, fill="x")
        ttk.Button(lb_btns, text="Delete", command=self.delete).pack(side="left", expand=True, fill="x", padx=(4, 0))

        form = ttk.Frame(self, style="P.TFrame", padding=10)
        form.grid(row=0, column=1, sticky="nsew")
        self.e = {}
        for i, (key, label) in enumerate(self.FIELDS):
            ttk.Label(form, text=label + ":", style="P.TLabel").grid(row=i, column=0, sticky="w", pady=4)
            ent = ttk.Entry(form, width=42, show="•" if key == "password" else "")
            ent.grid(row=i, column=1, sticky="we", pady=4)
            self.e[key] = ent
        ttk.Button(form, text="Browse...", command=self.browse_key).grid(row=5, column=2, padx=(4, 0))
        ttk.Label(form, style="M.TLabel", wraplength=380, justify="left",
                  text="The password is never saved. It is used once by 'Set up key login' to "
                       "install an SSH key on the server; after that you log in with the key. "
                       "Leave 'Key file' empty to have one generated (or to use your normal "
                       "~/.ssh keys / ssh-agent).").grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 4))

        btns = ttk.Frame(form, style="P.TFrame")
        btns.grid(row=7, column=0, columnspan=3, sticky="we", pady=(6, 0))
        self.buttons = []
        for text, fn in [("Save", self.save), ("Set up key login", self.setup_key),
                         ("Test connection", self.test), ("Use this server", self.use), ("Close", self.destroy)]:
            b = ttk.Button(btns, text=text, command=fn)
            b.pack(side="left", padx=(0, 4))
            self.buttons.append(b)
        self.status = ttk.Label(form, text="", style="P.TLabel", wraplength=420, justify="left")
        self.status.grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.reload()
        active = next((i for i, p in enumerate(CFG["profiles"]) if p["name"] == CFG.get("active")), None)
        if active is not None:
            self.lb.selection_set(active)
            self.load(active)
        else:
            self.new()
        self.grab_set()
        self.e["host" if self.editing is None else "password"].focus_set()

    def reload(self):
        self.lb.delete(0, "end")
        for p in CFG["profiles"]:
            star = "  (active)" if p["name"] == CFG.get("active") else ""
            self.lb.insert("end", p["name"] + star)

    def set_form(self, d):
        for k, _ in self.FIELDS:
            self.e[k].delete(0, "end")
            self.e[k].insert(0, str(d.get(k, "")))

    def load(self, i):
        self.editing = i
        self.set_form(CFG["profiles"][i])
        self.status.configure(text="")

    def on_pick(self, _=None):
        sel = self.lb.curselection()
        if sel:
            self.load(sel[0])

    def new(self):
        self.editing = None
        self.lb.selection_clear(0, "end")
        self.set_form({"port": 22})
        self.status.configure(text="Fill in the server details, then press 'Set up key login'.")
        self.e["name"].focus_set()

    def browse_key(self):
        f = filedialog.askopenfilename(parent=self, initialdir=SSH_DIR, title="Choose private key")
        if f:
            self.e["key"].delete(0, "end")
            self.e["key"].insert(0, f)

    def save(self, quiet=False):
        d = {k: self.e[k].get().strip() for k, _ in self.FIELDS if k != "password"}
        if not d["host"]:
            messagebox.showerror("Missing", "Server address is required.", parent=self)
            return None
        if not d["name"]:
            d["name"] = d["host"]
        try:
            d["port"] = int(d["port"] or 22)
            assert 1 <= d["port"] <= 65535
        except Exception:
            messagebox.showerror("Invalid port", "Port must be a number 1-65535.", parent=self)
            return None
        for i, p in enumerate(CFG["profiles"]):
            if p["name"] == d["name"] and i != self.editing:
                messagebox.showerror("Duplicate", f"A server named '{d['name']}' already exists.", parent=self)
                return None
        if self.editing is None:
            CFG["profiles"].append(d)
            self.editing = len(CFG["profiles"]) - 1
        else:
            old = CFG["profiles"][self.editing]["name"]
            CFG["profiles"][self.editing] = d
            if CFG.get("active") == old:
                CFG["active"] = d["name"]
        if not CFG.get("active"):
            CFG["active"] = d["name"]
        save_config()
        self.reload()
        self.lb.selection_set(self.editing)
        self.app.profiles_changed()
        if not quiet:
            self.status.configure(text="Saved.")
        return CFG["profiles"][self.editing]

    def busy(self, on, msg=""):
        for b in self.buttons:
            b.configure(state="disabled" if on else "normal")
        self.status.configure(text=msg)

    def setup_key(self):
        pw = self.e["password"].get()
        p = self.save(quiet=True)
        if not p:
            return
        if not p.get("user"):
            messagebox.showerror("Missing", "Username is required for key setup.", parent=self)
            return
        if not pw:
            messagebox.showinfo("Password needed", "Type the server password first. "
                                "It is used once and not saved.", parent=self)
            self.e["password"].focus_set()
            return
        self.busy(True, f"Connecting to {p['host']} and installing key...")
        idx = self.editing

        def done(res, err):
            if not self.winfo_exists():
                return
            self.e["password"].delete(0, "end")
            ok, msg = (False, str(err)) if err else res
            if ok:
                save_config()
                self.load(idx)
                self.app.profiles_changed()
            self.busy(False, ("✔ " if ok else "✖ ") + msg)
        run_bg(self, lambda: setup_key_login(p, pw), done)

    def test(self):
        p = self.save(quiet=True)
        if not p:
            return
        self.busy(True, "Testing...")
        run_bg(self, lambda: test_connection(p),
               lambda r, e: self.winfo_exists() and self.busy(
                   False, ("✔ " if (r and r[0]) else "✖ ") + (str(e) if e else r[1])))

    def use(self):
        p = self.save(quiet=True)
        if p:
            self.app.switch_profile(p["name"])
            self.destroy()

    def delete(self):
        if self.editing is None:
            return
        name = CFG["profiles"][self.editing]["name"]
        if not messagebox.askyesno("Delete server", f"Remove '{name}' from the list?\n"
                                   "(Nothing on the server is changed.)", parent=self):
            return
        del CFG["profiles"][self.editing]
        if CFG.get("active") == name:
            CFG["active"] = CFG["profiles"][0]["name"] if CFG["profiles"] else ""
        save_config()
        self.reload()
        self.app.profiles_changed()
        self.new()


class NewSessionDialog(simpledialog.Dialog):
    default_dir = "~"

    def body(self, m):
        self.title("New session")
        ttk.Label(m, text="Name:").grid(row=0, column=0, sticky="w", pady=3)
        self.e_name = ttk.Entry(m, width=36)
        self.e_name.grid(row=0, column=1, pady=3)
        self.e_name.insert(0, time.strftime("task-%H%M%S"))
        ttk.Label(m, text="Start dir:").grid(row=1, column=0, sticky="w", pady=3)
        self.e_dir = ttk.Entry(m, width=36)
        self.e_dir.grid(row=1, column=1, pady=3)
        self.e_dir.insert(0, self.default_dir)
        ttk.Label(m, text="Run:").grid(row=2, column=0, sticky="w", pady=3)
        self.e_cmd = ttk.Combobox(m, width=34, values=CFG.get("quick_commands", []))
        self.e_cmd.grid(row=2, column=1, pady=3)
        self.v_open = tk.BooleanVar(value=True)
        ttk.Checkbutton(m, text="Open it in a terminal tab now", variable=self.v_open).grid(
            row=3, column=1, sticky="w", pady=3)
        return self.e_name

    def validate(self):
        if not valid_name(self.e_name.get().strip()):
            messagebox.showerror("Invalid name", "Use letters, digits, - and _ only (max 40).", parent=self)
            return False
        return True

    def apply(self):
        self.result = (self.e_name.get().strip(), self.e_dir.get().strip(),
                       self.e_cmd.get().strip(), self.v_open.get())


class App:
    def __init__(self, root):
        self.root = root
        self.sessions = []
        self.busy = False
        self.selected = None
        self.gen = 0  # bumps when switching server, so stale results are ignored
        root.geometry("1150x720")
        root.minsize(800, 450)
        root.configure(bg=BG)
        self._style()

        bar = ttk.Frame(root, style="P.TFrame", padding=6)
        bar.pack(fill="x")
        ttk.Label(bar, text="Server:", style="P.TLabel").pack(side="left", padx=(2, 4))
        self.cb_server = ttk.Combobox(bar, state="readonly", width=22)
        self.cb_server.pack(side="left")
        self.cb_server.bind("<<ComboboxSelected>>", lambda e: self.switch_profile(self.cb_server.get()))
        ttk.Button(bar, text="Servers...", command=self.open_servers).pack(side="left", padx=(4, 14))
        for text, fn in [("+ New session", self.new_session), ("Attach", self.attach_sel),
                         ("Attach (new window)", lambda: self.attach_sel(True)),
                         ("Independent view", self.attach_view), ("Rename", self.rename_sel),
                         ("Kill", self.kill_sel), ("Plain shell", self.plain_shell),
                         ("Refresh", self.refresh)]:
            ttk.Button(bar, text=text, command=fn).pack(side="left", padx=2)

        self.status = ttk.Label(root, text="", style="M.TLabel", padding=(10, 0))
        self.status.pack(fill="x")

        pane = ttk.PanedWindow(root, orient="vertical")
        pane.pack(fill="both", expand=True, padx=6, pady=6)
        cols = ("name", "running", "windows", "attached", "activity", "path")
        self.tree = ttk.Treeview(pane, columns=cols, show="headings", selectmode="browse", height=8)
        widths = dict(name=170, running=130, windows=70, attached=80, activity=110, path=480)
        for c in cols:
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=widths[c], anchor="w")
        self.tree.tag_configure("att", foreground="#7ee787")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.attach_sel())
        self.tree.bind("<Return>", lambda e: self.attach_sel())
        self.tree.bind("<Delete>", lambda e: self.kill_sel())
        self.tree.bind("<F2>", lambda e: self.rename_sel())
        pane.add(self.tree, weight=1)

        bottom = ttk.Frame(pane, style="P.TFrame")
        self.prev_label = ttk.Label(bottom, text="Live preview (select a session)", style="P.TLabel")
        self.prev_label.pack(anchor="w", padx=4, pady=(4, 0))
        send = ttk.Frame(bottom, style="P.TFrame")
        send.pack(side="bottom", fill="x", pady=4)
        ttk.Label(send, text="Send to session:", style="P.TLabel").pack(side="left", padx=4)
        self.e_send = ttk.Entry(send)
        self.e_send.pack(side="left", fill="x", expand=True, padx=4)
        self.e_send.bind("<Return>", lambda e: self.send())
        ttk.Button(send, text="Send + Enter", command=self.send).pack(side="left", padx=2)
        ttk.Button(send, text="Ctrl-C", command=lambda: self.key("C-c")).pack(side="left", padx=2)
        ttk.Button(send, text="Esc", command=lambda: self.key("Escape")).pack(side="left", padx=2)
        self.preview = tk.Text(bottom, bg="#0d0e10", fg=FG, insertbackground=FG, wrap="none",
                               font=("Consolas", 10), relief="flat", state="disabled")
        ys = ttk.Scrollbar(bottom, command=self.preview.yview)
        self.preview.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        self.preview.pack(fill="both", expand=True)
        pane.add(bottom, weight=2)

        root.bind("<Control-n>", lambda e: self.new_session())
        root.bind("<Control-t>", lambda e: self.plain_shell())
        root.bind("<F5>", lambda e: self.refresh())

        self.profiles_changed()
        if not ssh_exe():
            messagebox.showwarning(APP_NAME, "The Windows OpenSSH client (ssh.exe) was not found.\n\n"
                                   "Install it from Settings > System > Optional features > "
                                   "'OpenSSH Client', then restart SessionDeck.")
        if not CFG["profiles"]:
            root.after(200, self.open_servers)
        self.refresh()
        self.root.after(int(CFG.get("refresh_seconds", 5)) * 1000, self.tick)

    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL)
        s.configure("P.TFrame", background=BG)
        s.configure("P.TLabel", background=BG, foreground=FG)
        s.configure("M.TLabel", background=BG, foreground=MUTED)
        s.configure("TButton", background=PANEL, foreground=FG, borderwidth=0, padding=(9, 5))
        s.map("TButton", background=[("active", ACC), ("disabled", BG)])
        s.configure("Treeview", background=PANEL, foreground=FG, fieldbackground=PANEL, rowheight=26)
        s.configure("Treeview.Heading", background=BG, foreground=MUTED)
        s.map("Treeview", background=[("selected", ACC)])
        s.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG)
        s.configure("TCombobox", fieldbackground=PANEL, foreground=FG, arrowcolor=FG)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)])

    @property
    def prof(self):
        return get_profile()

    # ---- server profiles
    def profiles_changed(self):
        names = [p["name"] for p in CFG["profiles"]]
        self.cb_server.configure(values=names)
        p = self.prof
        self.cb_server.set(p["name"] if p else "")
        self.root.title(f"{APP_NAME} - {p['user']}@{p['host']}:{p.get('port', 22)}" if p else APP_NAME)

    def switch_profile(self, name):
        if name == CFG.get("active"):
            return
        CFG["active"] = name
        save_config()
        self.gen += 1
        self.busy = False
        self.selected = None
        self.sessions = []
        self.tree.delete(*self.tree.get_children())
        self.show_preview("")
        self.prev_label.configure(text="Live preview (select a session)")
        self.profiles_changed()
        self.refresh()

    def open_servers(self):
        ServersDialog(self)

    # ---- refresh loop
    def set_status(self, text):
        self.status.configure(text=text)

    def tick(self):
        self.refresh(quiet=True)
        self.root.after(int(CFG.get("refresh_seconds", 5)) * 1000, self.tick)

    def refresh(self, quiet=False):
        p = self.prof
        if not p:
            self.set_status("No server configured - click 'Servers...' to add one.")
            return
        if self.busy:
            return
        self.busy = True
        if not quiet:
            self.set_status(f"Refreshing {p['name']}...")
        sel, gen = self.selected, self.gen

        def work():
            sessions = list_sessions(p)
            prev = capture(p, sel, CFG.get("preview_lines", 200)) if sel else None
            return sessions, prev

        run_bg(self.root, work, lambda r, e: self.on_refreshed(r, e, gen))

    def on_refreshed(self, res, err, gen):
        if gen != self.gen:
            return
        self.busy = False
        if err:
            self.set_status(f"⚠ {err}")
            return
        sessions, prev = res
        self.sessions = sessions
        names = [s["name"] for s in sessions]
        self.tree.delete(*self.tree.get_children())
        for s in sessions:
            self.tree.insert("", "end", iid=s["name"], tags=("att",) if s["attached"] else (),
                             values=(s["name"], s["cmd"], s["windows"],
                                     f"yes ({s['attached']})" if s["attached"] else "no",
                                     ago(s["activity"]), s["path"]))
        if self.selected in names:
            self.tree.selection_set(self.selected)
            self.tree.see(self.selected)
        else:
            self.selected = None
        self.set_status(f"{self.prof['name']}: {len(sessions)} session(s) - updated "
                        f"{time.strftime('%H:%M:%S')}   |   Ctrl+N new  -  Enter attach  -  "
                        f"F2 rename  -  Del kill  -  Ctrl+T plain shell")
        if prev and self.selected:
            self.show_preview(prev[1] if prev[0] == 0 else prev[2])

    def show_preview(self, text):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text.rstrip("\n"))
        self.preview.configure(state="disabled")
        self.preview.see("end")

    def on_select(self, _=None):
        sel = self.tree.selection()
        new = sel[0] if sel else None
        if new and new != self.selected:
            self.selected = new
            self.prev_label.configure(text=f"Live preview: {new}")
            p = self.prof
            run_bg(self.root, lambda: capture(p, new, CFG.get("preview_lines", 200)),
                   lambda r, e: (not e and self.selected == new) and
                   self.show_preview(r[1] if r[0] == 0 else r[2]))

    def need_sel(self):
        if not self.selected:
            messagebox.showinfo("No session", "Select a session first.")
            return None
        return self.selected

    # ---- actions
    def new_session(self):
        p = self.prof
        if not p:
            return self.open_servers()
        NewSessionDialog.default_dir = next((s["path"] for s in self.sessions
                                             if s["name"] == self.selected), "~")
        d = NewSessionDialog(self.root)
        if not d.result:
            return
        name, directory, command, open_now = d.result
        if name in [s["name"] for s in self.sessions]:
            messagebox.showerror("Exists", f"Session '{name}' already exists.")
            return
        self.set_status(f"Creating {name}...")

        def done(r, e):
            if e or r[0] != 0:
                messagebox.showerror("Failed", str(e) if e else friendly_error(r[2] or r[1]))
                return
            self.selected = name
            if open_now:
                attach(p, name)
            self.refresh()
        run_bg(self.root, lambda: create_session(p, name, directory, command), done)

    def attach_sel(self, new_window=False):
        n = self.need_sel()
        if n:
            attach(self.prof, n, new_window)
            self.set_status(f"Opened {n}")

    def attach_view(self):
        n = self.need_sel()
        if n:
            attach_independent(self.prof, n)

    def plain_shell(self):
        if self.prof:
            open_terminal(self.prof, "shell")

    def kill_sel(self):
        n = self.need_sel()
        if not n or not messagebox.askyesno("Kill session",
                                            f"Kill session '{n}'?\nAnything running in it will be stopped."):
            return
        p = self.prof
        self.selected = None
        run_bg(self.root, lambda: kill_session(p, n), lambda r, e: self.refresh())

    def rename_sel(self):
        n = self.need_sel()
        if not n:
            return
        new = simpledialog.askstring("Rename", f"New name for '{n}':", initialvalue=n, parent=self.root)
        if not new or new == n:
            return
        if not valid_name(new):
            messagebox.showerror("Invalid name", "Use letters, digits, - and _ only.")
            return
        p = self.prof

        def done(r, e):
            if e or r[0] != 0:
                messagebox.showerror("Failed", str(e) if e else (r[2] or r[1]))
            else:
                self.selected = new
            self.refresh()
        run_bg(self.root, lambda: rename_session(p, n, new), done)

    def send(self):
        n = self.need_sel()
        text = self.e_send.get()
        if not n or not text:
            return
        self.e_send.delete(0, "end")
        p = self.prof
        run_bg(self.root, lambda: send_text(p, n, text), lambda r, e: self.root.after(700, self.refresh))

    def key(self, k):
        n = self.need_sel()
        if n:
            p = self.prof
            run_bg(self.root, lambda: send_key(p, n, k), lambda r, e: self.root.after(500, self.refresh))


# ------------------------------------------------------------------------ CLI
def cli(argv):
    server = None
    if len(argv) >= 2 and argv[0] in ("-s", "--server"):
        server, argv = argv[1], argv[2:]
    if not argv:
        return print(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "servers":
        for p in CFG["profiles"]:
            mark = "*" if p["name"] == CFG.get("active") else " "
            print(f"{mark} {p['name']:<20} {p.get('user', '')}@{p['host']}:{p.get('port', 22)}")
        return
    p = get_profile(server)
    if not p:
        sys.exit("No server configured. Run the GUI and add one under 'Servers...'.")
    if cmd in ("ls", "list"):
        for s in list_sessions(p):
            print(f"{s['name']:<20} {s['cmd']:<14} {'ATTACHED' if s['attached'] else '':<9} "
                  f"{ago(s['activity']):<12} {s['path']}")
    elif cmd == "new" and rest:
        name, directory, command = rest[0], (rest[1] if len(rest) > 1 else ""), " ".join(rest[2:])
        if not valid_name(name):
            sys.exit("invalid name (letters, digits, - and _)")
        rc, out, err = create_session(p, name, directory, command)
        if rc:
            sys.exit(friendly_error(err or out))
        attach(p, name)
    elif cmd in ("a", "attach") and rest:
        attach(p, rest[0])
    elif cmd == "kill" and rest:
        rc, out, err = kill_session(p, rest[0])
        print(err.strip() if rc else "killed")
    elif cmd in ("sh", "shell"):
        open_terminal(p, "shell")
    else:
        print(__doc__)


def main():
    if len(sys.argv) > 1:
        if getattr(sys, "frozen", False) and os.name == "nt":
            # windowed .exe: attach to the calling console so CLI output is visible
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w")
                sys.stderr = sys.stdout
                print()
        cli(sys.argv[1:])
    else:
        if os.name == "nt":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        root = tk.Tk()
        App(root)
        root.mainloop()


if __name__ == "__main__":
    main()
