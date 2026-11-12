#!/usr/bin/env python3
"""Reapply the workbench tree delta to a freshly cloned installed agents mod."""
import argparse
import json
from pathlib import Path


def build(source, config_path):
    s = source
    def replace(old, new):
        nonlocal s
        if s.count(old) != 1:
            raise ValueError('Upstream anchor changed; inspect before rebuilding: ' + old)
        s = s.replace(old, new)
    replace(' layout } from "herdr";', ' layout, readTextFile, writeTextFile, watchFolder, nextCommand, exec } from "herdr";')
    replace('export default class Agents extends View {', '''const BENCH_CONFIG = __BENCH_CONFIG__;
    const BENCH_HELPER = __BENCH_HELPER__;
    const ROLE = {secretary: "디렉터", lead: "리드", "worker-code": "코딩", "worker-review": "리뷰", "worker-query": "조사"};
    // U6 (11/11): short model names for the role tag — claude-opus-5-5 → "Opus 5.5", gpt-6.1-sol → "sol".
    const modelShort = m => {
      if (!m) return "";
      const claude = /^claude-([a-z]+)-(\\d+)-(\\d+)/.exec(m);
      if (claude) return `${claude[1][0].toUpperCase()}${claude[1].slice(1)} ${claude[2]}.${claude[3]}`;
      const gpt = /^gpt-[\\d.]+-([a-z]+)$/.exec(m);
      return gpt ? gpt[1] : m;
    };
    const word = k => typeof k?.status === "string" ? k.status : k?.status?.state;
    // U7 (11/11): '내 순서'. Sessions keep the order the person dragged them into, per parent.
    const ORDER_KEY = "workbench.order";
    const savedOrder = () => { const v = shared(ORDER_KEY); return v && typeof v === "object" && !Array.isArray(v) ? v : {}; };
    const byOrder = (items, ids, key) => {
      if (!Array.isArray(ids) || !ids.length) return items;
      const pos = new Map(ids.map((id, i) => [id, i]));
      const at = x => pos.has(key(x)) ? pos.get(key(x)) : ids.length;
      return items.map((x, i) => [x, i]).sort(([a, i], [b, j]) => at(a) - at(b) || i - j).map(([x]) => x);
    };
    // Moves `from` to where `to` stands among `siblings` (the order on screen). Only siblings move;
    // the parent never changes here. The saved list is the siblings now on screen, so closed ones drop out.
    const moveInOrder = (order, parentKey, siblings, from, to) => {
      const list = [...siblings], i = list.indexOf(from), j = list.indexOf(to);
      if (i < 0 || j < 0 || i === j) return null;
      list.splice(i, 1);
      list.splice(j, 0, from);
      return { ...order, [parentKey]: list };
    };
    const stepInOrder = (order, parentKey, siblings, address, delta) => {
      const i = siblings.indexOf(address), j = i + delta;
      return i < 0 || j < 0 || j >= siblings.length ? null : moveInOrder(order, parentKey, siblings, address, siblings[j]);
    };
    
    export default class Agents extends View {''')
    replace('    this.folded = new Set();', '''    this.restoreFolds();
        this.benchNodes = new Map();
        this.benchDefaults = new Set();
        this.benchClosed = false;
        const refresh = (cx) => cx.spawn(async (cx) => {
          if (await this.reloadBench()) cx.notify();
        });
        refresh(cx);
        cx.timer.every(2000, refresh);
        // U9: ask bench to re-read each session's model every 30 s (rewrites tree.json only on change).
        const models = (cx) => cx.spawn(async () => {
          try { await exec("python3", [BENCH_HELPER, "--config", BENCH_CONFIG, "tree-refresh"], { timeout: 20000 }); }
          catch (error) { console.log("workbench-tree: tree-refresh " + error); }
        });
        models(cx);
        cx.timer.every(30000, models);
        cx.spawn(async (cx) => {
          while (!this.benchClosed) {
            const command = await nextCommand();
            if (command === "dump") { await this.reloadBench(); await this.dumpBench(); }
            else if (command === "move-up" || command === "move-down") { if (this.moveFocused(command === "move-up" ? -1 : 1)) cx.notify(); }
          }
        });''')
    replace('  // Stamps agents whose state changed.', '''  close() { this.benchClosed = true; }
    
      // U8 (11/11): leads start open, and what a person folds stays folded across reloads and restarts.
      // The upstream Set lived only in memory; shared("workbench.folded") is kept by Herdr.
      restoreFolds() {
        const saved = shared("workbench.folded");
        this.folded = new Set(Array.isArray(saved) ? saved.filter(x => typeof x === "string") : []);
        const keep = () => setShared("workbench.folded", [...this.folded]);
        const add = this.folded.add.bind(this.folded), drop = this.folded.delete.bind(this.folded);
        this.folded.add = x => { const had = this.folded.has(x); add(x); if (!had) keep(); return this.folded; };
        this.folded.delete = x => { const had = drop(x); if (had) keep(); return had; };
      }
    
      async reloadBench() {
        try {
          const configText = await readTextFile(BENCH_CONFIG);
          const config = JSON.parse(configText ?? "{}");
          if (!config.space_id || !config.mailbox) return false;
          // tree.json is the small file bench writes for this tree; view.json outgrew readTextFile's 1 MiB (U6, 11/11).
          const text = await readTextFile(`${config.mailbox}/tree.json`) ?? await readTextFile(`${config.mailbox}/view.json`) ?? "{}";
          // A copy that Herdr reloaded in place can keep the old snapshot with an empty node map (U6, 11/11):
          // skip only when the nodes from that snapshot are really here.
          const loaded = typeof this.benchNodes?.get === "function" && this.benchNodes.size > 0;
          if (this.benchSnapshot === configText + text && loaded) return false;
          if (!(typeof this.benchDefaults?.has === "function")) this.benchDefaults = new Set();
          const data = JSON.parse(text);
          if (data.space && data.space !== config.space_id) throw new Error("mailbox space mismatch");
          this.benchConfig = config;
          this.benchNodes = new Map((data.nodes ?? []).filter(n => !n.closed_at).map(n => [n.address, n]));
          this.benchSnapshot = configText + text;
          this.benchError = null;
          return true;
        } catch (error) {
          this.benchError = String(error);
          console.log("workbench-tree: " + this.benchError);
          return false;
        }
      }
    
      attention(address) {
        const all = terminals().filter(k => k.labels?.["herdr.space"] === this.benchConfig?.space_id && this.benchNodes.has(k.address));
        const node = this.benchNodes.get(address);
        const scope = [address, ...(node?.role === "lead" ? this.tree(all, address).map(s => s.t.address) : [])];
        return { unread: scope.reduce((n, id) => n + Number(this.benchNodes.get(id)?.unread_count ?? 0), 0),
          native_blocked: all.some(k => scope.includes(k.address) && ["blocked", "error"].includes(word(k))) };
      }
    
      displayStatus(address, native) {
        const a = this.attention(address);
        return a.native_blocked ? "blocked" : a.unread > 0 ? "done" : native;
      }
    
      // U9 (11/11): the model a session uses now (after /model), read by bench from its log; '*' when it is
      // not the one it was opened with. Without a reading, the spawn model.
      roleText(address) {
        const node = this.benchNodes.get(address);
        const now = modelShort(node?.model_now), opened = modelShort(node?.model);
        const model = now ? now + (opened && now !== opened ? "*" : "") : opened;
        return [ROLE[node?.role], model].filter(Boolean).join(" · ");
      }
    
      roleTag(t, address) {
        const node = this.benchNodes.get(address);
        const now = modelShort(node?.model_now), opened = modelShort(node?.model);
        return div().flex_none().text_size(10).text_color(t.dim).child(this.roleText(address))
          .when(Boolean(now && opened && now !== opened), el => el.tooltip(`띄울 때 ${opened}, 지금 ${now}`));
      }
    
      // U7: in '내 순서', press a row, release it on a sibling row, and it takes that place.
      // A thin line shows where it lands. Rows under another parent ignore the drop.
      draggable(el, t, address, parentKey, siblings) {
        const d = this.drag;
        const here = Boolean(d) && d.address !== address && d.parentKey === parentKey && this.dropAt === address;
        const down = here && siblings.indexOf(d.address) < siblings.indexOf(address);
        this.places?.set(address, { parentKey, siblings });
        return el
          .on_mouse_down("left", () => { this.drag = { address, parentKey }; this.dropAt = null; })
          .on_mouse_move((_e, cx) => {
            const d = this.drag;
            if (d && d.address !== address && d.parentKey === parentKey && this.dropAt !== address) { this.dropAt = address; cx.notify(); }
          })
          .on_mouse_up("left", (_e, cx) => {
            const d = this.drag;
            if (d && d.address !== address && d.parentKey === parentKey) {
              const next = moveInOrder(savedOrder(), parentKey, siblings, d.address, address);
              if (next) setShared(ORDER_KEY, next);
            }
            this.drag = null; this.dropAt = null; cx.notify();
          })
          .when(here && !down, x => x.border_t(2).border_color(t.foreground))
          .when(down, x => x.border_b(2).border_color(t.foreground));
      }
    
      // alt-shift-up/down (keys.json -> "<this mod>:move-up"): the focused session moves one place among its siblings.
      moveFocused(delta) {
        const address = focused()?.agent;
        const place = address && this.places?.get(address);
        if (!this.manual || !place) return false;
        const next = stepInOrder(savedOrder(), place.parentKey, place.siblings, address, delta);
        if (next) setShared(ORDER_KEY, next);
        return Boolean(next);
      }
    
      async dumpBench() {
        const all = terminals().filter(k => k.labels?.["herdr.space"] === this.benchConfig?.space_id && this.benchNodes.has(k.address));
        if (!all.length) return; // A headless check is not live terminal evidence.
        const rows = [];
        const add = (k, depth, hiddenBy = null) => {
          const children = all.filter(c => c.parent === k.address && c.state === "live");
          const native = all.some(p => p.address === k.parent) ? kidStatus(k, this.listed ?? new Map()) : this.listed?.get(k.address) ?? word(k);
          const a = this.attention(k.address), status = this.displayStatus(k.address, native);
          rows.push({address: k.address, parent: k.parent ?? null, role: this.benchNodes.get(k.address)?.role,
            native_role: k.labels?.["bench.role"], tag: this.roleText(k.address), depth, visible: hiddenBy === null, hidden_by: hiddenBy,
            collapsed: this.folded.has(k.address), child_count: children.length,
            unread_count: this.benchNodes.get(k.address)?.unread_count ?? 0, attention: a.unread > 0 || a.native_blocked,
            aggregate_unread: a.unread, native_blocked: a.native_blocked, native_status: word(k), display_status: status,
            dot: status === "done" || status === "blocked", last_activity: this.since(k), program: k.program ?? null});
          children.forEach(c => add(c, depth + 1, hiddenBy ?? (this.folded.has(k.address) ? k.address : null)));
        };
        all.filter(k => !all.some(p => p.address === k.parent)).forEach(k => add(k, 0));
        const path = `${this.benchConfig.mailbox}/mod-state.json`;
        await writeTextFile(path, JSON.stringify({observed_at: new Date().toISOString(), source: "herdr.mod.terminals",
          revision: "agents-superset", space: this.benchConfig.space_id, namespace: "workbench", error: this.benchError, nodes: rows}, null, 2), await readTextFile(path));
      }
    
      // Stamps agents whose state changed.''')
    replace('    return this.changed[a.address]?.at ?? 0;', '    return Math.max(this.changed[a.address]?.at ?? 0, Date.parse(this.benchNodes.get(a.address)?.last_activity ?? "") || 0);')
    replace('  tree(all, addr, lead = []) {', '  tree(all, addr, lead = [], visible = false) {')
    replace('    const kids = all.filter((k) => k.parent === addr && k.state === "live");',
            '    const kids = (list => this.manual ? byOrder(list, savedOrder()[addr], (k) => k.address) : list)(all.filter((k) => k.parent === addr && k.state === "live"));')
    replace('        { t: k, lines: [...lead, last ? "└" : "├"] },', '        { t: k, lines: [...lead, last ? "└" : "├"], parent: addr, siblings: kids.map((c) => c.address) },')
    replace('      .id(`sub-${k.address}`)', '      .id(`sub-${k.address}`)\n      .when(Boolean(this.manual && s.parent), el => this.draggable(el, t, k.address, s.parent, s.siblings))')
    # U7: the sort menu offers '내 순서' (its popup belongs to this mod; the built-in agents mod falls back to Priority)
    replace('  { id: "grouped", label: "Grouped by space", icon: "layers" },', '  { id: "grouped", label: "Grouped by space", icon: "layers" },\n  { id: "manual", label: "내 순서", icon: "square-pen" },')
    replace('height: 140, props: { sortMenu: true }', 'height: 175, props: { sortMenu: true }')
    replace('    const sort = sortOf();', '    const sort = sortOf();\n    this.manual = sort.id === "manual";')
    replace('    if (byPriority) list = [...list].sort(', '    if (this.manual) list = byOrder(list, savedOrder().root, (a) => a.address);\n    if (byPriority) list = [...list].sort(')
    replace('    list = [...pinned, ...rest];', '    list = [...pinned, ...rest];\n    this.topOrder = list.map((a) => a.address);\n    this.places = new Map();')
    replace('        .id(`ag-${a.address}`)\n        .px(8)\n        .h(30)', '        .id(`ag-${a.address}`)\n        .when(Boolean(this.manual), el => this.draggable(el, t, a.address, "root", this.topOrder))\n        .px(8)\n        .h(30)')
    replace('    return v_flex()\n      .size_full()', '    return v_flex()\n      .size_full()\n      .on_mouse_up("left", (_e, cx) => { if (this.drag) { this.drag = null; this.dropAt = null; cx.notify(); } })\n      .on_hover((on, cx) => { if (!on && this.drag) { this.drag = null; this.dropAt = null; cx.notify(); } })')
    replace('        ...this.tree(all, k.address, [...lead, last ? "" : "│"]),', '        ...(visible && this.folded.has(k.address) ? [] : this.tree(all, k.address, [...lead, last ? "" : "│"], visible)),')
    replace('  subRow(t, s, shown, compact) {', '  subRow(t, s, shown, compact, fold) {')
    replace('      .child(this.status(t, { status: st }, compact));', '''      .child(this.roleTag(t, k.address))
          .when(this.tree(terminals(), k.address).length > 0, el => el.child(fold(k, this.tree(terminals(), k.address))))
          .child(div().ml(6).text_size(11).text_color(t.dim).child(duration(Date.now() - this.since(k))))
          .child(this.status(t, { ...k, status: st }, compact));''')
    replace('    const color = t[a.status] ?? t.dim;', '    a = { ...a, status: this.displayStatus(a.address, a.status) };\n    const color = t[a.status] ?? t.dim;')
    replace('    const all = terminals();', '''    let all = terminals().filter(k => k.labels?.["herdr.space"] === this.benchConfig?.space_id && this.benchNodes.has(k.address));
        const scoped = new Set(all.map(k => k.address));
        const tracked = list;
        list = list.filter(a => !scoped.has(all.find(k => k.address === a.address)?.parent));
        all = terminals();''')
    replace('    this.track(list, now);', '    this.track(tracked, now);')
    replace('      return [r, ...subs.map((s) => this.subRow(t, s, shown, byPriority))];', '      return [r, ...(collapsed ? [] : this.tree(all, a.address, [], true)).map((s) => this.subRow(t, s, shown, byPriority, fold))];')
    replace('        .when(Boolean(machine), el => el.child(div().text_size(10).text_color(t.dim).child(machine)))', '        .child(this.roleTag(t, a.address))\n        .when(Boolean(machine), el => el.child(div().text_size(10).text_color(t.dim).child(machine)))')
    replace('      const name = full ? a.space_name || label(a) : more ?? (/^\\d+$/.test(label(a)) ? a.program?.name || label(a) : label(a));', '      const name = (n => n?.labels?.["bench.display"] || n?.name)(all.find(k => k.address === a.address)) || a.name || (full ? a.space_name || label(a) : more ?? (/^\\d+$/.test(label(a)) ? a.program?.name || label(a) : label(a)));')
    replace('    const k = s.t;', '    const k = s.t?.labels?.["bench.display"] ? { ...s.t, name: s.t.labels["bench.display"] } : s.t;')
    # B25 (11/12 운영자 15:19): the folder a session was opened in, by name only, dim, right after the name.
    # It takes only the room the name leaves (flex-basis 0), so when the row is short the folder goes first.
    replace('      roleTag(t, address) {', '''      // B25 (11/12): the folder name bench put in tree.json ('team-repo', 'hub'); nothing without one.
      folderTag(t, address) {
        return div().flex_1().min_w(0).truncate().text_size(11).text_color(t.dim).child(this.benchNodes.get(address)?.folder || "");
      }

      roleTag(t, address) {''')
    replace('          .child(div().min_w(0).max_w(full && more ? 120 : 200).truncate().text_color(idle ? t.muted : t.foreground).child(name))',
            '          .child(div().min_w(0).max_w(full && more ? 120 : 200).truncate().text_color(idle ? t.muted : t.foreground).child(name))\n'
            '          .child(this.folderTag(t, a.address))')
    # The child row's name was flex_1 (basis 0), which would make it give way before the folder. It now keeps
    # its own width and the folder, flex_1, fills what is left (and keeps the tags on the right when empty).
    replace('      .child(div().flex_1().truncate().text_color(on ? t.foreground : t.muted).child(k.name || k.template || k.program?.name || k.address))',
            '      .child(div().min_w(0).truncate().text_color(on ? t.foreground : t.muted).child(k.name || k.template || k.program?.name || k.address))\n'
            '      .child(this.folderTag(t, k.address).ml(5))')
    config = Path(config_path).resolve()
    return (s.replace('__BENCH_CONFIG__', json.dumps(str(config)))
             .replace('__BENCH_HELPER__', json.dumps(str(config.with_name('bench.py')))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('bench.yaml'))
    args = parser.parse_args()
    result = build(args.source.read_text(), args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result)
    print(f'Generated {args.output}: {len(result.splitlines())} lines')


if __name__ == '__main__':
    main()
