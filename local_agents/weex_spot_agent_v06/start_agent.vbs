Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = folder

pythonw = "C:\Users\user\AppData\Local\Programs\Python\Python314\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "Python не знайдено."
    WScript.Quit
End If

If fso.FileExists(folder & "\agent.pid") Then
    MsgBox "Агент уже запущений. Перевір agent.log."
    WScript.Quit
End If

shell.Run """" & pythonw & """ """ & folder & "\agent.py""", 0, False

MsgBox "WEEX Agent запущено! Перевір Telegram."