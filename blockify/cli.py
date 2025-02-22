#!/usr/bin/env python3
"""blockify

Usage:
    blockify [-l <path>] [-v...] [-q] [-h]

Options:
    -l, --log=<path>  Enables logging to the logfile/-path specified.
    -q, --quiet       Don't print anything to stdout.
    -v                Verbosity of the logging module, up to -vvv.
    -h, --help        Show this help text.
    --version         Show current version of blockify.
"""
import logging
import signal
import sys

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib

from enum import Enum

from blockify import blocklist, dbusclient, util
from blockify.muters import AlsaMuter, PulseMuter, SystemCommandNotFound

log = logging.getLogger("cli")

class Blockify(object):
    def __init__(self, blocklist: blocklist.Blocklist):
        self.blocklist = blocklist
        self.orglist = blocklist[:]

        self.autoplay = util.CONFIG["general"]["autoplay"]
        self.unmute_delay = util.CONFIG["cli"]["unmute_delay"]
        self.found = False # used by unmute_with_delay() to check if, in the meantime, no ad was found
        self.current_song = ""

        try:
            self.muter = PulseMuter()
            log.debug("Mute method is pulse sink.")
        except SystemCommandNotFound as e:
            log.info(f"No command '{e.command}' found. Falling back to system mute via ALSA.") #/pulse
            try:
                self.muter = AlsaMuter()
            except SystemCommandNotFound as e2:
                log.error(f"No command '{e2.command}' found. Exiting.")
                sys.exit(-1)

        # DBusGMainLoop(set_as_default=True)
        self.main_loop = GLib.MainLoop()
        self.spotify = self.connect_to_spotify()
        log.info("Blockify initialized.")

    def mute(self):
        self.muter.update()
        log.info(f"Muting {self.muter.__class__.__name__}: {self.current_song}.")
        # if not self.muter.is_muted:
        self.muter.mute()

    def unmute(self):
        self.muter.update()
        log.info(f"Unmuting {self.muter.__class__.__name__}.")
        # if self.muter.is_muted:
        self.muter.unmute()

    def toggle_block(self):
        """Block/unblock the current song."""
        self.muter.update()
        if self.muter.is_muted:
            log.info(f"Unmuting {self.muter.__class__.__name__}.")
            self.muter.unmute()
        else:
            log.info(f"Muting {self.muter.__class__.__name__}: {self.current_song}.")
            self.muter.mute()

    def connect_to_spotify(self):
        self.spotify = dbusclient.SpotifyDBusClient()
        if self.establish_spotify_connection(): # blocking call
            self.reconnect_if_closed(self.spotify.get_xdg_dbus())
        return self.spotify

    def establish_spotify_connection(self):
        try:
            self.spotify.connect()
        except KeyboardInterrupt as e:
            self.stop()
            return False
        except SystemExit:
            # self.stop() was already called on another thread
            return False
        return True

    def reconnect_if_closed(self, xdg_bus):
            def reconnect(bus_name, old_owner, new_owner):
                log.info("Lost connection to spotify.")
                if self.establish_spotify_connection():
                    self.start_autoplay()
            xdg_bus.connect_to_signal(
                signal_name="NameOwnerChanged",
                handler_function=reconnect,
                dbus_interface="org.freedesktop.DBus",
                arg0="org.mpris.MediaPlayer2.spotify",
                arg2="",  # new_owner
            )

    def start(self):
        def check_spotify(metadata=None):
            # NOTE: if autoplay is active and spotify was restarted, then this is executed twice in a row.
            log.info(self.spotify.get_song())
            self.find_ad(metadata)

        self.bind_signals()
        # Force unmute to properly initialize unmuted state

        self.find_ad() # don't wait for a metadata change to check for ads for the first time
        self.spotify.on_metadata_and_playback_change(check_spotify)

        if self.autoplay:
            GLib.timeout_add(100, self.start_autoplay)
            pass

        log.info("Blockify started.")
        self.main_loop.run()

    def start_autoplay(self):
        if self.autoplay:
            log.info("Starting Spotify autoplayback.")
            self.spotify.play()

    def find_ad(self, metadata=None):
        """Checks for ads and mutes accordingly."""

        artist = self.spotify.get_song_artist(metadata)
        title = self.spotify.get_song_title(metadata)
        previous_song = self.current_song
        self.current_song = f"{artist} - {title}"
        if self.current_song == previous_song:
            return self.found

        # if True:
        if self.current_song_is_ad(artist, title, self.spotify.get_spotify_url(metadata)):
            # GLib.timeout_add(1500, self.mute)
            self.mute()
            self.found = True
            return

        # Check if the blockfile has changed.
        try:
            current_timestamp = self.blocklist.get_timestamp()
        except OSError as e:
            log.debug("Failed reading blocklist timestamp: {}. Recovering.".format(e))
            self.blocklist.__init__()
            current_timestamp = self.blocklist.timestamp
        if self.blocklist.timestamp != current_timestamp:
            log.info("Blockfile changed. Reloading.")
            self.blocklist.__init__()

        if self.blocklist.find(self.current_song):
            self.mute()
            self.found = True
            return

        # Unmute with a certain delay to avoid the last second
        # of commercial you sometimes hear because it's unmuted too early.
        self.found = False
        GLib.timeout_add(self.unmute_delay, self.unmute_with_delay)

    def unmute_with_delay(self):
        if not self.found:
            self.unmute()

    # Audio ads typically have no artist information (via DBus) and/or "/ad/" in their spotify url.
    def current_song_is_ad(self, artist: str, title: str, spotify_url):
        missing_artist = title and not artist
        has_ad_url = "/ad/" in spotify_url
        has_podcast_url = "/episode/" in spotify_url

        # log.debug("missing_artist: {0}, has_ad_url: {1}, title_mismatch: {2}".format(missing_artist, has_ad_url,
        #                                                                             title_mismatch))

        return has_ad_url or (missing_artist and not has_podcast_url)

    def block_current(self):
        self.blocklist.append(self.current_song)

    def unblock_current(self):
        song = self.blocklist.find(self.current_song)
        if song:
            self.blocklist.remove(song)
        else:
            log.error("Not found in blocklist or block pattern too short.")

    def prepare_stop(self):
        log.info("Exiting safely. Bye.")
        # Save the list only if it changed during runtime.
        if self.blocklist != self.orglist:
            self.blocklist.save()
        # Unmute before exiting.
        self.unmute()

    def stop(self):
        self.prepare_stop()
        self.main_loop.quit()
        sys.exit()

    def signal_stop_received(self, sig, hdl):
        log.debug(f"{sig} received. Exiting safely.")
        self.stop()

    def signal_block_received(self, sig, hdl):
        log.debug(f"Signal {sig} received. Blocking current song: {self.current_song}")
        self.block_current()

    def signal_unblock_received(self, sig, hdl):
        log.debug(f"Signal {sig} received. Unblocking current song: {self.current_song}")
        self.unblock_current()

    def signal_toggle_block_received(self, sig, hdl):
        log.debug(f"Signal {sig} received. Toggling blocked state.")
        self.toggle_block()

    def bind_signals(self):
        """Catch signals because it seems like a great idea, right? ... Right?"""
        signal.signal(signal.SIGINT, self.signal_stop_received)  # 9
        signal.signal(signal.SIGTERM, self.signal_stop_received)  # 15

        signal.signal(signal.SIGUSR1, self.signal_toggle_block_received)  # 37
        signal.signal(signal.SIGUSR2, self.signal_block_received)  # 10
        signal.signal(signal.SIGRTMIN, self.signal_unblock_received)  # 12


def initialize(doc=__doc__):
    try:
        args = util.docopt(doc, version=f"blockify {util.VERSION}")
    except Exception:
        args = None
    util.initialize(args)

    _blocklist = blocklist.Blocklist()
    cli = Blockify(_blocklist)

    return cli


def main():
    """Entry point for the CLI-version of Blockify."""
    cli = initialize()
    cli.start()

if __name__ == "__main__":
    main()

