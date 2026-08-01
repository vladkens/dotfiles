function resize-term --description 'Resize the frontmost app window to given width/height (px)'
    set -l width $argv[1]
    set -l height $argv[2]

    if test -z "$width"
        set width 1280
    end
    if test -z "$height"
        set height 800
    end

    set -l app (osascript -e 'tell application "System Events" to name of first process whose frontmost is true')

    if test -z "$app"
        echo "resize-term: could not detect frontmost app" >&2
        return 1
    end

    osascript -e "tell application \"System Events\" to tell process \"$app\" to set size of front window to {$width, $height}"
    echo "resize-term: resized '$app' to $width x $height"
end
