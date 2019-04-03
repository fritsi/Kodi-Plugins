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
def getSetting(name):
    global __addon__
    value = __addon__.getSetting(name)
    if value == '':
        value = None
    return value


##########################
# Loading Addon Settings #
##########################

__service_port__ = getSetting('servicePort')
__user_token__ = getSetting('userToken')

if __service_port__ is not None:
    __service_port__ = int(__service_port__)

__spdyn_hostname__ = getSetting('spdynHost')
__spdyn_token__ = getSetting('spdynToken')
__spdyn_update_interval__ = getSetting('spdynUpdateIntervalLimit')

if __spdyn_update_interval__ is not None:
    __spdyn_update_interval__ = int(__spdyn_update_interval__)


######################
# Starting the Addon #
######################


# Displays a notification
def displayNotification(message):
    global __addon_name__
    xbmc.executebuiltin('Notification({}, {}, {})'.format(__addon_name__, message, 3000))


# Gets a fields from the JSON supplied in the POST body
def getField(content, name):
    if name not in content or content[name] is None:
        raise Exception('Could not find a field')
    return content[name]


# Checks whether there's any media (video or audio) loaded into Kodi's player
def isMediaLoaded():
    return xbmc.getCondVisibility('Player.HasMedia')


# Checks whether there's any media playing at the moment
def isPlaying():
    return xbmc.getCondVisibility('Player.Playing')


# Checks whether there's any media paused at the moment
def isPaused():
    return xbmc.getCondVisibility('Player.Paused')


# Pauses the media if it's playing or throws an Exception if there's no media loaded or the media is not playing at the moment
def pauseMedia(content):
    if not isMediaLoaded() or not isPlaying():
        raise Exception('Not playing anything right now')
    xbmc.Player().pause()


# Resumes the media if it's paused or throws an Exception if there's no media loaded or the media is not paused at the moment
def resumeMedia(content):
    if not isMediaLoaded() or not isPaused():
        raise Exception('Not paused anything right now')
    xbmc.Player().pause()  # pause will resume the media if it's paused currently


# Stops the media or throws an Exception if there's no media loaded
def stopMedia(content):
    if not isMediaLoaded():
        raise Exception('No media loaded')
    xbmc.Player().stop()


# Returns the time parameter from the POST content as seconds
def getTime(content):
    params = getField(content, 'params')
    time = float(getField(params, 'time'))
    unit = getField(params, 'unit')
    if unit == 'secs':
        return time
    elif unit == 'mins':
        return time * 60.0
    else:
        raise Exception('Invalid unit')


# Rewinds the media with the given amount of time
def rewindMedia(content):
    if not isMediaLoaded():
        raise Exception('No media loaded')
    position = xbmc.Player().getTime() - getTime(content)
    if position < 0:
        position = 0.0
    xbmc.Player().seekTime(position)


# Fast-forwards the media with the given amount of time
def forwardMedia(content):
    if not isMediaLoaded():
        raise Exception('No media loaded')
    position = xbmc.Player().getTime() + getTime(content)
    if position >= xbmc.Player().getTotalTime():
        position = xbmc.Player().getTotalTime() - 5.0
    xbmc.Player().seekTime(position)


# Exits Kodi
def exitKodi(parms):
    xbmc.shutdown()


# Some valid constants
__prev_next__ = ['previous', 'next']
__on_off__ = ['on', 'off']


def executeJSONRPC(method, params):
    xbmc.executeJSONRPC('{{ "jsonrpc": "2.0", "method": "{}", "params": {}, "id": 1 }}'.format(method, params))


# Selects the next or previous subtitle
def selectSubtitle(content):
    global __prev_next__
    global __on_off__
    if not isMediaLoaded():
        raise Exception('No media loaded')
    params = getField(content, 'params')
    mode = getField(params, 'mode')
    if not mode in __prev_next__ and not mode in __on_off__:
        raise Exception("Invalid mode")
    executeJSONRPC("Player.SetSubtitle", '{{ "playerid": 1, "subtitle": "{}" }}'.format(mode))


# Selects the next or previous audio track
def selectAudio(content):
    global __prev_next__
    if not isMediaLoaded():
        raise Exception('No media loaded')
    params = getField(content, 'params')
    mode = getField(params, 'mode')
    if not mode in __prev_next__:
        raise Exception("Invalid mode")
    executeJSONRPC("Player.SetAudioStream", '{{ "playerid": 1, "stream": "{}" }}'.format(mode))


__service_handlers__ = {
    'pause': pauseMedia,
    'resume': resumeMedia,
    'stop': stopMedia,
    'rewind': rewindMedia,
    'forward': forwardMedia,
    'exit': exitKodi,
    'subtitle': selectSubtitle,
    'audio': selectAudio
}


# Authorizes the request
def doAuthorization(content):
    global __user_token__
    raw_authorization = getField(content, 'authorization')
    authorization = base64.b64decode(raw_authorization)
    items = authorization.split('/')
    if len(items) != 2:
        raise Exception('Unauthorized')
    name = socket.gethostname()
    if items[0] != name or items[1] != __user_token__:
        raise Exception('Unauthorized')


class IFTTTRemoteService(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_POST(self):
        global __user_token__
        global __service_handlers__

        try:
            # Parsing the HTTP request
            result = urlparse.urlparse(self.path)
            if not result.path.startswith('/ifttt/remote/'):
                raise Exception('Invalid request')

            # Getting basic content info and validating it
            contentType = self.headers.getheader('Content-Type')
            if contentType is None or not contentType.startswith('application/json'):
                raise Exception('Invalid request')

            contentLength = self.headers.getheader('Content-Length')
            if contentLength is None or contentLength == '':
                raise Exception('Invalid request')
            contentLength = int(contentLength)
            if contentLength < 2:
                raise Exception('Invalid request')

            # Reading the content
            content = json_load(self.rfile.read(contentLength))
            if content is None:
                raise Exception('Invalid request')

            # Authorizing
            doAuthorization(content)

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
def toTimeText(time):
    global __time_format__
    return time.strftime(__time_format__)


# Converts a text into time
def fromTimeText(timeText):
    global __time_format__
    return datetime.datetime.strptime(timeText, __time_format__)


# Gets the current time
# The to string and then back conversion if for stripping the timezone
def getCurrentTime():
    return fromTimeText(toTimeText(datetime.datetime.now()))


# Issues an HTTP request and reads the response
def readHTTP(req):
    opener = urllib2.build_opener()
    return opener.open(req).read().replace('\r', '').replace('\n', '')


# Gets my IP address
def getIP():
    request = urllib2.Request('http://checkip4.spdns.de/', None, {})
    return readHTTP(request)


# Updates the IP address via SPDYN
def updateIP():
    global __addon__
    global __spdyn_hostname__
    global __spdyn_token__

    # Checking whether an IP update is necessary or not
    prevUpdate = getSetting("__prev_ip_update")

    if prevUpdate is not None and (getCurrentTime() - fromTimeText(prevUpdate)).total_seconds() < __spdyn_update_interval__ * 60:
        xbmc.log('[hu.fritsi.ifttt.remote] Not updating the IP address this time', level=xbmc.LOGNOTICE)
        return

    xbmc.log('[hu.fritsi.ifttt.remote] Updating the IP address', level=xbmc.LOGNOTICE)

    myIP = getIP()

    # Updating the IP address
    spdynHeaders = {
        'Authorization': 'Basic {}'.format(base64.b64encode('{}:{}'.format(__spdyn_hostname__, __spdyn_token__)))
    }
    request = urllib2.Request('https://update.spdyn.de/nic/update?hostname={}&myip={}'.format(__spdyn_hostname__, myIP), None, spdynHeaders)
    response = readHTTP(request)

    # Validating the response
    if response != 'nochg {}'.format(myIP) and response != 'good {}'.format(myIP):
        xbmc.log('[hu.fritsi.ifttt.remote] Invalid IP address update response: {}'.format(response), level=xbmc.LOGERROR)
        raise Exception('Invalid IP address update response: {}'.format(response))

    xbmc.log('[hu.fritsi.ifttt.remote] Successfully updated the IP address', level=xbmc.LOGNOTICE)

    # Storing when the last IP update happened
    __addon__.setSetting('__prev_ip_update', toTimeText(getCurrentTime()))


# Starts the addon
def run():
    if __service_port__ is None or __user_token__ is None or __spdyn_hostname__ is None or __spdyn_token__ is None or __spdyn_update_interval__ is None:
        xbmc.log('[hu.fritsi.ifttt.remote] Missing settings', level=xbmc.LOGWARNING)
        return

    # Creating the HTTP Server
    serviceHandler = SocketServer.TCPServer(('0.0.0.0', __service_port__), IFTTTRemoteService)

    # Starts the HTTP Server and displays a notification
    def startService():
        try:
            updateIP()
            displayNotification('Starting the IFTTT remote service')
            xbmc.log('[hu.fritsi.ifttt.remote] Starting the IFTTT remote service', level=xbmc.LOGNOTICE)
            serviceHandler.serve_forever()
        except:
            xbmc.log('[hu.fritsi.ifttt.remote] {}'.format(traceback.format_exc()), level=xbmc.LOGERROR)

    # Executing the server on a different Thread
    thread = threading.Thread(target=startService)
    thread.daemon = True
    thread.start()

    # Getting the Kodi monitor so we know when to stop the HTTP service
    monitor = xbmc.Monitor()

    while not monitor.abortRequested():
        if monitor.waitForAbort(10):
            displayNotification('Stopping the IFTTT remote service')
            serviceHandler.shutdown()
            break


if __name__ == '__main__':
    run()
