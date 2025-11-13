import html
import os, time
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lib import Config

STATUS_CONTEXT = {'config': None}


def _format_duration(seconds):
    if seconds is None:
        return '—'
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append('%dh' % hours)
    if minutes or not parts:
        parts.append('%dm' % minutes)
    return ' '.join(parts)


def _format_minutes(minutes):
    if minutes is None:
        return '—'
    try:
        total_minutes = max(0, int(minutes))
    except (TypeError, ValueError):
        return '—'
    hours, remainder = divmod(total_minutes, 60)
    parts = []
    if hours:
        parts.append('%dh' % hours)
    if remainder or not parts:
        parts.append('%dm' % remainder)
    return ' '.join(parts)


def _format_recharge(hours_value, reset_seconds):
    if hours_value is None:
        return '—'
    if float(hours_value).is_integer():
        base = '%dh' % int(hours_value)
    else:
        base = '%.1fh' % float(hours_value)
    if reset_seconds is None:
        return 'Every %s' % base
    return 'Every %s (ready in %s)' % (base, _format_duration(reset_seconds))


def _format_usage(used, limit):
    if limit is None:
        return '%s (no limit)' % _format_minutes(used)
    used = max(0, used)
    return '%s / %s' % (_format_minutes(used), _format_minutes(limit))


def _format_time_left(time_left, limit):
    if limit is None or time_left is None:
        return '—'
    return _format_minutes(max(0, int(time_left)))


def _collect_timer_snapshot(timer):
    usage_minutes = timer.usage.current
    limit_minutes = timer.timeLimit
    if limit_minutes < 0:
        limit_minutes = None
    time_left = None
    if limit_minutes is not None:
        time_left = max(limit_minutes - usage_minutes, 0)
    interval_hours = timer.limitInterval
    if interval_hours < 0:
        interval_hours = None
    reset_seconds = timer.usage.timeUntilIntervalReset() if interval_hours is not None else None
    running = timer.isRunning()
    blocked = bool(timer.usage.isOffLimit())
    return {
        'name': timer.name,
        'usage': usage_minutes,
        'limit': limit_minutes,
        'time_left': time_left,
        'interval_hours': interval_hours,
        'reset_in': reset_seconds,
        'running': running,
        'blocked': blocked,
        'apps': timer.apps,
    }


def _render_timer_row(snapshot):
    usage_text = _format_usage(snapshot['usage'], snapshot['limit'])
    time_left_text = _format_time_left(snapshot['time_left'], snapshot['limit'])
    interval_text = _format_recharge(snapshot['interval_hours'], snapshot['reset_in'])
    active_text = 'Yes' if snapshot['running'] else 'No'
    blocked_text = 'Yes' if snapshot['blocked'] else 'No'
    apps = snapshot['apps'] or []
    apps_text = ', '.join(html.escape(app) for app in apps) if apps else '—'
    return '<tr><td>{name}</td><td>{usage}</td><td>{time_left}</td><td>{interval}</td><td>{active}</td><td>{blocked}</td><td>{apps}</td></tr>'.format(
        name=html.escape(snapshot['name']),
        usage=usage_text,
        time_left=time_left_text,
        interval=interval_text,
        active=active_text,
        blocked=blocked_text,
        apps=apps_text,
    )


def _render_status_page(config):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    timers = config.timers if config else []
    rows = ''.join(_render_timer_row(_collect_timer_snapshot(timer)) for timer in timers)
    if not rows:
        rows = '<tr><td colspan="7">No timers configured</td></tr>'
    html_doc = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>App Timer Status</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0f172a;
      --surface: #1e293b;
      --surface-alt: #162033;
      --border: rgba(148, 163, 184, 0.3);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Inter", "Segoe UI", system-ui, sans-serif;
      padding: 2rem clamp(1rem, 3vw, 3rem);
      background: radial-gradient(circle at top, rgba(56, 189, 248, 0.15), transparent 55%), var(--bg);
      color: var(--text);
      min-height: 100vh;
      margin: 0;
    }}
    h1 {{
      margin-top: 0;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    p {{ color: var(--muted); margin-top: 0.3rem; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      background: var(--surface);
      border-radius: 0.75rem;
      overflow: hidden;
      box-shadow: 0 20px 50px rgba(15, 23, 42, 0.55);
      border: 1px solid var(--border);
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 0.85rem 1rem;
      text-align: left;
    }}
    th {{
      background: rgba(15, 23, 42, 0.65);
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    tbody tr:last-child td {{ border-bottom: none; }}
    tr:nth-child(even) {{ background: var(--surface-alt); }}
    tr:hover {{ background: rgba(56, 189, 248, 0.08); transition: background 0.15s ease-in-out; }}
  </style>
</head>
<body>
  <h1>App Timer Usage</h1>
  <p>Updated {timestamp}</p>
  <table>
    <thead>
      <tr>
        <th>Category</th>
        <th>Usage</th>
        <th>Time Left</th>
        <th>Recharge</th>
        <th>Active</th>
        <th>Blocked</th>
        <th>Apps</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>""".format(timestamp=timestamp, rows=rows)
    return html_doc


class StatusRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/status'):
            self.send_error(404, 'Not Found')
            return
        config = STATUS_CONTEXT.get('config')
        try:
            payload = _render_status_page(config).encode('utf-8')
        except Exception as exc:
            message = '<html><body><h1>Error</h1><p>%s</p></body></html>' % html.escape(str(exc))
            payload = message.encode('utf-8')
            self.send_response(500)
        else:
            self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # Keep HTTP logs concise
        print("HTTP %s - %s" % (self.log_date_time_string(), format % args))


def _resolve_status_server_bindings(config):
    raw_server_config = getattr(config, 'statusServer', None)
    config_data = getattr(config, 'data', None)
    if raw_server_config:
        server_config = raw_server_config or {}
    elif isinstance(config_data, dict):
        server_config = config_data.get('status-server') or {}
    else:
        server_config = {}
    env_host = os.environ.get('APP_TIMER_STATUS_HOST')
    env_port = os.environ.get('APP_TIMER_STATUS_PORT')
    host = env_host or server_config.get('host') or '127.0.0.1'
    if env_port is not None:
        try:
            port = int(env_port)
        except ValueError:
            raise ValueError('APP_TIMER_STATUS_PORT must be an integer')
    else:
        server_port = server_config.get('port')
        if server_port is not None:
            try:
                port = int(server_port)
            except (TypeError, ValueError):
                raise ValueError('status-server.port must be an integer')
        else:
            port = 8090
    return host, port


def start_status_server(host, port):
    try:
        httpd = ThreadingHTTPServer((host, port), StatusRequestHandler)
    except OSError as exc:
        print('Failed to start status server on %s:%s (%s)' % (host, port, exc))
        return None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print('Status server running on http://%s:%s' % (host, port))
    return httpd

def check_timers(config):
    '''Will check every timer setup for it's usage and limits'''
    for timer in config.timers:
        # restore timers after interval
        if timer.usage.isOffInterval():
            print('Timer %s is off interval' % timer.name)
            timer.usage.release()
        if not timer.isRunning():
            continue
        print('Timer %s is running' % timer.name)
        timer.maybeWarn(config.checkInterval)
        # check for off limit apps
        if timer.usage.isOffLimit():
            print('Timer %s is off limit' % timer.name)
            timer.block()
        # increment running apps timer
        timer.usage.increment(config.checkInterval)

config = Config()
STATUS_CONTEXT['config'] = config
status_host, status_port = _resolve_status_server_bindings(config)
status_server = start_status_server(status_host, status_port)
while True:
    # check config changes
    if config.hasChanges():
        print('Config has changes')
        config.reload()
    # check app timers
    check_timers(config)
    # wait interval in minutes
    time.sleep(-time.time() % (config.checkInterval * 60))
