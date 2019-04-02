import SimpleHTTPServer
import SocketServer
import threading
import traceback
import urlparse

import xbmc
import xbmcaddon

__addon__ = xbmcaddon.Addon()
__addon_name__ = __addon__.getAddonInfo('name')

__service_port__ = int(__addon__.getSetting('servicePort'))
__user_token__ = __addon__.getSetting('userToken')


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


__service_handlers__ = {
    'pause': pauseMedia,
    'resume': resumeMedia,
    'stop': stopMedia,
    'rewind': rewindMedia,
    'forward': forwardMedia,
    'exit': exitKodi
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
            xbmc.log(traceback.format_exc(), level=xbmc.LOGERROR)
            # Returning HTTP 500 if there was an error
            self.send_response(500, traceback.format_exc())
            self.end_headers()


if __name__ == '__main__':
    # Creating the HTTP Server
    serviceHandler = SocketServer.TCPServer(('0.0.0.0', __service_port__), IFTTTRemoteService)


    # Starts the HTTP Server and displays a notification
    def startService():
        try:
            displayNotification('Starting the IFTTT remote service')
            xbmc.log(
                'Starting the IFTTT remote service on port {}'.format(__service_port__),
                level=xbmc.LOGNOTICE)
            serviceHandler.serve_forever()
        except:
            xbmc.log(traceback.format_exc(), level=xbmc.LOGERROR)


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
