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
import os
import re
import signal
import subprocess
import sys
import time

from blockify import util

log = logging.getLogger("cli")

from enum import Enum
from gi import require_version

require_version('Gtk', '4.0')
from gi.repository import Gtk
from gi.repository import GObject, GLib

from blockify import blocklist
from blockify import dbusclient
from blockify import interludeplayer


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
        self.pulse_unmuted_value = ""
        self.song_delimiter = " - "  # u" \u2013 "
        self.found = False
        self.current_song = ""
        self.current_song_artist = ""
        self.current_song_title = ""
        self.previous_song = ""
        self.song_status = ""
        self.is_fully_muted = False
        self.is_sink_muted = False
        self.main_loop = GLib.MainLoop()
        self.spotify = self.connect_to_spotify()
        self.channels = self.initialize_channels()
        # The gst library used by interludeplayer for some reason modifies
        # argv, overwriting some of docopts functionality in the process,
        # so we import gst here, where docopts cannot be broken anymore.
        # import interludeplayer
        self.player = interludeplayer.InterludePlayer(self)

        self.initialize_mute_method()

        self.initialize_pulse_unmuted_value()

        # Only use interlude music if we use pulse sinks and the interlude playlist is non-empty.
        self.use_interlude_music = util.CONFIG["interlude"]["use_interlude_music"] and \
                                   self.mutemethod == self.pulsesink_mute and \
                                   self.player.max_index >= 0

        log.info("Blockify initialized.")

    def is_localized_pulseaudio(self):
        """Pulseaudio versions below 7.0 are localized."""
        localized = False
        try:
            subprocess.check_call(["pulseaudio"])
        except OSError:
            log.info("Assuming system is using PipeWire")
            return localized
        try:
            pulseaudio_version_string = subprocess.check_output("pulseaudio --version | awk '{print $2}'", shell=True)
            pulseaudio_version = int(pulseaudio_version_string[0])
            localized = pulseaudio_version < 7
        except Exception as e:
            log.error("Could not detect pulseaudio version: {}".format(e))

        return localized

    def initialize_pulse_unmuted_value(self):
        """Set 'no' as self.pulse_unmuted_value and try to translate if necessary."""
        unmuted_value = 'no'
        if self.is_localized_pulseaudio():
            try:
                self.install_locale()
                # Translate 'no' to the system locale.
                unmuted_value = _(unmuted_value)
            except (Exception):
                log.debug("Could not install localization. If your system "
                          "language is not english this *might* lead to unexpected "
                          "mute behaviour. A possible fix is to replace the "
                          "value of unmuted_value in blockify.py with your "
                          "translation of 'no', e.g. 'tak' in polish.")

        self.pulse_unmuted_value = unmuted_value

    def initialize_mute_method(self):
        """Determine if we can use sinks or have to use alsa."""
        try:
            devnull = open(os.devnull)
            subprocess.check_output(["pactl", "list", "sink-inputs"], stderr=devnull)
            self.mutemethod = self.pulsesink_mute
            log.debug("Mute method is pulse sink.")
        except (OSError, subprocess.CalledProcessError):
            log.debug("Mute method is alsa or pulse without sinks.")
            log.info("No pulse sinks found, falling back to system mute via alsa/pulse.")
            self.mutemethod = self.alsa_mute

    def install_locale(self):
        import locale
        import gettext

        current_locale, encoding = locale.getdefaultlocale()
        pulseaudio_domain = 'pulseaudio'
        localedir = gettext.find(pulseaudio_domain, languages=[current_locale])
        localedir = localedir[:localedir.find('locale/')] + 'locale'
        locale = gettext.translation(pulseaudio_domain, localedir=localedir, languages=[current_locale])
        locale.install()

    def initialize_channels(self):
        channel_list = ["Master"]
        amixer_output = subprocess.check_output("amixer")
        if "'Speaker',0" in amixer_output.decode("utf-8"):
            channel_list.append("Speaker")
        if "'Headphone',0" in amixer_output.decode("utf-8"):
            channel_list.append("Headphone")

        return channel_list

    def connect_to_spotify(self):
        try:
            return dbusclient.DBusClient()
        except Exception as e:
            log.error("Cannot connect to DBus. Exiting.\n ({}).".format(e))
            self.main_loop.quit()

    def start(self):
        self.bind_signals()
        # Force unmute to properly initialize unmuted state

        self.toggle_mute(MuteDetection.FORCE_UNMUTE)
        self.update(self.update())
        self.spotify.on_metadata_change(lambda metadata: self.update(metadata))

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

    def adjust_interlude(self):
        if self.use_interlude_music:
            self.player.toggle_music()

    def spotify_is_playing(self):
        return self.song_status == "Playing"

    def update(self, metadata=None):
        # Determine if a commercial is running and act accordingly.
        self.found = self.find_ad(metadata)
        self.adjust_interlude()

    def find_ad(self, metadata=None):
        """Checks for ads and mutes accordingly."""
        self.previous_song = self.current_song
        self.update_current_song_info(metadata)

        # Manual control is enabled so we exit here.
        if not self.automute:
            return False

        # if True:
        if self.autodetect and self.current_song and self.current_song_is_ad():
            if self.use_interlude_music and not self.player.temp_disable:
                self.player.temp_disable = True
                GLib.timeout_add(self.player.playback_delay, self.player.play_with_delay)
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
        GLib.timeout_add(self.unmute_delay, self.unmute_with_delay)

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
            if self.use_interlude_music:
                self.player.pause()
            song = self.blocklist.find(self.current_song)
            if song:
                self.blocklist.remove(song)
            else:
                log.error("Not found in blocklist or block pattern too short.")

    def toggle_mute(self, mode=MuteDetection.AUTOMATIC):
        self.mutemethod(mode)

    def is_muted(self):
        for channel in self.channels:
            try:
                output = subprocess.check_output(["amixer", "get", channel])
                if "[off]" in output.decode("utf-8"):
                    return True
            except subprocess.CalledProcessError:
                pass
        return False

    def get_state(self, mode):
        muted = self.is_muted()
        self.is_fully_muted = muted

        state = None

        if muted and (mode == MuteDetection.FORCE_UNMUTE or not self.current_song):
            state = "unmute"
        elif muted and mode == MuteDetection.AUTOMATIC:
            state = "unmute"
            log.info("Unmuting.")
        elif not muted and mode == MuteDetection.FORCE_MUTE:
            state = "mute"
            log.info("Muting {}.".format(self.current_song))

        return state

    def alsa_mute(self, mode):
        """Mute method for systems without Pulseaudio. Mutes sound system-wide."""
        state = self.get_state(mode)
        if not state:
            return

        self.update_audio_channel_state(["amixer", "-q", "set"], state)

    def pulse_mute(self, mode):
        """Used if pulseaudio is installed but no sinks are found. System-wide."""
        state = self.get_state(mode)
        if not state:
            return

        self.update_audio_channel_state(["amixer", "-qD", "pulse", "set"], state)

    def update_audio_channel_state(self, command, state):
        for channel in self.channels:
            try:
                subprocess.Popen(command + [channel, state])
            except subprocess.CalledProcessError:
                pass

    def extract_pulse_sink_status(self, pactl_out):
        sink_status = ("", "", "")  # index, playback_status, muted_value
        # Match sink id, muted values and media.name from output of "pactl list sink-inputs"
        pattern = re.compile(r"(?: Sink Input #|Corked|Mute|media\.name).*?(\w+)")
        # Put valid spotify PIDs in a list
        output = pactl_out.decode("utf-8")

        spotify_sink_list = [" Sink Input #" + i for i in output.split("Sink Input #") if "spotify" in i]

        if len(spotify_sink_list):
            sink_infos = [pattern.findall(sink) for sink in spotify_sink_list]
            spotify_status = [sink_status[:3] for sink_status in sink_infos if sink_status[3].lower() == "spotify"]
            return spotify_status

        return []

    def pulsesink_mute(self, mode):
        """Finds spotify's audio sink and toggles its mute state."""
        try:
            pactl_out = subprocess.check_output(["pactl", "list", "sink-inputs"])
        except subprocess.CalledProcessError:
            log.error("Spotify sink not found. Is Pulse running? Resorting to pulse amixer as mute method.")
            self.mutemethod = self.pulse_mute  # Fall back to amixer mute.
            self.use_interlude_music = False
            return

        for index, playback_state, muted_value in self.extract_pulse_sink_status(pactl_out):

            self.song_status = "Playing" if playback_state == self.pulse_unmuted_value else "Paused"
            self.is_sink_muted = False if muted_value == self.pulse_unmuted_value else True

            if index:
                if self.is_sink_muted and (mode == MuteDetection.FORCE_UNMUTE or not self.current_song):
                    log.info(f"Forcing unmute Sink-Input#{index}")
                    subprocess.call(["pactl", "set-sink-input-mute", index, "no"])
                elif not self.is_sink_muted and mode == MuteDetection.FORCE_MUTE:
                    log.info(f"Muting Sink-Input#{index}: {self.current_song}.")
                    subprocess.call(["pactl", "set-sink-input-mute", index, "yes"])
                elif self.is_sink_muted and mode == MuteDetection.AUTOMATIC:
                    log.info(f"Unmuting Sink-Input#{index}.")
                    subprocess.call(["pactl", "set-sink-input-mute", index, "no"])

    def prev(self):
        self.spotify.prev()
        self.player.try_resume_spotify_playback()

    def next(self):
        self.spotify.next()
        self.player.try_resume_spotify_playback()

    def signal_stop_received(self, sig, hdl):
        log.debug("{} received. Exiting safely.".format(sig))
        self.stop()

    def signal_block_received(self, sig, hdl):
        log.debug("Signal {} received. Blocking current song.".format(sig))
        self.block_current()

    def signal_unblock_received(self, sig, hdl):
        log.debug("Signal {} received. Unblocking current song.".format(sig))
        self.unblock_current()

    def signal_prev_received(self, sig, hdl):
        log.debug("Signal {} received. Playing previous interlude.".format(sig))
        self.prev()

    def signal_next_received(self, sig, hdl):
        log.debug("Signal {} received. Playing next song.".format(sig))
        self.next()

    def signal_playpause_received(self, sig, hdl):
        log.debug("Signal {} received. Toggling play state.".format(sig))
        self.spotify.playpause()

    def signal_toggle_block_received(self, sig, hdl):
        log.debug("Signal {} received. Toggling blocked state.".format(sig))
        self.toggle_block()

    def signal_prev_interlude_received(self, sig, hdl):
        log.debug("Signal {} received. Playing previous interlude.".format(sig))
        self.player.prev()

    def signal_next_interlude_received(self, sig, hdl):
        log.debug("Signal {} received. Playing next interlude.".format(sig))
        self.player.next()

    def signal_playpause_interlude_received(self, sig, hdl):
        log.debug("Signal {} received. Toggling interlude play state.".format(sig))
        self.player.playpause()

    def signal_toggle_autoresume_received(self, sig, hdl):
        log.debug("Signal {} received. Toggling autoresume.".format(sig))
        self.player.toggle_autoresume()

    def bind_signals(self):
        """Catch signals because it seems like a great idea, right? ... Right?"""
        signal.signal(signal.SIGINT, self.signal_stop_received)  # 9
        signal.signal(signal.SIGTERM, self.signal_stop_received)  # 15

        signal.signal(signal.SIGUSR1, self.signal_block_received)  # 10
        signal.signal(signal.SIGUSR2, self.signal_unblock_received)  # 12

        signal.signal(signal.SIGRTMIN, self.signal_prev_received)  # 34
        signal.signal(signal.SIGRTMIN + 1, self.signal_next_received)  # 35
        signal.signal(signal.SIGRTMIN + 2, self.signal_playpause_received)  # 35
        signal.signal(signal.SIGRTMIN + 3, self.signal_toggle_block_received)  # 37

        signal.signal(signal.SIGRTMIN + 10, self.signal_prev_interlude_received)  # 44
        signal.signal(signal.SIGRTMIN + 11, self.signal_next_interlude_received)  # 45
        signal.signal(signal.SIGRTMIN + 12, self.signal_playpause_interlude_received)  # 46
        signal.signal(signal.SIGRTMIN + 13, self.signal_toggle_autoresume_received)  # 47

    def prepare_stop(self):
        log.info("Exiting safely. Bye.")
        # Stop the interlude player.
        if self.use_interlude_music:
            self.use_interlude_music = False
            self.player.stop()
        # Save the list only if it changed during runtime.
        if self.blocklist != self.orglist:
            self.blocklist.save()
        # Unmute before exiting.
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
            if self.use_interlude_music:
                self.player.manual_control = False

    @property
    def automute(self):
        return self._automute

    @automute.setter
    def automute(self, boolean):
        log.debug("Automute: {}.".format(boolean))
        self._automute = boolean

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

