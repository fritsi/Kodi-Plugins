import BaseHTTPServer
import SocketServer
import base64
import datetime
import socket
import threading
import traceback
import urllib2
import urlparse

import xbmc
import xbmcaddon

from lib.fjson import json_load

__addon__ = xbmcaddon.Addon()
__addon_name__ = __addon__.getAddonInfo('name')


# Reads a Kodi addons setting or returns None if the setting is empty
def get_setting(name):
    global __addon__
    value = __addon__.getSetting(name)
    if value == '':
        value = None
    return value


##########################
# Loading Addon Settings #
##########################

__service_port__ = get_setting('servicePort')
__user_token__ = get_setting('userToken')

if __service_port__ is not None:
    __service_port__ = int(__service_port__)

__spdyn_hostname__ = get_setting('spdynHost')
__spdyn_token__ = get_setting('spdynToken')
__spdyn_update_interval__ = get_setting('spdynUpdateIntervalLimit')

if __spdyn_update_interval__ is not None:
    __spdyn_update_interval__ = int(__spdyn_update_interval__)


######################
# Starting the Addon #
######################


# Displays a notification
def display_notification(message):
    global __addon_name__
    xbmc.executebuiltin('Notification({}, {}, {})'.format(__addon_name__, message, 3000))


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


# Exits Kodi
# noinspection PyUnusedLocal
def exit_kodi(content):
    xbmc.shutdown()


# Some valid constants
__prev_next__ = ['previous', 'next']
__on_off__ = ['on', 'off']


def execute_jsonrpc(method, params):
    xbmc.executeJSONRPC('{{ "jsonrpc": "2.0", "method": "{}", "params": {}, "id": 1 }}'.format(method, params))


# Selects the next or previous subtitle
def select_subtitle(content):
    global __prev_next__
    global __on_off__
    if not is_media_loaded():
        raise Exception('No media loaded')
    params = get_field(content, 'params')
    mode = get_field(params, 'mode')
    if mode not in __prev_next__ and mode not in __on_off__:
        raise Exception("Invalid mode")
    execute_jsonrpc("Player.SetSubtitle", '{{ "playerid": 1, "subtitle": "{}" }}'.format(mode))


# Selects the next or previous audio track
def select_audio(content):
    global __prev_next__
    if not is_media_loaded():
        raise Exception('No media loaded')
    params = get_field(content, 'params')
    mode = get_field(params, 'mode')
    if mode not in __prev_next__:
        raise Exception("Invalid mode")
    execute_jsonrpc("Player.SetAudioStream", '{{ "playerid": 1, "stream": "{}" }}'.format(mode))


__service_handlers__ = {
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
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    if local_ip is None:
        raise Exception('Could not get the IP address')
    return str(local_ip)


# Authorizes the request
def do_authorization(content):
    global __user_token__
    raw_authorization = get_field(content, 'authorization')
    authorization = base64.b64decode(raw_authorization)
    items = authorization.split('/')
    if len(items) != 2:
        raise Exception('Unauthorized')
    if items[0] != get_local_ip() or items[1] != __user_token__:
        raise Exception('Unauthorized')


class IFTTTRemoteService(BaseHTTPServer.BaseHTTPRequestHandler):
    # noinspection PyPep8Naming
    def do_POST(self):
        global __user_token__
        global __service_handlers__

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
            if service not in __service_handlers__:
                raise Exception('Invalid service')

            # Executing the service and returning HTTP 200 on successful execution
            __service_handlers__[service](content)

            self.send_response(200, 'OK')
            self.end_headers()
        except:
            xbmc.log('[hu.fritsi.ifttt.remote] {}'.format(traceback.format_exc()), level=xbmc.LOGERROR)

            # Returning HTTP 500 if there was an error
            self.send_response(500, traceback.format_exc())
            self.end_headers()


__time_format__ = '%Y-%m-%d %H:%M:%S'


# Converts a time into text
def to_time_text(time):
    global __time_format__
    return time.strftime(__time_format__)


# Converts a text into time
def from_time_text(time_text):
    global __time_format__
    return datetime.datetime.strptime(time_text, __time_format__)


# Gets the current time
# The to string and then back conversion if for stripping the timezone
def get_current_time():
    return from_time_text(to_time_text(datetime.datetime.now()))


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
    global __addon__
    global __spdyn_hostname__
    global __spdyn_token__

    # Checking whether an IP update is necessary or not
    prev_update = get_setting("__prev_ip_update")

    if prev_update is not None and (get_current_time() - from_time_text(prev_update)).total_seconds() < __spdyn_update_interval__ * 60:
        xbmc.log('[hu.fritsi.ifttt.remote] Not updating the IP address this time', level=xbmc.LOGNOTICE)
        return

    xbmc.log('[hu.fritsi.ifttt.remote] Updating the IP address', level=xbmc.LOGNOTICE)

    my_ip = get_ip()

    # Updating the IP address
    headers = {
        'Authorization': 'Basic {}'.format(base64.b64encode('{}:{}'.format(__spdyn_hostname__, __spdyn_token__)))
    }
    request = urllib2.Request('https://update.spdyn.de/nic/update?hostname={}&myip={}'.format(__spdyn_hostname__, my_ip), None, headers)
    response = read_http(request)

    # Validating the response
    if response != 'nochg {}'.format(my_ip) and response != 'good {}'.format(my_ip):
        xbmc.log('[hu.fritsi.ifttt.remote] Invalid IP address update response: {}'.format(response), level=xbmc.LOGERROR)
        raise Exception('Invalid IP address update response: {}'.format(response))

    xbmc.log('[hu.fritsi.ifttt.remote] Successfully updated the IP address', level=xbmc.LOGNOTICE)

    # Storing when the last IP update happened
    __addon__.setSetting('__prev_ip_update', to_time_text(get_current_time()))


# Starts the addon
def run():
    if __service_port__ is None or __user_token__ is None or __spdyn_hostname__ is None or __spdyn_token__ is None or __spdyn_update_interval__ is None:
        xbmc.log('[hu.fritsi.ifttt.remote] Missing settings', level=xbmc.LOGWARNING)
        return

    # Creating the HTTP Server
    tcp_server = SocketServer.TCPServer(('0.0.0.0', __service_port__), IFTTTRemoteService)

    # Executing a dummy get_current_time before we start a Thread,
    # because the datetime library has an issue when its first being imported on a Thread
    get_current_time()

    # Starts the HTTP Server and displays a notification
    def start_service():
        try:
            # Updating the IP
            # Failing to update the IP should not block the start
            try:
                update_ip()
            except:
                xbmc.log('[hu.fritsi.ifttt.remote] {}'.format(traceback.format_exc()), level=xbmc.LOGERROR)

            display_notification('Starting the IFTTT remote service')
            xbmc.log('[hu.fritsi.ifttt.remote] Starting the IFTTT remote service', level=xbmc.LOGNOTICE)
            tcp_server.serve_forever()
        except:
            xbmc.log('[hu.fritsi.ifttt.remote] {}'.format(traceback.format_exc()), level=xbmc.LOGERROR)

    # Executing the server on a different Thread
    thread = threading.Thread(target=start_service)
    thread.daemon = True
    thread.start()

    # Getting the Kodi monitor so we know when to stop the HTTP service
    monitor = xbmc.Monitor()

    while not monitor.abortRequested():
        if monitor.waitForAbort(10):
            display_notification('Stopping the IFTTT remote service')
            tcp_server.shutdown()
            break


if __name__ == '__main__':
    run()
