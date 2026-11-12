#!/usr/bin/env python3
"""Native CLI workbench with durable parent mailboxes and conservative worktree cleanup."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from zoneinfo import ZoneInfo

ROLES = {r: r + '.md' for r in ('secretary', 'lead', 'worker-code', 'worker-review', 'worker-query')}
DEFAULT_CONFIG = Path(__file__).with_name('bench.yaml')
NATIVE_NAME = re.compile(r'[a-z0-9_-]{1,32}')
SESSION_ID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
WEEKDAYS = '월화수목금토일'
WAIT_MAX_SECONDS = 3600
TAB_POLL_SECONDS = 0.5
AUTO_TAB_NAME = re.compile(r'\d+')   # Herdr names an unnamed tab by its number
KST = ZoneInfo('Asia/Seoul')
# A weekday written right after a date: '(금)', '(금요일)', '금요일', or a bare '금' that is not the
# start of another word ('목표', '수정'). A bare '일' is too often the noun 'work', so it needs a form.
_WEEKDAY_TAIL = (r'\s*(?:\(\s*(?P<w1>[월화수목금토일])(?:요일)?\s*\)|(?P<w2>[월화수목금토일])요일'
                 r'|(?P<w3>[월화수목금토])(?![가-힣A-Za-z0-9]))')
DATE_FORMS = [re.compile(p + _WEEKDAY_TAIL) for p in (
    r'(?<![\d/.-])(?P<y>\d{4})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})(?![\d])',
    r'(?<![\d/.-])(?P<m>\d{1,2})/(?P<d>\d{1,2})(?![\d/])',
    r'(?:(?P<y>\d{4})년\s*)?(?<!\d)(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일',
)]


def today_kst():
    return datetime.now(KST).date()


def week_calendar(today):
    """One line naming today and the ISO week so briefs never guess a weekday."""
    monday = today - timedelta(days=today.weekday())
    days = ' '.join(f'{d.month}/{d.day}({WEEKDAYS[d.weekday()]})'
                    for d in (monday + timedelta(days=i) for i in range(7)))
    following = monday + timedelta(days=7)
    return (f'[작업대 달력] 오늘은 {today.isoformat()}({WEEKDAYS[today.weekday()]}) KST다. '
            f'이번 주: {days}. 다음 주 월요일: {following.month}/{following.day}. '
            '날짜에 요일을 붙일 때는 이 달력과 맞춘다.')


def date_mismatches(text, today):
    """Dates written with a weekday that the calendar contradicts. Missing years take the nearest one."""
    found = []
    for form in DATE_FORMS:
        for match in form.finditer(text or ''):
            groups = match.groupdict()
            written = groups['w1'] or groups['w2'] or groups['w3']
            month, day = int(groups['m']), int(groups['d'])
            years = [int(groups['y'])] if groups.get('y') else [today.year - 1, today.year, today.year + 1]
            candidates = []
            for year in years:
                try:
                    candidates.append(date(year, month, day))
                except ValueError:
                    continue
            if not candidates:
                continue
            actual = min(candidates, key=lambda d: abs((d - today).days))
            if WEEKDAYS[actual.weekday()] != written:
                found.append({'text': match.group(0).strip(), 'date': actual.isoformat(),
                              'written': written, 'actual': WEEKDAYS[actual.weekday()]})
    return found


def checked_dates(text, allow_mismatch=False):
    """Refuse instructions whose date and weekday disagree; the override is explicit and per call."""
    if allow_mismatch:
        return
    found = date_mismatches(text, today_kst())
    if found:
        listed = '; '.join(f"'{f['text']}' is {f['date']} ({f['actual']}), not {f['written']}" for f in found)
        raise ValueError('Date and weekday disagree: ' + listed
                         + '. Fix the text, or pass --allow-date-mismatch if it is intended.')


# B16 (11/11): a report's header time must not run ahead of when it is sent. Only the first line is
# checked; plans, deadlines, other dates, quotes and UTC stamps there are not "now" and are skipped.
CLOCK = re.compile(r'(?<![\d:T])([01]?\d|2[0-3]):([0-5])([0-9xX])(?![\d:Z])')
CLOCK_PLAN_AFTER = re.compile(r'^\s*(?:KST\s*)?(?:기한|까지|마감|예정|예약|목표|쯤|전에|이후|부터)')
CLOCK_PLAN_BEFORE = re.compile(r'(?:끝낼\s*시각|예상|목표|기한|마감|예정)\s*[:：]?\s*$')
CLOCK_DATE_BEFORE = re.compile(r'(?:(\d{4})[-./])?(\d{1,2})[/.-](\d{1,2})\s*(?:\([월화수목금토일]\)\s*)?$')
CLOCK_SLACK_MINUTES = 5
CLOCK_WINDOW_MINUTES = 90   # slips seen were 6-23 minutes; plans in a header were 3+ hours ahead


def sent_kst(created_at):
    sent = datetime.fromisoformat(created_at).astimezone(KST)
    return f'{sent.month}/{sent.day}({WEEKDAYS[sent.weekday()]}) {sent:%H:%M} KST'


def late_header_times(summary, created_at):
    """Times in the first line written later than the send time (KST); 'x' digits take their earliest value."""
    sent = datetime.fromisoformat(created_at).astimezone(KST)
    line = (summary or '').split('\n', 1)[0][:300]
    found = []
    for match in CLOCK.finditer(line):
        before, after = line[:match.start()], line[match.end():]
        if CLOCK_PLAN_AFTER.match(after) or CLOCK_PLAN_BEFORE.search(before[-12:]):
            continue
        if any(before.count(q) % 2 for q in '"\'`') or before.count('“') > before.count('”') \
                or before.count('‘') > before.count('’'):
            continue
        dated = CLOCK_DATE_BEFORE.search(before[-16:])
        if dated and (int(dated.group(2)), int(dated.group(3))) != (sent.month, sent.day):
            continue
        hour, tens, ones = int(match.group(1)), int(match.group(2)), match.group(3)
        written = sent.replace(hour=hour, minute=tens * 10 + (0 if ones in 'xX' else int(ones)), second=0, microsecond=0)
        late = (written - sent).total_seconds() / 60
        if CLOCK_SLACK_MINUTES < late <= CLOCK_WINDOW_MINUTES:
            found.append({'text': match.group(0), 'read_as': f'{written:%H:%M}', 'sent': f'{sent:%H:%M}',
                          'late_minutes': int(late)})
    return found


def checked_header_time(summary, created_at, allow_late=False):
    if allow_late:
        return
    found = late_header_times(summary, created_at)
    if found:
        listed = '; '.join(f"'{f['text']}' reads as {f['read_as']}, {f['late_minutes']} minutes after the send time {f['sent']} KST"
                           for f in found)
        raise ValueError('Report header time is later than now: ' + listed
                         + f". Write the time you send it ({found[0]['sent']} KST, or leave the time out: the inbox records it as sent_kst)."
                         + ' A deadline or plan reads as one when followed by 까지·기한·예정·쯤 or after 끝낼 시각.'
                         + ' Pass --allow-late-time (MCP: allow_late_time) only if the time is intended.')


def checked_spawn_identity(name, display, resume, worktree):
    """Validate operator-chosen names and a resumed Claude session before anything launches."""
    if name is not None and not NATIVE_NAME.fullmatch(name):
        raise ValueError('Name must be 1-32 of a-z 0-9 - _ (Herdr rule); put other text in --display')
    if display is not None and (not 1 <= len(display) <= 32
                                or any(ord(c) < 32 or ord(c) == 127 for c in display)):
        raise ValueError('Display name must be 1-32 printable characters')
    if resume is not None:
        if not SESSION_ID.fullmatch(resume):
            raise ValueError('Resume needs a Claude session id (UUID)')
        if worktree:
            raise ValueError('A resumed session keeps its own directory; it cannot take --worktree')


REGENERABLE_DIRECTORIES = {'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache',
                           '.mypy_cache', '.ruff_cache', 'dist', 'build', 'cdk.out', 'coverage'}


def regenerable_output(path, root=None):
    """Only ignored outputs in the reviewed regeneration list may be discarded.

    A symlink named like a listed directory (a worktree's node_modules pointing at the main checkout,
    B19 11/11) is listed by git as one entry, not as files under it. It counts only when it really is a
    symlink under root: removing the worktree unlinks the link and never follows it to its target.
    """
    parts = Path(path).parts
    directories = REGENERABLE_DIRECTORIES
    if root is not None and parts and parts[-1] in directories and (Path(root) / path).is_symlink():
        return True
    return (bool(directories.intersection(parts[:-1]))
            or parts[0] in {'.agents', '.codex'}
            or path == '.claude/settings.local.json'
            or parts[-1] in {'.coverage', '.DS_Store'}
            or parts[-1].endswith('.tsbuildinfo'))


SHELLS = {'zsh', 'bash', 'sh', 'fish', 'dash', 'ksh', 'tcsh', 'csh', '-zsh', '-bash', '-sh'}


def checked_state_file(path):
    """A Codex session's state file: an absolute path, so a reopened session can be told to read it."""
    if path is None:
        return None
    if not isinstance(path, str) or not path.startswith('/') or any(ord(c) < 32 for c in path) or len(path) > 1024:
        raise ValueError('State file must be an absolute path')
    return path


def terminal_kind(info):
    """What hc get says is in a terminal now: running agent, a revived shell, finished or gone (B21)."""
    if info is None:
        return 'not_found'
    state = info.get('state')
    if state != 'live':
        return 'finished' if state == 'finished' else 'unknown'
    fg = info.get('foreground') or {}
    names = {str(fg.get('name') or ''), Path(str((fg.get('argv') or [''])[0])).name}
    if names & SHELLS or (not fg and Path(str((info.get('argv') or [''])[0])).name in SHELLS):
        return 'shell'
    return 'running'


def claude_project_dir(cwd):
    return Path.home() / '.claude' / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', str(cwd))


def find_claude_session(cwd, title):
    """For sessions opened before bench recorded session ids: the one conversation in that folder whose
    title is this display name. None when there is none or more than one."""
    if not title:
        return None
    folder = claude_project_dir(cwd)
    marker = json.dumps(title, ensure_ascii=False)
    found = []
    for path in folder.glob('*.jsonl') if folder.is_dir() else []:
        try:
            text = path.read_text(errors='replace')
        except OSError:
            continue
        titles = re.findall(r'"customTitle":\s*("(?:[^"\\]|\\.)*")', text)
        if titles and titles[-1] == marker:
            found.append(path.stem)
    return found[0] if len(found) == 1 and SESSION_ID.fullmatch(found[0]) else None


MODEL_WORDS = re.compile(r'\b(Opus|Sonnet|Haiku|Fable)\s+(\d+)\.(\d+)\b')


def tail_lines(path, limit=262144):
    """The last `limit` bytes of a log as whole lines (the first, partial line dropped)."""
    with open(path, 'rb') as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        data = stream.read().decode('utf-8', errors='replace')
    lines = data.splitlines()
    return lines[1:] if size > limit else lines


def claude_model_from_log(path):
    """The latest model signal in a Claude Code session log: '/model' prints 'Set model to `Opus 5.5`' at
    once; requests and answers name the model id. Returns (model id, source) or (None, None)."""
    found = (None, None)
    for line in tail_lines(path):
        if 'Set model to' in line and 'local-command-stdout' in line:
            words = MODEL_WORDS.search(line.split('Set model to', 1)[1][:80])
            if words:
                found = (f'claude-{words.group(1).lower()}-{words.group(2)}-{words.group(3)}', '/model')
            continue
        if '"model"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get('type') == 'assistant' and (entry.get('message') or {}).get('model', '').startswith('claude-'):
            found = (entry['message']['model'], 'answer')
        elif entry.get('type') == 'api-request' and str((entry.get('params') or {}).get('model', '')).startswith('claude-'):
            found = (entry['params']['model'], 'request')
    return found


def codex_rollout_for(node):
    """The Codex session log started in this session's folder within two minutes of its spawn."""
    try:
        started = datetime.fromisoformat(node['created_at'])
    except (KeyError, TypeError, ValueError):
        return None
    hits = []
    for day in {started.astimezone().date(), started.date()}:
        folder = Path.home() / '.codex' / 'sessions' / f'{day:%Y}' / f'{day:%m}' / f'{day:%d}'
        for path in folder.glob('rollout-*.jsonl') if folder.is_dir() else []:
            try:
                with open(path, encoding='utf-8', errors='replace') as stream:
                    meta = json.loads(stream.readline()).get('payload') or {}
                when = datetime.fromisoformat(str(meta.get('timestamp')).replace('Z', '+00:00'))
            except (OSError, ValueError, TypeError):
                continue
            if meta.get('cwd') == node.get('cwd') and abs((when - started).total_seconds()) <= 120:
                hits.append(path)
    return hits[0] if len(hits) == 1 else None


def codex_model_from_log(path):
    found = (None, None)
    for line in tail_lines(path):
        if '"turn_context"' not in line:
            continue
        try:
            payload = json.loads(line).get('payload') or {}
        except ValueError:
            continue
        if payload.get('model'):
            found = (payload['model'], 'turn')
    return found


def worktree_repos(nodes):
    """Every worktree bench has recorded (open or closed sessions): its path -> the repository it belongs to."""
    return {str(Path(wt['path'])): wt['repo'] for wt in ((n.get('worktree') or {}) for n in nodes)
            if wt.get('path') and wt.get('repo')}


def folder_name(cwd, repos, worktrees_root):
    """B25 (11/12 운영자): the folder name the tree shows next to a session's name. Names only, never paths.
    A session opened in a worktree (bench's own, or a repository's .claude/worktrees) shows the repository
    the worktree belongs to. Anything else shows the last name of the folder it was opened in, so a session
    opened at a repository's root shows that repository and one opened in the hub shows hub.
    No cwd on record: None (the tree then shows nothing). Reads only the record, and for a bench worktree
    no record names, that worktree's .git file."""
    if not cwd:
        return None
    path = Path(cwd)
    parts = path.parts
    root = Path(worktrees_root) if worktrees_root else None
    if root is not None and len(parts) > len(root.parts) and parts[:len(root.parts)] == root.parts:
        top = root / parts[len(root.parts)]
        repo = repos.get(str(top))
        if not repo:
            try:
                found = re.match(r'gitdir:\s*(.+?)/\.git/worktrees/[^/]+\s*$', (top / '.git').read_text())
                repo = found.group(1) if found else None
            except OSError:
                repo = None
        if repo:
            return Path(repo).name
    for i in range(len(parts) - 3):
        if parts[i + 1] == '.claude' and parts[i + 2] == 'worktrees':
            return parts[i]
    return path.name or str(path)


def model_now(node):
    """(model, source) the session uses now, or (None, None) to fall back to the spawn model."""
    try:
        if node.get('vendor') == 'codex':
            path = codex_rollout_for(node)
            return codex_model_from_log(path) if path else (None, None)
        session = node.get('resumed_session') or node.get('session_id')
        path = claude_project_dir(node.get('cwd') or '') / f'{session}.jsonl' if session else None
        return claude_model_from_log(path) if path and path.is_file() else (None, None)
    except OSError:
        return (None, None)


def load_config(path):
    path = Path(path).expanduser().resolve()
    # JSON is a YAML subset. Prefer the stdlib for shipped JSON-form YAML;
    # accept ordinary YAML when PyYAML is installed.
    raw = path.read_text()
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        import yaml
        config = yaml.safe_load(raw)
    if not isinstance(config, dict) or not isinstance(config.get('space_id'), str):
        raise ValueError('bench.yaml needs a space_id string')
    for key in ('mailbox', 'roles', 'cwd', 'worktrees', 'hc', 'link_repo_skills', 'policy'):
        value = Path(config[key]).expanduser()
        config[key] = os.path.abspath(path.parent / value)
    if config.get('herdr_app'):
        # Optional: with it, spawn and retitle name Herdr tabs; without it (tests) they never touch the app.
        config['herdr_app'] = os.path.abspath(path.parent / Path(config['herdr_app']).expanduser())
    for name in ('claude', 'codex'):
        vendor = config['vendors'][name]
        if not vendor.get('model'):
            raise ValueError('Each vendor needs a default model')
        for key in ('executable', 'process_executable'):
            if key in vendor:
                vendor[key] = os.path.abspath(path.parent / Path(vendor[key]).expanduser())
    return config


def now():
    return datetime.now(timezone.utc).isoformat()


PROC_ROOT = Path('/proc')


def proc_executable(pid, proc_root=None):
    """B28 (11/12): the full path of a process's executable from Linux /proc/<pid>/exe.
    None where there is no such link (macOS has no /proc) or it cannot be read."""
    try:
        return os.readlink(Path(proc_root or PROC_ROOT) / str(int(pid)) / 'exe')
    except (OSError, ValueError):
        return None


def process_metadata(pid, proc_root=None):
    """Read only OS process identity; never request arguments or environment.
    B28 (11/12): Linux ps comm= gives only the name ('python3', 'codex'), so where /proc/<pid>/exe can be
    read its target is the executable (source 'proc'). macOS has no /proc and keeps ps's full path ('ps')."""
    result = subprocess.run(['/bin/ps', '-o', 'pid=,ppid=,lstart=,comm=', '-p', str(int(pid))],
                            capture_output=True, text=True, timeout=2, shell=False, env={'LC_ALL': 'C'})
    if result.returncode or not result.stdout.strip():
        return None
    fields = result.stdout.strip().split(maxsplit=7)
    if len(fields) != 8:
        return None
    started = datetime.strptime(' '.join(fields[2:7]), '%a %b %d %H:%M:%S %Y').astimezone()
    linked = proc_executable(fields[0], proc_root)
    return {'pid': int(fields[0]), 'ppid': int(fields[1]), 'started_at': started.isoformat(),
            'executable': linked or fields[7], 'executable_source': 'proc' if linked else 'ps'}


def atomic_json(path, value):
    """Commit a single authoritative JSON file and fsync its containing directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def format_ls(rows):
    """One readable line per node; depth is shown by indentation."""
    lines = []
    for r in rows:
        name = r['display'] or r['name'] or ''
        live = r['state'] + ('/' + r['status'] if r['status'] else '')
        extra = ([f"미확인 {r['unread_count']}"] if r['unread_count'] else []) + ([r['branch']] if r['branch'] else [])
        folder = f"  {r['folder']}" if r.get('folder') else ''
        lines.append('  ' * r['depth'] + f"{r['address']}  {name}{folder}  [{r['role']} · {r['model'] or r['vendor'] or ''}]  {live}"
                     + ('  ' + ' · '.join(extra) if extra else '') + ('  (closed)' if r['closed'] else ''))
    if rows and rows[0].get('hc_error'):
        lines.append('hc ls 실패: ' + rows[0]['hc_error'])
    return '\n'.join(lines) + '\n'


class SessionHost:
    def __init__(self, config=DEFAULT_CONFIG):
        self.config_path = Path(config).expanduser().resolve()
        self.config = load_config(self.config_path)
        self.root = self.config_path.parent
        self.mailbox = Path(self.config['mailbox'])
        self.mailbox.mkdir(parents=True, exist_ok=True)
        self.evidence = self.mailbox / 'evidence'
        self.helper = Path(__file__).resolve()

    @contextmanager
    def locked(self):
        lock_path = self.mailbox / '.lock'
        try:
            lock = lock_path.open('a+')
        except PermissionError as error:
            raise PermissionError(
                error.errno,
                'Mailbox lock requires write access; the worker sandbox may deny this path. '
                'Workers should use MCP bench_inbox and bench_report instead of CLI inspect.',
                str(lock_path)) from error
        with lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state_path = self.mailbox / 'state.json'
            if state_path.exists():
                state = json.loads(state_path.read_text())
            else:
                state = {'version': 1, 'space': self.config['space_id'], 'nodes': {}, 'reports': {}}
            if state['space'] != self.config['space_id']:
                raise ValueError('Mailbox belongs to a different space; use a separate mailbox')
            yield state

    def projection(self, state):
        nodes = []
        for node in state['nodes'].values():
            pending = [r['report_id'] for r in state['reports'].values()
                       if r['to'] == node['address'] and r['acked_at'] is None]
            nodes.append({**node, 'pending_report_ids': pending, 'unread_count': len(pending)})
        return {'version': 1, 'space': self.config['space_id'], 'updated_at': now(), 'nodes': nodes,
                'reports': list(state['reports'].values()),
                'directives': list(state.get('directives', {}).values())}

    def worktrees_root(self):
        """bench's own worktree folder, resolved as spawn resolves it (None if the config names none)."""
        return Path(self.config['worktrees']).expanduser().resolve() if self.config.get('worktrees') else None

    TREE_FIELDS = ('address', 'parent', 'role', 'model', 'display', 'vendor', 'unread_count', 'last_activity',
                   'model_now', 'model_now_source', 'folder')

    def tree_projection(self, view):
        """The Herdr tree's own file. Herdr's readTextFile reads at most 1 MiB and view.json carries every
        report (1.58 MB on 11/11), so the tree reads this: open sessions only, only the fields it shows.
        U9: model_now is the model the session uses now (after /model), read from its conversation log."""
        nodes = []
        repos = worktree_repos(view['nodes'])
        wroot = self.worktrees_root()
        for n in view['nodes']:
            if n.get('closed_at'):
                continue
            row = {k: n.get(k) for k in self.TREE_FIELDS}
            row['model_now'], row['model_now_source'] = model_now(n)
            row['folder'] = folder_name(n.get('cwd'), repos, wroot)
            nodes.append(row)
        return {'version': 1, 'space': view['space'], 'updated_at': view['updated_at'], 'nodes': nodes}

    def tree_refresh(self):
        """Rewrite tree.json only when what the tree shows changed (U9: the tree mod calls this every 30 s).
        Claude sessions opened before bench recorded ids are looked up once by title and the id is kept."""
        with self.locked() as state:
            missing = [dict(n) for n in state['nodes'].values() if not n.get('closed_at') and n.get('vendor') == 'claude'
                       and not (n.get('resumed_session') or n.get('session_id') or n.get('session_lookup_failed'))]
        found = {n['address']: find_claude_session(n['cwd'], n.get('display') or n.get('name')) for n in missing}
        with self.locked() as state:
            if found:
                for address, sid in found.items():
                    node = state['nodes'].get(address)
                    if node is None:
                        continue
                    if sid:
                        node.update(session_id=sid, session_id_source='title')
                    else:
                        node['session_lookup_failed'] = now()
                self.commit(state)
            tree = self.tree_projection(self.projection(state))
        path = self.mailbox / 'tree.json'
        try:
            if json.loads(path.read_text()).get('nodes') == tree['nodes']:
                return {'changed': False}
        except (OSError, ValueError):
            pass
        atomic_json(path, tree)
        return {'changed': True}

    def commit(self, state):
        # The report and registry are authoritative. view.json and tree.json are recoverable projections.
        atomic_json(self.mailbox / 'state.json', state)
        view = self.projection(state)
        atomic_json(self.mailbox / 'view.json', view)
        atomic_json(self.mailbox / 'tree.json', self.tree_projection(view))

    def identity(self, state, caller):
        if not caller or caller not in state['nodes']:
            raise ValueError('HC_TERMINAL_ID is not a registered workbench session')
        return state['nodes'][caller]

    def parent_for(self, state, role, caller):
        if role not in ROLES:
            raise ValueError('Unknown role')
        if role == 'secretary':
            if any(n['role'] == 'secretary' and not n.get('closed_at') for n in state['nodes'].values()):
                raise ValueError('An active secretary already exists')
            return None
        parent = self.identity(state, caller)
        required = 'secretary' if role == 'lead' else 'lead'
        if parent['role'] != required or parent.get('closed_at'):
            raise ValueError('Caller role cannot create this child')
        return parent['address']

    def argv(self, role, parent, *, vendor=None, model=None, cwd=None, task=None, no_task=False, name=None,
             display=None, resume=None, session_id=None):
        vendor = vendor or ('codex' if role.startswith('worker-') else 'claude')
        if vendor not in self.config['vendors']:
            raise ValueError('Unknown vendor')
        if resume and vendor != 'claude':
            raise ValueError('--resume reopens Claude sessions only')
        settings = self.config['vendors'][vendor]
        cwd = Path(cwd or self.config['cwd']).expanduser().resolve()
        role_file = Path(self.config['roles']) / ROLES[role]
        if not cwd.is_dir() or not role_file.is_file():
            raise ValueError('Working directory and role document must exist')
        if not self.config['space_id']:
            raise ValueError('Set space_id in bench.yaml before spawning')
        prompt = None if no_task else (f'Read and follow {role_file}. Your role is {role}. '
                  f'Use python3 {self.helper} --config {self.config_path} for bench operations. '
                  'Identity is your inherited HC_TERMINAL_ID; never override it.\n\n'
                  + role_file.read_text() + '\n\n' + week_calendar(today_kst())
                  + ('\n\nTask:\n' + task if task else ''))
        name = name or ('bench-' + role + '-' + uuid.uuid4().hex[:12])
        command = [self.config['hc'], 'run', '--bg', '--no-notify', '--name', name,
                   '--label', 'herdr.space=' + self.config['space_id'], '--label', 'bench.role=' + role,
                   '--cwd', str(cwd)]
        if display:
            command += ['--label', 'bench.display=' + display]
        command += ['--no-parent'] if parent is None else ['--parent', parent]
        command += ['--', '/usr/bin/env', '-u', 'ANTHROPIC_API_KEY', '-u', 'OPENAI_API_KEY',
                    'TERM=xterm-256color', 'python3', str(self.helper.with_name('native_exec.py')),
                    '--config', str(self.config_path), settings['executable']]
        if vendor == 'codex':
            command += ['--no-daemon', '--no-alt-screen', '--model', model or settings['model'],
                        '--sandbox', 'workspace-write' if role in ('worker-code', 'lead') else 'read-only',
                        '--ask-for-approval', 'on-request', '-c', 'forced_login_method="chatgpt"',
                        '-c', 'mcp_servers.bench.command="python3"',
                        '-c', 'mcp_servers.bench.env_vars=["HC_TERMINAL_ID"]',
                        '-c', 'mcp_servers.bench.args=' + json.dumps([
                            str(self.helper), '--config', str(self.config_path), 'mcp'])]
            if prompt:
                command.append(prompt)
        else:
            if resume:
                command += ['--resume', resume]
            elif session_id:
                # B21: bench picks the Claude session id, so a reboot can reopen the same conversation.
                command += ['--session-id', session_id]
            command += ['--model', model or settings['model'], '--name', display or name]
            if prompt:
                command += ['--', prompt]
        return command

    def spawn(self, role, caller, run=None, dry_run=False, **options):
        node = self._spawn(role, caller, run=run, dry_run=dry_run, **options)
        if dry_run:
            return node
        # Best effort and outside the mailbox lock: the tab may take a moment to appear, and a missing
        # or slow app never fails a launch that already succeeded.
        try:
            title = self.retitle_nodes([node], run or subprocess.run,
                                       polls=int(self.config.get('tab_title_polls', 10)))[0]
        except Exception as error:   # noqa: BLE001 - the session is registered; record and move on
            title = {'address': node['address'], 'status': 'failed', 'error': str(error)}
        with self.locked() as state:
            state['nodes'][node['address']]['tab_title'] = title
            self.commit(state)
        return {**node, 'tab_title': title}

    def _spawn(self, role, caller, run=None, dry_run=False, no_task=False, parent_override=None,
               vendor=None, model=None, cwd=None, task=None, worktree=None, name=None, display=None, resume=None,
               allow_date_mismatch=False, state_file=None):
        if parent_override is not None and (role == 'secretary' or (not no_task and parent_override != caller)):
            raise ValueError('Explicit parent must be the caller; operator inspection requires --no-task')
        checked_spawn_identity(name, display, resume, worktree)
        checked_dates(task, allow_date_mismatch)
        state_file = checked_state_file(state_file)
        run = run or subprocess.run
        chosen = vendor or ('codex' if role.startswith('worker-') else 'claude')
        session_id = None if resume or chosen != 'claude' else str(uuid.uuid4())
        with self.locked() as state:
            parent = self.parent_for(state, role, parent_override if parent_override is not None else caller)
            name = name or 'bench-' + role + '-' + uuid.uuid4().hex[:12]
            command = self.argv(role, parent, vendor=vendor, model=model, cwd=cwd, task=task,
                                no_task=no_task, name=name, display=display, resume=resume, session_id=session_id)
            for prior_path in self.evidence.glob('spawn-*.json'):
                prior = json.loads(prior_path.read_text())
                if (prior.get('launch_attempted', True) and prior.get('status') != 'registered'
                        and prior.get('returncode') in (None, 0)):
                    raise RuntimeError('Previous launch outcome is uncertain; inspect scoped evidence before retry')
            ownership = None
            if worktree:
                if role == 'secretary' or cwd:
                    raise ValueError('--worktree requires a lead or worker and cannot be combined with --cwd')
                ownership = self.worktree_plan(*worktree, parent=parent)
            if dry_run:
                return {'role': role, 'parent': parent, 'invocation_caller': caller,
                        'argv': command, 'worktree_plan': ownership}
            record = self.evidence / ('spawn-' + role + '-' + uuid.uuid4().hex + '.json')
            evidence = {'role': role, 'parent': parent, 'invocation_caller': caller,
                        'created_at': now(), 'argv': command, 'status': 'preparing',
                        'launch_attempted': False,
                        'task_provided': not no_task, 'space_id': self.config['space_id'], 'worktree': ownership}
            atomic_json(record, evidence)
            try:
                if ownership:
                    self.create_worktree(ownership, record)
                    evidence['worktree'] = ownership
                    command = self.argv(role, parent, vendor=vendor, model=model,
                                        cwd=ownership['path'], task=task, no_task=no_task, name=name,
                                        display=display, resume=resume, session_id=session_id)
                evidence.update(status='invoking', argv=command, launch_attempted=True)
                atomic_json(record, evidence)
                result = run(command, capture_output=True, text=True, timeout=60, shell=False)
                evidence.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                if result.returncode:
                    raise RuntimeError('hc run failed; see scoped spawn evidence (created worktree is preserved)')
                response = json.loads(result.stdout)
                address = response.get('address')
                if not isinstance(address, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', address):
                    raise RuntimeError('hc returned no valid terminal address; do not retry blindly')
                if address in state['nodes']:
                    raise RuntimeError('hc returned duplicate terminal address')
                vendor = vendor or ('codex' if role.startswith('worker-') else 'claude')
                node = {'address': address, 'parent': parent, 'role': role, 'name': name,
                        'display': display, 'resumed_session': resume, 'vendor': vendor, 'model': model or self.config['vendors'][vendor]['model'],
                        'cwd': ownership['path'] if ownership else str(Path(cwd or self.config['cwd']).resolve()),
                        'created_at': now(), 'last_activity': now(), 'complete': False,
                        'invocation_caller': caller, 'spawn_evidence': str(record),
                        'task_provided': not no_task, 'space_id': self.config['space_id'], 'worktree': ownership}
                if vendor == 'claude':
                    node['session_id'] = resume or session_id
                if state_file:
                    node['state_file'] = state_file
                state['nodes'][address] = node
                self.commit(state)
                evidence.update(status='registered', address=address)
                atomic_json(record, evidence)
                return node
            except Exception as error:
                evidence.update(status='failed', error=str(error), finished_at=now())
                atomic_json(record, evidence)
                raise

    @staticmethod
    def git(repo, *args, check=True):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                text=True, timeout=30, shell=False)
        if check and result.returncode:
            raise RuntimeError('git ' + args[0] + ' failed: ' + result.stderr.strip())
        return result

    def worktree_plan(self, repo, branch, parent):
        repo = Path(repo).expanduser().resolve()
        if self.git(repo, 'check-ref-format', '--branch', branch, check=False).returncode or branch.startswith('-'):
            raise ValueError('Invalid local branch name')
        if branch in ('main', 'master', 'HEAD'):
            raise ValueError('Worktree requires a new feature branch')
        if self.git(repo, 'show-ref', '--verify', 'refs/heads/' + branch, check=False).returncode == 0:
            for record in sorted(self.evidence.glob('spawn-*.json')):
                receipt = json.loads(record.read_text())
                owned = receipt.get('worktree') or {}
                if (receipt.get('status') == 'failed' and owned.get('repo') == str(repo)
                        and owned.get('branch') == branch and owned.get('worktree_created')):
                    raise ValueError(
                        f"Failed spawn preserved worktree {owned['path']}; evidence: {record}. "
                        'Successful session registration is not confirmed by this failure; '
                        'close requires a registered node. '
                        'Automatic adoption is disabled; inspect evidence and actual terminals '
                        'before operator recovery. No retry or cleanup was performed.')
            raise ValueError('Existing local branch cannot be adopted by workbench')
        root = Path(self.config['worktrees']).resolve()
        path = root / ('worker-' + uuid.uuid4().hex[:12])
        common = self.git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip()
        base_ref, base = self.default_base(repo)
        return {'repo': str(repo), 'path': str(path), 'branch': branch, 'common_dir': common,
                'created_by': parent, 'created_at': now(), 'branch_created': False,
                'worktree_created': False, 'base': base, 'base_ref': base_ref}

    def default_base(self, repo):
        """B22 (11/11): a new worktree starts from origin's default branch after a fetch, never from whatever
        the main checkout has checked out (t56 branched from a meeting branch 188 commits behind)."""
        fetched = self.git(repo, 'fetch', '--no-tags', '--prune', 'origin', check=False)
        if fetched.returncode:
            raise RuntimeError('git fetch origin failed; no worktree was created: ' + fetched.stderr.strip()[-300:])
        head = self.git(repo, 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD', check=False).stdout.strip()
        for ref in ([head] if head else []) + ['refs/remotes/origin/main', 'refs/remotes/origin/master']:
            found = self.git(repo, 'rev-parse', '--verify', '--quiet', ref + '^{commit}', check=False)
            if found.returncode == 0:
                return ref, found.stdout.strip()
        raise RuntimeError("origin has no default branch (origin/HEAD, main or master); no worktree was created")

    def create_worktree(self, ownership, record):
        Path(ownership['path']).parent.mkdir(parents=True, exist_ok=True)
        self.git(ownership['repo'], 'worktree', 'add', '-b', ownership['branch'], ownership['path'], ownership['base'])
        ownership.update(branch_created=True, worktree_created=True)
        # Save ownership before linker/native launch. Failed launches never discard local work.
        receipt = json.loads(record.read_text())
        receipt['worktree'] = ownership
        atomic_json(record, receipt)
        # 11/10: a 30 s limit expired once on a fresh team-repo worktree (B11); the script itself takes ~0.1 s.
        result = subprocess.run(['bash', self.config['link_repo_skills'], ownership['path']],
                                capture_output=True, text=True, timeout=120, shell=False)
        if result.returncode:
            raise RuntimeError('Skill link failed; created worktree is preserved: ' + result.stderr.strip())
        ownership['skills_linked'] = True

    def renamed_branch(self, repo, recorded, head):
        """The current branch name if git's reflog proves it is the recorded branch renamed (git branch -m)."""
        if not head.startswith('refs/heads/'):
            return None
        current = head[len('refs/heads/'):]
        if self.git(repo, 'show-ref', '--verify', '--quiet', 'refs/heads/' + recorded, check=False).returncode == 0:
            return None   # the recorded name exists again: two different branches, adopt neither
        log = self.git(repo, 'log', '-g', '--format=%gs', 'refs/heads/' + current, '--', check=False).stdout
        name = current
        for line in log.splitlines():
            found = re.fullmatch(r'Branch: renamed refs/heads/(.+) to refs/heads/(.+)', line.strip())
            if found and found.group(2) == name:
                name = found.group(1)
                if name == recorded:
                    return current
        return None

    def check_worktree_clean(self, path):
        indexed = self.git(path, 'ls-files', '-v', '-z').stdout.split('\0')
        if any(entry and (entry[0].islower() or entry[0] == 'S') for entry in indexed):
            raise RuntimeError('Index has assume-unchanged or skip-worktree entries; hidden changes may exist')
        status = self.git(path, 'status', '--porcelain=v1', '--untracked-files=all').stdout
        ignored = self.git(path, 'ls-files', '--others', '--ignored', '--exclude-standard', '-z').stdout.split('\0')
        unknown_ignored = [p for p in ignored if p and not regenerable_output(p, root=path)]
        if status or unknown_ignored:
            raise RuntimeError('Worktree has changes or ignored user files')

    def discard(self, caller, worktree_path):
        """Clean the worktree of a spawn that failed before hc ran (no session exists), under close's rules."""
        target = str(Path(worktree_path).expanduser().resolve())
        with self.locked() as state:
            self.identity(state, caller)
            matches = []
            for record in sorted(self.evidence.glob('spawn-*.json')):
                receipt = json.loads(record.read_text())
                if (receipt.get('worktree') or {}).get('path') == target:
                    matches.append((record, receipt))
            if len(matches) != 1:
                raise ValueError('No unique spawn record owns this worktree')
            record, receipt = matches[0]
            if receipt.get('status') == 'discarded':
                return receipt['discard_result']
            wt = receipt['worktree']
            if receipt.get('status') != 'failed' or receipt.get('launch_attempted') is not False:
                raise ValueError('Only a spawn that failed before hc ran can be discarded; a registered session uses close')
            if receipt.get('parent') != caller or wt.get('created_by') != caller or not wt.get('worktree_created'):
                raise ValueError('Only the parent that created this worktree may discard it')
            if any((n.get('worktree') or {}).get('path') == target for n in state['nodes'].values()):
                raise ValueError('A registered session uses this worktree; use close')
            repo, path, branch = wt['repo'], Path(wt['path']), wt['branch']
            result = {'worktree': target, 'branch': branch, 'status': 'blocked',
                      'worktree_removed': False, 'branch_deleted': False, 'reason': ''}
            try:
                if self.git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip() != wt['common_dir']:
                    raise RuntimeError('Repository identity changed')
                if branch in ('main', 'master', 'HEAD') or branch.startswith('-'):
                    raise RuntimeError('Protected or non-local branch')
                if not path.is_dir() or self.git(path, 'symbolic-ref', '--quiet', 'HEAD', check=False).stdout.strip() != 'refs/heads/' + branch:
                    raise RuntimeError('Worktree missing or not on its recorded branch; preserved')
                self.check_worktree_clean(path)
                # Same rule as close: nothing may exist only here. Work done by hand after the failure is
                # removable once pushed, and its branch goes only once merged.
                self.git(repo, 'fetch', '--prune', '--no-tags', 'origin', '+refs/heads/*:refs/remotes/origin/*')
                if self.git(repo, 'rev-list', 'refs/heads/' + branch, '--not', '--remotes=origin').stdout.strip():
                    raise RuntimeError('Branch has unpushed commits; preserved')
                merged = self.git(repo, 'merge-base', '--is-ancestor', 'refs/heads/' + branch, 'refs/remotes/origin/main', check=False)
                self.git(repo, 'worktree', 'remove', str(path))
                result['worktree_removed'] = True
                if wt.get('branch_created') is not True or not self.cleanup_policy_enabled():
                    reason = 'Branch retained: ownership or cleanup policy not established'
                elif merged.returncode:
                    reason = 'Branch retained: not merged into origin/main by ancestry; verify PR state for squash merges'
                else:
                    deleted = self.git(repo, 'branch', '-d', branch, check=False)
                    result['branch_deleted'] = deleted.returncode == 0
                    reason = 'Merged local branch deleted' if deleted.returncode == 0 else 'Branch retained: git branch -d refused: ' + deleted.stderr.strip()
                result.update(status='discarded', reason=reason)
                receipt.update(status='discarded', discard_result=result, discarded_at=now(), discarded_by=caller)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                result['reason'] = str(error)
                receipt.setdefault('discard_attempts', []).append({'at': now(), 'by': caller, 'reason': str(error)})
            atomic_json(record, receipt)
            return result

    def cleanup_policy_enabled(self):
        try:
            import yaml
            policy = yaml.safe_load(Path(self.config['policy']).read_text())
            rule = next(r for r in policy['autonomous'] if r['id'] == 'own-merged-branch-cleanup')
            return rule['command'] == 'git branch -d *' and set(rule['conditions']) == {
                'branch_created_by_workbench_session', 'merged_into_origin_main',
                'no_changes_or_unpushed_commits', 'local_branch_only'}
        except (OSError, ValueError, TypeError, KeyError, StopIteration, ImportError):
            return False

    def close(self, caller, target, run=None):
        run = run or subprocess.run
        with self.locked() as state:
            self.identity(state, caller)
            node = self.identity(state, target)
            if node['parent'] != caller:
                raise ValueError('Only the registered parent may close its child')
            if node.get('closed_at'):
                return node['close_result']
            if any(n['parent'] == target and not n.get('closed_at') for n in state['nodes'].values()):
                raise ValueError('Close active children first')
            result = {'target': target, 'status': 'blocked', 'session_stopped': False,
                      'worktree_removed': False, 'branch_deleted': False, 'reason': ''}
            try:
                if not node.get('session_stopped_at'):
                    info = run([self.config['hc'], 'get', target], capture_output=True, text=True, timeout=15, shell=False)
                    if info.returncode:
                        raise RuntimeError('Cannot verify child terminal; no cleanup performed')
                    terminal = json.loads(info.stdout)
                    if terminal.get('state') == 'live':
                        stopped = run([self.config['hc'], 'kill', target], capture_output=True, text=True, timeout=15, shell=False)
                        if stopped.returncode:
                            raise RuntimeError('Child terminal did not stop; no cleanup performed')
                    elif terminal.get('state') != 'finished':
                        raise RuntimeError('Unknown terminal state; no cleanup performed')
                    node['session_stopped_at'] = now()
                    self.commit(state)
                result['session_stopped'] = True
                wt = node.get('worktree')
                reason = 'No worktree attached'
                if wt:
                    repo, path, branch = wt['repo'], Path(wt['path']), wt['branch']
                    if not wt.get('worktree_created') or wt.get('created_by') != caller:
                        raise RuntimeError('Worktree ownership is not established')
                    if self.git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip() != wt['common_dir']:
                        raise RuntimeError('Repository identity changed')
                    if branch in ('main', 'master', 'HEAD') or branch.startswith('-'):
                        raise RuntimeError('Protected or non-local branch')
                    if not node.get('worktree_removed_at'):
                        if not path.is_dir():
                            raise RuntimeError('Worktree missing; preserve branch')
                        head = self.git(path, 'symbolic-ref', '--quiet', 'HEAD', check=False).stdout.strip()
                        if head != 'refs/heads/' + branch:
                            renamed = self.renamed_branch(repo, branch, head)
                            if not renamed:
                                raise RuntimeError(
                                    f"Worktree is on {head or 'a detached HEAD'}, not the recorded branch {branch}; preserved. "
                                    'A branch renamed with git branch -m is followed through its reflog; '
                                    'a branch made with switch -c is not adopted.')
                            wt.setdefault('renames', []).append({'from': branch, 'to': renamed, 'seen_at': now()})
                            wt['branch'] = branch = renamed
                            self.commit(state)
                        self.check_worktree_clean(path)
                    # Fresh origin/main is required. Fetch failure is a preservation decision.
                    self.git(repo, 'fetch', '--prune', '--no-tags', 'origin', '+refs/heads/*:refs/remotes/origin/*')
                    if self.git(repo, 'rev-list', branch, '--not', '--remotes=origin').stdout.strip():
                        raise RuntimeError('Branch has unpushed commits')
                    merged = self.git(repo, 'merge-base', '--is-ancestor', 'refs/heads/' + branch,
                                      'refs/remotes/origin/main', check=False)
                    if merged.returncode not in (0, 1):
                        raise RuntimeError('Cannot verify origin/main ancestry')
                    owns_branch = wt.get('branch_created') is True and wt.get('created_by') == caller
                    policy_ok = self.cleanup_policy_enabled()
                    if not node.get('worktree_removed_at'):
                        self.git(repo, 'worktree', 'remove', str(path))
                        node['worktree_removed_at'] = now()
                        self.commit(state)
                    result['worktree_removed'] = True
                    if not owns_branch:
                        reason = 'Branch retained: ownership not established'
                    elif not policy_ok:
                        reason = 'Branch retained: cleanup policy absent or changed'
                    elif merged.returncode:
                        reason = 'Branch retained: not merged into origin/main by ancestry; verify PR state for squash merges'
                    else:
                        deleted = self.git(repo, 'branch', '-d', branch, check=False)
                        result['branch_deleted'] = deleted.returncode == 0
                        reason = 'Merged local branch deleted' if deleted.returncode == 0 else 'Branch retained: git branch -d refused: ' + deleted.stderr.strip()
                    if wt.get('renames'):
                        reason += f" (branch {branch} renamed from {wt['renames'][0]['from']}, proven by git reflog)"
                result.update(status='closed', reason=reason)
                node['closed_at'] = now()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                result['reason'] = str(error)
            node['close_result'] = result
            node['last_activity'] = now()
            # Keep lifecycle evidence and parent notification in the same authoritative commit.
            report_id = 'close-' + target + '-' + hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
            state['reports'].setdefault(report_id, {
                'from': target, 'to': caller, 'report_id': report_id, 'kind': 'close',
                'summary': json.dumps(result, ensure_ascii=False), 'complete': result['status'] == 'closed',
                'created_at': now(), 'acked_at': None, 'ack_kind': None})
            self.commit(state)
            return result

    def terminal_ended(self, address, run):
        """True when hc says the terminal finished or no longer exists; raises when it is live or unknown."""
        info = run([self.config['hc'], 'get', address], capture_output=True, text=True, timeout=15, shell=False)
        try:
            data = json.loads(info.stdout or '{}')
        except json.JSONDecodeError:
            data = {}
        if info.returncode:
            if (data.get('error') or {}).get('kind') == 'not_found':
                return 'not_found'
            raise RuntimeError('Cannot verify the old terminal with hc get; nothing changed')
        if data.get('state') == 'live':
            raise ValueError(f'{address} is still live; takeover refuses so two sessions never share one record')
        if data.get('state') != 'finished':
            raise RuntimeError('Unknown terminal state; nothing changed')
        return 'finished'

    def backup_state(self, label):
        folder = self.mailbox / 'backups'
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        saved = {}
        for name in ('state.json', 'view.json'):
            source = self.mailbox / name
            if source.exists():
                target = folder / f'{stamp}-{label}-{name}'
                shutil.copy2(source, target)
                saved[name] = str(target)
        restore = ' && '.join(f"cp '{path}' '{self.mailbox / name}'" for name, path in saved.items())
        return {'files': saved, 'restore_command': restore}

    def takeover(self, caller, old, resume=None, model=None, fresh=False, task=None, display=None,
                 run=None, dry_run=False, recovery=None):
        """B1 (11/11): reopen an ended session in a new terminal that inherits its place in the tree.

        The new terminal's HC_TERMINAL_ID is the address hc gives it. Its parent, children, worktree
        ownership and unread reports move from the old address; the old record closes as 'replaced'.
        """
        run = run or subprocess.run
        checked_spawn_identity(None, display, resume, None)
        with self.locked() as state:
            node = state['nodes'].get(old)
            if not node:
                raise ValueError('No registered session at that address')
            if node.get('closed_at'):
                raise ValueError('That session is already closed' + (f" (replaced by {node['replaced_by']})" if node.get('replaced_by') else ''))
            parent = node['parent']
            if parent is not None and recovery is not None:
                # B21 plan A (운영자 11/11 21:37): only inside recover, only when the whole tree is down, and only
                # after this child's parent was reopened in the same recovery. Anything else is refused.
                if not recovery.get('all_down'):
                    raise ValueError('Recovery may reopen a child only when the whole tree is down; a running parent takes over its own children')
                if parent not in set(recovery.get('reopened') or ()):
                    raise ValueError('Recovery reopens a child only after its parent was reopened in the same recovery')
                if (state['nodes'].get(parent) or {}).get('closed_at'):
                    raise ValueError('The parent record is closed')
            elif parent is not None:
                caller_node = self.identity(state, caller)
                if caller != parent or caller_node.get('closed_at'):
                    raise ValueError('Only the registered parent may take over its child (take over the parent first)')
            vendor = node.get('vendor', 'claude')
            notes = []
            if vendor == 'codex':
                if resume:
                    raise ValueError('Codex conversations cannot be reopened; use --fresh with --task to start a new conversation')
                if not fresh or not task:
                    raise ValueError('Codex conversations cannot be reopened. Use --fresh --task "<what to read first>" to start a new one in the same place')
                notes.append('Codex: started a new conversation; the old conversation is not continued')
            else:
                resume = resume or self.session_for(node)
                if fresh:
                    resume = None
                    notes.append('Claude: --fresh starts a new conversation')
                elif not resume:
                    raise ValueError('Give --resume <Claude session id> (the bench record does not know it), or --fresh')
            ended = self.terminal_ended(old, run)
            model = model or node.get('model')
            display = display or node.get('display')
            name = 'bench-' + node['role'] + '-' + uuid.uuid4().hex[:12]
            message = (f'[작업대 takeover] 이 세션은 끝난 터미널 {old}을(를) 이어받았다. 새 주소는 이 터미널의 HC_TERMINAL_ID다(덮어쓰지 않는다). '
                       '부모·자식·워크트리·안 읽은 보고는 bench가 옮겼다. inbox부터 확인하고 하던 일을 이어 간다.')
            prompt_task = message + ('\n\n' + task if task else '')
            command = self.argv(node['role'], parent, vendor=vendor, model=model, cwd=node['cwd'],
                                task=None if resume else prompt_task, no_task=bool(resume), name=name,
                                display=display, resume=resume)
            if resume:
                command += ['--', prompt_task]
            if dry_run:
                return {'old': old, 'old_terminal': ended, 'parent': parent, 'argv': command, 'notes': notes}
            backup = self.backup_state('takeover-' + old)
            record = self.evidence / ('takeover-' + old + '-' + uuid.uuid4().hex + '.json')
            self.evidence.mkdir(parents=True, exist_ok=True)
            evidence = {'kind': 'takeover', 'old': old, 'parent': parent, 'invocation_caller': caller,
                        'created_at': now(), 'argv': command, 'status': 'invoking', 'backup': backup}
            atomic_json(record, evidence)
            try:
                result = run(command, capture_output=True, text=True, timeout=60, shell=False)
                evidence.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                if result.returncode:
                    raise RuntimeError('hc run failed; nothing in the mailbox changed')
                address = json.loads(result.stdout).get('address')
                if not isinstance(address, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', address):
                    raise RuntimeError('hc returned no valid terminal address; the mailbox is unchanged, inspect the new terminal')
                if address in state['nodes']:
                    raise RuntimeError('hc returned an address already in the mailbox')
                stamp = now()
                new = {**node, 'address': address, 'name': name, 'display': display, 'model': model,
                       'resumed_session': resume, 'created_at': stamp, 'last_activity': stamp, 'complete': False,
                       'invocation_caller': caller, 'spawn_evidence': str(record), 'replaces': old,
                       'tab_title': None}
                if vendor == 'claude':
                    new['session_id'] = resume
                if recovery is not None:
                    new.update(recovered_by=caller, recovery_id=recovery.get('id'))
                for key in ('session_stopped_at', 'close_result', 'closed_at', 'replaced_by'):
                    new.pop(key, None)
                moved = {'children': [], 'worktrees': [], 'reports': []}
                for other in state['nodes'].values():
                    if other['parent'] == old and not other.get('closed_at'):
                        other['parent'] = address
                        moved['children'].append(other['address'])
                    wt = other.get('worktree') or {}
                    if wt.get('created_by') == old:
                        wt['created_by'] = address
                        wt.setdefault('ownership_moves', []).append({'from': old, 'to': address, 'at': stamp})
                        moved['worktrees'].append(wt.get('path'))
                if (new.get('worktree') or {}).get('path') and new['worktree']['path'] not in moved['worktrees']:
                    moved['worktrees'].append(new['worktree']['path'] + ' (its own)')
                for r in state['reports'].values():
                    if r['to'] == old and r['acked_at'] is None:
                        r.setdefault('original_to', old)
                        r['to'] = address
                        moved['reports'].append(r['report_id'])
                state['nodes'][address] = new
                node.update(closed_at=stamp, replaced_by=address, session_stopped_at=node.get('session_stopped_at') or stamp,
                            close_result={'target': old, 'status': 'replaced', 'by': address, 'old_terminal': ended,
                                          'reason': 'Taken over by ' + address})
                outcome = {'old': old, 'new': address, 'parent': parent, 'role': node['role'], 'vendor': vendor,
                           'model': model, 'resumed_session': resume, 'old_terminal': ended, 'moved': moved,
                           'notes': notes, 'backup': backup}
                if parent is not None:
                    rid = 'takeover-' + old + '-' + address
                    state['reports'][rid] = {'from': address, 'to': parent, 'report_id': rid, 'kind': 'takeover',
                                             'summary': json.dumps(outcome, ensure_ascii=False), 'complete': False,
                                             'created_at': stamp, 'acked_at': None, 'ack_kind': None}
                self.commit(state)
                evidence.update(status='registered', address=address, outcome=outcome)
                atomic_json(record, evidence)
            except Exception as error:
                evidence.update(status='failed', error=str(error), finished_at=now())
                atomic_json(record, evidence)
                raise RuntimeError(f"{error}. To restore the mailbox as it was before this takeover: {backup['restore_command']}") from error
        try:
            outcome['tab_title'] = self.retitle_nodes([state['nodes'][address]], run,
                                                      polls=int(self.config.get('tab_title_polls', 10)))[0]
        except Exception as error:   # noqa: BLE001 - the takeover is committed
            outcome['tab_title'] = {'status': 'failed', 'error': str(error)}
        outcome['if_wrong'] = 'Restore the mailbox with: ' + backup['restore_command']
        return outcome

    # ---- B21: reopen everything after a reboot -------------------------------------------------

    def hc_get(self, address, run):
        info = run([self.config['hc'], 'get', address], capture_output=True, text=True, timeout=15, shell=False)
        try:
            data = json.loads(info.stdout or '{}')
        except json.JSONDecodeError:
            data = {}
        if info.returncode:
            if (data.get('error') or {}).get('kind') == 'not_found':
                return None
            raise RuntimeError(f'hc get {address} failed; is herdr-core running?')
        return data

    def note_alive(self, terminals):
        """Remember which registered sessions had a running agent, so a reboot that loses every terminal
        reopens only those (a session already ended on purpose, like t28, stays ended)."""
        alive = sorted(t['address'] for t in terminals
                       if t.get('state') == 'live' and t.get('agent') and t.get('agent') not in SHELLS)
        try:
            with self.locked() as state:
                registered = [a for a in alive if a in state['nodes'] and not state['nodes'][a].get('closed_at')]
            atomic_json(self.mailbox / 'last-alive.json', {'observed_at': now(), 'alive': registered})
        except (OSError, ValueError):
            pass

    def note_alive_from_hc(self, run=None):
        run = run or subprocess.run
        try:
            result = run([self.config['hc'], 'ls', '--json'], capture_output=True, text=True, timeout=5, shell=False)
            if result.returncode == 0:
                self.note_alive([t for t in json.loads(result.stdout or '{}').get('terminals', []) if isinstance(t, dict)])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    def own_or_child(self, state, caller, target):
        self.identity(state, caller)
        node = self.identity(state, target)
        if target != caller and node['parent'] != caller:
            raise ValueError('Only the session itself or its registered parent may change this')
        return node

    def set_state_file(self, caller, path, target=None):
        path = checked_state_file(path)
        with self.locked() as state:
            node = self.own_or_child(state, caller, target or caller)
            node['state_file'] = path
            self.commit(state)
            return {'address': node['address'], 'state_file': path}

    def park(self, caller, target, off=False, reason=None):
        """Mark a session as stopped on purpose: recover never reopens it."""
        with self.locked() as state:
            node = self.own_or_child(state, caller, target)
            if off:
                node.pop('parked_at', None)
                node.pop('parked_reason', None)
            else:
                node.update(parked_at=now(), parked_by=caller, parked_reason=(reason or '')[:500])
            self.commit(state)
            return {'address': target, 'parked': not off}

    def session_for(self, node):
        """The conversation to reopen: recorded id, or for older Claude sessions the unique titled one."""
        if node.get('vendor') == 'codex':
            return None
        return (node.get('resumed_session') or node.get('session_id')
                or find_claude_session(node['cwd'], node.get('display') or node.get('name')))

    def relaunch_command(self, node):
        """The program a session's own terminal runs to come back (what spawn ran after `hc run --`)."""
        message = ('[작업대 recover] 재부팅으로 끝났던 이 세션을 같은 터미널 주소에서 다시 열었다. '
                   'HC_TERMINAL_ID는 그대로다. inbox부터 확인하고 하던 일을 이어 간다.')
        if node.get('vendor') == 'codex':
            if not node.get('state_file'):
                raise ValueError('Codex session has no state_file; record one with bench state-file first')
            task = (message + ' Codex는 대화를 잇지 못해 새 대화로 시작한다. 먼저 상태 파일을 처음부터 끝까지 읽어라: '
                    + node['state_file'] + ' 이 파일이 지금 상태의 정본이다. 읽은 뒤 이어 갈 일을 report로 한 줄 보낸다.')
            command = self.argv(node['role'], node['parent'], vendor='codex', model=node.get('model'),
                                cwd=node['cwd'], task=task, name=node.get('name'), display=node.get('display'))
        else:
            resume = self.session_for(node)
            if not resume:
                raise ValueError('No Claude session id is known for this session; give it with takeover --resume')
            command = self.argv(node['role'], node['parent'], vendor='claude', model=node.get('model'),
                                cwd=node['cwd'], no_task=True, name=node.get('name'),
                                display=node.get('display'), resume=resume) + ['--', message]
        return command[command.index('--') + 1:]

    def relaunch(self, caller, exec_fn=None):
        """Run inside a revived shell: become this session again, by its own HC_TERMINAL_ID."""
        with self.locked() as state:
            node = self.identity(state, caller)
            if node.get('closed_at') or node.get('parked_at'):
                raise ValueError('This session is closed or parked; it is not reopened')
            inner = self.relaunch_command(node)
            node.setdefault('relaunches', []).append(now())
            node['last_activity'] = now()
            self.commit(state)
        (exec_fn or os.execv)(inner[0], inner)

    def recover_plan(self, run):
        state = self.inspect()
        nodes = {n['address']: n for n in state['nodes'] if not n.get('closed_at')}
        try:
            alive = set(json.loads((self.mailbox / 'last-alive.json').read_text()).get('alive', []))
        except (OSError, ValueError):
            alive = None
        order, seen = [], set()
        def walk(parent):
            for n in sorted((n for n in nodes.values() if n['parent'] == parent), key=lambda n: n.get('created_at') or ''):
                if n['address'] not in seen:
                    seen.add(n['address']); order.append(n); walk(n['address'])
        walk(None)
        order += [n for n in nodes.values() if n['address'] not in seen]   # parent already closed
        plan = []
        for n in order:
            info = self.hc_get(n['address'], run)
            kind = terminal_kind(info)
            row = {'address': n['address'], 'display': n.get('display') or n.get('name'), 'role': n['role'],
                   'parent': n['parent'], 'vendor': n.get('vendor'), 'terminal': kind}
            labels = (info or {}).get('labels') or {}
            if kind in ('shell', 'running') and (labels.get('herdr.space') != self.config['space_id']
                                                 or labels.get('bench.role') != n['role']
                                                 or (info.get('name') and n.get('name') and info.get('name') != n.get('name'))):
                row.update(action='stop', why='the terminal at this address does not match the record (space, role or name)')
            elif n.get('parked_at'):
                row.update(action='skip', why='parked on purpose')
            elif kind == 'running':
                row.update(action='skip', why='agent already running')
            elif kind == 'shell':
                try:
                    self.relaunch_command(n)
                    row.update(action='relaunch', why='revived shell at the same address',
                               send=f"exec python3 {self.helper} --config {self.config_path} relaunch")
                except ValueError as error:
                    row.update(action='blocked', why=str(error))
            elif kind in ('finished', 'not_found'):
                if alive is not None and n['address'] not in alive:
                    row.update(action='skip', why='already ended before the outage (not in last-alive.json)')
                elif n['parent'] is None:
                    row.update(action='takeover', why='terminal is gone; the root reopens with takeover')
                else:
                    try:
                        self.relaunch_command(n)
                        row.update(action='recover-child', why='terminal is gone; reopened after its parent (plan A)')
                    except ValueError as error:
                        row.update(action='blocked', why=str(error))
            else:
                row.update(action='stop', why='unknown terminal state')
            plan.append(row)
        # Plan A needs the whole tree down: with any agent still running, its parent takes over its children.
        if any(r['terminal'] == 'running' for r in plan):
            for r in plan:
                if r.get('action') == 'recover-child':
                    r.update(action='decide', why='terminal is gone but another agent in the tree is running; its registered parent takes it over (bench takeover)')
        return plan

    def recover(self, caller, run=None, dry_run=False, wait_seconds=40, sleep=time.sleep):
        """One command after a reboot. Prints the plan first; on the first failure it stops and says what is
        done and what is left. Never answers trust or approval prompts and never sets HC_TERMINAL_ID."""
        run = run or subprocess.run
        plan = self.recover_plan(run)
        if dry_run:
            return {'dry_run': True, 'plan': plan}
        if any(r['action'] == 'stop' for r in plan):
            return {'status': 'refused', 'plan': plan, 'reason': 'a terminal does not match its record; nothing was changed'}
        backup = self.backup_state('recover')
        recovery = {'id': 'recovery-' + uuid.uuid4().hex[:12], 'reopened': set(),
                    'all_down': not any(r['terminal'] == 'running' for r in plan)}
        done, result = [], {'status': 'done', 'plan': plan, 'backup': backup, 'recovery_id': recovery['id'],
                             'if_wrong': 'Restore the mailbox with: ' + backup['restore_command']}
        acting = ('relaunch', 'takeover', 'recover-child')
        skipped = []
        for row in plan:
            if row['action'] not in acting:
                continue
            try:
                if row['action'] == 'recover-child':
                    current = self.inspect_node(row['address'])
                    if current['parent'] not in recovery['reopened']:
                        skipped.append({'address': row['address'], 'action': 'blocked',
                                        'why': 'its parent was not reopened in this recovery'})
                        continue
                    codex = current.get('vendor') == 'codex'
                    task = None
                    if codex:
                        task = ('Herdr 재부팅으로 끝났던 세션을 recover로 새 대화로 다시 열었다. 먼저 상태 파일을 처음부터 끝까지 읽어라: '
                                + current['state_file'] + ' 이 파일이 지금 상태의 정본이다. 읽은 뒤 이어 갈 일을 report로 한 줄 보낸다.')
                    out = self.takeover(caller, row['address'], fresh=codex, task=task, run=run, recovery=recovery)
                    recovery['reopened'].add(out['new'])
                    done.append({'address': row['address'], 'action': 'recover-child', 'new': out['new']})
                elif row['action'] == 'relaunch':
                    with self.locked() as state:
                        state['nodes'][row['address']].update(recovered_by=caller, recovery_id=recovery['id'])
                        self.commit(state)
                    sent = run([self.config['hc'], 'send', row['address'], row['send']],
                               capture_output=True, text=True, timeout=30, shell=False)
                    if sent.returncode:
                        raise RuntimeError('hc send failed: ' + (sent.stderr or '').strip())
                    for _ in range(max(1, int(wait_seconds))):
                        if terminal_kind(self.hc_get(row['address'], run)) == 'running':
                            break
                        sleep(1)
                    else:
                        raise RuntimeError('the agent did not start within %d seconds' % wait_seconds)
                    recovery['reopened'].add(row['address'])
                    done.append({'address': row['address'], 'action': 'relaunch'})
                else:
                    out = self.takeover(caller, row['address'], run=run, recovery=recovery)
                    recovery['reopened'].add(out['new'])
                    done.append({'address': row['address'], 'action': 'takeover', 'new': out['new']})
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                left = [r['address'] for r in plan if r['action'] in acting
                        and r['address'] not in {d['address'] for d in done + skipped} and r['address'] != row['address']]
                result.update(status='stopped', failed={'address': row['address'], 'error': str(error)}, left=left)
                break
        result['done'] = done
        result['not_reopened'] = skipped + [{k: r[k] for k in ('address', 'action', 'why')} for r in plan
                                            if r['action'] not in acting]
        return result

    def inspect_node(self, address):
        with self.locked() as state:
            return dict(state['nodes'][address])

    def report(self, caller, summary, complete=False, report_id=None, notify=None, allow_late_time=False):
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 16000:
            raise ValueError('summary must contain 1..16000 characters')
        if not isinstance(complete, bool):
            raise ValueError('complete must be boolean')
        with self.locked() as state:
            node = self.identity(state, caller)
            target = node['parent']
            if target is None:
                raise ValueError('Root secretary has no parent inbox')
            payload = {'from': caller, 'to': target, 'summary': summary, 'complete': complete}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            report_id = report_id or ('r-' + digest[:24])
            if not isinstance(report_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', report_id):
                raise ValueError('Invalid report ID')
            existing = state['reports'].get(report_id)
            if existing:
                if existing['payload_sha256'] != digest:
                    raise ValueError('Report ID already used for a different payload')
                return existing
            created = now()
            checked_header_time(summary, created, allow_late_time)
            report = {**payload, 'report_id': report_id, 'payload_sha256': digest,
                      'created_at': created, 'sent_kst': sent_kst(created), 'acked_at': None, 'ack_kind': None}
            state['reports'][report_id] = report
            node['last_activity'] = report['created_at']
            node['complete'] = node['complete'] or complete
            state['nodes'][target]['last_activity'] = report['created_at']
            self.commit(state)
        # Notification callbacks can never run before durable state and projection writes.
        # Production uses the atomic projection, polled by the native tree mod; no hc send.
        if notify:
            notify(report)
        return report

    def send(self, caller, target, text, run=None, if_status=None, allow_date_mismatch=False):
        """Type a follow-up instruction into the caller's own live child. Never forces past a dialog."""
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ValueError('text must contain 1..16000 characters')
        if if_status not in (None, 'idle', 'working'):
            raise ValueError('--if takes idle or working')
        checked_dates(text, allow_date_mismatch)
        run = run or subprocess.run
        with self.locked() as state:
            self.identity(state, caller)
            node = self.identity(state, target)
            if node['parent'] != caller:
                raise ValueError('Only the registered parent may send follow-up instructions to its child')
            if node.get('closed_at'):
                raise ValueError('Child is closed; spawn a new session instead')
            directive_id = 'd-' + uuid.uuid4().hex[:24]
            record = {'directive_id': directive_id, 'from': caller, 'to': target, 'text': text,
                      'text_sha256': hashlib.sha256(text.encode()).hexdigest(), 'if_status': if_status,
                      'created_at': now(), 'status': 'sending'}
            state.setdefault('directives', {})[directive_id] = record
            self.commit(state)
        # hc waits for a person to stop typing; never hold the mailbox lock while it does.
        command = [self.config['hc'], 'send', '--json'] + (['--if', if_status] if if_status else []) + ['--', target, text]
        try:
            result = run(command, capture_output=True, text=True, timeout=120, shell=False)
            outcome = {'status': 'sent' if result.returncode == 0 else 'failed', 'returncode': result.returncode,
                       'stdout': (result.stdout or '')[-2000:], 'stderr': (result.stderr or '')[-2000:]}
        except subprocess.TimeoutExpired:
            outcome = {'status': 'uncertain', 'error': 'hc send timed out after 120 seconds'}
        with self.locked() as state:
            record = state['directives'][directive_id]
            record.update(outcome, finished_at=now())
            if outcome['status'] == 'sent':
                state['nodes'][caller]['last_activity'] = record['finished_at']
            self.commit(state)
        if outcome['status'] != 'sent':
            raise RuntimeError(f"hc send did not confirm delivery ({outcome['status']}); record {directive_id}. "
                               f'Do not resend blindly: read the child screen with hc read {target} first.')
        return record

    def inbox(self, caller, include_archived=False):
        with self.locked() as state:
            self.identity(state, caller)
            return [r for r in state['reports'].values() if r['to'] == caller
                    and (include_archived or r['acked_at'] is None)]

    def ack(self, caller, report_id, kind='received'):
        if kind not in ('received', 'accepted'):
            raise ValueError('Ack kind must be received or accepted')
        with self.locked() as state:
            self.identity(state, caller)
            report = state['reports'].get(report_id)
            if report is None or report['to'] != caller:
                raise ValueError('Only registered recipient can acknowledge this report')
            if report['acked_at'] is None:
                report['acked_at'] = now()
                report['ack_kind'] = kind
                state['nodes'][caller]['last_activity'] = now()
                self.commit(state)
            return report

    def inspect(self):
        with self.locked() as state:
            view = self.projection(state)
            atomic_json(self.mailbox / 'view.json', view)
            return view

    def ls(self, run=None, include_closed=False):
        """Registered nodes in tree order, joined with hc's live view. Missing hc fields stay None."""
        run = run or subprocess.run
        live, live_error = {}, None
        try:
            result = run([self.config['hc'], 'ls', '--json'], capture_output=True, text=True, timeout=15, shell=False)
            if result.returncode:
                live_error = (result.stderr or 'hc ls failed').strip()
            else:
                live = {t.get('address'): t for t in json.loads(result.stdout or '{}').get('terminals', [])
                        if isinstance(t, dict)}
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            live_error = str(error)
        if not live_error:
            self.note_alive(list(live.values()))
        view = self.inspect()
        repos = worktree_repos(view['nodes'])
        wroot = self.worktrees_root()
        nodes = {n['address']: n for n in view['nodes'] if include_closed or not n.get('closed_at')}
        children = {}
        for node in nodes.values():
            children.setdefault(node['parent'] if node['parent'] in nodes else None, []).append(node)
        rows = []

        def walk(parent, depth):
            for node in sorted(children.get(parent, []), key=lambda n: n.get('created_at') or ''):
                terminal = live.get(node['address'])
                status = terminal.get('status') if terminal else None
                if isinstance(status, dict):
                    status = status.get('state')
                rows.append({
                    'address': node['address'], 'depth': depth, 'role': node['role'],
                    'display': node.get('display'), 'name': node.get('name'),
                    'vendor': node.get('vendor'), 'model': node.get('model'),
                    'state': 'unknown' if live_error else (terminal.get('state') if terminal else 'not listed'),
                    'status': status, 'where': (terminal or {}).get('where') or ((terminal or {}).get('labels') or {}).get('where'),
                    'unread_count': node.get('unread_count', 0), 'closed': bool(node.get('closed_at')),
                    'branch': (node.get('worktree') or {}).get('branch'), 'hc_error': live_error,
                    'folder': folder_name(node.get('cwd'), repos, wroot)})
                walk(node['address'], depth + 1)
        walk(None, 0)
        return rows

    def rename(self, caller, target, display, run=None):
        """Change the shown name of yourself or your direct child: bench record and hc label together."""
        if not isinstance(display, str) or not 1 <= len(display) <= 32 or any(ord(c) < 32 or ord(c) == 127 for c in display):
            raise ValueError('Display name must be 1-32 printable characters')
        run = run or subprocess.run
        with self.locked() as state:
            self.identity(state, caller)
            node = self.identity(state, target)
            if target != caller and node['parent'] != caller:
                raise ValueError('Only the session itself or its registered parent may rename it')
            if node.get('closed_at'):
                raise ValueError('Closed sessions keep their recorded name')
            # Label first: if hc refuses, the record stays as it was.
            result = run([self.config['hc'], 'label', target, 'bench.display=' + display],
                         capture_output=True, text=True, timeout=15, shell=False)
            if result.returncode:
                raise RuntimeError('hc label failed; record unchanged: ' + (result.stderr or '').strip())
            old = node.get('display')
            node['display'] = display
            node.setdefault('display_history', []).append({'from': old, 'to': display, 'by': caller, 'at': now()})
            self.commit(state)
            renamed = dict(node)
        steps = ['Claude 세션 이름은 그 세션 안에서 /rename ' + display + ' 로 바꾼다']
        tab = self.retitle_nodes([renamed], run)[0]
        if tab['status'] == 'named_by_person':
            steps.append('Herdr 탭 이름(hc의 where)은 사람이 붙인 이름(' + tab['was'] + ')이라 두었다. 바꾸려면 '
                         + tab['command'])
        return {'address': target, 'display': display, 'previous': old, 'label_set': True,
                'tab_title': tab, 'manual_steps': steps}

    def herdr_tabs(self, run):
        """Terminal address -> the Herdr tab it heads, or None when tab naming is off or the app does not answer."""
        app = self.config.get('herdr_app')
        if not app:
            return None
        try:
            result = run([app, 'ls'], capture_output=True, text=True, timeout=15, shell=False)
            spaces = json.loads(result.stdout or '{}').get('spaces') if result.returncode == 0 else None
        except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
            return None
        if not isinstance(spaces, list):
            return None
        tabs = {}
        for space in spaces:
            for tab in (space.get('tabs') or []) if isinstance(space, dict) else []:
                terminals = [t.get('terminal') for t in tab.get('terminals') or [] if isinstance(t, dict)]
                if terminals:
                    tabs.setdefault(terminals[0], tab)   # a tab is titled after its first terminal only
        return tabs

    @staticmethod
    def title_for(node):
        return node.get('display') or node.get('name')

    def retitle_nodes(self, nodes, run, polls=1):
        """Name each session's Herdr tab after its display name. Only auto-numbered tabs, or tabs still
        showing one of the session's earlier names, are renamed; a name a person chose is reported instead."""
        tabs = None
        for attempt in range(max(1, polls)):
            tabs = self.herdr_tabs(run)
            if tabs is None or all(n['address'] in tabs for n in nodes):
                break
            if attempt + 1 < polls:
                time.sleep(TAB_POLL_SECONDS)
        results = []
        for node in nodes:
            title = self.title_for(node)
            result = {'address': node['address'], 'title': title}
            tab = (tabs or {}).get(node['address'])
            if tabs is None:
                result['status'] = 'app_unavailable' if self.config.get('herdr_app') else 'disabled'
            elif not tab:
                result['status'] = 'no_tab'
            else:
                current = tab.get('name') or ''
                earlier = {h.get('from') for h in node.get('display_history', [])} | {node.get('name')}
                change = json.dumps({'id': tab.get('id'), 'name': title}, ensure_ascii=False)
                result.update(tab=tab.get('id'), was=current)
                if current == title:
                    result['status'] = 'already'
                elif not (AUTO_TAB_NAME.fullmatch(current) or current in earlier):
                    result.update(status='named_by_person', command="herdr-app do tab.rename '" + change + "'")
                else:
                    try:
                        done = run([self.config['herdr_app'], 'do', 'tab.rename', change],
                                   capture_output=True, text=True, timeout=15, shell=False)
                        result['status'] = 'renamed' if done.returncode == 0 else 'failed'
                    except (OSError, subprocess.SubprocessError) as error:
                        result.update(status='failed', error=str(error))
            results.append(result)
        return results

    def retitle(self, caller, run=None):
        """Apply tab titles to every open session (for sessions opened before tab naming existed)."""
        with self.locked() as state:
            self.identity(state, caller)
            nodes = [dict(n) for n in state['nodes'].values() if not n.get('closed_at')]
        return self.retitle_nodes(nodes, run or subprocess.run)

    def wait(self, caller, timeout=120, poll_ms=500, release_file=None, sender=None):
        # Up to an hour: a Claude parent runs a long wait in the background and is woken when it exits.
        if not 0 <= timeout <= WAIT_MAX_SECONDS or not 20 <= poll_ms <= 5000:
            raise ValueError(f'wait limits: timeout 0..{WAIT_MAX_SECONDS} seconds, poll-ms 20..5000')
        gate = None
        if release_file:
            gate = Path(release_file).resolve()
            if self.mailbox.resolve() not in gate.parents:
                raise ValueError('Release file must be inside this workbench mailbox')
        end = time.monotonic() + timeout
        while True:
            pending = self.inbox(caller)
            # --from narrows what wakes the caller; the pending count and ids still cover every sender.
            reports = [r for r in pending if sender is None or r['from'] == sender]
            gate_released = gate is None or gate.is_file()
            ready = bool(reports) and gate_released
            if ready or time.monotonic() >= end:
                return {'status': 'ready' if ready else 'timeout', 'reports': reports,
                        'pending_report_count': len(pending),
                        'pending_report_ids': [r['report_id'] for r in pending],
                        'gate_released': gate_released}
            time.sleep(min(poll_ms / 1000, max(0, end - time.monotonic())))

    def resolve_mcp_identity(self, caller, process_info=None, starting_pid=None):
        """Recover only an actual registered Codex ancestor when MCP filtered HC identity."""
        with self.locked() as state:
            if caller:
                self.identity(state, caller)
                return caller
            nodes = dict(state['nodes'])
        process_info = process_info or process_metadata
        starting_pid = starting_pid or os.getpid()
        ancestors = {}
        current = starting_pid
        for _ in range(24):
            if not isinstance(current, int) or current <= 1 or current in ancestors:
                break
            info = process_info(current)
            if info is None or info.get('pid') != current:
                break
            ancestors[current] = info
            current = info.get('ppid')
        matches = []
        for address, node in nodes.items():
            if node.get('vendor') != 'codex' or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', address):
                continue
            witness_path = self.evidence / ('native-' + address + '.json')
            if not witness_path.is_file():
                continue
            witness = json.loads(witness_path.read_text())
            ancestor = ancestors.get(witness.get('pid'))
            expected = self.config['vendors']['codex'].get('process_executable')
            if not ancestor or not expected:
                continue
            # /proc/<pid>/exe names the file with every symlink resolved, so on Linux the configured path is
            # compared resolved too. ps (macOS) is compared exactly as before.
            if ancestor.get('executable') != (os.path.realpath(expected) if ancestor.get('executable_source') == 'proc' else expected):
                continue
            if (witness.get('address') != address or witness.get('native_executable') != self.config['vendors']['codex']['executable']
                    or witness.get('keys_removed') is not True
                    or witness.get('anthropic_api_key_present') is not False
                    or witness.get('openai_api_key_present') is not False):
                continue
            try:
                elapsed = (datetime.fromisoformat(witness['timestamp'])
                           - datetime.fromisoformat(ancestor['started_at'])).total_seconds()
            except (ValueError, TypeError, KeyError):
                continue
            # A reused PID starting after the witness cannot authorize this helper.
            if not 0 <= elapsed < 5:
                continue
            matches.append((address, witness_path, ancestor))
        if len(matches) != 1:
            raise ValueError('MCP identity absent and no unique live registered Codex ancestor matched')
        address, witness_path, ancestor = matches[0]
        atomic_json(self.evidence / ('mcp-identity-' + str(starting_pid) + '.json'), {
            'resolved_at': now(), 'source': 'native_ancestor', 'address': address,
            'helper_pid': starting_pid, 'ancestor_pid': ancestor['pid'],
            'ancestor_started_at': ancestor['started_at'], 'native_executable': ancestor['executable'],
            'witness_path': str(witness_path)})
        return address

    def wait_registered(self, caller, timeout=20):
        end = time.monotonic() + timeout
        while True:
            with self.locked() as state:
                if caller in state['nodes']:
                    return
            if time.monotonic() >= end:
                raise ValueError('Session identity did not become registered')
            time.sleep(0.2)


class McpServer:
    """Line-delimited JSON-RPC MCP. The host process writes outside the model sandbox."""
    def __init__(self, host, caller):
        self.host = host
        self.caller = caller

    def handle(self, request):
        ident = request.get('id')
        method = request.get('method')
        if ident is None:
            return None
        reply = {'jsonrpc': '2.0', 'id': ident}
        if method == 'initialize':
            reply['result'] = {'protocolVersion': request.get('params', {}).get('protocolVersion', '2024-11-05'),
                               'capabilities': {'tools': {}}, 'serverInfo': {'name': 'workbench-mailbox', 'version': '1.0'}}
        elif method == 'ping':
            reply['result'] = {}
        elif method == 'tools/list':
            def tool(name, description, properties, required):
                return {'name': name, 'description': description, 'inputSchema': {
                    'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}
            reply['result'] = {'tools': [
                tool('bench_report', 'Durably report only to your registered parent; complete means result ready.',
                     {'summary': {'type': 'string'}, 'complete': {'type': 'boolean'}, 'report_id': {'type': 'string'},
                      'allow_late_time': {'type': 'boolean'}}, ['summary']),
                tool('bench_inbox', 'Read only your own pending reports.', {}, []),
                tool('bench_ack', 'Acknowledge only a report addressed to you.', {'report_id': {'type': 'string'}}, ['report_id'])]}
        elif method == 'tools/call':
            params = request.get('params', {})
            args = params.get('arguments', {})
            name = params.get('name')
            try:
                allowed = {'bench_report': {'summary', 'complete', 'report_id', 'allow_late_time'}, 'bench_inbox': set(),
                           'bench_ack': {'report_id'}}
                if name not in allowed or not isinstance(args, dict) or set(args) - allowed[name]:
                    raise ValueError('Unknown tool or unsupported arguments')
                if name == 'bench_report':
                    result = self.host.report(self.caller, args.get('summary'), args.get('complete', False), args.get('report_id'),
                                              allow_late_time=args.get('allow_late_time') is True)
                    self.host.note_alive_from_hc()
                elif name == 'bench_inbox':
                    result = self.host.inbox(self.caller)
                else:
                    result = self.host.ack(self.caller, args.get('report_id'))
                reply['result'] = {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}]}
            except (ValueError, TypeError) as error:
                reply['result'] = {'isError': True, 'content': [{'type': 'text', 'text': str(error)}]}
        else:
            reply['error'] = {'code': -32601, 'message': 'Method not found'}
        return reply

    def serve(self, reader=sys.stdin, writer=sys.stdout):
        for line in reader:
            try:
                reply = self.handle(json.loads(line))
            except (ValueError, TypeError, AttributeError):
                reply = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid JSON-RPC request'}}
            if reply is not None:
                writer.write(json.dumps(reply, ensure_ascii=False) + '\n')
                writer.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    commands = parser.add_subparsers(dest='command', required=True)
    spawn = commands.add_parser('spawn')
    spawn.add_argument('--role', choices=ROLES, required=True)
    spawn.add_argument('--vendor', choices=['claude', 'codex'])
    spawn.add_argument('--model')
    spawn.add_argument('--cwd')
    spawn.add_argument('--task')
    spawn.add_argument('--worktree', nargs=2, metavar=('REPO', 'BRANCH'))
    spawn.add_argument('--dry-run', action='store_true')
    spawn.add_argument('--no-task', action='store_true')
    spawn.add_argument('--parent', help='Caller parent, or --no-task operator inspection')
    spawn.add_argument('--name', help='Herdr terminal name: 1-32 of a-z 0-9 - _ (default bench-<role>-<id>)')
    spawn.add_argument('--display', help='Name shown in the tree and Claude session list; any text up to 32 characters')
    spawn.add_argument('--resume', metavar='SESSION_ID', help='Reopen this Claude session in the new terminal (Claude only)')
    spawn.add_argument('--state-file', help='Codex: the absolute path of the state file a reopened session reads first')
    spawn.add_argument('--allow-date-mismatch', action='store_true',
                       help='Launch even if the task writes a weekday the calendar contradicts')
    send = commands.add_parser('send', help='Type a follow-up instruction into your own registered child')
    send.add_argument('target')
    send.add_argument('text')
    send.add_argument('--if', dest='if_status', choices=['idle', 'working'],
                      help='Only type if the child status is exactly this (passed to hc send --if)')
    send.add_argument('--allow-date-mismatch', action='store_true',
                      help='Send even if the text writes a weekday the calendar contradicts')
    report = commands.add_parser('report')
    report.add_argument('--summary', required=True)
    report.add_argument('--complete', action='store_true')
    report.add_argument('--report-id')
    report.add_argument('--allow-late-time', action='store_true',
                        help='Send even if the first line names a time later than now (B16)')
    inbox = commands.add_parser('inbox')
    inbox.add_argument('--json', action='store_true')
    inbox.add_argument('--include-archived', action='store_true')
    ack = commands.add_parser('ack')
    ack.add_argument('--report', required=True)
    ack.add_argument('--kind', choices=['received', 'accepted'], default='received')
    ls = commands.add_parser('ls', help='Registered sessions as a tree with live hc state')
    ls.add_argument('--json', action='store_true')
    ls.add_argument('--all', action='store_true', help='Include closed sessions')
    commands.add_parser('retitle', help='Name auto-numbered Herdr tabs of open sessions after their display names')
    rename = commands.add_parser('rename', help='Rename yourself or your direct child (record and tree label)')
    rename.add_argument('target')
    rename.add_argument('--display', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--json', action='store_true')
    wait = commands.add_parser('wait')
    wait.add_argument('--timeout', type=float, default=120)
    wait.add_argument('--poll-ms', type=int, default=500)
    wait.add_argument('--release-file')
    wait.add_argument('--from', dest='sender', help='Only reports from this child wake the wait')
    recover = commands.add_parser('recover', help='After a reboot: reopen every session that was running, top down (B21)')
    recover.add_argument('--dry-run', action='store_true')
    commands.add_parser('tree-refresh', help='Rewrite tree.json if what the tree shows changed (U9)')
    commands.add_parser('relaunch', help='Run inside a revived shell: this session comes back by its own HC_TERMINAL_ID')
    park = commands.add_parser('park', help='Mark yourself or your child as stopped on purpose (recover skips it)')
    park.add_argument('target')
    park.add_argument('--off', action='store_true')
    park.add_argument('--reason', help='Why it stays stopped (kept in the record)')
    state_file = commands.add_parser('state-file', help="Record a Codex session's state file (yourself or your child)")
    state_file.add_argument('path')
    state_file.add_argument('--target')
    takeover = commands.add_parser('takeover', help='Reopen an ended session in a new terminal that inherits its tree place (B1)')
    takeover.add_argument('old')
    takeover.add_argument('--resume', metavar='SESSION_ID', help='Claude session id (default: the one bench recorded)')
    takeover.add_argument('--model')
    takeover.add_argument('--display')
    takeover.add_argument('--fresh', action='store_true', help='Start a new conversation (the only option for Codex)')
    takeover.add_argument('--task', help='Extra text for the new terminal (required with --fresh for Codex)')
    takeover.add_argument('--dry-run', action='store_true')
    close = commands.add_parser('close')
    close.add_argument('target')
    discard = commands.add_parser('discard', help='Clean the worktree of your spawn that failed before hc ran')
    discard.add_argument('worktree')
    commands.add_parser('mcp')
    args = parser.parse_args()
    host = SessionHost(args.config)
    caller = os.environ.get('HC_TERMINAL_ID')
    try:
        if args.command == 'mcp':
            caller = host.resolve_mcp_identity(caller)
        if args.command not in ('inspect', 'ls', 'takeover', 'recover', 'tree-refresh') and not (args.command == 'spawn' and (args.role == 'secretary' or args.no_task)):
            host.wait_registered(caller)
        if args.command == 'spawn':
            result = host.spawn(args.role, caller, dry_run=args.dry_run, no_task=args.no_task, parent_override=args.parent, vendor=args.vendor, model=args.model, cwd=args.cwd, task=args.task, worktree=args.worktree, name=args.name, display=args.display, resume=args.resume, allow_date_mismatch=args.allow_date_mismatch, state_file=args.state_file)
        elif args.command == 'send':
            result = host.send(caller, args.target, args.text, if_status=args.if_status,
                               allow_date_mismatch=args.allow_date_mismatch)
        elif args.command == 'recover':
            result = host.recover(caller, dry_run=args.dry_run)
        elif args.command == 'tree-refresh':
            result = host.tree_refresh()
        elif args.command == 'relaunch':
            result = host.relaunch(caller)
        elif args.command == 'park':
            result = host.park(caller, args.target, off=args.off, reason=args.reason)
        elif args.command == 'state-file':
            result = host.set_state_file(caller, args.path, target=args.target)
        elif args.command == 'takeover':
            result = host.takeover(caller, args.old, resume=args.resume, model=args.model, fresh=args.fresh,
                                   task=args.task, display=args.display, dry_run=args.dry_run)
        elif args.command == 'close':
            result = host.close(caller, args.target)
        elif args.command == 'discard':
            result = host.discard(caller, args.worktree)
        elif args.command == 'report':
            result = host.report(caller, args.summary, args.complete, args.report_id, allow_late_time=args.allow_late_time)
            host.note_alive_from_hc()
        elif args.command == 'inbox':
            result = host.inbox(caller, args.include_archived)
        elif args.command == 'ack':
            result = host.ack(caller, args.report, args.kind)
        elif args.command == 'ls':
            rows = host.ls(include_closed=args.all)
            if not args.json:
                sys.stdout.write(format_ls(rows))
                return
            result = rows
        elif args.command == 'rename':
            result = host.rename(caller, args.target, args.display)
        elif args.command == 'retitle':
            result = host.retitle(caller)
        elif args.command == 'inspect':
            result = host.inspect()
        elif args.command == 'wait':
            result = host.wait(caller, args.timeout, args.poll_ms, args.release_file, args.sender)
        else:
            McpServer(host, caller).serve()
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
