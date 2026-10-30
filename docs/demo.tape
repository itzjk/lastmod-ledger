Output docs/demo.gif
Set Shell "bash"
Set FontSize 15
Set Width 1320
Set Height 1260
Set Padding 18
Set TypingSpeed 25ms
Set Theme "Dracula"
Env PS1 "$ "
Hide
Type `export PATH="$PWD/.venv/bin:$PATH"; export PS1='$ '; clear`
Enter
Sleep 500ms
Show
Type "lastmod-ledger compare examples/before.json examples/after.json"
Enter
Sleep 7s
Hide
Type "clear"
Enter
Sleep 500ms
Show
Type "lastmod-ledger compare examples/before.json examples/coverage.json"
Enter
Sleep 8s
