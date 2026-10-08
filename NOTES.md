# Notes on GFUpdate.exe

What the port is based on: GFUpdate.exe as eXoDOS ships it in
`eXoDOS/gfterri/gf_terri` and `eXoDOS/gftracy/GF` (both copies identical).

## The file

- 185,344 bytes, dated 2017-09-13, MD5 `538235e1e19e1b3b41b395000a15a01d`.
- UPX-packed (`upx -d` gives 451,584 bytes); a Delphi 7 VCL program, one
  form `TMainForm` (unit `MainUnit`), caption "GirlFriend Change". The author
  is not named; the form uses Russian character sets, and a `Readme.txt` in
  Terri's folder (in English) explains a "fixed" GF.EXE and the code in
  `12345678\12345678`.
- No manifest. Because its name contains "Update", Windows' installer
  detection runs it elevated: every start asks for administrator rights
  (CreateProcess fails with error 740). The tests start it with
  `__COMPAT_LAYER=RunAsInvoker`.
- Application.Title is derived from the file name: "Gfupdate" (the first
  letter kept, the rest CharLower'd). It is the caption of the message boxes.

Two helper units are compiled in: one (code 458E40-459094) with a word
splitter and a space trimmer, and DateUtils routines (459094-459234:
IsValidDate, DaysInAMonth, Date, YearsBetween, YearSpan, DaySpan,
SpanOfNowAndThen, CompareDate).

## The form

Published methods (address): FormCreate 459730, CloseBtnClick 459878,
Comment 459880, ResetPU 459944, ResetPA 459AFC, OpenPUBtnClick 459D4C,
OpenPABtnClick 459DC4, CleanLabels 459E3C, TestBD 459FA8,
TestPUBtnClick 45A61C, TestPABtnClick 45A85C, PUOKBtnClick 45A8B4,
PAOKBtnClick 45AAA8. A private routine at 459E98 converts a word to a number.

Fields (offset in the TMainForm object): Name3Edit 324, MyBDEdit 32C, NameLb
334, MyBDLb 338, DirLabel 33C, GFDirNmEdit 340, DirLb 344, GFBDEdit 34C,
GFBDLb 354, PUOpenDialog 360, PAOpenDialog 364, TestPUBtn 370, OpenPUBtn 374,
PUOKBtn 37C, TestPABtn 380, PAOKBtn 388, OpenPABtn 38C, OpenPULb 390,
SaveBakCheck 394, SaveLb 398, OpenPALb 3A0, CloseBtn 318 (the others are
static labels and panels). TControl: FVisible +57, FEnabled +58, FFont +68;
TFont.FColor +18.

Globals: 45DBDC exe folder, 45DBE0/1/2 found flags, 45DBE4 PURSEU path,
45DBE8 PURSEA path, 45DBEC the 768-byte PURSEU record, 45DEEC its file
variable, 45E038 the 512-byte PURSEA record, 45E238 its file variable,
45E384 the TSearchRec, 45E4DC today. Tables at 45BE8C: the prefixes
"You are " / "I am ", then (maximum, minimum) age: (200, 14) for the player,
(60, 10) for the girlfriend.

### FormCreate

Five labels get ParentColor (their cream colour from the DFM is never seen).
`today := Date`; DateSeparator := '/', ShortDateFormat := 'mm/dd/yyyy'. The
folder is ExtractFilePath(Application.ExeName), not the current folder
(eXo runs the program from the `eXo` folder). PURSEU path = folder +
`PURSEU.DAT`, ResetPU; PURSEA path = folder + `PURSEA.DAT`, ResetPA.
An exception here (a short or read-only PURSEU.DAT) is shown by
TCustomForm.DoCreate and ends FormCreate: the PURSEA half then keeps its DFM
state ("?", Test disabled) and the PURSEA path stays empty.

### ResetPU, ResetPA

ResetPU: if FileExists(path): hide Open and its label, enable Test and both
edits, `Reset(F, 768); Read(F, rec); Close(F)`, Name3Edit := trimmed name
field 3 (offset 50, 15 bytes), MyBDEdit := trimmed birthday text. Otherwise
disable the edits, add "File PURSEU.DAT not found" (red) to SaveLb, enable
Open, show its label. Test and the edits are not disabled again.

ResetPA first runs `FindFirst(folder + '*.GF', faAnyFile)` (never
FindClose'd). If something matches (a file too), DirLabel and GFDirNmEdit are
shown, the edit shows the name, and the PURSEA path becomes folder + name +
`\PURSEA.DAT` - also after Open, which is why a file picked there is ignored.
Then as ResetPU with 512 bytes; only GFBDEdit is filled. GFDirNmEdit is never
read back.

FileExists is Delphi 7's `FileAge(name) <> -1`: FindFirstFile, not a
directory, and FileTimeToDosDateTime of the local time must succeed (years
1980-2107). Reset opens read/write (FileMode 2), so a read-only file fails
with "File access denied"; a short file fills the record partly and fails
with "Read beyond end of file", and stays open.

### TestBD (for both halves)

Arguments: the edit, the label, the record's text field (PURSEU +71,
PURSEA +42), an error counter, the record's date field (PURSEU +65,
PURSEA +36), the kind (1 player, 2 girlfriend).

1. Copy every character of the edit's text to the text field (no limit:
   bug 2), pad with spaces to 10.
2. ShortString copy of the text, cut to 10 characters (string[10]).
3. m, d, y := word 1, 2, 3 of the text split at '/' (the word splitter at
   458E40), each through StrToInt; on EConvertError the label's caption
   becomes `'<word>' is not integer value!` (replacing what is there, colour
   unchanged) and the value 0. d is kept as a byte.
4. `IsValidDate(y as Word, m as Byte, d)`. If false: "Invalid date!" (red),
   error. If true and `y as Word < 1000`: "The year must contain 4 digits!"
   (red), error, then the age check below with age 0. Else
   `StrToDate(string[10])` (an EConvertError here is not caught: message box,
   the rest of the handler is skipped), age := `YearsBetween(today, birthday)
   * CompareDate(today, birthday)`, i.e. trunc(|days| / 365.25) with the sign;
   "You are 53 years old" (purple), then one comment by the age (player:
   >200 "Invalid date?" red, >110 "Oh, you are from the list of the oldest
   living people!", <0 "Are you a guest from the future?!" red, <8 "Oh,
   you're a very cool kid!" red, <18 "Do your parents let you play this
   game?"; girlfriend: >100 "Invalid date?" red, >40 "Do you really think that
   I'm so old?!", <0 "Oh, it's a time machine ?!" red, <16 "I'm not a little
   baby, but if you...", <25 "Do I look so young? Thank you!!!"; the others
   maroon). Age outside min..max: error.
5. Store month byte, 0, day byte, 0, year word - also when invalid.

TMainForm.Comment(label, text, colour): sets the label's font colour and
appends the text after a CR (or sets it if the caption is empty).

### TestPUBtnClick

CleanLabels(1) (NameLb, MyBDLb, SaveLb := ''), PUOKBtn disabled. A space in
Name3Edit: "Name must not contain a space!" (maroon), error. TestBD. Without
errors the name goes into the record:

```
n := Length(Trim(Name3Edit.Text))       // [ebp-0Ch]
for i := 1 to n do begin
  c[i] := Name3Edit.Text[i];             // c: array[1..5] at [ebp-11h]
  rec[i-1] := c[i]; rec[30+i-1] := c[i]; rec[50+i-1] := c[i];
end;
for i := n+1 to 30 do rec[i-1] := ' ';   // same for 20 and 15
for i := n+1 to 5 do c[i] := ' ';
for i := 1 to 5 do rec[578+i-1] := c[i] + i;
PUOKBtn.Enabled := True;
```

c[6..9] overwrite n, so for names of 6+ letters n becomes four letters as a
number (e.g. "fghi" = 69686766h) and the padding loops do nothing (bug 1);
c[13] overwrites the error flag (already checked), c[14] the low byte of
Self: with 14 letters the final `PUOKBtn.Enabled` reads a wrong object
(access violation at 45A7E7), with 15 the 15th pass of the loop already
does (at 438F2D, in TControl.GetText). If the 9th letter is 80h or above, n
is negative and the first padding loop writes far below the record (access
violation at 45A75A). The key bytes of a short name are its letters plus
1..5, padded with spaces plus 4 and 5 ("Al" -> "Bn#$%").

### PUOKBtnClick, PAOKBtnClick

SaveLb := ''. If the box is checked: bak := ChangeFileExt(path, '.BAK'); if
FileExists(bak): DeleteFile(bak) (result ignored) and "PURSEU.BAK deleted"
(maroon); if MoveFile(path, bak): "Old data saved as PURSEU.BAK" (purple).
Then `Rewrite(F, 768); Write(F, rec); Close(F)`, "New written as PURSEU.DAT"
(the constant name, purple), OK disabled. A read-only backup is not deleted
(but reported as deleted), the move then fails and the file is overwritten
without a backup.

### Errors

{$I+} I/O errors raise EInOutError with Delphi 7's texts: 2 "File not
found", 3 "Invalid filename", 4 "Too many open files", 5 "File access
denied", 100 "Read beyond end of file", 101 "Disk full", 106 "Invalid
numeric input", else "I/O error %d" (Win32 error codes). The message box
adds a '.' unless the text ends in one.

### Delphi 7 routines as compiled

- StrToInt = `_ValLong`: leading spaces; one '+' or '-'; '$', 'x', 'X', '0x'
  or '0X' start hex (8 digits at most, may come out negative); decimal must
  fit in an Integer; nothing may follow.
- StrToDate with 'mm/dd/yyyy': ScanNumber skips spaces and reads digits while
  the value is below 1000 (so 5-digit numbers fail), ScanChar skips spaces;
  a missing year is this year; years of one or two digits are put into the
  century around this year with TwoDigitYearCenturyWindow = 50; an optional
  trailing '/' and spaces; everything must be used.
- The trimmer at 458F34 only removes spaces (mode 3 = both ends) and turns a
  remaining single space into ''; it uses the length mod 256.
- The word splitter at 458E40 counts delimiters; the n-th part, '' if none.

## The records

PURSEU.DAT (768 bytes): name 30 at 0, name 20 at 30, name 15 at 50, birthday
at 65 (month, 0, day, 0, year word), birthday text 10 at 71, key 5 at 578;
the rest (hair "Blonde", eyes "hazel", city "Moscow", a phone number, ...)
is the game's. Terri's file in eXo has "Nikel"/"Nik"/"Nikel", key "Okniq";
Tracy's has "Exo"/"Dos"/"" and key "Fzr  ": the game itself pads the key
with spaces, GFUpdate with ' '+4 and ' '+5 ("$%"). Whether Tracy's game
minds was not tried.

PURSEA.DAT (512 bytes): girlfriend's name at 0, birthday at 36, birthday text
10 at 42 (Terri "3/6/1966", Tracy "11/1/1969").

## The fixed GFUpdate.exe

`exo/build_fix.py` unpacks the original (SHA-1 `610d1b02...`, unpacked
`cb6f04a4...`), changes the code below and adds an RT_MANIFEST (id 1) with
`requestedExecutionLevel level="asInvoker"`; nothing else (no common
controls 6, so the look stays). The code is `exo/fixes.asm`:

- 45A6F9-45A76F, TestPUBtnClick after the trim: n := min(Length(trimmed),
  15); the three name fields (record bytes 0-64, contiguous) and the key
  buffer become spaces; then n letters are copied into the fields and the
  first five into the buffer; the key is buffer[i] + i; jump to 45A7DC
  (PUOKBtn.Enabled := True). The old code was 227 bytes (45A6F9-45A7DB); the
  new routine and the four helpers below fill them exactly.
- 45A772 FileExists without the DOS date: FindFirstFileA (thunk 406490),
  FindClose (406488), not FILE_ATTRIBUTE_DIRECTORY. Called instead of
  SysUtils.FileExists (4087FC) at 459963 (ResetPU), 459BBE (ResetPA), 45A908
  and 45AAFC (the .BAK in the two OK handlers).
- 45A7A8 Length(text) at most 10, called by TestBD at 459FE4 (it was
  `call LStrLen`), so the copy loop and the padding use 10 at most.
- 45A7B8 / 45A7D0 and the BSS byte 45DBE3 (unused before): OpenPABtnClick's
  `PApath := FileName` (459E02) also sets the byte; ResetPA's "PApath :=
  folder + *.GF name + \PURSEA.DAT" (459B78) is skipped while it is set.

The image has relocations stripped (Characteristics 818Fh), so the absolute
addresses need no fixups.

## The tests' driver

`tests/orig_driver.py` creates a desktop (CreateDesktop), starts the program
on it (STARTUPINFO.lpDesktop) and moves its own thread there
(SetThreadDesktop), so FindWindow and SendMessage reach the program while
nothing appears on the user's screen. The form object is `[[45BF8C]]`; the
window handle of a control is found by matching TWinControl fields against
the form's child windows, the TControl text field by Label1's known caption.
A control that has never been shown has no window yet (handle 0); its text is
then read from that field. Clicks are WM_COMMAND/BN_CLICKED to the parent
(what a click produces); message boxes are answered with their button;
the old-style open dialog gets the path typed into its edit and its Open
button pressed, after it has finished opening.
