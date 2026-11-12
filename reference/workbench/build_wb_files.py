#!/usr/bin/env python3
"""Make the workbench Files mod: Herdr's Files with rendered markdown previews.

Reads a fresh `mod.clone` of Herdr's `files` and patches it in place. Every anchor must occur
exactly once; a Herdr update that moves the code stops this script instead of mis-patching.
"""
import argparse
from pathlib import Path

PATCHES = [
    ('import { v_flex, h_flex, Editor, EditorState } from "gpui-base";',
     'import { v_flex, h_flex, Editor, EditorState, TextView } from "gpui-base";'),
    ('// A lazy file browser for the focused pane\'s folder, with bounded read-only previews.',
     '// A lazy file browser for the focused pane\'s folder, with bounded read-only previews.\n'
     '// Workbench copy: .md files render as markdown (toggle to raw), and refresh when the file changes.'),
    ("const PER_FOLDER = 500, TOTAL = 5000;",
     "const PER_FOLDER = 500, TOTAL = 5000;\n"
     "const MARKDOWN = new Set([\"md\", \"markdown\"]);\n"
     "function joinPath(dir, rel) {\n"
     "  const parts = (rel.startsWith(\"/\") ? rel : `${dir}/${rel}`).split(\"/\"), out = [];\n"
     "  for (const p of parts) { if (p === \"..\") out.pop(); else if (p && p !== \".\") out.push(p); }\n"
     "  return \"/\" + out.join(\"/\");\n"
     "}"),
    ("    cx.timer.every(10000, cx => this.refresh(cx));\n  }",
     "    cx.timer.every(10000, cx => this.refresh(cx));\n"
     "    // An open markdown file is re-read gently so a lead's result file updates in place.\n"
     "    cx.timer.every(3000, cx => this.pollMarkdown(cx));\n"
     "  }\n\n"
     "  pollMarkdown(cx) {\n"
     "    const path = this.file, root = this.root, on = this.on;\n"
     "    if (!path || this.markdown === null || this.markdown === undefined) return;\n"
     "    cx.spawn(async cx => {\n"
     "      try {\n"
     "        const text = await readTextFile(`${root}/${path}`, { on });\n"
     "        if (this.file === path && text !== null && text !== this.markdownSource) { this.setMarkdown(text); cx.notify(); }\n"
     "      } catch { /* the next show() reports unreadable files */ }\n"
     "    });\n"
     "  }\n\n"
     "  setMarkdown(text) {\n"
     "    this.markdownSource = text;\n"
     "    this.markdown = text.length > 400000 ? text.slice(0, 400000) + \"\\n\\n… (file truncated)\" : text;\n"
     "  }\n\n"
     "  openLink(url, cx) {\n"
     "    if (/^https?:\\/\\//.test(url)) { cx.open_url(url); return; }\n"
     "    const target = decodeURI(url.split(\"#\")[0]);\n"
     "    if (!target) return;\n"
     "    const dir = `${this.root}/${this.file}`.split(\"/\").slice(0, -1).join(\"/\");\n"
     "    const absolute = joinPath(dir, target);\n"
     "    if (!absolute.startsWith(`${this.root}/`)) return;\n"
     "    this.show(absolute.slice(this.root.length + 1), cx);\n"
     "  }"),
    ("    this.code?.release(); this.code = null; this.file = path; this.fileError = null;",
     "    this.code?.release(); this.code = null; this.file = path; this.fileError = null;\n"
     "    this.markdown = null; this.markdownSource = null;"),
    ("        const t = theme(), ext = path.includes(\".\") ? path.split(\".\").pop() : \"txt\";",
     "        const t = theme(), ext = path.includes(\".\") ? path.split(\".\").pop() : \"txt\";\n"
     "        if (MARKDOWN.has(ext.toLowerCase()) && !this.raw) { this.setMarkdown(text); return; }"),
    ("        .child(div().font_semibold().child(\"Files\"))",
     "        .child(div().font_semibold().child(\"Files\"))\n"
     "        .when(Boolean(this.file) && MARKDOWN.has((this.file.split(\".\").pop() ?? \"\").toLowerCase()), el => el.child(\n"
     "          div().id(\"files-md-toggle\").px(6).rounded(5).cursor_pointer().text_size(11).text_color(t.muted).hover(s => s.bg(t.hover))\n"
     "            .on_click((_e, cx) => { this.raw = !this.raw; this.show(this.file, cx); cx.notify(); })\n"
     "            .child(this.raw ? \"보기\" : \"원문\")))\n"
     "        .when(Boolean(this.file) && /\\.html?$/i.test(this.file), el => el.child(\n"
     "          div().id(\"files-html-open\").px(6).rounded(5).cursor_pointer().text_size(11).text_color(t.muted).hover(s => s.bg(t.hover))\n"
     "            .on_click(() => { exec(\"open\", [`${this.root}/${this.file}`], { on: this.on }); })\n"
     "            .child(\"브라우저\")))"),
    ("      .when(Boolean(this.file), el => el.child(this.code ? Editor.new(this.code).flex_1().min_h(0) : div().p(12).text_color(t.dim).child(this.fileError || \"Loading file…\")));",
     "      .when(Boolean(this.file), el => el.child(this.markdown != null\n"
     "        ? v_flex().id(\"files-md\").flex_1().min_h(0).overflow_y_scrollbar().px(16).py(12)\n"
     "            .child(TextView.markdown(`md-${this.file}`, this.markdown).selectable(true).on_link_click((url, cx) => this.openLink(url, cx)))\n"
     "        : this.code ? Editor.new(this.code).flex_1().min_h(0) : div().p(12).text_color(t.dim).child(this.fileError || \"Loading file…\")));"),
    # 11/10 U5: open a file another mod asks for (wb-menu's 'Files에서 열기'), even outside this folder.
    ('import { spaces, panes, focused, exec, readTextFile, watchFolder, theme, settings, window } from "herdr";',
     'import { spaces, panes, focused, exec, readTextFile, watchFolder, theme, settings, window, shared } from "herdr";'),
    ("    this.saved = new Map();\n",
     "    this.saved = new Map();\n"
     "    this.requestAt = shared(\"workbench.files.open\")?.at ?? null;   // only requests made after this copy started\n"),
    ("  show(path, cx) {\n",
     "  show(path, cx, absolute = false) {\n    this.absolute = Boolean(absolute && path);\n"),
    ("        const text = await readTextFile(`${root}/${path}`, { on });\n        if (this.file !== path || !this.current(context)) return;",
     "        const absolute = this.absolute;\n"
     "        const text = await readTextFile(absolute ? path : `${root}/${path}`, { on: absolute ? null : on });\n"
     "        if (this.file !== path || !this.current(context)) return;"),
    ("        const text = await readTextFile(`${root}/${path}`, { on });\n        if (this.file === path && text !== null && text !== this.markdownSource)",
     "        const text = await readTextFile(this.absolute ? path : `${root}/${path}`, { on: this.absolute ? null : on });\n"
     "        if (this.file === path && text !== null && text !== this.markdownSource)"),
    ("    const dir = `${this.root}/${this.file}`.split(\"/\").slice(0, -1).join(\"/\");\n"
     "    const absolute = joinPath(dir, target);\n"
     "    if (!absolute.startsWith(`${this.root}/`)) return;\n"
     "    this.show(absolute.slice(this.root.length + 1), cx);",
     "    const full = this.absolute ? this.file : `${this.root}/${this.file}`;\n"
     "    const absolute = joinPath(full.split(\"/\").slice(0, -1).join(\"/\"), target);\n"
     "    if (absolute.startsWith(`${this.root}/`)) this.show(absolute.slice(this.root.length + 1), cx);\n"
     "    else this.show(absolute, cx, true);"),
    ("      if (this.context) this.saved.set(this.context.key, { folders: this.folders, file: this.file });",
     "      if (this.context) this.saved.set(this.context.key, { folders: this.folders, file: this.file, absolute: this.absolute });"),
    ("      if (saved?.file) this.show(saved.file, cx);",
     "      if (saved?.file) this.show(saved.file, cx, saved.absolute);"),
    ("  render(cx) {\n    if (key() !== this.context?.key) this.refresh(cx);\n",
     "  render(cx) {\n    if (key() !== this.context?.key) this.refresh(cx);\n"
     "    const request = shared(\"workbench.files.open\");\n"
     "    if (request?.path && request.at !== this.requestAt) {\n"
     "      this.requestAt = request.at; this.raw = false;\n"
     "      const inside = Boolean(this.root) && request.path.startsWith(`${this.root}/`);\n"
     "      this.show(inside ? request.path.slice(this.root.length + 1) : request.path, cx, !inside);\n"
     "    }\n"),
    ("this.raw = !this.raw; this.show(this.file, cx);",
     "this.raw = !this.raw; this.show(this.file, cx, this.absolute);"),
    ("exec(\"open\", [`${this.root}/${this.file}`], { on: this.on });",
     "exec(\"open\", [this.absolute ? this.file : `${this.root}/${this.file}`], { on: this.absolute ? null : this.on });"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main_js', help='main.js of a fresh mod.clone of files')
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
