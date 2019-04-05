## IFTTT Remote Service Kodi Plugin

### Introduction

Kodi has its WebServer, however that required authorization in the HTTP header which you cannot do in IFTTT.
Therefore there are various plugins, etc. out there which help you overcome this issue.

Most of them require you hosting a nodejs or PHP server somewhere which would be a "router" between IFTTT and Kodi's internal WebServer.
Now I did not want to do that, so I decided to create my very first Kodi plugin.

That became the IFTTT remote controller.

### How it works

The plugin itself starts its own HTTP Server inside Kodi. That's the trick. :)

Of course my plugin does authorization as well just like Kodi's own WebServer, but mine does it with a field in the POST JSON request.
Since IFTTT supports POST HTTP requests with JSON bodies I choose this way.

After this the only thing you have to do is open a port on your router and forward to your PC where Kodi is running.
Then you can setup IFTTT WebRequests to control your Kodi.

### Additional information

Since in IFTTT WebRequests like ``http://192.168.0.45/ifttt/remote/pause`` do not work, because Google can send requests from anywhere, you'll need a DDNS service.
So after you have your port open on your router you just direct IFTTT's WebRequest through your DDNS Host to that port. :)

Of course I have a router which does not support using DDNS services. :(
So I extended my plugin with the capabilities to use one specific DDNS service. That's https://spdyn.de/.
When Kodi starts-up and the plugin is started, it will register my public IP into my spdyn DDNS Host which I'm using in IFTTT.

### How to setup

#### General settings

![General settings](pics/ss1.jpg?raw=true "General settings")

* __Service port:__ the port your HTTP service inside Kodi will listen on.
Remember, this is a different HTTP server than Kodi's internal one, so please choose a different port.
* __Authentication token:__ essentially a password. :) I'll explain later how this can be used.

#### Dynamic DNS settings

![Dynamic DNS settings](pics/ss2.jpg?raw=true "Dynamic DNS settings")

For now this only supports spdyn DDNS service and it's mandatory. Without these the plugin will not start.
However you can fork the repo and make changes to my plugin. :)

* __DDNS name:__ your spdyn Host name.
* __DDNS token:__ you need to generate a token on spdyn for your Host and this should be that token.
So this is not your spdyn password, but your Host token.
* __IP update interval:__ we do not want to overflow spdyn with many requests, so this is the time where if you restart Kodi within this time (minutes) then the IP address
will not be updated in spdyn. More specifically the IP address will not be updated if there was an update previously within this many minutes.

### Commands and HTTP requests

The following commands can be initiated to the plugin and this is how you can do it.

#### Common to all commands

* Every command should be an HTTP POST request.
* Every command should have application/json as the Content-Type.
* Every command should include an authorization in the format: ``{ "authorization": "[your.access.token]" }``<br/>
The token is not simply the token you specified in the General settings section, but a BASE64 encoded text of ``[YOUR_PC_INTERNAL_IP]/[YOUR_TOKEN]``<br/>
E.g.: ``base64encode('192.168.1.57/MySecrectToken')``
* Each HTTP path ``/ifttt/remote`` as its base path.<br/>
So when below I'm going to refer to `/pause` then the full HTTP path should be
``http://your.dns.host:port/ifttt/remote/pause``
* When a command requires parameter(s) those should be under a ``params`` JSON node in the content.<br/>
E.g.: ``{ "authorization": "...", "params": { "param1": "value1", "param2": "value2" } }``

#### Commands

HTTP path     | Description | Parameters
------------- | ----------- | ----------
``/pause``    | Pauses Kodi if there is a media playing currently | N/A
``/resume``   | Resumes the media if there is a media paused currently | N/A
``/stop``     | Stops the media if there is a media paused currently | N/A
``/exit``     | Exits Kodi | N/A
``/rewind``   | Rewinds the media x seconds of minutes if there is a media loaded | ``time`` - the amount to rewind<br/>``unit`` - ``secs`` or ``mins``
``/forward``  | Fast-forwards the media x seconds of minutes if there is a media loaded | ``time`` - the amount to fast-forward<br/>``unit`` - ``secs`` or ``mins``
``/subtitle`` | Selects the next/previous subtitles or turns subtitles on/off | ``mode`` - ``on/off/next/previous``
``/audio``    | Selects the next/previous audio track | ``mode`` - ``next/previous``

### IFTTT

If you are reading this page, I'm sure you are familiar with IFTTT.

What I did for each command is set up a Google Assistant trigger and a WebHook action.
For commands which don't have input parameters you can choose 'Say a simple phrase' for others 'Say a phrase with a number' for example.
For the commands which can have different input, I've setup multiple IFTTT applets.
So for the subtitle command I have 4 'simple phrase' applets.
For rewind I have 2 'number ingredient' applets.

I'll walk you through the rewind applet and you can created the rest based on that.

1. __Go to creating a new applet.__<br/><br/>
![New applet](pics/ss3.jpg?raw=true "New applet")
2. __For 'this' select Google Assistant.__<br/><br/>
![Google Assistant](pics/ss4.jpg?raw=true "Google Assistant")
3. __Select 'Say a phrase with a number'.__
4. __Enter the information as request. E.g.:__<br/><br/>
![Information](pics/ss5.jpg?raw=true "Information")
5. __Click on 'Create trigger'__
6. __For 'that' select WebHook.__<br/><br/>
![WebHook](pics/ss6.jpg?raw=true "WebHook")
7. __Select 'Make a web request'.__
8. __For URL enter__ ``http://[your.ddns.address]:[your.port]/ifttt/remote/rewind``
9. __For Method select POST.__
10. __For Content type select application/json.__
11. __And for Body enter:__<br/>
``{ "authorization": "[your.access.token]", "params": { "time": "{{NumberField}}", "unit": "secs" } }``
12. __Click on 'Create action'.__

That's it. :)

If you want replaceable/copy-pastable URLs and conentents please see [this](examples.txt).
