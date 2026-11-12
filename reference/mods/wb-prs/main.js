// Workbench PR panel: open YOUR_ORG PRs I wrote and PRs waiting for my review.
// Uses the person's own gh login through exec (no token is read or stored here).
// One GraphQL call (cost 1 point) every 3 minutes, plus the ↻ button. The last result is cached per copy.
import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, theme } from "herdr";

const EVERY_MS = 180000, ORG = "YOUR_ORG";
const QUERY = `query($mine: String!, $review: String!) {
  mine: search(query: $mine, type: ISSUE, first: 30) { issueCount nodes { ...pr } }
  review: search(query: $review, type: ISSUE, first: 30) { issueCount nodes { ...pr } }
}
fragment pr on PullRequest {
  number title url isDraft mergeable reviewDecision updatedAt
  repository { name }
  labels(first: 10) { nodes { name } }
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
}`;
const REVIEW = { APPROVED: "승인", CHANGES_REQUESTED: "변경 요청", REVIEW_REQUIRED: "대기" };

function rows(search) {
  return (search?.nodes ?? []).filter(n => n?.number).map(n => ({
    id: `${n.repository.name}#${n.number}`, title: n.title, url: n.url, draft: n.isDraft,
    conflict: n.mergeable === "CONFLICTING", review: n.reviewDecision ?? null,
    ci: n.commits?.nodes?.[0]?.commit?.statusCheckRollup?.state ?? null,
    bot: (n.labels?.nodes ?? []).some(l => l.name.startsWith("봇리뷰") && l.name !== "봇리뷰제외"),
  })).sort((a, b) => a.id.localeCompare(b.id));
}

export default class PullRequests extends View {
  init(_props, cx) {
    this.tab = "mine"; this.data = null; this.error = null; this.loading = false; this.fetchedAt = null;
    try {
      const cached = JSON.parse(localStorage.getItem("prs") ?? "null");
      if (cached?.mine) { this.data = cached; this.fetchedAt = cached.fetchedAt; }
    } catch { /* an unreadable cache is ignored */ }
    this.refresh(cx);
    cx.timer.every(EVERY_MS, cx => this.refresh(cx));
    cx.timer.every(60000, cx => cx.notify());   // the "n분 전" label only
  }

  refresh(cx) {
    if (this.loading) return;
    this.loading = true; cx.notify();
    cx.spawn(async cx => {
      try {
        const r = await exec("gh", ["api", "graphql",
          "-F", `mine=is:open is:pr author:@me org:${ORG}`,
          "-F", `review=is:open is:pr review-requested:@me org:${ORG}`,
          "-f", `query=${QUERY}`], { timeout: 20000 });
        if (r.code !== 0) throw new Error((r.stderr || "gh failed").split("\n")[0]);
        const d = JSON.parse(r.stdout).data;
        this.data = { mine: rows(d.mine), review: rows(d.review), fetchedAt: Date.now() };
        this.fetchedAt = this.data.fetchedAt; this.error = null;
        try { localStorage.setItem("prs", JSON.stringify(this.data)); } catch { /* cache is optional */ }
      } catch (e) { this.error = String(e?.message ?? e).slice(0, 120); }
      finally { this.loading = false; cx.notify(); }
    });
  }

  ago() {
    if (!this.fetchedAt) return "";
    const m = Math.floor((Date.now() - this.fetchedAt) / 60000);
    return m < 1 ? "방금" : `${m}분 전`;
  }

  render(cx) {
    const t = theme(), list = this.data?.[this.tab] ?? [];
    const ciColor = s => s === "SUCCESS" ? t.ansi2 : s === "FAILURE" || s === "ERROR" ? t.ansi1 : s ? t.ansi3 : t.dim;
    const tabButton = (id, label) => div().id(`prs-tab-${id}`).px(6).py(1).rounded(5).cursor_pointer().text_size(11)
      .text_color(this.tab === id ? t.foreground : t.muted).when(this.tab === id, el => el.bg(t.selected)).hover(s => s.bg(t.hover))
      .on_click((_e, cx) => { this.tab = id; cx.notify(); })
      .child(`${label} ${this.data?.[id]?.length ?? "·"}`);
    return v_flex().id("wb-prs").size_full().min_h(0).text_color(t.foreground).text_size(12)
      .child(h_flex().h(28).flex_none().px(12).gap(6).items_center()
        .child(div().text_size(11).text_color(t.muted).child("PR"))
        .child(tabButton("mine", "내가 작성"))
        .child(tabButton("review", "내 검토"))
        .child(div().flex_1())
        .child(div().text_size(10).text_color(this.error ? t.ansi1 : t.dim).child(this.loading ? "…" : this.error ? "오류" : this.ago()))
        .child(div().id("prs-refresh").px(4).rounded(4).cursor_pointer().text_color(t.muted).hover(s => s.bg(t.hover))
          .on_click((_e, cx) => this.refresh(cx)).child("↻")))
      .child(v_flex().id("prs-list").flex_1().min_h(0).overflow_y_scrollbar().px(6).pb(6)
        .when(Boolean(this.error), el => el.child(div().px(6).py(2).text_size(11).text_color(t.dim).truncate().child(this.error)))
        .when(!list.length && !this.error, el => el.child(div().px(6).py(2).text_size(11).text_color(t.dim).child(this.data ? "열린 PR 없음" : "불러오는 중")))
        .children(list.map(pr => h_flex().id(`pr-${pr.id}`).h(24).flex_none().px(6).gap(6).items_center().rounded(6).cursor_pointer()
          .hover(s => s.bg(t.hover)).on_click((_e, cx) => cx.open_url(pr.url))
          .child(div().size(7).flex_none().rounded(4).bg(ciColor(pr.ci)))
          .child(div().flex_none().text_size(10).text_color(t.dim).child(pr.id))
          .child(div().flex_1().min_w(0).truncate().text_color(pr.draft ? t.muted : t.foreground).child(pr.title))
          .when(pr.bot, el => el.child(div().flex_none().text_size(10).text_color(t.accent).child("봇")))
          .when(pr.conflict, el => el.child(div().flex_none().text_size(10).text_color(t.ansi1).child("충돌")))
          .child(div().flex_none().text_size(10).text_color(pr.review === "APPROVED" ? t.ansi2 : pr.review === "CHANGES_REQUESTED" ? t.ansi1 : t.muted)
            .child(pr.draft ? "초안" : REVIEW[pr.review] ?? "")))));
  }
}
