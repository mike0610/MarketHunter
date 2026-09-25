Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
pidfile = folder & "\agent.pid"
If Not fso.FileExists(pidfile) Then
  MsgBox "No agent.pid found. Agent may already be stopped."
  WScript.Quit
End If
Set file = fso.OpenTextFile(pidfile, 1)
pid = Trim(file.ReadAll())
file.Close
Set shell = CreateObject("WScript.Shell")
Set result = shell.Exec("powershell -NoProfile -Command ""$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" & pid & "'; if($p -and $p.CommandLine -like '*agent.py*' -and $p.CommandLine -like '*weex_spot_agent*'){Stop-Process -Id " & pid & " -Force; exit 0}else{exit 1}""")
Do While result.Status = 0
  WScript.Sleep 100
Loop
If result.ExitCode = 0 Then
  fso.DeleteFile pidfile, True
  MsgBox "Agent stopped."
Else
  MsgBox "Process not confirmed. Check agent.log; remove stale agent.pid only after verifying agent is stopped."
End If
