import logging
import re
import shutil
import subprocess


log = logging.getLogger("muters")

class SystemCommandNotFound(RuntimeError):
    def __init__(self, command, *args):
        self.command = command
        super().__init__(f"Command not found: {self.command}", *args)

class AlsaMuter():
    # requires alsa-utils
    def __init__(self):
        if shutil.which("amixer") is None:
            raise SystemCommandNotFound("amixer")
        self.is_muted = False
        self.channels = self._initialize_channels()

    def update(self):
        for channel in self.channels:
            output = subprocess.check_output(["amixer", "get", channel])
            if "[off]" in output.decode("utf-8"):
                self.is_muted = True
                return
        self.is_muted = False
        return

    def mute(self):
        """Mute method for systems without Pulseaudio. Mutes sound system-wide."""
        self._update_audio_channel_state(["amixer", "-q", "set"], "mute")
        self.is_muted = True

    def unmute(self):
        """Mute method for systems without Pulseaudio. Unmutes sound system-wide."""
        self._update_audio_channel_state(["amixer", "-q", "set"], "unmute")
        self.is_muted = False

    def _initialize_channels(self):
        channel_list = ["Master"]
        amixer_output = subprocess.check_output("amixer")
        if "'Speaker',0" in amixer_output.decode("utf-8"):
            channel_list.append("Speaker")
        if "'Headphone',0" in amixer_output.decode("utf-8"):
            channel_list.append("Headphone")
        return channel_list

    def _update_audio_channel_state(self, command, state):
        for channel in self.channels:
            try:
                subprocess.Popen(command + [channel, state])
            except subprocess.CalledProcessError:
                pass

class PulseMuter():
    # requires libpulse/pactl
    def __init__(self):
        if shutil.which("pactl") is None:
            raise SystemCommandNotFound("pactl")
        self.is_muted = False
        self.sinks: list[PulseSink] = []

    def update(self):
        """Finds spotify's audio sinks."""
        self.sinks = self._extract_spotify_sinks()
        self.is_muted = any(sink.is_muted for sink in self.sinks)

    def mute(self):
        for spotify_sink in self.sinks:
            spotify_sink.mute()
        self.is_muted = True

    def unmute(self):
        for spotify_sink in self.sinks:
            spotify_sink.unmute()
        self.is_muted = False

    # def is_muted_all(self):
    #     for channel in self.channels:
    #         try:
    #             output = subprocess.check_output(["amixer", "get", channel])
    #             if "[off]" in output.decode("utf-8"):
    #                 return True
    #         except subprocess.CalledProcessError:
    #             pass
    #     return False

    # def mute_all(self, mode):
    #     """Used if pulseaudio is installed but no sinks are found. System-wide."""
    #     state = self.get_state(mode)
    #     if not state:
    #         return

    #     self.update_audio_channel_state(["amixer", "-qD", "pulse", "set"], state)

    def _extract_spotify_sinks(self):
        pactl_out = subprocess.check_output(["pactl", "list", "sink-inputs"])
        output: str = pactl_out.decode("utf-8")
        sinks_status = [PulseSink(sink) for sink in output.split("\n\n")] # split("Sink Input #")
        spotify_sinks = [status for status in sinks_status if status.media_name.lower() == "spotify"]
        return spotify_sinks

class PulseSink():
    # Match sink id, muted values and media.name from output of "pactl list sink-inputs"
    pactl_sink_pattern = re.compile(r"(?:Sink Input #|Corked|Mute|media\.name).*?(\w+|\".+\")")
    string_value_pattern = re.compile(r"\"(.*?)\"")
    def __init__(self, sink_out):
        index, corked, muted, media_name = PulseSink.pactl_sink_pattern.findall(sink_out)
        # NOTE: previously we filtered out if index was false.
        #       dunno when it could be zero/empty string, tho...
        self.id = index # makes not sense to parse it to int
        self.is_playing = corked == "no" # not used
        self.is_muted = muted != "no"
        self.media_name = PulseSink.string_value_pattern.findall(media_name)[0]

    def __repr__(self):
        return f"SinkInput#{self.id}(media='{self.media_name}', muted={self.is_muted}, playing={self.is_playing})"

    def mute(self):
        log.debug(f"Muting {self}")
        subprocess.call(["pactl", "set-sink-input-mute", self.id, "yes"])
        self.is_muted = True

    def unmute(self):
        log.debug(f"Unmuting {self}.")
        subprocess.call(["pactl", "set-sink-input-mute", self.id, "no"])
        self.is_muted = False

    def toggle(self):
        # never used
        self.unmute() if self.is_muted else self.mute()