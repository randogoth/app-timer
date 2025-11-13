import math
import os, time
import subprocess

from yaml import load, dump, Loader, Dumper

CONFIG_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def shell(cmd):
    # cmd = cmd.split(' ')
    p = subprocess.Popen(cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=True)
    # p.communicate()
    return p.stdout.read()


class Usage(object):
    """
    Apps Usage Control.
    Will store and inform about timers run time and limits.
    """
    timer = None
    file = None

    def __init__(self, timer):
        super(Usage, self).__init__()
        self.timer = timer
        self.file = '%s/usage/%s' % (CONFIG_PATH, self.timer.name)
        self.final_warning_sent = False

    @property
    def current(self):
        '''Current usage of this timer in minutes'''
        if not os.path.isfile(self.file):
            return 0
        with open(self.file, 'r') as f:
            current = f.read()
        return int(current) if current else 0

    def increment(self, time):
        '''Increment this timer usage'''
        usage = self.current + int(time)
        with open(self.file, 'w') as f:
            f.write(str(usage))

    def release(self):
        '''Remove the timer usage to restart the counter'''
        if os.path.exists(self.file):
            os.remove(self.file)
        self.final_warning_sent = False

    def usageStartTimestamp(self):
        '''Start timestamp (ctime) for the current interval'''
        if not os.path.exists(self.file):
            return None
        return os.path.getctime(self.file)

    def intervalResetTimestamp(self):
        '''Epoch timestamp when the usage interval resets'''
        limit_interval = self.timer.limitInterval
        if (limit_interval < 0):
            return None
        usage_started = self.usageStartTimestamp()
        if usage_started is None:
            return None
        usage_expiry = usage_started + (limit_interval * 60 * 60)
        return usage_expiry

    def timeUntilIntervalReset(self):
        '''Seconds remaining until the interval resets'''
        usage_expiry = self.intervalResetTimestamp()
        if usage_expiry is None:
            return None
        return max(0, usage_expiry - time.time())

    def isOffLimit(self):
        '''Is the timer usage off its limits'''
        time_limit = self.timer.timeLimit
        if (time_limit < 0):
            return False
        if self.current > time_limit:
            return True

    def isOffInterval(self):
        '''Is the timer usage expired'''
        usage_expiry = self.intervalResetTimestamp()
        if usage_expiry is None:
            return False
        return time.time() >= usage_expiry


class Timer(object):
    """
    Apps Timer Setup.
    Will manage a timer and proxy its configuration
    """
    item = None
    name = None
    usage = None

    def __init__(self, name, item):
        super(Timer, self).__init__()
        self.name = name
        self.item = item
        self.usage = Usage(self)

    @property
    def timeLimit(self):
        time_limit = self.item.get('time-limit', -1)
        return int(time_limit)
    @property
    def limitInterval(self):
        limit_interval = self.item.get('limit-interval', -1)
        return float(limit_interval)

    @property
    def apps(self):
        item_apps = self.item.get('apps', [])
        if not isinstance(item_apps, list):
            item_apps = [item_apps]
        apps = [app.strip() for app in item_apps]
        return apps

    @property
    def warnThreshold(self):
        threshold = self.item.get('warn-threshold', None)
        if threshold is None:
            return None
        return float(threshold)

    @property
    def warnCommand(self):
        return self.item.get('warn-command')

    @property
    def finalWarnCommand(self):
        return self.item.get('final-warn-command')

    def _command_context(self, time_left):
        minutes = max(time_left, 0)
        seconds = minutes * 60
        return {
            'timer_name': self.name,
            'time_left': minutes,
            'time_left_int': int(math.ceil(minutes)),
            'time_left_floor': int(math.floor(minutes)),
            'time_left_seconds': int(math.ceil(seconds)),
        }

    def _prepareCommand(self, command, context):
        if isinstance(command, (list, tuple)):
            command = ' '.join([str(part) for part in command])
        if not command:
            return None
        context = context or {}
        try:
            return command.format(**context)
        except (KeyError, IndexError, ValueError) as exc:
            print('Timer %s warning command format error (%s), using raw command' % (self.name, exc))
            return command

    def _runCommand(self, command, label, context=None):
        cmd = self._prepareCommand(command, context)
        if not cmd:
            return
        print('Timer %s running %s command: %s' % (self.name, label, cmd))
        shell(cmd)

    def maybeWarn(self, check_interval):
        if self.timeLimit < 0:
            return
        current_usage = self.usage.current
        time_left = self.timeLimit - current_usage
        if time_left <= 0:
            if self.usage.final_warning_sent:
                self.usage.final_warning_sent = False
            return
        context = self._command_context(time_left)
        if (self.warnThreshold is not None and self.warnCommand and
                time_left <= self.warnThreshold):
            self._runCommand(self.warnCommand, 'warning', context)
        final_command = self.finalWarnCommand
        if not final_command:
            return
        interval = float(check_interval)
        if time_left <= interval:
            if not self.usage.final_warning_sent:
                self._runCommand(final_command, 'final warning', context)
                self.usage.final_warning_sent = True
        else:
            # reset flag if the next loop is no longer the final one
            if self.usage.final_warning_sent:
                self.usage.final_warning_sent = False

    def isRunning(self):
        running = False
        for app in self.apps:
            cmd = 'pgrep -f "%s"' % app
            res = shell(cmd)
            if res.strip():
                running = True
        return running

    def block(self):
        for app in self.apps:
            cmd = 'pkill -f "%s"' % app
            shell(cmd)


class Config(object):
    """
    Config Parser.
    Read and normalize the configuration objects
    """
    data = None
    timers = None
    mtime = 0

    def __init__(self):
        super(Config, self).__init__()
        self.file = '%s/config.yaml' % CONFIG_PATH
        self.reload()

    def hasChanges(self):
        '''Check if the config file has changes'''
        mtime = os.path.getmtime(self.file)
        return self.mtime != mtime

    def reload(self):
        '''Reload config file data'''
        self.mtime = os.path.getmtime(self.file)
        self.data = self.read()
        self.timers = self.getTimers()

    def read(self):
        '''Read the config file yaml object'''
        with open(self.file, 'r') as f:
            data = load(f, Loader=Loader)
        return data

    def getTimers(self):
        '''Gets a generator of Timer objects'''
        config_timers = self.data.get('timers', {})
        timers = []
        for name, item in config_timers.items():
            timers.append(Timer(name, item))
        return timers

    @property
    def checkInterval(self):
        '''How often the usage check should happen'''
        interval = self.data.get('check-interval', 1)
        return int(interval)

    @property
    def statusServer(self):
        '''Optional host/port overrides for the embedded status server'''
        config = self.data.get('status-server') or {}
        host = config.get('host')
        port = config.get('port')
        if port is None:
            parsed_port = None
        else:
            try:
                parsed_port = int(port)
            except (TypeError, ValueError):
                raise ValueError('status-server.port must be an integer')
        return {
            'host': host,
            'port': parsed_port,
        }
