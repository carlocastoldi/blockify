# Version v4.0.1a0
This is a work in progress for the next release.
## Enhancements
- now blockify can also be run as a [systemd service](blockify/data/blockify.service)
- fixups in logging levels
- fixed a bug were blockify would always exit with code 120
## Bugs fixed
## Dependency updates

# Version v4.0.0
## Enhancements
 - removed GUI
 - removed suppot for an interlude player
 - rewritten CLI interface
 - rewritten Pulse and ALSA audio muters
 - now CLI awaits for MPRIS signals from Spotify instead of polling
 - improved overall error handling
 - moved to Poetry as build system
## Bugs fixed
 - fix podcast episodes being muted
 - fix PipeWire not being supported
 - fix interaction between manual toggling, blocklist and ad detection
## Dependency updates
 - removed dependencies on gstreamer and GTK
 - removed dependency on libwnck and wmctrl

# Old changelog

- v3.6.3 (2016-05-20): Fix [issue #105](https://github.com/serialoverflow/blockify/issues/105) by adding new general option "use_window_title".
- v3.6.2 (2016-05-08): Fix issue where pulse sink would sometimes not be unmuted on exit, fix false positive ad detection on pause for people not using pulseaudio sinks ([issue #97](https://github.com/serialoverflow/blockify/issues/97)), fix pypi installation ([issue #99](https://github.com/serialoverflow/blockify/issues/99)), include README.rst, remove requirements.txt and reimplement dbusclient.py CLI.
- v3.6.1 (2016-04-11): Fix Gst initialization in interlude player, refactor dbusclient CLI and improve some documentation.
- v3.6.0 (2016-04-10): Published blockify to PyPI, made it virtualenv compatible (still requires --system-site-packages for gi.repository) and refactored the import structure.
- v3.5.0 (2016-04-08): Reintroduce wmctrl to catch video ads ([issue #89](https://github.com/serialoverflow/blockify/issues/89)) and block some audio ads more reliably. Fix encoding issues ([issue #95](https://github.com/serialoverflow/blockify/issues/95)).
- v3.4.0 (2016-03-25): Fix play/pause toggle button, right click on tray [issue #83](https://github.com/serialoverflow/blockify/issues/83) and add start_minimized option [issue #93](https://github.com/serialoverflow/blockify/issues/93).
- v3.3.1 (2016-01-03): Fix interlude player crashes ([issue #84](https://github.com/serialoverflow/blockify/issues/84)).
- v3.3.0 (2016-01-03): Enable profiling, improve GUI performance, fix playback button & title status functionality and add tray icon toolip.
- v3.2.1 (2016-01-03): Remove unnecessary imports and other cleanups.
- v3.2.0 (2015-12-31): Reintroduce playback status (see [issue #68](https://github.com/serialoverflow/blockify/issues/68))
- v3.1.0 (2015-12-31): Remove wmctrl dependency (see [issue #67](https://github.com/serialoverflow/blockify/issues/67))
- v3.0.0 (2015-10-16): Remove beta status and port to python3 and gstreamer1.0 (see [issue #59](https://github.com/serialoverflow/blockify/issues/59)).
- v2.0.1 (2015-10-05): (prerelease) Fix [issue #58](https://github.com/serialoverflow/blockify/issues/58) and [issue #38](https://github.com/serialoverflow/blockify/issues/38).
- v2.0.0 (2015-09-05): (prerelease) Added rudimentary support for Spotify v1.0 and higher. Fixed autoplay option.
- v1.9.0 (2015-08-15): Fix [issue #52](https://github.com/serialoverflow/blockify/issues/52), introduce autoplay option and change start_spotify option to boolean type
- v1.8.8 (2015-07-11): Fix [issue #46](https://github.com/serialoverflow/blockify/issues/46) and [issue #47](https://github.com/serialoverflow/blockify/issues/47)
- v1.8.7 (2015-06-11): Pressing play will now properly pause interlude music before resuming spotify playback.
- v1.8.6 (2015-05-10): Minor refactoring and removed incomplete "fix" for [issue #44](https://github.com/serialoverflow/blockify/issues/44).
- v1.8.5 (2015-05-09): Signal cleanups and [issue #44](https://github.com/serialoverflow/blockify/issues/44) again.
- v1.8.4 (2015-05-08): Add additional signals for both spotify and interlude controls (prev/next/playpause, ...), see Controls/Actions section in this README
- v1.8.3 (2015-05-06): Fix [issue #44](https://github.com/serialoverflow/blockify/issues/44): Cancel current interlude song and resume spotify playback if next spotify song button is clicked when no ad is playing
- v1.8.2 (2015-03-18): Reintroduced pacmd_muted_value option in general section ([issue #38](https://github.com/serialoverflow/blockify/issues/38)). Added `gobject.threads_init()` to address ([issue #42](https://github.com/serialoverflow/blockify/issues/42)).
- v1.8.1 (2015-03-17): Added start_shuffled option in interlude-section ([issue #41](https://github.com/serialoverflow/blockify/issues/41))
- v1.8.0 (2015-03-15): Added substring_search option ([issue #36](https://github.com/serialoverflow/blockify/issues/36)). Added pacmd_muted_value option ([issue #38](https://github.com/serialoverflow/blockify/issues/38)). Removed gtk.threads_init() ([issue #39](https://github.com/serialoverflow/blockify/issues/39)).
- v1.7.2 (2015-01-10): Added unmute_delay option for the GUI, too. Removed forced unmute when Spotify is not playing a song or blockify can't find an ad.
- v1.7.1 (2014-12-26): Fix for [issue #32](https://github.com/serialoverflow/blockify/issues/32) (introduced playback_delay option), better load_config and update_slider error catching
- v1.7 (2014-12-24): Unmute delay (avoid last second of commercial), segfault bug fix, Timeout for radio stations, logging improvements, threading improvements (complete switch to gtk), refactorings.
- v1.6 (2014-12-23): Configuration file, playlist and notepad improvements, bug fixes.
- v1.5 (2014-12-21): Mini-audio player for interlude music (media buttons, interactive progress bar, interactive playlist, ...)
- v1.4 (2014-12-14): Interlude music of your choice during commercials
- v1.3 (2014-12-14): GUI-Update (Buttons, Icons, Systray) and Refactoring
- v1.2 (2014-12-11): Cover-Art and config/cache folder in ~/.config/blockify
- v1.1 (2014-06-17): Autodetection of commercials
- v1.0 (2014-05-02): First moderately stable version
- v0.9 (2014-04-29): Pulseaudio (sink) support
