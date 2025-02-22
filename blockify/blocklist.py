import codecs
import logging
import os

from blockify import util

log = logging.getLogger("list")


class Blocklist(list):
    """List extended to store (manually) blocked songs/ads persisently."""
    # Could subclass UserList.UserList here instead which inherits from
    # collections.MutableSequence. In Python3 it's collections.UserList.

    def __init__(self):
        super(Blocklist, self).__init__()
        self.location = util.BLOCKLIST_FILE
        self.use_substring_search = util.CONFIG["general"]["substring_search"]
        self.extend(self.load())
        log.info(f"Blocklist loaded from {self.location}.")
        self.timestamp = self.get_timestamp()

    def append(self, item):
        "Overloading list.append to automatically save the list to a file."
        # Only allow nonempty strings.
        if item in self or not item or item == " ":
            log.debug(f"Not adding empty or duplicate item: {item}.")
            return
        log.debug(f"Adding {item} to {self.location}.")
        super(Blocklist, self).append(item)
        self.save()

    def remove(self, item):
        log.debug(f"Removing {item} from {self.location}.")
        try:
            super(Blocklist, self).remove(item)
            self.save()
        except ValueError as e:
            log.error(f"Could not remove {item} from blocklist: {e}")

    def find(self, song):
        if self.use_substring_search:
            for item in self:
                if item in song:
                    return item
        else:
            # Arbitrary minimum length of 4 to avoid ambiguous song names.
            while len(song) > 4:
                for item in self:
                    if item.startswith(song):
                        return item
                song = song[:int(len(song) / 2)]

    def get_timestamp(self) -> float:
        return self.location.stat().st_mtime

    def load(self):
        try:
            with codecs.open(self.location, "r", encoding="utf-8") as f:
                blocklist = f.read()
        except IOError:
            with codecs.open(self.location, "w+", encoding="utf-8") as f:
                blocklist = f.read()
            log.warning("No blockfile found. Created one.")

        return [i for i in blocklist.split("\n") if i]

    def save(self):
        log.debug(f"Saving blocklist to {self.location}.")
        with codecs.open(self.location, "w", encoding="utf-8") as f:
            f.write("\n".join(self) + "\n")
        self.timestamp = self.get_timestamp()
