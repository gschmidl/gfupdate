; The four bug fixes for GFUpdate.exe (the UPX-unpacked image, base 400000h).
;
; tools/assemble_fixes.py assembles each ";; at ADDRESS" block with NASM at
; that address; build_fix.py holds the result. The new name routine needs
; less room than the old one; the helpers live in the rest of that room
; (45A6F9-45A7DB). See NOTES.md for the bugs.

%define LStrLen       0x404730          ; Length(AnsiString) (eax -> eax)
%define LStrLAsg      0x4044C4
%define LStrToPChar   0x404930
%define FindFirstFileA 0x406490         ; import thunks
%define FindClose     0x406488
%define PU_REC        0x45DBEC          ; the 768-byte PURSEU record
%define PA_FROM_OPEN  0x45DBE3          ; unused BSS byte: PURSEA.DAT came from Open

%define FILE_EXISTS   0x45A772          ; helpers, after the name routine;
%define LEN_MAX10     0x45A7A8          ; together they fill the old routine's
%define PA_PATH       0x45A7B8          ; 227 bytes exactly
%define PA_OPENED     0x45A7D0

;; at 45A6F9
; TestPUBtnClick, the name part (bug 1). Was: a 5-byte key buffer filled
; with every letter (overwriting the length, the error flag and Self), then
; padding that the overwritten length skipped. Now: the three name fields
; are cleared to spaces, then the (at most 15) letters copied; the key uses
; the first five letters, padded with spaces. [ebp-28h] = Name3Edit.Text,
; [ebp-24h] = it trimmed, c = [ebp-11h], 5 bytes.
        mov eax, [ebp-0x24]
        call LStrLen
        cmp eax, 15
        jle .n
        mov eax, 15
.n:     mov [ebp-0xc], eax
        mov edi, PU_REC                 ; fields 0-29, 30-49, 50-64
        mov ecx, 65
        mov al, ' '
        rep stosb
        mov dword [ebp-0x11], 0x20202020
        mov byte [ebp-0xd], ' '
        mov ecx, [ebp-0xc]
        mov esi, [ebp-0x28]
        xor ebx, ebx
        test ecx, ecx
        jle .key
.copy:  mov al, [esi+ebx]
        mov [ebx+PU_REC], al
        mov [ebx+PU_REC+30], al
        mov [ebx+PU_REC+50], al
        cmp ebx, 5
        jae .next
        mov [ebp+ebx-0x11], al
.next:  inc ebx
        cmp ebx, ecx
        jl .copy
.key:   xor ebx, ebx
.k:     mov al, [ebp+ebx-0x11]
        lea edx, [ebx+1]
        add al, dl
        mov [ebx+PU_REC+578], al
        inc ebx
        cmp ebx, 5
        jl .k
        jmp 0x45A7DC                    ; PUOKBtn.Enabled := True

;; at 45A772
; FileExists without FileAge's DOS date (bug 3): an existing file that is
; not a directory. eax = AnsiString -> al = Boolean.
        push ebx
        add esp, -0x140                 ; WIN32_FIND_DATAA
        mov ebx, eax
        push esp
        mov eax, ebx
        call LStrToPChar
        push eax
        call FindFirstFileA
        cmp eax, -1
        je .no
        push eax
        call FindClose
        test byte [esp], 0x10           ; FILE_ATTRIBUTE_DIRECTORY
        jne .no
        mov al, 1
        jmp .out
.no:    xor eax, eax
.out:   add esp, 0x140
        pop ebx
        ret

;; at 45A7A8
; TestBD: the length of the birthday text, at most 10 (bug 2).
        call LStrLen
        cmp eax, 10
        jle .r
        mov eax, 10
.r:     ret

;; at 45A7B8
; ResetPA: keep a PURSEA.DAT chosen with Open (bug 4).
        cmp byte [PA_FROM_OPEN], 0
        jne 0x459BB9                    ; skip "PApath := dir + *.GF + ..."
        push dword [0x45DBDC]           ; the replaced instruction
        jmp 0x459B7E

;; at 45A7D0
; OpenPABtnClick: PApath := the dialog's file name, and remember that.
        mov byte [PA_FROM_OPEN], 1
        jmp LStrLAsg

;; at 459B78
        jmp PA_PATH
        nop

;; at 459E02
        call PA_OPENED

;; at 459FE4
        call LEN_MAX10

;; at 459963
        call FILE_EXISTS                ; ResetPU: FileExists(PUpath)

;; at 459BBE
        call FILE_EXISTS                ; ResetPA: FileExists(PApath)

;; at 45A908
        call FILE_EXISTS                ; PUOKBtnClick: FileExists(bak)

;; at 45AAFC
        call FILE_EXISTS                ; PAOKBtnClick: FileExists(bak)
