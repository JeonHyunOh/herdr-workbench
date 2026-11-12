// Workbench markdown viewer: renders one .md file given as props.file, and follows its changes.
// Open beside a terminal: herdr-app do pane.split '{"direction":"right","mod":"wb-md","props":{"file":"/abs/path.md"}}'
import { View, div } from "gpui-kit";
import { v_flex, h_flex, TextView } from "gpui-base";
import { readTextFile, theme, exec, props } from "herdr";

const LIMIT = 400000;
function joinPath(dir, rel) {
  const parts = (rel.startsWith("/") ? rel : `${dir}/${rel}`).split("/"), out = [];
  for (const p of parts) { if (p === "..") out.pop(); else if (p && p !== ".") out.push(p); }
  return "/" + out.join("/");
}

export default class MarkdownView extends View {
  init(initial, cx) {
    // A pane or tab mod gets its props through props(); the init argument is kept as a fallback.
    const given = props() ?? initial ?? {};
    this.file = typeof given.file === "string" && given.file.startsWith("/") ? given.file : null;
    this.text = null; this.source = null; this.error = this.file ? null : "props.file에 절대 경로가 필요하다";
    this.load(cx);
    cx.timer.every(3000, cx => this.load(cx));
  }

  load(cx) {
    const file = this.file;
    if (!file) return;
    cx.spawn(async cx => {
      try {
        const text = await readTextFile(file);
        if (file !== this.file) return;
        if (text === null) { this.error = "파일이 없다"; cx.notify(); return; }
        if (text === this.source) return;
        this.source = text; this.error = null;
        this.text = text.length > LIMIT ? text.slice(0, LIMIT) + "\n\n… (file truncated)" : text;
        cx.notify();
      } catch { this.error = "읽을 수 없다 (1 MiB 초과이거나 권한 없음)"; cx.notify(); }
    });
  }

  openLink(url, cx) {
    if (/^https?:\/\//.test(url)) { cx.open_url(url); return; }
    const target = decodeURI(url.split("#")[0]);
    if (!target) return;
    this.file = joinPath(this.file.split("/").slice(0, -1).join("/"), target);
    this.source = null; this.text = null;
    this.load(cx); cx.notify();
  }

  render(cx) {
    const t = theme(), name = this.file?.split("/").pop() ?? "";
    return v_flex().id("wb-md").size_full().min_h(0).rounded(10).overflow_hidden().bg(t.background).border_1().border_color(t.border).text_color(t.foreground).text_size(13)
      .child(h_flex().h(36).flex_none().px(12).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().font_semibold().child(name || "Markdown"))
        .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.dim).child(this.file ?? ""))
        .when(Boolean(this.file), el => el.child(div().id("wb-md-open").px(6).rounded(5).cursor_pointer().text_size(11).text_color(t.muted).hover(s => s.bg(t.hover))
          .on_click(() => { exec("open", ["-R", this.file]); }).child("Finder"))))
      .child(this.text !== null
        ? v_flex().id("wb-md-body").flex_1().min_h(0).overflow_y_scrollbar().px(16).py(12)
            .child(TextView.markdown(`md-${this.file}`, this.text).selectable(true).on_link_click((url, cx) => this.openLink(url, cx)))
        : div().p(12).text_color(t.dim).child(this.error ?? "Loading…"));
  }
}
