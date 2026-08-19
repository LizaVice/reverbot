Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
scriptDir = Fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run """" & scriptDir & "\supervisor.bat""", 0, False
