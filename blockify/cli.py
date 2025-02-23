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
        self.blocking = False   # used by unmute_with_delay() to check if, in the meantime, no ad was found
                                # it must be changed after having called mute()/umute()
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
                exit(1)
        self.main_loop = GLib.MainLoop()
        self.spotify = self.connect_to_spotify()
        log.info("Blockify initialized.")

    def mute(self):
        log.debug(f"mute(): blocking={self.blocking} muter={self.muter.is_muted}")
        if self.blocking and self.muter.is_muted:
            return
        self.muter.update()
        log.debug(f"Muting {self.muter.__class__.__name__}: {self.current_song}.")
        self.muter.mute()

    def unmute(self):
        log.debug(f"unmute(): blocking={self.blocking} muter={self.muter.is_muted}")
        if not self.blocking and not self.muter.is_muted:
            # if it's not blocking (i.e. ad or blocklist) but it's still muted (it was toggled),
            # we force the unmute
            return
        self.muter.update()
        log.debug(f"Unmuting {self.muter.__class__.__name__}.")
        self.muter.unmute()

    def toggle(self):
        """Mute/unmute the current song."""
        # ignores self.blocking
        self.muter.update()
        if self.muter.is_muted:
            log.debug(f"Toggling (unmute) {self.muter.__class__.__name__}.")
            self.muter.unmute()
        else:
            log.debug(f"Toggling (mute) {self.muter.__class__.__name__}: {self.current_song}.")
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
                log.warning("Lost connection to spotify.")
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
        def check_spotify_on_change(metadata):
            # NOTE: if autoplay is active and spotify was restarted, then this is executed twice in a row.
            log.debug("Spotify changed status or playback: "+self.spotify.get_song())
            self.check_spotify(metadata)

        self.bind_signals()
        # Force unmute to properly initialize unmuted state

        self.check_spotify() # don't wait for a metadata change to check for ads for the first time
        self.spotify.on_metadata_and_playback_change(check_spotify_on_change)

        if self.autoplay:
            GLib.timeout_add(100, self.start_autoplay)
            pass

        log.info("Blockify started.")
        self.main_loop.run()

    def start_autoplay(self):
        if self.autoplay:
            log.info("Starting Spotify autoplayback.")
            self.spotify.play()

    def check_spotify(self, changed_metadata=None):
        """Checks for ads and mutes accordingly."""
        # is the only function who modifies self.blocking
        artist = self.spotify.get_song_artist(changed_metadata)
        title = self.spotify.get_song_title(changed_metadata)
        self.current_song = f"{artist} - {title}"
        in_blocklist = self.find_in_blocklist(self.current_song)
        if in_blocklist or self.is_ad(artist, title, self.spotify.get_spotify_url(changed_metadata)):
            # GLib.timeout_add(1500, self.mute)
            self.mute()
            self.blocking = True
            return
        # Unmute with a certain delay to avoid the last second
        # of commercial you sometimes hear because it's unmuted too early.
        GLib.timeout_add(self.unmute_delay, self.unmute_with_delay)
        return

    def find_in_blocklist(self, song: str):
        # Check if the blockfile has changed.
        try:
            current_timestamp = self.blocklist.get_timestamp()
        except OSError as e:
            log.debug(f"Failed reading blocklist timestamp: {e}. Recovering.")
            self.blocklist.__init__()
            current_timestamp = self.blocklist.timestamp
        if self.blocklist.timestamp != current_timestamp:
            log.warning("Blockfile changed. Reloading.")
            self.blocklist.__init__()

        if self.blocklist.find(song):
            log.debug(f"Current song found in blocklist: {song}")
            return True
        return False

    def unmute_with_delay(self):
        self.unmute()
        self.blocking = False

    # Audio ads typically have no artist information (via DBus) and/or "/ad/" in their spotify url.
    def is_ad(self, artist: str, title: str, spotify_url):
        missing_artist = title and not artist
        has_ad_url = "/ad/" in spotify_url
        has_podcast_url = "/episode/" in spotify_url

        # log.debug("missing_artist: {0}, has_ad_url: {1}, title_mismatch: {2}".format(missing_artist, has_ad_url,
        #                                                                             title_mismatch))

        return has_ad_url or (missing_artist and not has_podcast_url)

    def block_current(self):
        self.blocklist.append(self.current_song)
        self.check_spotify()

    def unblock_current(self):
        song = self.blocklist.find(self.current_song)
        if song:
            self.blocklist.remove(song)
            self.check_spotify()
        else:
            log.error("Not found in blocklist or block pattern too short.")

    def prepare_stop(self):
        log.warning("Exiting safely. Bye.")
        # Save the list only if it changed during runtime.
        if self.blocklist != self.orglist:
            self.blocklist.save()
        # Unmute before exiting.
        self.unmute()
        self.blocking = False

    def stop(self):
        self.prepare_stop()
        self.main_loop.quit()
        sys.stderr = sys.__stderr__ # otherwise exit code is always != 0. This is util.init_logger() fault
        exit(0)

    def signal_stop_received(self, sig, hdl):
        log.info(f"{sig} received. Exiting safely.")
        self.stop()

    def signal_block_received(self, sig, hdl):
        log.info(f"Signal {sig} received. Blocking current song: {self.current_song}")
        self.block_current()

    def signal_unblock_received(self, sig, hdl):
        log.info(f"Signal {sig} received. Unblocking current song: {self.current_song}")
        self.unblock_current()

    def signal_toggle_received(self, sig, hdl):
        log.info(f"Signal {sig} received. Toggling blocked state.")
        self.toggle()

    def bind_signals(self):
        """Catch signals because it seems like a great idea, right? ... Right?"""
        signal.signal(signal.SIGINT, self.signal_stop_received)  # 9
        signal.signal(signal.SIGTERM, self.signal_stop_received)  # 15

        signal.signal(signal.SIGUSR1, self.signal_toggle_received)  # 37
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

