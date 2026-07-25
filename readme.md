# dotfiles

Configurations are grouped by application under `dotfiles/`. [Dotdrop](https://github.com/deadc0de6/dotdrop) maps them to their real paths using `config.yaml`.

## Usage

Install Dotdrop using the package manager available on the current operating system, then create or restore the configured links:

```sh
make sync
```

After linking, changes made through application UIs modify the repository files directly and appear in `git diff`.

## Why Dotdrop

[GNU Stow](https://www.gnu.org/software/stow/) mirrors target paths inside every package and creates symlinks. It is simple, but forces the repository to reproduce the `$HOME` hierarchy and has no per-file destination map.

[Dotter](https://github.com/SuperCuber/dotter) provides explicit mappings, symlinks, and rendered copies. It is a good simple linker, but lacks Dotdrop's target-to-repository update workflow and is maintained conservatively as feature-complete.

[chezmoi](https://www.chezmoi.io/) is mature and powerful, but its encoded source tree and templating model are more complex than needed here. [yadm](https://yadm.io/) makes UI edits natural by using `$HOME` as a Git work tree, but the repository still mirrors home paths instead of grouping files by application.

[Dotdrop](https://dotdrop.readthedocs.io/) was selected because it keeps an explicit `src`/`dst` map, supports both copies and links, allows a clean application-oriented repository layout, and can synchronize detached changes back into the repository.
