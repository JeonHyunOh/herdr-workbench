#!/usr/bin/env python3
"""Make the workbench terminal menu: Herdr's right-click menu plus 'Files에서 열기' items.

Right-clicking a terminal lists the file names that terminal printed recently (its screen and
history through `hc read`). Each name is resolved against that terminal's folder and the hub's
`_my` folder, so a bare `solution-plan.md` from a lead whose cwd is team-repo is still found.
Choosing one asks the wb-files panel (shared key `workbench.files.open`) to open it.

Reads a fresh `mod.clone` of Herdr's `menu` and patches it in place; every anchor must occur once.
"""
import argparse
import json
from pathlib import Path

HUB = '/home/you/Project/work/hub'

FIND_JS = r'''
// Workbench: file names the clicked terminal printed, resolved to real files (newest mention first).
// A Korean particle may follow the name directly ("solution-plan.md를"): only a word character or "/" ends it.
const HUB = __HUB__;
const EXT = "md|markdown|html?|json|jsonl|ya?ml|toml|txt|csv|tsv|log|py|js|mjs|ts|tsx|sh|diff|patch";
const MENTION = new RegExp(`(?:^|[\\s'"\`(\\[<:=])((?:~/|/|\\.{1,2}/)?[\\w가-힣.@+-]+(?:/[\\w가-힣.@+-]+)*\\.(?:${EXT}))(?![\\w/])`, "giu");
const SHELL = `for c in "$@"; do
  case "$c" in "~/"*) c="$HOME/\${c#\\~/}";; esac
  case "$c" in /*) [ -f "$c" ] && printf '%s\\t%s\\n' "$c" "$c"; continue;; esac
  [ -f "$WB_CWD/$c" ] && { printf '%s\\t%s\\n' "$c" "$WB_CWD/$c"; continue; }
  name=\${c##*/}
  find "$WB_CWD" "$WB_HUB/_my" -maxdepth 8 \\( -name node_modules -o -name .git -o -name .venv -o -name cdk.out -o -name worktrees -o -name mailbox \\) -prune -o -type f -name "$name" -path "*$c" -print 2>/dev/null | head -2 | while read -r f; do printf '%s\\t%s\\n' "$c" "$f"; done
done`;

async function mentionedFiles(terminal, cwd) {
  const screen = await hc(["read", "--lines", "400", terminal]).catch(() => null);
  if (!screen || screen.code !== 0) return [];
  const seen = [];
  for (const m of screen.stdout.matchAll(MENTION)) {
    const c = m[1].replace(/[.,;:]+$/, "");
    const at = seen.indexOf(c);
    if (at >= 0) seen.splice(at, 1);
    seen.push(c);
  }
  const recent = seen.reverse().slice(0, 12);
  if (!recent.length) return [];
  const r = await exec("sh", ["-c", `WB_CWD="$1"; WB_HUB="$2"; shift 2; ${SHELL}`, "wb-menu", cwd || HUB, HUB, ...recent], { timeout: 8000 }).catch(() => null);
  if (!r || r.code !== 0) return [];
  const out = [], paths = new Set();
  for (const line of r.stdout.split("\n").filter(Boolean)) {
    const [mention, path] = line.split("\t");
    if (!path || paths.has(path)) continue;
    paths.add(path);
    const dir = path.startsWith(`${HUB}/`) ? path.slice(HUB.length + 1).split("/").slice(0, -1).join("/") : path.split("/").slice(0, -1).join("/");
    out.push({ mention, path, label: `${path.split("/").pop()}  ·  ${dir.split("/").slice(-2).join("/")}` });
    if (out.length >= 8) break;
  }
  return out;
}
'''.replace('__HUB__', json.dumps(HUB))

PATCHES = [
    ('import { run, props, closeOverlay, openOverlay, theme, keys, terminals, spaces, panes, exec } from "herdr";',
     'import { run, props, closeOverlay, openOverlay, theme, keys, terminals, spaces, panes, exec, hc, setShared } from "herdr";'
     + FIND_JS),
    ('function items(p, git) {\n  p = p ?? {};',
     'function items(p, git, files = []) {\n  p = p ?? {};'),
    ('      return [\n        ...(inTab\n          ? [\n              ["Split right", "pane.split", { direction: "right", pane: tg.pane }],',
     '      return [\n        ...files.map((f) => [`Files에서 열기: ${f.label}`, "wb.open-file", { path: f.path }]),\n'
     '        ...(inTab\n          ? [\n              ["Split right", "pane.split", { direction: "right", pane: tg.pane }],'),
    ('function menuIcon(command) {\n',
     'function menuIcon(command) {\n  if (command === "wb.open-file") return "mods/wb-files/file.svg";\n'),
    ('    const p = props();\n    const space = p?.tab === "space" && spaces().find((s) => s.id === p.target?.id);',
     '    const p = props();\n    this.files = [];\n'
     '    const clicked = p?.tab === "pane" && p.target?.terminal;\n'
     '    if (clicked) {\n'
     '      const cwd = panes().find((pane) => pane.pane === p.target.pane)?.cwd ?? terminals().find((t) => t.address === clicked)?.cwd;\n'
     '      cx.spawn(async (cx) => { this.files = await mentionedFiles(clicked, cwd).catch(() => []); cx.notify(); });\n'
     '    }\n'
     '    const space = p?.tab === "space" && spaces().find((s) => s.id === p.target?.id);'),
    ('    const it = items(props(), this.git)[i];\n    if (!it) return;\n    closeOverlay(props()?.overlay);',
     '    const it = items(props(), this.git, this.files)[i];\n    if (!it) return;\n    closeOverlay(props()?.overlay);\n'
     '    if (it[1] === "wb.open-file") {\n'
     '      setShared("workbench.files.open", { path: it[2].path, at: Date.now() });\n'
     '      run("layout.show", { id: "panel" });\n'
     '      run("layout.select", { stack: "panel-body", child: "files" });\n'
     '      return;\n'
     '    }'),
    ('    const list = items(props(), this.git);',
     '    const list = items(props(), this.git, this.files);'),
    ('            .when(i > 0 && (it[1].endsWith(".close")',
     '            .when(i > 0 && it[1] !== "wb.open-file" && list[i - 1][1] === "wb.open-file", el => el.child(div().mx(7).my(4).h(1).bg(t.border)))\n'
     '            .when(i > 0 && (it[1].endsWith(".close")'),
    ('            .child(div().flex_1().child(it[0]))',
     '            .child(div().flex_1().min_w(0).truncate().child(it[0]))'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main_js', help='main.js of a fresh mod.clone of menu')
    path = Path(parser.parse_args().main_js)
    text = path.read_text()
    for old, new in PATCHES:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f'Anchor found {count} times, expected 1: {old[:70]!r}')
        text = text.replace(old, new)
    path.write_text(text)
    print(f'patched {len(PATCHES)} anchors in {path}')


if __name__ == '__main__':
    main()
