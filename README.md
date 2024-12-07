# RapidRelinker
Built to relink arbitrary binary blobs in the simplest, stupidest way possible, because Ghidra doesn't support doing so. Tool was thrown together in a few days in anger, and as such, isn't really fit for use by anyone.

Usage:
`python3 relinker.py <file>`

Input files take the following general format:

```
;comments are pretty self-explanatory
BIT(2) ;bus address length, determines max address. not currently super important.
ORG(0000) ;hex address to assume blob starts at
DEF(Name,0122) ;hardcoded address
INCLUDE(file/name) ;includes are parsed in order on their own
SymbolName(00 01 02 03 OtherSymbolName,1 ff fe de ad be ef OtherSymbolName2,2)
;references will be built on the fly, params are as such:
;Name,Length/Byte
;Name: name to reference
;Length: length of address to reference. length 1 currently emits 6502-style relative jump
;Byte: selects specific byte of output, for split pointers and similar (optional, 0 is high byte)
OtherSymbolName(00 01 02 03 00 00 ff fe de ad be ef 00 00) ;the text "ignore-dupe" in a comment prevents warnings about duplicate data.
;duplicates are checked for with all references containing 00h to fill the required length.
;symbol data is emitted in the order it appears in the input file. sparse files unsupported.
```

The tool will output a `.LNK` file containing the linked data, and a `.DEF` containing final symbols, as `DEF()` statements.
