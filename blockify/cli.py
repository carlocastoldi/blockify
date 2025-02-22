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
class MuteDetection(Enum):
    AUTOMATIC = 0
    FORCE_MUTE = 1
    FORCE_UNMUTE = 2

class Blockify(object):
    def __init__(self, blocklist):
        self.blocklist = blocklist
        self.orglist = blocklist[:]

        self._autodetect = util.CONFIG["general"]["autodetect"]
        self._automute = util.CONFIG["general"]["automute"]
        self.autoplay = util.CONFIG["general"]["autoplay"]
        self.unmute_delay = util.CONFIG["cli"]["unmute_delay"]
        self.song_delimiter = " - "  # u" \u2013 "
        self.found = False
        self.current_song = ""
        self.current_song_artist = ""
        self.current_song_title = ""
        self.song_status = ""
        self.is_fully_muted = False

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

    def toggle_mute(self, mode=MuteDetection.AUTOMATIC):
        self.muter.update()
        if self.muter.is_muted and (mode == MuteDetection.FORCE_UNMUTE or not self.current_song):
            log.info(f"Forcing unmute {self.muter.__class__.__name__}.")
            self.muter.unmute()
        elif not self.muter.is_muted and mode == MuteDetection.FORCE_MUTE:
            log.info(f"Muting: {self.current_song}.")
            self.muter.mute()
        elif self.muter.is_muted and mode == MuteDetection.AUTOMATIC:
            log.info(f"Unmuting {self.muter.__class__.__name__}.")
            self.muter.unmute()

    def connect_to_spotify(self):
        try:
            return dbusclient.DBusClient() # blocking call
        except KeyboardInterrupt as e:
            self.stop()
            # sys.exit(0)
        except Exception as e:
            log.error("Cannot connect to DBus. Exiting.\n ({}).".format(e))
            self.main_loop.quit()
            sys.exit(-1)

    def start(self):
        def on_spotify_update(metadata=None):
            logging.info(self.spotify.get_song())
            self.found = self.find_ad(metadata)

        self.bind_signals()
        # Force unmute to properly initialize unmuted state

        self.toggle_mute(MuteDetection.FORCE_UNMUTE)
        self.spotify.on_metadata_change(on_spotify_update)

        if self.autoplay:
            # Delay autoplayback until self.spotify_is_playing was called at least once.
            # GLib.timeout_add(self.update_interval + 100, self.start_autoplay)
            pass

        log.info("Blockify started.")
        self.main_loop.run()

    def start_autoplay(self):
        if self.autoplay:
            log.debug("Autoplay is activated.")
            log.info("Starting Spotify autoplayback.")
            self.spotify.play()
        return False

    def spotify_is_playing(self):
        return self.song_status == "Playing"

    def find_ad(self, metadata=None):
        """Checks for ads and mutes accordingly."""
        self.update_current_song_info(metadata)

        # if True:
        if self.autodetect and self.current_song and self.current_song_is_ad():
            self.ad_found()
            return True

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
            self.ad_found()
            return True

        # Unmute with a certain delay to avoid the last second
        # of commercial you sometimes hear because it's unmuted too early.
        # GLib.timeout_add(self.unmute_delay, self.unmute_with_delay) # NOTE: commented out to remove Glib dependency

        return False

    def ad_found(self):
        # log.debug("Ad found: {0}".format(self.current_song))
        self.toggle_mute(MuteDetection.FORCE_MUTE)

    def unmute_with_delay(self):
        if not self.found:
            self.toggle_mute(MuteDetection.AUTOMATIC)
        return False

    # Audio ads typically have no artist information (via DBus) and/or "/ad/" in their spotify url.
    def current_song_is_ad(self):

        missing_artist = self.current_song_title and not self.current_song_artist
        has_ad_url = "/ad/" in self.spotify.get_spotify_url()
        has_podcast_url = "/episode/" in self.spotify.get_spotify_url()

        # log.debug("missing_artist: {0}, has_ad_url: {1}, title_mismatch: {2}".format(missing_artist, has_ad_url,
        #                                                                             title_mismatch))

        return (missing_artist and not has_podcast_url) or has_ad_url

    def update_current_song_info(self, metadata=None):
        self.current_song_artist = self.spotify.get_song_artist(metadata)
        self.current_song_title = self.spotify.get_song_title(metadata)
        self.current_song = self.current_song_artist + self.song_delimiter + self.current_song_title

    def block_current(self):
        if self.current_song:
            self.blocklist.append(self.current_song)

    def unblock_current(self):
        if self.current_song:
            song = self.blocklist.find(self.current_song)
            if song:
                self.blocklist.remove(song)
            else:
                log.error("Not found in blocklist or block pattern too short.")

    def signal_stop_received(self, sig, hdl):
        log.debug("{} received. Exiting safely.".format(sig))
        self.stop()

    def signal_block_received(self, sig, hdl):
        log.debug("Signal {} received. Blocking current song.".format(sig))
        self.block_current()

    def signal_unblock_received(self, sig, hdl):
        log.debug("Signal {} received. Unblocking current song.".format(sig))
        self.unblock_current()

    def signal_toggle_block_received(self, sig, hdl):
        log.debug("Signal {} received. Toggling blocked state.".format(sig))
        self.toggle_block()

    def bind_signals(self):
        """Catch signals because it seems like a great idea, right? ... Right?"""
        signal.signal(signal.SIGINT, self.signal_stop_received)  # 9
        signal.signal(signal.SIGTERM, self.signal_stop_received)  # 15

        signal.signal(signal.SIGUSR1, self.signal_block_received)  # 10
        signal.signal(signal.SIGUSR2, self.signal_unblock_received)  # 12
        signal.signal(signal.SIGRTMIN + 3, self.signal_toggle_block_received)  # 37

    def prepare_stop(self):
        log.info("Exiting safely. Bye.")
        # Save the list only if it changed during runtime.
        if self.blocklist != self.orglist:
            self.blocklist.save()
        # Unmute before exiting.
        if "mutemethod" in self.__dict__:
            self.toggle_mute(MuteDetection.FORCE_UNMUTE)

    def stop(self):
        self.prepare_stop()
        self.main_loop.quit()
        sys.exit()

    def toggle_block(self):
        """Block/unblock the current song."""
        if self.found:
            self.unblock_current()
        else:
            self.block_current()

    @property
    def autodetect(self):
        return self._autodetect

    @autodetect.setter
    def autodetect(self, boolean):
        log.debug("Autodetect: {}.".format(boolean))
        self._autodetect = boolean


def initialize(doc=__doc__):
    try:
        args = util.docopt(doc, version="blockify {}".format(util.VERSION))
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

