## KodiPlugins

### Introduction

I created this repo, because I was looking for a way to control my Kodi running on my Android TV using IFTTT.

Kodi has its WebServer, however that required authorization in the HTTP header which you cannot do in IFTTT.
Therefore there are various plugins, etc. out there which help you overcome this issue.

Most of them require you hosting a nodejs or PHP server somewhere which would be a "router" between IFTTT and Kodi's internal WebServer.
Now I did not want to do that, so I decided to create my very first Kodi plugin.

That became the IFTTT remote controller.

More about that [here](IFTTTRemote).
