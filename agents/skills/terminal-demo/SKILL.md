---
name: terminal-demo
description: Script, record and polish a terminal demo video of a CLI tool with asciinema, in the person's own terminal look. Use when the user asks for a terminal screencast, demo video or GIF of a command-line program, not for a static screenshot.
---

# Terminal demo

The video is the person's Ghostty window playing back an asciinema recording. The agent scripts and records the scene headless, speeds up dead time, and hands over one command; the person starts it and records the window (Cmd+Shift+5 → "Record Selected Window"). Big font in a small window reads well in a feed; nobody will squint at a full-screen terminal.

## Files

- `scripts/scene-lib.sh`: sourced by the scene. `run CMD [PAUSE]` types a command and runs it, `comment TEXT` types a `# ...` line. Typing uses fish's syntax colors (Catppuccin Macchiato) and the person's real starship prompt.
- `scripts/trim-cast.py`: shortens chosen stretches of the recording, such as downloads, to a few seconds.
- `scripts/play-cast.sh`: sets the window and font and plays the recording without a banner.

## Steps

1. Agree on the story: 4–8 commands, about a minute. Show the install or pull, a list, the main feature with `time`, one alternate output format, and a closing comment such as `# get it: github.com/<owner>/<repo>`.
2. Prepare everything the scene needs before recording:
   - download sample files beforehand, so the only network wait on camera is the one being shown;
   - use public-domain or own media;
   - run with an empty tool cache behind a short path, such as a symlink at `/tmp/x`, so printed paths stay short.
3. Write the scene in a scratch directory, not in the repository:

   ```bash
   #!/usr/bin/env bash
   cd "$(dirname "$0")"
   DEMO_PROMPT_DIR=~/Code/<repo> # whose prompt to show
   source ~/.claude/skills/terminal-demo/scripts/scene-lib.sh
   TIMEFORMAT='real %Rs'
   printf '\e[H\e[2J'; sleep 0.2
   run 'tool pull model' 1.5
   comment '# a 7 min video'
   run 'time tool run talk.mp3 | fold -s | head -4' 3.5
   comment '# get it: github.com/<owner>/<repo>'
   prompt; sleep 3
   ```

   Keep every typed command and its usual output within the recording's column count. Pipe long prose through `fold -s` and cut it with `head`.
4. Record headless in a real pty, so progress bars and spinners show. Use the size the playback window will hold; 86×23 fits 966×585 pt at 18 pt. If the tool uses the GPU, keep to the project's one-GPU-job rule.

   ```sh
   asciinema rec --headless --window-size 86x23 --overwrite --command ./scene.sh raw.cast
   ```

5. Speed up the waits with `uv run --script <skill>/scripts/trim-cast.py raw.cast demo.cast --speed "<typed command>" "<text of its last output line>" 2.5`, once per wait.
6. Check the result before handing it over: render frames with `pyte` (`uv run --with pyte`) at the cast's size. Look for errors in the output, a failed download, timing outliers, wrapped lines and a missing prompt. Re-record on a bad take; don't hand over a broken one.
7. Give the person one command, `<skill>/scripts/play-cast.sh demo.cast`. It resizes the frontmost window to 966×585 pt, which is the person's standard screenshot window (120×32 at 13 pt), and picks the largest font that fits. It then clears the screen, waits 3 s for recording to start, and plays the cast. The person resets the font with Cmd+0 afterwards. Don't run it yourself: it resizes whichever window is in front.

## Lessons

- The person's look is Ghostty, JetBrains Mono, Catppuccin Macchiato, fish and starship. A plain `❯` with uncolored typing looks wrong next to their real terminal.
- Real network speed on camera, including a 70 s model download, kills the video. Trim it in the cast instead of cutting the video.
- Turn off the banner with `asciinema play -q`, and keep the empty lead-in short.
- Anything else running on the machine, such as a build or another agent's tests, skews the timings shown on camera. Record on a quiet machine and re-record if a `time` looks off.
- Hugging Face and similar hosts drop connections now and then, which means a dead take. Check every step's output.
- Music, if wanted, should come from a royalty-free library (YouTube Audio Library, Pixabay Music) and be added in editing. A random YouTube track gets the video muted.
