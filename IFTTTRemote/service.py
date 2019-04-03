import SimpleHTTPServer
import SocketServer
import base64
import threading
import traceback
import urllib2
import urlparse

import xbmc
import xbmcaddon

__addon__ = xbmcaddon.Addon()
__addon_name__ = __addon__.getAddonInfo('name')

__service_port__ = int(__addon__.getSetting('servicePort'))
__user_token__ = __addon__.getSetting('userToken')

__spdyn_hostname__ = __addon__.getSetting('spdynHost')
__spdyn_token__ = __addon__.getSetting('spdynToken')


# Displays a notification
def displayNotification(message):
    xbmc.executebuiltin('Notification({}, {}, {})'.format(__addon_name__, message, 3000))


# Gets a HTTP query parameter
# Handles the scenario where the query parameter gets parsed as a List
def getQueryParam(params, name):
    if name not in params or params[name] is None:
        raise Exception('Could not find a parameter')
    result = params[name]
    if isinstance(result, list):
        if len(result) != 1:
            raise Exception('Invalid parameter value')
        return result[0]
    return result


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
def pauseMedia(params):
    if not isMediaLoaded() or not isPlaying():
        raise Exception('Not playing anything right now')
    xbmc.Player().pause()


# Resumes the media if it's paused or throws an Exception if there's no media loaded or the media is not paused at the moment
def resumeMedia(params):
    if not isMediaLoaded() or not isPaused():
        raise Exception('Not paused anything right now')
    xbmc.Player().pause()  # pause will resume the media if it's paused currently


# Stops the media or throws an Exception if there's no media loaded
def stopMedia(params):
    if not isMediaLoaded():
        raise Exception('No media loaded')
    xbmc.Player().stop()


# Returns the time parameter from the HTTP query params as seconds
def getTime(params):
    time = float(getQueryParam(params, '__time'))
    unit = getQueryParam(params, '__unit')
    if unit == 'secs':
        return time
    elif unit == 'mins':
        return time * 60.0
    else:
        raise Exception('Invalid unit')


# Rewinds the media with the given amount of time
def rewindMedia(params):
    if not isMediaLoaded():
        raise Exception('No media loaded')
    position = xbmc.Player().getTime() - getTime(params)
    if position < 0:
        position = 0.0
    xbmc.Player().seekTime(position)


# Fast-forwards the media with the given amount of time
def forwardMedia(params):
    if not isMediaLoaded():
        raise Exception('No media loaded')
    position = xbmc.Player().getTime() + getTime(params)
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
def selectSubtitle(params):
    global __prev_next__
    if not isMediaLoaded():
        raise Exception('No media loaded')
    mode = getQueryParam(params, '__mode')
    if not mode in __prev_next__ and not mode in __on_off__:
        raise Exception("Invalid mode")
    executeJSONRPC("Player.SetSubtitle", '{{ "playerid": 1, "subtitle": "{}" }}'.format(mode))


# Selects the next or previous audio track
def selectAudio(params):
    global __prev_next__
    if not isMediaLoaded():
        raise Exception('No media loaded')
    mode = getQueryParam(params, '__mode')
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


class IFTTTRemoteService(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_GET(self):
        global __user_token__
        global __service_handlers__

        try:
            # Parsing the HTTP request
            result = urlparse.urlparse(self.path)
            params = urlparse.parse_qs(result.query)
            if not result.path.startswith('/ifttt/remote/'):
                raise Exception('Invalid request')

            # Authorizing
            if params is None:
                raise Exception('Unauthorized')
            suppliedToken = getQueryParam(params, '__authorization')
            if suppliedToken != __user_token__:
                raise Exception('Unauthorized')

            # Getting the service to execute
            service = result.path[14:]
            if service not in __service_handlers__:
                raise Exception('Invalid service: {}'.format(service))

            # Executing the service and returning HTTP 200 on successful execution
            __service_handlers__[service](params)
            self.send_response(200, 'OK')
            self.end_headers()
        except:
            xbmc.log('[IFTTT] {}'.format(traceback.format_exc()), level=xbmc.LOGERROR)
            # Returning HTTP 500 if there was an error
            self.send_response(500, traceback.format_exc())
            self.end_headers()


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
    global __spdyn_hostname__
    global __spdyn_token__
    myIP = getIP()
    xbmc.log('[IFTTT] Updating SPDYN with IP {}'.format(myIP), level=xbmc.LOGNOTICE)
    spdynHeaders = {
        'Authorization': 'Basic {}'.format(base64.b64encode('{}:{}'.format(__spdyn_hostname__, __spdyn_token__)))
    }
    request = urllib2.Request('https://update.spdyn.de/nic/update?hostname={}&myip={}'.format(__spdyn_hostname__, myIP), None, spdynHeaders)
    response = readHTTP(request)
    if response != 'nochg {}'.format(myIP) and response != 'good {}'.format(myIP):
        xbmc.log('[IFTTT] Invalid SPDYN response: {}'.format(response), level=xbmc.LOGERROR)
        raise Exception('Invalid update IP response: {}'.format(response))


if __name__ == '__main__':
    # Creating the HTTP Server
    serviceHandler = SocketServer.TCPServer(('0.0.0.0', __service_port__), IFTTTRemoteService)


    # Starts the HTTP Server and displays a notification
    def startService():
        try:
            updateIP()
            displayNotification('Starting the IFTTT remote service')
            xbmc.log(
                '[IFTTT] Starting the IFTTT remote service on port {}'.format(__service_port__),
                level=xbmc.LOGNOTICE)
            serviceHandler.serve_forever()
        except:
            xbmc.log('[IFTTT] {}'.format(traceback.format_exc()), level=xbmc.LOGERROR)


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
