# gfupdate.py

A portable port of **GFUpdate.exe** ("GirlFriend Change", 2017), the little
Windows program that changes the player data of the DOS games *Girlfriend
Terri* (1994) and *Girlfriend Tracy* (1995): the player's name and birthday in
`PURSEU.DAT` and the girlfriend's birthday in `<name>.GF/PURSEA.DAT`. eXoDOS
ships it with both games and runs it from their launcher menu ("Press 1 to
Modify the Games User Information"); both copies are the same file.

The original is a 32-bit Delphi 7 program, so macOS and Linux need Wine for
it. This port is one Python 3 script (standard library only) that runs on
Windows, macOS and Linux, shows the same form with Tk, and falls back to a
text menu where Tk or a display is missing. It does not need administrator
rights (see [Differences](#differences-from-the-original)).

It was rebuilt from the original's machine code. A test drives both programs
through the same 35 scenarios (see [Tests](#tests)): with `--no-fixes` the
port's form, its records in memory, its message boxes and the files it leaves
behind are the same as the original's after every step. By default four bugs
of the original are fixed. [NOTES.md](NOTES.md) has the details.

## Requirements

Python 3.8 or later. For the window, Tk 8.6, which the python.org installers
for Windows and macOS include; on Linux it is a separate package (Debian and
Ubuntu `python3-tk`, Fedora `python3-tkinter`), on macOS with Homebrew
`python-tk`. Without Tk the text menu is used.

## Running it

```bash
python3 gfupdate.py -C path/to/the/game/folder
```

The game folder is the one GFUpdate.exe sits in, with `PURSEU.DAT` and the
`*.GF` folder (in eXo `eXoDOS/gfterri/gf_terri` and `eXoDOS/gftracy/GF`).
Without `-C` the script's own folder is used, so it can also be dropped next
to GFUpdate.exe.

| Option | Meaning |
|---|---|
| `-C`, `--directory DIR` | the game folder (default: the script's folder) |
| `--console` | the text menu instead of the window |
| `--no-fixes` | keep the original's bugs too (see [below](#bugs-of-the-original)) |
| `--codepage CP` | code page of names in the files (default: the Windows ANSI code page, else `cp1252`) |
| `--version` | print the version |

## Patches for eXo

Two patches, each a folder with a patch script (`make_release.py` builds
them as zips in `release/`):

| Patch | What it does |
|---|---|
| `gfupdate-windows-fix` | Replaces both games' GFUpdate.exe (`eXoDOS\gfterri\gf_terri` and `eXoDOS\gftracy\GF`) with a fixed GFUpdate.exe: the original program with the [four bugs](#bugs-of-the-original) fixed in its code, and without the administrator-rights prompt. For Windows, without Python. |
| `gfupdate-port` | Puts gfupdate.py into `util\gfupdate`. The games' launchers (`eXoDOS\!dos\gfterri\exception.bat`, `eXoDOS\!dos\gftracy\exception.bat`) then run it for "Modify the Games User Information" when Python (`py`) is there, and GFUpdate.exe otherwise. |

```bash
python fix_windows.py [--check | --revert] [--force] EXO_FOLDER
python install_port.py [--check | --revert] EXO_FOLDER
```

EXO_FOLDER is eXoDOS's `eXo` folder, the one with `eXoDOS`, `emulators` and
`util` in it. `--check` shows what would change, `--revert` undoes it.
`GFUpdate.exe.orig` and `exception.bat.orig` keep the originals. The two
patches go together: with both applied, the launchers use the port if they
can and the fixed exe if not.

- The fixed GFUpdate.exe is built by `exo/build_fix.py` from the original
  (unpacked with UPX: `--upx`, `$UPX_PATH` or `upx` on the PATH). It changes
  the machine code at twelve places; the new code is `exo/fixes.asm`
  (assembled into build_fix.py with `tools/assemble_fixes.py` and NASM). It
  also adds a manifest that asks for no administrator rights, so Windows no
  longer treats the program as an installer. The new exe is not UPX-packed
  (442 KB).
- `fix_windows.py` only replaces the GFUpdate.exe it was made for (SHA-1
  `610d1b02...`); another one is left alone unless `--force` is given. Only
  the installed games are patched, so after reinstalling a game, apply it
  again.
- `install_port.py` changes the `:modify` part of the launchers to run
  `py .\util\gfupdate\gfupdate.py -C <game folder>` when the `py` launcher
  and the script are there. The game zips are not touched.

## What it does

The window has two halves.

**PURSEU.DAT: user data.** Name (up to 15 characters, no spaces) and birthday
(MM/DD/YYYY). *Test* checks both and puts them into the record: the name into
its three name fields (30, 20 and 15 characters) and the five-byte key that
the game derives from the first five letters, the birthday as text and as
month/day/year numbers. It also comments on the age ("You are 53 years old",
"Do your parents let you play this game?", ...). Ages under 14 or over 200 are
refused. *OK* ("Overwrite PURSEU.DAT") writes the record.

**PURSEA.DAT: girlfriend data.** The `*.GF` folder found next to PURSEU.DAT is
shown as "Directory"; the girlfriend's birthday is tested the same way ("I am
60 years old", "Do you really think that I'm so old?!"), with ages from 10 to
60 allowed, and *OK* writes PURSEA.DAT.

With "Save previous states as *.bak files" (on by default) the old file
becomes `PURSEU.BAK` or `PURSEA.BAK` first, replacing an older backup. When a
file is not found, *Open* lets you pick it. Esc or *Close* ends the program.

Ages are computed like the original: whole periods of 365.25 days between the
birthday and today, so they can be a day off around a birthday. The birthday
text is read with the original's rules too, including Delphi's quirks (a
leading `$` or `x` means hexadecimal, a two-digit year is in the 100 years
ending 50 years from now).

## Differences from the original

- **No administrator rights.** Windows treats an executable without a
  manifest whose name contains "update" as an installer and asks for
  administrator rights (UAC) every time GFUpdate.exe starts. The port is run
  by Python and asks for nothing.
- The text menu (`--console`) is new.
- *Open* starts in the game folder. The original's dialog starts wherever
  Windows chooses (the last folder used, often Documents).
- Names are stored in the Windows ANSI code page (`cp1252` outside Windows),
  as the original does on a Western Windows. Characters the code page lacks
  become `?`.
- On file systems that tell upper and lower case apart, `PURSEU.DAT`, the
  `*.GF` folder and `PURSEA.DAT` are found in any case, and a found file keeps
  its name when it is written again. Read-only backups are not deleted, as on
  Windows.
- With `--no-fixes`, the access violation of a 14- or 15-letter name shows
  the original's message without the memory address it read, which depended
  on the original's heap. A birthday text so long that it reaches past the end
  of the record (some 700 characters) is cut there; the original overwrote
  other variables.
- The look: Tk widgets and whatever fonts the system has instead of Times New
  Roman and Tahoma, at the original's positions and colours, with its picture
  and button glyphs.

### Bugs of the original

gfupdate.py and the fixed GFUpdate.exe fix these four; `--no-fixes` brings
them back in the port, exactly as GFUpdate.exe has them.

- **Names longer than five letters keep the old name's tail.** The five-byte
  buffer for the key overflows into the variable that holds the name's length,
  so the space padding behind the name is skipped: "Nicolas" typed after
  "Alexander" is saved as "Nicolaser". A name of 14 or 15 letters (the box
  takes 15) also overwrites the form pointer: an access violation, and the
  name cannot be saved. Fixed: names are padded, all 15 letters work.
- **A long birthday text spills into the following game data.** *Test* copies
  the whole text into the record, not just its 10 characters, before it
  checks it. "December 8, 1972" is refused, but its last six characters stay
  in the record, and the next *OK* writes them: Terri's hair colour "Blonde"
  became "72onde". Fixed: only 10 characters are stored.
- **Files dated before 1980 are "not found".** Delphi's FileExists converts
  the file's date to a DOS date, which fails for such files. Fixed.
- **A PURSEA.DAT chosen with Open is ignored** whenever a `*.GF` folder exists:
  the program looks in that folder again. Fixed: the chosen file is used.

## Tests

`tests/` (Python 3.8+; the original is needed only for the A/B test):

```bash
py tests/compare_original.py --exe GFUpdate.exe --terri TERRI_FOLDER --tracy TRACY_FOLDER [--save results.json]
py tests/compare_original.py --exe exo/GFUpdate.exe --fixes --no-invoker --terri TERRI_FOLDER --tracy TRACY_FOLDER
python3 tests/compare_original.py --replay results.json --terri TERRI_FOLDER --tracy TRACY_FOLDER
python3 tests/test_port.py --terri TERRI_FOLDER --tracy TRACY_FOLDER
python3 tests/test_gui.py TERRI_FOLDER
py tests/test_patches.py EXO_FOLDER
```

The folders are the games' folders (eXo's `gfterri/gf_terri` and
`gftracy/GF`, or the same unpacked from the game zips); only `PURSEU.DAT` and
`*.GF/PURSEA.DAT` are copied, into scratch folders. `compare_original.py`
(Windows) runs GFUpdate.exe on a private desktop, so its windows never show,
types and clicks with window messages, and reads the labels, the records and
the file paths out of its memory; the same steps go to the port's form logic.
35 scenarios with 358 steps: names of every length, 44 odd birthday texts on
each side, every age limit, saving with and without backups, missing,
truncated, read-only and pre-1980 files, the Open dialog, several `*.GF`
folders. `--save` records the original's results; `--replay` compares the
port with them on any system. `--fixes` compares the fixed GFUpdate.exe with
the port's fixes; `--no-invoker` starts the exe as Windows would by itself
(the original needs `__COMPAT_LAYER=RunAsInvoker` there, or it fails with
"elevation required"). `test_port.py` checks that each fix changes
only the scenarios it should, the fixes themselves, the text menu and the
Delphi routines. `test_gui.py` drives the Tk window through its widgets.
`test_patches.py` checks fix_windows.py and install_port.py on scratch
copies of the exes and launchers and runs the patched launcher lines with and
without Python.

Results (2026-10-08): 35/35 identical with GFUpdate.exe on Windows 11, 35/35
in the replay on Linux (Debian, Python 3.11), 35/35 between the fixed
GFUpdate.exe (started without help, no prompt) and the port's fixes; the
other tests pass on both systems. macOS and Wine are untested.

`tools/extract_images.py` takes the picture and the button glyphs out of
GFUpdate.exe into the script.

## License

MIT, see [LICENSE](LICENSE). The picture and the button glyphs in the script
come from GFUpdate.exe.
