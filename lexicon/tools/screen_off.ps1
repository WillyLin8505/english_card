# Turn the screen off; everything keeps running. Mouse or key brings it back.
# Changes no power settings: the same "monitor off" message the display-off key sends.
param([switch]$Check)
Add-Type -Namespace W -Name M -MemberDefinition @'
[DllImport("user32.dll")] public static extern System.IntPtr SendMessage(System.IntPtr h, int m, System.IntPtr w, System.IntPtr l);
'@
if ($Check) { 'ok'; return }
Start-Sleep -Milliseconds 800   # let the click/keypress that started us finish, or it wakes the screen again
[W.M]::SendMessage([IntPtr]0xFFFF, 0x0112, [IntPtr]0xF170, [IntPtr]2) | Out-Null
