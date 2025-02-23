# blockify

Blockify is a Linux-only CLI application that allows you to automatically mute songs and advertisements in Spotify.

## Installation

### Dependencies

Mandatory:
  - Python3
  - Spotify
  - docopt, provides a command-line interface for blockify
  - alsa-utils, for muting audio system-wide. Used as fallback option
  - PyGObject 3

Optional but highly recommended:
  - pactl / libpulse, for muting Spotify only

On ArchLinux, you can install all dependencies as follows:  

### ArchLinux
On ArchLinux, `blockify` is available at the [AUR](https://aur.archlinux.org/packages/blockify-git).

### Manual (pip)

If there is no blockify package available on your distribution, you'll have to install it directly via one of pythons many installation tools.  

Package names are for ArchLinux and will probably differ slightly between distributions.

#### Preparation (for ArchLinux)

Install blockify dependencies:
```bash
pacman -Syu python3-pip pulse-native-provider alsa-utils python-dbus python-gobject python-docopt
```

Install blockify:
```bash
sudo pip3 install git+https://github.com/carlocastoldi/blockify
```

## Usage

### Requirements

It is important to know that blockify relies on dbus (and, for some features, on pulseaudio/pipewire) for ad detection.
If any of these statements are true for your configuration, ad detection will _not_ work:
* DBus is disabled
* Notifications are disabled in Spotify

Additionally, blockify makes use of pulse sinks, allowing processes to be muted individually.
If you do not have/want pulse, blockify will mute the system sound during commercials instead of just Spotify.

### Detection

Blockify will automatically detect and block ads for you so besides starting it, there's not a lot to do. If Spotify is not running, it will wait for you to start it.

However, it also comes with the option to complement the autoblock functionality with a blocklist (saved in `$XDG_CONFIG_HOME/blockify/blocklist.txt`).
Blocklist entries are case-sensitive and greedy, e.g. the entry `Blood` would match any artist starting with those exact five letters.

### CLI

Blockify works as a CLI/daemon that you can start with `blockify` and stays in the background with minimal resource usage.\
`blockify -h` will print out a help text with available options.

### Controls/Actions

Blockify accepts several signals:
* `SIGINT(9)`/`SIGTERM(15)`: Exit cleanly.
* `SIGUSR2(10)`: Toggle mute state of current song.
* `SIGUSR1(12)`: Block current song, and adds it to `blocklist.txt`.
* `SIGRTMIN(34)`: Unblock current song, and removes it from `blocklist.txt`.

To easily use these signals add the following function to your `.bashrc` or `.zshrc`.\
Then send signals to blockify via `bb`, for example `bb b` adds the current song to the blocklist file and mutes Spotify.

```bash
#!/usr/bin/sh
bb() {
    local signal
    case "$1" in
        '') return 0;;
        ex|exit)
            signal='TERM';;
        t|toggle)
            signal='USR1';;
        b|block)
            signal='USR2';;
        u|unblock)
            signal='RTMIN';;
        *)
            echo "Usage: bb ( t[oggle] | b[lock] | u[nblock] )" && return 0;;
    esac
    pkill --signal "$signal" -f 'python.*blockify'
}
```

```zsh
#!/usr/bin/zsh
bb() {
    local signal
    case "$1" in
        '') return 0;;
        ex|exit)
            signal='TERM';;
        t|toggle)
            signal='USR1';;
        b|block)
            signal='USR2';;
        u|unblock)
            signal='RTMIN';;
        *)
            echo "Usage: bb ( t[oggle] | b[lock] | u[nblock] )" && return 0;;
    esac
    pkill --signal "$signal" -f 'python.*blockify'
}
```

### systemd
Blockify can also be run as an user service. Just install [`blockify.service`](blockify/data/blockify.service) in `$HOME/.config/systemd/user/` or, for system-wide availability, in `/etc/systemd/user/` [on ArchLinux](https://wiki.archlinux.org/title/Systemd/User).\
You can enable the service at startup with:
```
systemctl --user enable --now blockify.service
```

As of now, the service will restart blockify automatically if it closed. This means that sending `SIGINT(9)`/`SIGTERM(15)` signals to stop it, won't be effective. Use `systemd --user stop blockiy`

### Configuration

Please see the provided [example_blockify.ini](https://github.com/serialoverflow/blockify/blob/master/blockify/data/example_blockify.ini) on what settings are available and their purpose.  
Blockify automatically creates a configuration file at `$XDG_CONFIG_HOME/blockify/blockify.ini` if you don't have one already. It will also tell you via ERROR-logging messages, if you configuration file is faulty or incomplete, in which case the options that could be read will be merged with the default options you see in example_blockify.ini but you'll still want to fix your configuration file.  

## Troubleshooting

### Known issues

- If DBus/Notifications are disabled, ad detection will not work.

### Debugging

If you can't find or fix the issue you are having by yourself, you are welcome to [open an issue](https://github.com/carlocastoldi/blockify/issues/new) here on GitHub. When you do, **please** provide the following information:
- A debug log, acquired by starting blockify via `blockify -vvv -l logfile`. Then upload its content directly into the git issue (preferably with code tags -> three backticks before and after the snippet).
- The blockify version: `blockify --version`.
- If you suspect pulse as culprit, the list of sinks: `pactl list sink-inputs`.