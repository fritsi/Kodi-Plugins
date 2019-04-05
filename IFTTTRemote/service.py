import base64
import socket
import threading
import traceback
import urllib2
import urlparse

import _strptime # DO NOT remove this import as it's fixing a threading/importing issue in datetime

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

import xbmc
import xbmcaddon

from lib.fjson import json_load
from lib.threads import AtomicValue

_addon = xbmcaddon.Addon()
_addon_name = _addon.getAddonInfo('name')


# Reads a Kodi addons setting or returns None if the setting is empty
def get_setting(name):
    global _addon
    value = _addon.getSetting(name)
    if value == '':
        value = None
    return value


##########################
# Loading Addon Settings #
##########################

_service_port = get_setting('servicePort')
_user_token = get_setting('userToken')

if _service_port is not None:
    _service_port = int(_service_port)

_spdyn_hostname = get_setting('spdynHost')
_spdyn_token = get_setting('spdynToken')
_spdyn_update_interval = get_setting('spdynUpdateIntervalLimit')

if _spdyn_update_interval is not None:
    _spdyn_update_interval = int(_spdyn_update_interval)


######################
# Starting the Addon #
######################


# Displays a notification
def display_notification(message):
    global _addon_name
    xbmc.executebuiltin('Notification({}, {}, {})'.format(_addon_name, message, 3000))


# Gets a fields from the JSON supplied in the POST body
def get_field(content, name):
    if name not in content or content[name] is None:
        raise Exception('Could not find a field')
    return content[name]


# Checks whether there's any media (video or audio) loaded into Kodi's player
def is_media_loaded():
    return xbmc.getCondVisibility('Player.HasMedia')


# Checks whether there's any media playing at the moment
def is_playing():
    return xbmc.getCondVisibility('Player.Playing')


# Checks whether there's any media paused at the moment
def is_paused():
    return xbmc.getCondVisibility('Player.Paused')


# Pauses the media if it's playing or throws an Exception if there's no media loaded or the media is not playing at the moment
# noinspection PyUnusedLocal
def pause_media(content):
    if not is_media_loaded() or not is_playing():
        raise Exception('Not playing anything right now')
    xbmc.Player().pause()


# Resumes the media if it's paused or throws an Exception if there's no media loaded or the media is not paused at the moment
# noinspection PyUnusedLocal
def resume_media(content):
    if not is_media_loaded() or not is_paused():
        raise Exception('Not paused anything right now')
    xbmc.Player().pause()  # pause will resume the media if it's paused currently


# Stops the media or throws an Exception if there's no media loaded
# noinspection PyUnusedLocal
def stop_media(content):
    if not is_media_loaded():
        raise Exception('No media loaded')
    xbmc.Player().stop()


# Returns the time parameter from the POST content as seconds
def get_time(content):
    params = get_field(content, 'params')
    time = float(get_field(params, 'time'))
    unit = get_field(params, 'unit')
    if unit == 'secs':
        return time
    elif unit == 'mins':
        return time * 60.0
    else:
        raise Exception('Invalid unit')


# Rewinds the media with the given amount of time
def rewind_media(content):
    if not is_media_loaded():
        raise Exception('No media loaded')
    position = xbmc.Player().getTime() - get_time(content)
    if position < 0:
        position = 0.0
    xbmc.Player().seekTime(position)


# Fast-forwards the media with the given amount of time
def forward_media(content):
    if not is_media_loaded():
        raise Exception('No media loaded')
    position = xbmc.Player().getTime() + get_time(content)
    if position >= xbmc.Player().getTotalTime():
        position = xbmc.Player().getTotalTime() - 5.0
    xbmc.Player().seekTime(position)


_exit_triggered = AtomicValue(False)


# Triggers a Kodi exit
# noinspection PyUnusedLocal
def exit_kodi(content):
    global _exit_triggered
    _exit_triggered.set(True)


# Some valid constants
_prev_next = ['previous', 'next']
_on_off = ['on', 'off']


def execute_jsonrpc(method, params):
    xbmc.executeJSONRPC('{{ "jsonrpc": "2.0", "method": "{}", "params": {}, "id": 1 }}'.format(method, params))


# Selects the next or previous subtitle
def select_subtitle(content):
    global _prev_next
    global _on_off
    if not is_media_loaded():
        raise Exception('No media loaded')
    params = get_field(content, 'params')
    mode = get_field(params, 'mode')
    if mode not in _prev_next and mode not in _on_off:
        raise Exception('Invalid mode')
    execute_jsonrpc('Player.SetSubtitle', '{{ "playerid": 1, "subtitle": "{}" }}'.format(mode))


# Selects the next or previous audio track
def select_audio(content):
    global _prev_next
    if not is_media_loaded():
        raise Exception('No media loaded')
    params = get_field(content, 'params')
    mode = get_field(params, 'mode')
    if mode not in _prev_next:
        raise Exception('Invalid mode')
    execute_jsonrpc('Player.SetAudioStream', '{{ "playerid": 1, "stream": "{}" }}'.format(mode))


_service_handlers = {
    'pause': pause_media,
    'resume': resume_media,
    'stop': stop_media,
    'rewind': rewind_media,
    'forward': forward_media,
    'exit': exit_kodi,
    'subtitle': select_subtitle,
    'audio': select_audio
}


# Gets the device's local IP address (e.g.: 192.168.1.42)
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    if local_ip is None:
        raise Exception('Could not get the IP address')
    return str(local_ip)


# Authorizes the request
def do_authorization(content):
    global _user_token
    raw_authorization = get_field(content, 'authorization')
    authorization = base64.b64decode(raw_authorization)
    items = authorization.split('/')
    if len(items) != 2:
        raise Exception('Unauthorized')
    if items[0] != get_local_ip() or items[1] != _user_token:
        raise Exception('Unauthorized')


class IFTTTRemoteService(BaseHTTPRequestHandler):
    # noinspection PyPep8Naming
    def do_POST(self):
        global _service_handlers
        global _exit_triggered

        # If an exit was triggered we do not handle the request
        if self.__should_not_handle():
            return

        try:
            # Parsing the HTTP request
            result = urlparse.urlparse(self.path)
            if not result.path.startswith('/ifttt/remote/'):
                raise Exception('Invalid request')

            # Getting basic content info and validating it
            content_type = self.headers.getheader('Content-Type')
            if content_type is None or not content_type.startswith('application/json'):
                raise Exception('Invalid request')

            content_length = self.headers.getheader('Content-Length')
            if content_length is None or content_length == '':
                raise Exception('Invalid request')
            content_length = int(content_length)
            if content_length < 2:
                raise Exception('Invalid request')

            # Reading the content
            content = json_load(self.rfile.read(content_length))
            if content is None:
                raise Exception('Invalid request')

            # Authorizing
            do_authorization(content)

            # Getting the service to execute
            service = result.path[14:]
            if service not in _service_handlers:
                raise Exception('Invalid service')

            # If an exit was triggered we do not handle the request
            if self.__should_not_handle():
                return

            # Executing the service
            _service_handlers[service](content)

            # Returning HTTP 200 on successful execution
            self.__end_request(200)
        except:
            # Gathering the error
            error = traceback.format_exc()
            xbmc.log('[IFTTT remote] Error while handling the request\n{}'.format(error), level=xbmc.LOGERROR)

            # Returning HTTP 500 if there was an error
            self.__end_request(500, error)

    # Returns HTTP 500 if an exit was triggered
    def __should_not_handle(self):
        global _exit_triggered
        if _exit_triggered.get():
            self.__end_request(500, "Exit was initiated")
            return True
        return False

    def __end_request(self, code, content=None):
        self.send_response(code)
        if content is not None:
            while content.endswith('\r') or content.endswith('\n'):
                content = content[:-1]
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', len(content))
        self.end_headers()
        if content is not None:
            self.wfile.write(content)


__time_format = '%Y-%m-%d %H:%M:%S'


# Converts a time into text
def to_time_text(time):
    global __time_format
    return time.strftime(__time_format)


# Converts a text into time
def from_time_text(time_text):
    global __time_format
    return datetime.strptime(time_text, __time_format)


# Gets the current time
# The to string and then back conversion if for stripping the timezone
def get_current_time():
    current_time = datetime.now()
    as_text = to_time_text(current_time)
    return from_time_text(as_text)


# Issues an HTTP request and reads the response
def read_http(req):
    opener = urllib2.build_opener()
    return opener.open(req).read().replace('\r', '').replace('\n', '')


# Gets my IP address
def get_ip():
    request = urllib2.Request('http://checkip4.spdns.de/', None, {})
    return read_http(request)


# Updates the IP address via SPDYN
def update_ip():
    global _addon
    global _spdyn_hostname
    global _spdyn_token

    # Checking whether an IP update is necessary or not
    prev_update = get_setting('__prev_ip_update')

    if prev_update is not None and (get_current_time() - from_time_text(prev_update)).total_seconds() < _spdyn_update_interval * 60:
        xbmc.log('[IFTTT remote] Not updating the IP address this time', level=xbmc.LOGNOTICE)
        return

    xbmc.log('[IFTTT remote] Updating the IP address', level=xbmc.LOGNOTICE)

    my_ip = get_ip()

    # Updating the IP address
    headers = {
        'Authorization': 'Basic {}'.format(base64.b64encode('{}:{}'.format(_spdyn_hostname, _spdyn_token)))
    }
    request = urllib2.Request('https://update.spdyn.de/nic/update?hostname={}&myip={}'.format(_spdyn_hostname, my_ip), None, headers)
    response = read_http(request)

    # Validating the response
    if response != 'nochg {}'.format(my_ip) and response != 'good {}'.format(my_ip):
        xbmc.log('[IFTTT remote] Invalid IP address update response: {}'.format(response), level=xbmc.LOGERROR)
        raise Exception('Invalid IP address update response: {}'.format(response))

    xbmc.log('[IFTTT remote] Successfully updated the IP address', level=xbmc.LOGNOTICE)

    # Storing when the last IP update happened
    _addon.setSetting('__prev_ip_update', to_time_text(get_current_time()))


# Stores whether we've started out IFTTT service or not
_tcp_server_running = AtomicValue(False)


class Main:
    def run(self):
        global _service_port
        global _user_token
        global _spdyn_hostname
        global _spdyn_token
        global _spdyn_update_interval
        global _exit_triggered
        global _tcp_server_running

        if _service_port is None or _user_token is None or _spdyn_hostname is None or _spdyn_token is None or _spdyn_update_interval is None:
            xbmc.log('[IFTTT remote] Missing settings', level=xbmc.LOGWARNING)
            return

        # Creating the HTTP Server
        self.__tcp_server = HTTPServer(('0.0.0.0', _service_port), IFTTTRemoteService)

        # Executing the server on a different Thread
        thread = threading.Thread(target=self.__start_service)
        thread.daemon = True
        thread.start()

        # Getting the Kodi monitor so we know when to stop the HTTP service
        monitor = xbmc.Monitor()

        # Starting a loop to monitor when we need to exit
        while not monitor.abortRequested():
            if _exit_triggered.get() or monitor.waitForAbort(2):
                break

        if _tcp_server_running.get():
            xbmc.log('[IFTTT remote] Stopping the IFTTT remote service', level=xbmc.LOGNOTICE)
            display_notification('Stopping the IFTTT remote service')
            self.__tcp_server.shutdown()
            _tcp_server_running.set(False)
            xbmc.log('[IFTTT remote] Stopped the IFTTT remote service', level=xbmc.LOGNOTICE)

        # If an exit was triggered we shut down Kodi
        if _exit_triggered.get() and not monitor.abortRequested():
            xbmc.log('[IFTTT remote] Triggering Kodi shutdown', level=xbmc.LOGNOTICE)
            xbmc.shutdown()

    # Starts the HTTP Server and displays a notification
    def __start_service(self):
        global _tcp_server_running

        try:
            # Updating the IP
            # Failing to update the IP should not block the start
            try:
                update_ip()
            except:
                xbmc.log('[IFTTT remote] Error while updating the IP address\n{}'.format(traceback.format_exc()), level=xbmc.LOGERROR)

            xbmc.log('[IFTTT remote] Starting the IFTTT remote service', level=xbmc.LOGNOTICE)
            display_notification('Starting the IFTTT remote service')

            try:
                _tcp_server_running.set(True)
                self.__tcp_server.serve_forever()
            except:
                xbmc.log('[IFTTT remote] Error while serving requests\n{}'.format(traceback.format_exc()), level=xbmc.LOGERROR)
                display_notification('Error while serving requests')
                _tcp_server_running.set(False)
        except:
            xbmc.log('[IFTTT remote] Error in start service\n{}'.format(traceback.format_exc()), level=xbmc.LOGERROR)


if __name__ == '__main__':
    Main().run()
